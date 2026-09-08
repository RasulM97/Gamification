side (UTC ms) — upcoming and expired rewards
    # stay visible to management but cannot be redeemed.
    if r.archived or not r.active or (r.stock is not None and r.stock <= 0):
        raise DomainError('OUT_OF_STOCK', 'This reward is not available')
    if r.available_from is not None and now < r.available_from:
        raise DomainError('BAD_STATE', 'This reward is not available yet')
    if r.available_until is not None and now > r.available_until:
        raise DomainError('BAD_STATE', 'This reward has expired')
    # N2.2 §2: the per-user limit is enforced server-side under the reward
    # row lock — a disabled button is never the only guard. Only
    # non-CANCELLED redemptions count: cancellation restores the quota, a
    # FULFILLED redemption keeps it consumed.
    if r.per_user_limit is not None:
        used = db.query(func.count(Redemption.id)).filter(
            Redemption.company_id == cid, Redemption.user_id == actor.id,
            Redemption.reward_id == r.id, Redemption.status != 'CANCELLED').scalar() or 0
        if used >= r.per_user_limit:
            raise DomainError('LIMIT_REACHED', 'You have reached the personal limit for this reward')
    if balance_of(db, cid, actor.id) < r.cost:
        raise DomainError('INSUFFICIENT_FUNDS', 'Not enough Coins for this reward')
    # Economy timing (N2.2 §9, documented): Coins are debited and stock is
    # decremented at REQUEST time; both are refunded/restored exactly once if
    # the redemption is cancelled from PENDING or APPROVED; a FULFILLED
    # redemption keeps them consumed. No double-debit, no double-restore.
    if r.stock is not None:
        r.stock -= 1
    ledger(db, cid, actor.id, 'REDEMPTION', -r.cost, f'Reward redemption — {r.name}')
    rd = Redemption(company_id=cid, user_id=actor.id, reward_id=r.id, cost=r.cost,
                    status='PENDING', at=now)
    db.add(rd)
    db.flush()
    act(db, cid, actor.id, 'redeemed reward', r.name, econ=f'-{_num(r.cost)} Coins')
    # N2.1-R2 + N2.2 §12: the approval request goes only to users who hold
    # decision authority over THIS redemption — an employee's redemption asks
    # all management; a manager's redemption asks admins only.
    for m in managers(db, cid):
        if not _can_decide(actor, m):
            continue
        note(db, cid, m.id, 'ACTION_REQUIRED', 'Rewards',
             f'Reward approval needed — {r.name} for {actor.name} ({_num(r.cost)} Coins).',
             redemption_id=rd.id)
    return rd


def approve_redemption(db: Session, actor: User, redemption_id: str) -> Redemption:
    """N2.2 §5: approval is the management decision step. It moves a PENDING
    redemption to APPROVED (ready for fulfillment) and notifies the reward's
    executors. Approval never delivers anything by itself."""
    rd = db.scalar(select(Redemption).where(Redemption.id == redemption_id,
                                            Redemption.company_id == actor.company_id)
                   .with_for_update())
    if rd is None:
        raise DomainError('NOT_FOUND', 'Redemption not found')
    # the PENDING gate (under row lock) makes double approvals single-outcome
    if rd.status != 'PENDING':
        raise DomainError('BAD_STATE', 'Only a pending redemption can be approved')
    redeemer = get_user(db, actor.company_id, rd.user_id)
    if not _can_decide(redeemer, actor):
        raise DomainError('FORBIDDEN', "Only an admin can decide a manager's redemption"
                          if actor.role == 'MANAGER' else 'Approval is a management act')
    now = now_ms()
    rd.status = 'APPROVED'
    rd.approved_by = actor.id
    rd.approved_at = now
    r = db.get(Reward, rd.reward_id)
    act(db, actor.company_id, actor.id, 'approved redemption', f'{r.name} — {redeemer.name}')
    note(db, actor.company_id, rd.user_id, 'INFORMATIONAL', 'Rewards',
         f'Approved — {r.name}. It now waits for fulfillment.', redemption_id=rd.id)
    # N2.2 §12: executors (and admins, who fulfill by office) are told the
    # item is ready. Non-assigned users are not notified.
    for u in db.query(User).filter(User.company_id == actor.company_id).all():
        if _can_fulfill(db, u, r):
            note(db, actor.company_id, u.id, 'ACTION_REQUIRED', 'Rewards',
                 f'Ready for fulfillment — {r.name} for {redeemer.name} ({_num(rd.cost)} Coins).',
                 redemption_id=rd.id)
    return rd


