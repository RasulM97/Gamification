"""Database reconciliation over the authoritative ledger and its E7 provenance."""
from decimal import Decimal
import sqlalchemy as sa
from app.db import engine, SessionLocal
from app.economy_position import net_position


def reconcile():
    checks = {
        'effects': 'SELECT count(*) FROM economic_effects',
        'credits': "SELECT count(*) FROM ledger WHERE type='INCENTIVE_REWARD'",
        'reversals': 'SELECT count(*) FROM economic_reversals',
        'debits': "SELECT count(*) FROM ledger WHERE type='INCENTIVE_REVERSAL'",
        'issued_amount': 'SELECT coalesce(sum(amount),0) FROM economic_effects',
        'reversed_amount': 'SELECT coalesce(sum(amount),0) FROM economic_reversals',
        'ledger_credit_amount': "SELECT coalesce(sum(amount),0) FROM ledger WHERE type='INCENTIVE_REWARD'",
        'ledger_debit_amount': "SELECT coalesce(sum(amount),0) FROM ledger WHERE type='INCENTIVE_REVERSAL'",
        'orphan_effects': 'SELECT count(*) FROM economic_effects e LEFT JOIN ledger l ON l.id=e.ledger_transaction_id WHERE l.id IS NULL',
        'orphan_credits': "SELECT count(*) FROM ledger l LEFT JOIN economic_effects e ON e.ledger_transaction_id=l.id WHERE l.type='INCENTIVE_REWARD' AND e.id IS NULL",
        'orphan_reversals': 'SELECT count(*) FROM economic_reversals r LEFT JOIN economic_effects e ON e.id=r.original_effect_id LEFT JOIN ledger l ON l.id=r.ledger_transaction_id WHERE e.id IS NULL OR l.id IS NULL',
        'orphan_debits': "SELECT count(*) FROM ledger l LEFT JOIN economic_reversals r ON r.ledger_transaction_id=l.id WHERE l.type='INCENTIVE_REVERSAL' AND r.id IS NULL",
        'cross_tenant': '''SELECT count(*) FROM economic_effects e JOIN ledger l ON l.id=e.ledger_transaction_id
            JOIN rule_candidates c ON c.id=e.candidate_id JOIN policy_decisions p ON p.id=e.policy_decision_id
            WHERE e.company_id<>l.company_id OR e.company_id<>c.company_id OR e.company_id<>p.company_id
            OR e.beneficiary_user_id<>l.user_id OR e.candidate_id<>p.candidate_id OR e.amount<>l.amount''',
        'reversal_mismatch': '''SELECT count(*) FROM economic_reversals r JOIN economic_effects e ON e.id=r.original_effect_id
            JOIN ledger l ON l.id=r.ledger_transaction_id WHERE r.company_id<>e.company_id OR r.company_id<>l.company_id
            OR l.user_id<>e.beneficiary_user_id OR r.amount<>-e.amount OR r.amount<>l.amount''',
        'duplicate_candidates': 'SELECT count(*) FROM (SELECT candidate_id FROM economic_effects GROUP BY company_id,candidate_id HAVING count(*)>1) t',
        'duplicate_reversals': 'SELECT count(*) FROM (SELECT original_effect_id FROM economic_reversals GROUP BY original_effect_id HAVING count(*)>1) t',
        'activity_rows': 'SELECT count(*) FROM activity',
        'notification_rows': 'SELECT count(*) FROM notifications',
        'task_rows': 'SELECT count(*) FROM tasks',
        'redemption_rows': 'SELECT count(*) FROM redemptions',
    }
    with engine.connect() as conn:
        result = {key: conn.scalar(sa.text(sql)) for key,sql in checks.items()}
        users = list(conn.execute(sa.text('SELECT DISTINCT company_id,beneficiary_user_id FROM economic_effects ORDER BY 1,2')))
    assert result['effects']==result['credits'] and result['reversals']==result['debits']
    assert result['issued_amount']==result['ledger_credit_amount'] and result['reversed_amount']==result['ledger_debit_amount']
    assert all(result[key]==0 for key in checks if key.startswith(('orphan','cross','duplicate')) or key=='reversal_mismatch')
    assert all(result[key]==0 for key in ('activity_rows','notification_rows','task_rows','redemption_rows'))
    mismatches=0
    with SessionLocal() as db:
        for company,user in users:
            amount=db.scalar(sa.text('SELECT sum(amount) FROM ledger WHERE company_id=:company AND user_id=:user'),{'company':company,'user':user})
            mismatches += Decimal(str(net_position(db,company,user))) != amount
    assert len(users)>=100 and mismatches==0
    result.update(amount_variance=Decimal(0),net_e7_amount=result['issued_amount']+result['reversed_amount'],
                  balance_users=len(users),balance_mismatches=mismatches)
    return result
