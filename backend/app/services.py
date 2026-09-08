if t.owner_id != actor.id or t.status != 'REJECTED':
        raise DomainError('BAD_STATE', 'Only your own rejected task can be resumed')
    if active_count(db, actor.company_id, actor.id) >= MAX_ACTIVE:
        raise DomainError('CAPACITY', f'You already have {MAX_ACTIVE} active tasks')
    t.status = 'IN_PROGRESS'
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id, 'resumed rework', t.title,
        task_id=t.id, cycle=t.cycle)
    return t


# ── review decisions ────────────────────────────────────────────────────────


def approve_work(db: Session, actor: User, task_id: str) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Review decisions are management acts')
    t = get_task(db, actor.company_id, task_id)
    if t.status != 'SUBMITTED':
        raise DomainError('BAD_STATE', 'Only a submitted task can be approved')
    if t.owner_id == actor.id:
        raise DomainError('FORBIDDEN', 'Nobody reviews their own submission')
    owner = t.owner_id
    accepted_pct = 100 - t.verified
    remaining = max(0.0, t.reward - t.paid)
    now = now_ms()
    if remaining > 0:
        ledger(db, actor.company_id, owner, 'TASK_REWARD', remaining,
               f'Task reward — {t.title}', t)
        t.paid += remaining
    db.add(Contribution(company_id=actor.company_id, task_id=t.id, cycle=t.cycle,
                        employee_id=owner, reported_pct=t.reported,
                        accepted_pct=accepted_pct, payout=remaining,
                        decision='APPROVED', reason='Work approved', at=now))
    _close_pending_submission(db, t, 'APPROVED', actor.id, None)
    t.verified = 100
    t.status = 'APPROVED'
    t.updated_at = now
    t.instructions = None
    cyc = _current_cycle(db, t)
    cyc.closed_at = now
    cyc.outcome = 'APPROVED'
    cyc.paid = t.paid
    cyc.verified = 100
    act(db, actor.company_id, actor.id, 'approved work', t.title, task_id=t.id,
        econ=fmt_coins(remaining) if remaining > 0 else None, cycle=t.cycle)
    note(db, actor.company_id, owner, 'IMPORTANT', 'Economy',
         f'Approved — {t.title}. '
         f'{f"{fmt_coins(remaining)} credited to your wallet." if remaining > 0 else "Cycle already fully paid."}', t)
    return t


def reject_work(db: Session, actor: User, task_id: str, reason: str) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Review decisions are management acts')
    t = get_task(db, actor.company_id, task_id)
    if t.status != 'SUBMITTED':
        raise DomainError('BAD_STATE', 'Only a submitted task can be rejected')
    if t.owner_id == actor.id:
        raise DomainError('FORBIDDEN', 'Nobody reviews their own submission')
    _close_pending_submission(db, t, 'REJECTED', actor.id, reason)
    t.status = 'REJECTED'
    t.rejection_reason = reason
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id, 'rejected submission', t.title,
        task_id=t.id, reason=reason, cycle=t.cycle)
    note(db, actor.company_id, t.owner_id, 'ACTION_REQUIRED', 'Tasks',
         f'Rework required — {t.title}. Reason: {reason}', t)
    return t


