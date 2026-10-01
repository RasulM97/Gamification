"""Seed E7/E8 schema-shaped provenance under its real deferred database guards.

Current ORM/service requires E11 schema. Historical migration tests deliberately
exercise older schemas, so reflect their columns instead of importing new ones.
"""
from decimal import Decimal
import sqlalchemy as sa
from app.models import LedgerTransaction, new_id, now_ms


def issue(db, actor, decision_id):
    row = db.execute(sa.text('''SELECT p.candidate_id,c.data,e.subject_id,e.type
        FROM policy_decisions p JOIN rule_candidates c ON c.id=p.candidate_id AND c.company_id=p.company_id
        JOIN canonical_events e ON e.id=c.canonical_event_id AND e.company_id=c.company_id
        WHERE p.id=:id AND p.company_id=:company AND p.effective_decision='ALLOW' '''),
        dict(id=decision_id,company=actor.company_id)).one()
    amount=Decimal(str(row.data['proposedReward']))
    identity, ledger_id = new_id('ee'), new_id('l')
    table=sa.Table('economic_effects',sa.MetaData(),autoload_with=db.connection())
    db.execute(table.insert().values(id=identity,company_id=actor.company_id,candidate_id=row.candidate_id,
        policy_decision_id=decision_id,approval_decision_id=None,effect_type='INCENTIVE_CREDIT',
        amount=amount,beneficiary_user_id=row.subject_id,status='ISSUED',ledger_transaction_id=ledger_id,created_at=now_ms()))
    db.add(LedgerTransaction(id=ledger_id,company_id=actor.company_id,user_id=row.subject_id,
        type='INCENTIVE_REWARD',amount=amount,ref='economic:'+row.candidate_id,
        params=dict(economicEffectId=identity,candidateId=row.candidate_id,sourceType=row.type)))
