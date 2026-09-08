er]]:
    """Shared reopen/reactivate reset: fresh cycle, zeroed economics, brief
    choice — plus NEW-cycle routing (M1-D D7). A new cycle is new work: the
    previous cycle's worker type must NOT restrict the new cycle's audience
    or assignee. The admin stays excluded as a worker (role_fits), PRIVATE
    stays one-to-one, and past cycles remain immutable."""
    now = now_ms()
    eff_audience = audience or t.audience
    if eff_audience == 'PRIVATE' and not assignee_id:
        raise DomainError('VALIDATION', 'A private cycle needs a specific assignee')
    nu: Optional[User] = None
    if assignee_id:
        nu = get_user(db, actor.company_id, assignee_id)
        if not role_fits(eff_audience, nu.role):
            raise DomainError('FORBIDDEN', 'The chosen person is not eligible for this audience')
    t.cycle += 1
    t.status = 'OPEN'
    t.owner_id = None
    t.audience = eff_audience
    t.assign_mode = 'SPECIFIC_EMPLOYEE' if nu is not None else 'ALL_EMPLOYEES'
    t.assignee_id = nu.id if nu is not None else None
    t.verified = 0
    t.reported = 0
    t.paid = 0
    _reset_live_submission_slots(t, now)
    t.instructions = None
    t.updated_at = now
    brief_changes: list[str] = []
    if description and description.strip() and description.strip() != t.description:
        t.description = description.strip()
        brief_changes.append('brief updated')
    if files:
        _attach(db, actor.company_id, files, 'brief', t.id)
        brief_changes.append(f'{len(files)} file{"s" if len(files) != 1 else ""} added to the brief')
    db.add(TaskCycle(company_id=actor.company_id, task_id=t.id, cycle=t.cycle,
                     opened_at=now))
    return brief_changes, nu


def reopen_task(db: Session, actor: User, task_id: str, *, description=None,
                audience: Optional[str] = None, assignee_id: Optional[str] = None,
                files: Sequence[StoredFile] = ()) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Reopening work is a management act')
    t = get_task(db, actor.company_id, task_id)
    if t.status != 'APPROVED':
        raise DomainError('BAD_STATE', 'Only an approved task can be reopened')
    brief_changes, nu = _new_cycle_reset(db, actor, t, description=description,
                                         audience=audience, assignee_id=assignee_id,
                                         files=files)
    parts = brief_changes + ([f'assigned to {nu.name}'] if nu is not None else [])
    act(db, actor.company_id, actor.id, 'reopened task (new cycle)', t.title,
        task_id=t.id, cycle=t.cycle,
        reason=' · '.join(parts) or 'previous brief reused')
    if nu is not None:
        note(db, actor.company_id, nu.id, 'ACTION_REQUIRED', 'Assignments',
             f'New assignment — {t.title} (worth {_num(t.reward)} Coins, cycle {t.cycle}). Accept or decline.', t)
    for m in managers(db, actor.company_id):
        if m.id != actor.id:
            note(db, actor.company_id, m.id, 'INFORMATIONAL', 'Tasks',
                 f'“{t.title}” reopened — cycle {t.cycle} started. Reward budget refreshed.', t)
    return t


def cancel_task(db: Session, actor: User, task_id: str, *, reason: str,
                accepted_pct: Optional[float] = None) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Cancelling work is a management act')
    t = get_task(db, actor.company_id, task_id)
    # N2.1-A1: canonical-ownership protection — creator or admin only. A
    # manager must NOT cancel an admin-created task as management owner.
    if actor.role != 'ADMIN' and t.created_by != actor.id:
        raise DomainError('FORBIDDEN', 'Only the task creator or an admin can cancel this task')
    if t.status in ('APPROVED', 'CANCELLED'):
        raise DomainError('BAD_STATE', 'Terminal tasks cannot be cancelled')
    if t.owner_id and t.owner_id == actor.id:
        raise DomainError('FORBIDDEN', 'Owners cannot cancel-decide their own payout')
    cid = actor.company_id
    pct = max(0, min(100 - t.verified, _round(accepted_pct or 0))) if t.owner_id else 0
    payout = min(partial_payout(t.reward, pct), max(0.0, t.reward - t.paid)) if pct > 0 else 0.0
    now = now_ms()
    if payout > 0:
        ledger(db, cid, t.owner_id, 'TASK_PARTIAL_REWARD', payout,
               f'Partial reward ({pct}%) — {t.title} (cancelled)', t)
        t.paid += payout
    if pct > 0:
        db.add(Contribution(company_id=cid, task_id=t.id, cycle=t.cycle,
                            employee_id=t.owner_id, reported_pct=t.reported,
                            accepted_pct=pct, payout=payout,
                            decision='CANCELLED', reason=reason, at=now))
        t.verified = min(100, t.verified + pct)
    _close_pending_submission(db, t, 'CANCELLED', actor.id, reason)
    t.status = 'CANCELLED'
    t.updated_at = now
    t.instructions = None
    cyc = _current_cycle(db, t)
    cyc.closed_at = now
    cyc.outcome = 'CANCELLED'
    cyc.paid = t.paid
    cyc.verified = t.verified
    act(db, cid, actor.id,
        f'cancelled task ({pct}% credited)' if pct > 0 else 'cancelled task',
        t.title, task_id=t.id, reason=reason,
        econ=fmt_coins(payout) if payout > 0 else None, cycle=t.cycle)
    if t.owner_id:
        note(db, cid, t.owner_id, 'IMPORTANT', 'Tasks',
             f'Cancelled — {t.title}. '
             f'{f"{fmt_coins(payout)} credited for work already done ({pct}% accepted). " if payout > 0 else ""}'
             f'{reason}', t)
    return t


