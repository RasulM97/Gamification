"""Rewards-owned snapshots; no balance calculation or economic side effects."""
from sqlalchemy.orm import Session
from .canonical_events.contracts import EventInput, StoredEvent
from .internal_event_recorder import record_internal_event
from .models import Redemption, Reward, User


def record_redemption_created(db: Session, actor: User, reward: Reward,
                              redemption: Redemption) -> StoredEvent:
    return record_internal_event(db, actor.company_id, lambda: EventInput(
        type='reward.redemption.created', schema_version=1, source_kind='REWARDS',
        source_id=redemption.id, source_event_id=f'created:{redemption.id}',
        actor_id=actor.id, subject_id=redemption.user_id, occurred_at=redemption.at,
        correlation_id=redemption.id,
        payload=dict(redemptionId=redemption.id, rewardId=reward.id,
                     userId=redemption.user_id, cost=redemption.cost,
                     rewardEligibility=reward.eligibility, status=redemption.status)))


def record_redemption_fulfilled(db: Session, actor: User,
                                redemption: Redemption) -> StoredEvent:
    return record_internal_event(db, actor.company_id, lambda: EventInput(
        type='reward.redemption.fulfilled', schema_version=1, source_kind='REWARDS',
        source_id=redemption.id, source_event_id=f'fulfilled:{redemption.id}',
        actor_id=actor.id, subject_id=redemption.user_id, occurred_at=redemption.fulfilled_at,
        correlation_id=redemption.id,
        payload=dict(redemptionId=redemption.id, rewardId=redemption.reward_id,
                     redeemerId=redemption.user_id, fulfilledBy=redemption.fulfilled_by,
                     cost=redemption.cost, status=redemption.status)))
