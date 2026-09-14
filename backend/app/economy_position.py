"""One signed ledger; spendable and debt are projections, never stored wallets."""
from sqlalchemy import func, select
from .models import LedgerTransaction


def position(net: float) -> dict:
    return {'netPosition': net, 'spendableBalance': max(0.0, net), 'coinDebt': max(0.0, -net)}


def net_position(db, company_id: str, user_id: str) -> float:
    return float(db.scalar(select(func.coalesce(func.sum(LedgerTransaction.amount), 0.0))
                           .where(LedgerTransaction.company_id == company_id,
                                  LedgerTransaction.user_id == user_id)))


def balance_of(db, company_id: str, user_id: str) -> float:
    return position(net_position(db, company_id, user_id))['spendableBalance']


def debt_of(db, company_id: str, user_id: str) -> float:
    return position(net_position(db, company_id, user_id))['coinDebt']