def reactivate_task(db: Session, actor: User, task_id: str, *, reason: str,
                    description=None, audience: Optional[str] = None,
                    assignee_id: Optional[str] = None,
                    files: Sequence[StoredFile] = ()) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Reactivating work is a management act')
    t = get_task(db, actor.company_id, task_id)
    if t.status != 'CANCELLED':
        raise DomainError('BAD_STATE', 'Only a cancelled task can be reactivated')
    brief_changes, nu = _new_cycle_reset(db, actor, t, description=description,
                                         audience=audience, assignee_id=assignee_id,
                                         files=files)
    parts = [reason, *brief_changes] + ([f'assigned to {nu.name}'] if nu is not None else [])
    act(db, actor.company_id, actor.id, 'reactivated task (new cycle)', t.title,
        task_id=t.id, reason=' · '.join(parts), cycle=t.cycle)
    if nu is not None:
        note(db, actor.company_id, nu.id, 'ACTION_REQUIRED', 'Assignments',
             f'New assignment — {t.title} (worth {_num(t.reward)} Coins, cycle {t.cycle}). Accept or decline.', t)
    for m in managers(db, actor.company_id):
        if m.id != actor.id:
            note(db, actor.company_id, m.id, 'INFORMATIONAL', 'Tasks',
                 f'“{t.title}” reactivated — cycle {t.cycle} started. Reason: {reason}', t)
    return t


# ── economy: redemptions & adjustments ──────────────────────────────────────


# N2.2 §6/§7: fulfillment authority — admins fulfill by office; anyone else
# needs BOTH the REWARD_FULFILL capability AND an executor seat on that
# reward. Approval authority (can_decide below) never implies fulfillment.
def _executor_ids(db: Session, reward_id: str) -> list[str]:
    return [x for (x,) in db.query(RewardExecutor.user_id)
            .filter(RewardExecutor.reward_id == reward_id).all()]


def _can_fulfill(db: Session, actor: User, r: Reward) -> bool:
    if actor.role == 'ADMIN':
        return True
    return (actor.can_fulfill_rewards
            and actor.id in _executor_ids(db, r.id))


# N2.1-R2 canonical decision matrix (verbatim): the admin decides all; a
# manager decides EMPLOYEE redemptions only — never their own or another
# manager's.
def _can_decide(redeemer: User, decider: User) -> bool:
    return decider.role == 'ADMIN' or (decider.role == 'MANAGER' and redeemer.role == 'EMPLOYEE')


def redeem(db: Session, actor: User, reward_id: str) -> Redemption:
    cid = actor.company_id
    if actor.role == 'ADMIN':
        raise DomainError('FORBIDDEN', 'The founder/admin never redeems rewards')
    r = db.scalar(select(Reward).where(Reward.id == reward_id, Reward.company_id == cid)
                  .with_for_update())
    if r is None:
        raise DomainError('NOT_FOUND', 'Reward not found')
    # N2-A: eligibility is enforced by the backend, never only by the UI
    if r.eligibility == 'EMPLOYEES' and actor.role != 'EMPLOYEE':
        raise DomainError('FORBIDDEN', 'This reward is for employees only')
    if r.eligibility == 'MANAGERS' and actor.role != 'MANAGER':
        raise DomainError('FORBIDDEN', 'This reward is for managers only')
    now = now_ms()
    # N2.2 §3/§4: archived rewards are never redeemable; the availability
    # window is evaluated server-