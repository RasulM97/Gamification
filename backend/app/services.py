t_task(db, actor.company_id, task_id)
    if t.status != 'OPEN':
        raise DomainError('BAD_STATE', 'This task is not open for claims')
    if not role_fits(t.audience, actor.role):
        raise DomainError('FORBIDDEN', 'You are not eligible for this task')
    specific = t.assign_mode == 'SPECIFIC_EMPLOYEE' and t.assignee_id == actor.id
    open_ = t.assign_mode == 'ALL_EMPLOYEES'
    if not specific and not open_:
        raise DomainError('FORBIDDEN', 'This task is assigned to someone else')
    if active_count(db, actor.company_id, actor.id) >= MAX_ACTIVE:
        raise DomainError('CAPACITY', f'You already have {MAX_ACTIVE} active tasks')
    t.owner_id = actor.id
    t.status = 'IN_PROGRESS'
    t.assignee_id = None
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id,
        'accepted assignment' if specific else 'claimed task', t.title,
        task_id=t.id, cycle=t.cycle)
    return t


def decline_assignment(db: Session, actor: User, task_id: str, reason: str) -> Task:
    t = get_task(db, actor.company_id, task_id)
    pending = t.status == 'OPEN' and t.assignee_id == actor.id
    owned = (t.owner_id == actor.id and t.status in ('IN_PROGRESS', 'REJECTED')
             and t.assign_mode == 'SPECIFIC_EMPLOYEE')
    if not pending and not owned:
        raise DomainError('BAD_STATE', 'Nothing to decline on this task')
    if owned:
        t.owner_id = None
        t.status = 'OPEN'
        t.reported = 0
        _reset_live_submission_slots(t, now_ms())
    t.assignee_id = None
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id,
        'handed back assignment' if owned else 'declined assignment', t.title,
        task_id=t.id, reason=reason, cycle=t.cycle)
    lvl = 'ACTION_REQUIRED' if t.priority in ('URGENT', 'IMPORTANT') else 'IMPORTANT'
    for m in managers(db, actor.company_id):
        if m.id != actor.id:
            note(db, actor.company_id, m.id, lvl, 'Assignments',
                 f'{actor.name} {"handed back" if owned else "declined"} “{t.title}” — {reason}. Reassignment needed.', t)
    return t


def return_claim(db: Session, actor: User, task_id: str, reason: str) -> Task:
    t = get_task(db, actor.company_id, task_id)
    if (t.owner_id != actor.id or t.status not in ('IN_PROGRESS', 'REJECTED')
            or t.assign_mode != 'ALL_EMPLOYEES'):
        raise DomainError('BAD_STATE', 'Only a self-claimed task in progress (or rework) can be returned')
    pen = min(claim_penalty(t.priority), max(0.0, balance_of(db, actor.company_id, actor.id)))
    if pen > 0:
        ledger(db, actor.company_id, actor.id, 'TASK_CLAIM_PENALTY', -pen,
               f'Claim return penalty — {t.title}', t)
    t.owner_id = None
    t.status = 'OPEN'
    t.reported = 0
    _reset_live_submission_slots(t, now_ms())
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id, 'returned claimed task', t.title,
        task_id=t.id, reason=reason,
        econ=f'-{_num(pen)} Coins' if pen > 0 else 'no penalty (empty wallet)',
        cycle=t.cycle)
    if t.priority in ('URGENT', 'IMPORTANT'):
        for m in managers(db, actor.company_id):
            note(db, actor.company_id, m.id, 'IMPORTANT', 'Tasks',
                 f'{actor.name} returned “{t.title}” to the marketplace'
                 f'{f" (−{_num(pen)} Coins penalty)" if pen > 0 else ""} — {reason}', t)
    if pen > 0:
        note(db, actor.company_id, actor.id, 'INFORMATIONAL', 'Economy',
             f'Claim return penalty applied: −{_num(pen)} Coins for “{t.title}”.', t)
    return t