def handoff(db: Session, actor: User, task_id: str, *, accepted_pct: float,
            reason: str, next_kind: str, next_id: Optional[str] = None,
            audience: Optional[str] = None, priority: Optional[str] = None,
            deadline=..., remaining_reward: Optional[float] = None,
            override_reason: Optional[str] = None,
            files: Sequence[StoredFile] = ()) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Review decisions are management acts')
    t = get_task(db, actor.company_id, task_id)
    if t.status not in ('IN_PROGRESS', 'SUBMITTED'):
        raise DomainError('BAD_STATE', 'Only work in progress or under review can be handed off')
    if t.owner_id == actor.id:
        raise DomainError('FORBIDDEN', 'Payout decisions need a second pair of eyes')
    cid = actor.company_id
    # N2.1-R2 canonical routing (mirrors the demo engine exactly): the audience
    # choice DEFINES eligibility; without an explicit audience the effective
    # audience follows the target (employee → EMPLOYEES, manager → MANAGEMENT),
    # for every authorized actor. The founder/admin never owns work; PRIVATE
    # work stays one-to-one.
    nu = get_user(db, cid, next_id) if next_kind == 'EMPLOYEE' and next_id else None
    if nu is not None and nu.role == 'ADMIN':
        raise DomainError('FORBIDDEN', 'The founder/admin never owns work')
    eff_audience = audience or (('EMPLOYEES' if nu.role == 'EMPLOYEE' else 'MANAGEMENT')
                                if nu is not None else t.audience)
    if eff_audience == 'PRIVATE' and next_kind != 'EMPLOYEE':
        raise DomainError('VALIDATION', 'Private work stays one-to-one — pick a person')
    if nu is not None and not role_fits(eff_audience, nu.role):
        raise DomainError('FORBIDDEN', 'The chosen person is not eligible for this audience')
    # remaining-reward suggestion + audited override, validated BEFORE mutation
    pct_probe = max(0, min(100 - t.verified, _round(accepted_pct)))
    probe = (min(partial_payout(t.reward, pct_probe), max(0.0, t.reward - t.paid))
             if pct_probe > 0 else 0.0)
    suggested_after = max(0.0, t.reward - t.paid - probe)
    overrides = (remaining_reward is not None
                 and _round(remaining_reward) != suggested_after)
    if overrides and not (override_reason and override_reason.strip()):
        raise DomainError('VALIDATION', 'Changing the remaining reward requires an audited reason')
    if remaining_reward is not None and remaining_reward < 0:
        raise DomainError('VALIDATION', 'Remaining reward cannot be negative')

    from_id = t.owner_id
    pct = pct_probe
    payout = min(partial_payout(t.reward, pct), max(0.0, t.reward - t.paid)) if pct > 0 else 0.0
    now = now_ms()
    if payout > 0:
        ledger(db, cid, from_id, 'TASK_PARTIAL_REWARD', payout,
               f'Partial reward ({pct}%) — {t.title}', t)
        t.paid += payout
    db.add(Contribution(company_id=cid, task_id=t.id, cycle=t.cycle,
                        employee_id=from_id, reported_pct=t.reported,
                        accepted_pct=pct, payout=payout,
                        decision='HANDOFF', reason=reason, at=now))
    t.verified = min(100, t.verified + pct)
    _close_pending_submission(db, t, 'HANDED_OFF', actor.id, reason)
    t.owner_id = None
    _reset_live_submission_slots(t, now)
    t.reported = 0
    t.updated_at = now
    t.instructions = reason
    t.audience = eff_audience
    if priority:
        t.priority = priority
    if deadline is not ...:
        t.deadline = _dl(deadline)
    if remaining_reward is not None:
        t.reward = t.paid + max(0, _round(remaining_reward))
    if files:
        _attach(db, cid, files, 'brief', t.id)
    change_note = ' · '.join(x for x in [
        reason,
        f'priority → {priority}' if priority else '',
        'deadline updated' if deadline is not ... else '',
        (f'remaining reward set to {_num(_round(remaining_reward))} Coins — {override_reason.strip()}'
         if overrides else ''),
        (f'{len(files)} file{"s" if len(files) != 1 else ""} added to the brief' if files else ''),
    ] if x)
    act(db, cid, actor.id, f'handed off ({pct}% accepted)', t.title, task_id=t.id,
        reason=change_note, econ=fmt_coins(payout) if payout > 0 else None, cycle=t.cycle)
    note(db, cid, from_id, 'IMPORTANT', 'Economy',
         f'Handoff on “{t.title}” — {pct}% accepted'
         f'{f", {fmt_coins(payout)} credited" if payout > 0 else ", no payout"}.', t)
    if next_kind == 'EMPLOYEE' and nu is not None:
        # audience already resolved above (explicit choice or target-derived)
        t.assign_mode = 'SPECIFIC_EMPLOYEE'
        t.assignee_id = nu.id
        t.status = 'OPEN'
        note(db, cid, nu.id, 'ACTION_REQUIRED', 'Assignments',
             f'Handoff assignment — {t.title} ({_num(t.verified)}% verified, '
             f'{_num(max(0.0, t.reward - t.paid))} Coins remaining) from {actor.name}. '
             f'Instructions: {reason} Accept or decline.', t)
    else:
        t.assign_mode = 'ALL_EMPLOYEES'
        t.assignee_id = None
        t.status = 'OPEN'
        if t.priority in ('URGENT', 'IMPORTANT'):
            for m in managers(db, cid):
                note(db, cid, m.id, 'IMPORTANT', 'Tasks',
                     f'Handoff returned “{t.title}” to the marketplace ({_num(t.verified)}% verified).', t)
    return t


# ── cycles: reopen / cancel / reactivate ────────────────────────────────────


def _new_cycle_reset(db: Session, actor: User, t: Task, *, description=None,
                     audience: Optional[str] = None, assignee_id: Optional[str] = None,
                     files: Sequence[StoredFile] = ()) -> tuple[list[str], Optional[Us