def fulfill_redemption(db: Session, actor: User, redemption_id: str, *,
                       reference: Optional[str] = None,
                       note_text: Optional[str] = None) -> Redemption:
    """N2.2 §5/§10: fulfillment executes on APPROVED redemptions only, by an
    executor of that reward (or an admin). Records who/when plus an optional
    tracking reference and internal note. Decision authority alone does NOT
    fulfill — the two powers stay technically separate."""
    rd = db.scalar(select(Redemption).where(Redemption.id == redemption_id,
                                            Redemption.company_id == actor.company_id)
                   .with_for_update())
    if rd is None:
        raise DomainError('NOT_FOUND', 'Redemption not found')
    r = db.get(Reward, rd.reward_id)
    # authority before state: an actor without fulfillment rights gets
    # FORBIDDEN regardless of the redemption's status
    if not _can_fulfill(db, actor, r):
        raise DomainError('FORBIDDEN', 'You are not an executor for this reward')
    # the APPROVED gate (under row lock) makes double fulfills and
    # fulfill-vs-cancel races single-outcome
    if rd.status != 'APPROVED':
        raise DomainError('BAD_STATE', 'Only an approved redemption can be fulfilled')
    now = now_ms()
    rd.status = 'FULFILLED'
    rd.fulfilled_by = actor.id
    rd.fulfilled_at = now
    rd.fulfillment_reference = (reference or '').strip() or None
    rd.fulfillment_note = (note_text or '').strip() or None
    user = get_user(db, actor.company_id, rd.user_id)
    act(db, actor.company_id, actor.id, 'fulfilled redemption', f'{r.name} — {user.name}')
    note(db, actor.company_id, rd.user_id, 'INFORMATIONAL', 'Rewards',
         f'Fulfilled — {r.name}. Enjoy!', redemption_id=rd.id)
    return rd


def cancel_redemption(db: Session, actor: User, redemption_id: str, reason: str) -> Redemption:
    rd = db.scalar(select(Redemption).where(Redemption.id == redemption_id,
                                            Redemption.company_id == actor.company_id)
                   .with_for_update())
    if rd is None:
        raise DomainError('NOT_FOUND', 'Redemption not found')
    # N2.2 §9: cancellation is allowed from PENDING or APPROVED (never
    # FULFILLED). The status gate (under row lock) makes refund + stock
    # restore exactly-once, even against a concurrent fulfill.
    if rd.status not in ('PENDING', 'APPROVED'):
        raise DomainError('BAD_STATE', 'Only a pending or approved redemption can be cancelled')
    if actor.role == 'EMPLOYEE' and rd.user_id != actor.id:
        raise DomainError('FORBIDDEN', 'You can only cancel your own redemption')
    # N2.1-R2: a manager cancels EMPLOYEE redemptions only — never their own
    # or another manager's; the admin decides all.
    if actor.role != 'EMPLOYEE' and not _can_decide(get_user(db, actor.company_id, rd.user_id), actor):
        raise DomainError('FORBIDDEN', "Only an admin can decide a manager's redemption"
                          if actor.role == 'MANAGER' else 'Cancellation is a management act')
    rd.status = 'CANCELLED'
    rd.reason = reason
    r = db.scalar(select(Reward).where(Reward.id == rd.reward_id).with_for_update())
    if r.stock is not None:
        r.stock += 1
    ledger(db, actor.company_id, rd.user_id, 'REFUND', rd.cost, f'Refund — {r.name}')
    user = get_user(db, actor.company_id, rd.user_id)
    act(db, actor.company_id, actor.id, 'cancelled redemption', f'{r.name} — {user.name}',
        reason=reason, econ=fmt_coins(rd.cost))
    note(db, actor.company_id, rd.user_id, 'IMPORTANT', 'Rewards',
         f'Redemption cancelled — {r.name}. {fmt_coins(rd.cost)} refunded. Reason: {reason}',
         redemption_id=rd.id)
    # N2-D: manager's redemption cancelled by management — the other
    # managers/admins see the decision and the refund.
    if user.role == 'MANAGER' and actor.role != 'EMPLOYEE':
        for m in managers(db, actor.company_id):
            if m.id == actor.id:
                continue
            note(db, actor.company_id, m.id, 'INFORMATIONAL', 'Rewards',
                 f'Redemption cancelled — {r.name} for {user.name}, refunded {fmt_coins(rd.cost)}, by {actor.name}.',
                 redemption_id=rd.id)
    return rd


def admin_adjust(db: Session, actor: User, *, user_id: str, amount: float,
                 reason: str) -> None:
    if actor.role != 'ADMIN':
        raise DomainError('FORBIDDEN', 'Adjustmen