def edit_task(db: Session, actor: User, task_id: str, *, title=None, description=None,
              priority=None, deadline=..., reward=None) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Editing work is a management act')
    t = get_task(db, actor.company_id, task_id)
    # N2.1-A1: canonical-ownership protection — the task's creator and any
    # admin may edit the canonical definition. A manager must NOT edit an
    # admin-created task (mirrors the demo reducer's frozen rule).
    if actor.role != 'ADMIN' and t.created_by != actor.id:
        raise DomainError('FORBIDDEN', 'Only the task creator or an admin can edit this task')
    if t.status in ('APPROVED', 'CANCELLED'):
        raise DomainError('BAD_STATE', 'Terminal tasks are immutable history')
    if reward is not None and reward < t.paid:
        raise DomainError('VALIDATION', 'Reward cannot drop below what is already paid')
    changed: list[str] = []
    if title is not None and title.strip() and title != t.title:
        changed.append('title')
        t.title = title.strip()
    if description is not None and description.strip() and description != t.description:
        changed.append('description')
        t.description = description.strip()
    if priority is not None and priority != t.priority:
        changed.append(f'priority → {priority}')
        t.priority = priority
    if deadline is not ...:
        nd = _dl(deadline)
        if nd != t.deadline:
            changed.append('deadline')
            t.deadline = nd
    if reward is not None and reward != t.reward:
        changed.append(f'reward → {_num(reward)} Coins')
        t.reward = reward
    if not changed:
        raise DomainError('NO_CHANGE', 'Nothing changed')
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id, 'edited task', t.title,
        task_id=t.id, reason=', '.join(changed), cycle=t.cycle)
    msg = f'“{t.title}” was updated by management ({", ".join(changed)}).'
    if t.owner_id and t.owner_id != actor.id:
        note(db, actor.company_id, t.owner_id, 'IMPORTANT', 'Tasks', msg, t)
    elif t.assignee_id and t.assignee_id != actor.id:
        note(db, actor.company_id, t.assignee_id, 'IMPORTANT', 'Tasks', msg, t)
    return t


def reassign(db: Session, actor: User, task_id: str, assignee_id: Optional[str]) -> Task:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Reassigning work is a management act')
    t = get_task(db, actor.company_id, task_id)
    if t.status != 'OPEN':
        raise DomainError('BAD_STATE', 'Only open tasks can be reassigned')
    target = None
    if assignee_id:
        target = get_user(db, actor.company_id, assignee_id)
        if not role_fits(t.audience, target.role):
            raise DomainError('FORBIDDEN', 'The chosen person is not eligible for this audience')
    t.assign_mode = 'SPECIFIC_EMPLOYEE' if assignee_id else 'ALL_EMPLOYEES'
    t.assignee_id = assignee_id
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id,
        f'reassigned to {target.name}' if target else 'made available to all employees',
        t.title, task_id=t.id, cycle=t.cycle)
    if assignee_id:
        note(db, actor.company_id, assignee_id, 'ACTION_REQUIRED', 'Assignments',
             f'New assignment — {t.title} (worth {_num(t.reward)} Coins). Accept or decline.', t)
    return t


def report_progress(db: Session, actor: User, task_id: str, pct: float) -> Task:
    t = get_task(db, actor.company_id, task_id)
    if t.owner_id != actor.id:
        raise DomainError('FORBIDDEN', 'Only the current owner reports progress')
    if t.status not in ('IN_PROGRESS', 'REJECTED'):
        raise DomainError('BAD_STATE', 'Progress can only be reported on active work')
    t.reported = _clamp_pct(pct)
    t.updated_at = now_ms()
    act(db, actor.company_id, actor.id, 'reported progress',
        f'{t.title} — {_num(t.reported)}% (self-reported)', task_id=t.id, cycle=t.cycle)
    return t


def submit_work(db: Session, actor: User, task_id: str, *, note_text: str,
                files: Sequence[StoredFile] = (), pct: Optional[float] = None) -> Task:
    t = get_task(db, actor.company_id, task_id)
    if t.owner_id != actor.id or t.status != 'IN_PROGRESS':
        raise DomainError('BAD_STATE', 'Only the owner of an in-progress task can submit')
    now = now_ms()
    t.status = 'SUBMITTED'
    t.submission_note = note_text
    if pct is not None:
        t.reported = _clamp_pct(pct)
    t.submitted_at = now
    t.updated_at = now
    sub = Submission(company_id=actor.company_id, task_id=t.id, cycle=t.cycle,
                     user_id=actor.id, note=note_text, reported_pct=t.reported,
                     at=now, outcome='PENDING')
    db.add(sub)
    db.flush()
    _attach(db, actor.company_id, files, 'submission', t.id, submission_id=sub.id)
    act(db, actor.company_id, actor.id, 'submitted work for review', t.title,
        task_id=t.id, cycle=t.cycle)
    for m in managers(db, actor.company_id):
        if m.id != actor.id:
            note(db, actor.company_id, m.id, 'ACTION_REQUIRED', 'Reviews',
                 f'Submission ready for review — {t.title} by {actor.name}.', t)
    return t


def resume_work(db: Session, actor: User, task_id: str) -> Task:
    t = get_task(db, actor.company_id, task_id)