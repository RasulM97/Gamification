"""Explicit issuance. Caller owns commit; a failed command rolls back its writes."""
from sqlalchemy import select, text
from ..domain import DomainError
from ..ledger import append_exact
from ..models import new_id
from .contracts import CREDIT_TYPE, EFFECT_TYPE
from .eligibility import economic_admin, is_candidate_economically_processable, lock_authority_wallet
from .model import EconomicEffect, EconomicReversal


def lock_identity(db, company_id, candidate_id):
    # Serializes issuer/reverser/retries across *all* policy histories. The
    # UNIQUE constraint is the final invariant, not this coordination lock.
    db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),
               {'key': 'cve-economic:'+company_id+':'+candidate_id})


def reversal_view(row):
    return dict(id=row.id, companyId=row.company_id, originalEconomicEffectId=row.original_effect_id,
                amount=str(row.amount), reasonCode=row.reason_code, initiatedBy=row.initiated_by,
                ledgerTransactionId=row.ledger_transaction_id, createdAt=row.created_at)


def effect_view(db, row):
    reversal = db.scalar(select(EconomicReversal).where(
        EconomicReversal.company_id == row.company_id, EconomicReversal.original_effect_id == row.id))
    return dict(id=row.id, companyId=row.company_id, candidateId=row.candidate_id,
        policyDecisionId=row.policy_decision_id, approvalDecisionId=row.approval_decision_id,
        effectType=row.effect_type, amount=str(row.amount), beneficiaryUserId=row.beneficiary_user_id,
        status='REVERSED' if reversal else 'ISSUED', ledgerTransactionId=row.ledger_transaction_id,
        createdAt=row.created_at, reversal=reversal_view(reversal) if reversal else None)


def issue(db, actor, policy_decision_id):
    actor = economic_admin(db, actor, lock=False)
    value = is_candidate_economically_processable(db, actor.company_id, policy_decision_id)
    lock_identity(db, value.company_id, value.candidate_id)
    lock_authority_wallet(db, actor, value.beneficiary_user_id)
    prior = db.scalar(select(EconomicEffect).where(EconomicEffect.company_id == value.company_id,
        EconomicEffect.candidate_id == value.candidate_id, EconomicEffect.effect_type == EFFECT_TYPE))
    if prior:
        result = effect_view(db, prior)
        if result['status'] == 'REVERSED':
            raise DomainError('ECONOMIC_EFFECT_ALREADY_REVERSED', 'Candidate economic identity is permanently consumed')
        return result
    # Savepoint also protects internal callers that catch a persistence failure
    # and subsequently commit unrelated work in their outer transaction.
    with db.begin_nested():
        row = EconomicEffect(id=new_id('ee'), company_id=value.company_id,
            candidate_id=value.candidate_id, policy_decision_id=value.policy_decision_id,
            approval_decision_id=value.approval_decision_id, amount=value.amount,
            safety_evaluation_id=value.safety_evaluation_id,
            beneficiary_user_id=value.beneficiary_user_id, ledger_transaction_id=new_id('l'))
        db.add(row)
        db.flush()
        append_exact(db, transaction_id=row.ledger_transaction_id, company_id=row.company_id,
            user_id=row.beneficiary_user_id, type_=CREDIT_TYPE, amount=row.amount,
            ref='economic:'+row.candidate_id, params=dict(economicEffectId=row.id,
                candidateId=row.candidate_id, sourceType=value.source_type))
    return effect_view(db, row)


def economic_detail(db, actor, effect_id):
    actor = economic_admin(db, actor)
    row = db.scalar(select(EconomicEffect).where(EconomicEffect.company_id == actor.company_id,
                                                 EconomicEffect.id == effect_id))
    if row is None:
        raise DomainError('ECONOMIC_EFFECT_NOT_FOUND', 'Economic effect not found')
    return effect_view(db, row)
