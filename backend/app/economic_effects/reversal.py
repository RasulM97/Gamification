"""Full append-only reversal, including into debt; no reissue of consumed candidates."""
from sqlalchemy import select
from ..domain import DomainError
from ..ledger import append_exact
from ..models import new_id
from .contracts import REVERSAL_TYPE, reversal_command
from .eligibility import economic_admin, lock_authority_wallet
from .model import EconomicEffect, EconomicReversal
from .service import lock_identity, reversal_view


def reverse(db, actor, effect_id, body):
    reason = reversal_command(body)
    actor = economic_admin(db, actor, lock=False)
    original = db.scalar(select(EconomicEffect).where(EconomicEffect.company_id == actor.company_id,
                                                      EconomicEffect.id == effect_id))
    if original is None:
        raise DomainError('ECONOMIC_EFFECT_NOT_FOUND', 'Economic effect not found')
    lock_identity(db, original.company_id, original.candidate_id)
    lock_authority_wallet(db, actor, original.beneficiary_user_id)
    prior = db.scalar(select(EconomicReversal).where(EconomicReversal.company_id == actor.company_id,
        EconomicReversal.original_effect_id == original.id))
    if prior:
        if (prior.reason_code, prior.initiated_by) != (reason, actor.id):
            raise DomainError('ECONOMIC_EFFECT_ALREADY_REVERSED', 'Effect already reversed by another command')
        return reversal_view(prior)
    with db.begin_nested():
        row = EconomicReversal(id=new_id('er'), company_id=actor.company_id, original_effect_id=original.id,
            reason_code=reason, amount=-original.amount, initiated_by=actor.id, ledger_transaction_id=new_id('l'))
        db.add(row)
        db.flush()
        append_exact(db, transaction_id=row.ledger_transaction_id, company_id=row.company_id,
            user_id=original.beneficiary_user_id, type_=REVERSAL_TYPE, amount=row.amount,
            participant_only=False,
            ref='economic-reversal:'+original.id, params=dict(economicEffectId=original.id,
                economicReversalId=row.id, candidateId=original.candidate_id))
    return reversal_view(row)
