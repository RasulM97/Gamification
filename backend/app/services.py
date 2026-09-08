ts are an admin-only act')
    if amount == 0:
        raise DomainError('VALIDATION', 'Adjustment amount cannot be zero')
    target = get_user(db, actor.company_id, user_id)
    # never-negative invariant for EVERY entry type: negative adjustments clamp
    # to the current balance; if nothing can be deducted, no entry is written.
    eff = (-min(-amount, max(0.0, balance_of(db, actor.company_id, user_id)))
           if amount < 0 else amount)
    if eff == 0:
        raise DomainError('VALIDATION', 'Nothing to deduct — balance is already zero')
    ledger(db, actor.company_id, user_id, 'ADMIN_ADJUSTMENT', eff,
           f'Admin adjustment — {reason}')
    act(db, actor.company_id, actor.id, 'admin adjustment',
        f'{target.name} — {reason}', econ=fmt_coins(eff))
    note(db, actor.company_id, user_id, 'IMPORTANT', 'Economy',
         f'Admin adjustment: {fmt_coins(eff)} — {reason}')


# ── reward catalog ──────────────────────────────────────────────────────────


def save_reward(db: Session, actor: User, *, reward_id: Optional[str], name: str,
                description: str, cost: float, stock: Optional[int],
                active: bool, category: str, eligibility: str,
                per_user_limit: Optional[int] = None,
                available_from: Optional[float] = None,
                available_until: Optional[float] = None,
                archived: bool = False,
                executor_ids: Optional[list[str]] = None) -> Reward:
    if not _is_mgmt(actor):
        raise DomainError('FORBIDDEN', 'Managing the catalog is a management act')
    # N2-A: canonical eligibility values only — never ADMIN.
    if eligibility not in ('EMPLOYEES', 'MANAGERS', 'BOTH'):
        raise DomainError('BAD_REQUEST', 'Eligibility must be EMPLOYEES, MANAGERS or BOTH')
    # N2.2 §1: the category must come from the canonical flat list (an
    # archived category remains valid for rewards that already carry it, but
    # cannot be newly selected).
    cat = db.scalar(select(RewardCategory).where(
        RewardCategory.company_id == actor.company_id,
        RewardCategory.name == category))
    if cat is None or not cat.active:
        existing = db.scalar(select(Reward).where(
            Reward.id == reward_id, Reward.company_id == actor.company_id)) if reward_id else None
        if cat is None or existing is None or existing.category != category:
            raise DomainError('BAD_REQUEST', 'Unknown reward category')
    if per_user_limit is not None and per_user_limit <= 0:
        raise DomainError('BAD_REQUEST', 'Per-user limit must be a positive integer')
    if available_from is not None and available_until is not None and available_from > available_until:
        raise DomainError('BAD_REQUEST', 'Availability window is inverted')

    # N2.2 §7: executor seats are admin-only and must reference users who
    # actually hold the REWARD_FULFILL capability. A manager's edit leaves
    # existing assignments untouched.
    def apply_executors(r: Reward) -> None:
        if actor.role != 'ADMIN' or executor_ids is None:
            return
        holders = {u.id for u in db.query(User).filter(
            User.company_id == actor.company_id, User.role != 'ADMIN',
            User.can_fulfill_rewards.is_(True)).all()}
        db.query(RewardExecutor).filter(RewardExecutor.reward_id == r.id).delete()
        for uid in dict.fromkeys(executor_ids):
            if uid in holders:
                db.add(RewardExecutor(reward_id=r.id, user_id=uid, company_id=actor.company_id))
        db.flush()

    if reward_id:
        r = db.scalar(select(Reward).where(Reward.id == reward_id,
                                           Reward.company_id == actor.company_id))
        if r is None:
            raise DomainError('NOT_FOUND', 'Reward not found')
        # N2.1-R2 canonical governance matrix (replaces the creator-ownership
        # rule): a manager manages only EMPLOYEES-targeted rewards — even ones
        # they created — and can never steer a reward to a MANAGERS audience.
        # created_by is audit/history only and is never changed by an edit.
        if actor.role == 'MANAGER' and (r.eligibility != 'EMPLOYEES' or eligibility == 'MANAGERS'):
            raise DomainError('FORBIDDEN', 'Managers manage employee-targeted rewards only')
        prev_category, prev_active, prev_archived = r.category, r.active, r.archived
        r.name, r.description, r.cost = name, description, cost
        r.stock, r.active, r.category = stock, active, category
        r.eligibility = eligibility
        r.per_user_limit = per_user_limit
        r.available_from, r.available_until = available_from, available_until
        r.archived = archived
        apply_executors(r)
        # N2.2 §13: human-readable audit detail for governance-relevant
        # changes (category / availability / lifecycle), no raw enums.
        changes = []
        if prev_category != category:
            changes.append(f'category changed to {category}')
        if prev_active != active:
            changes.append('activated' if active else 'deactivated')
        if prev_archived != archived:
            changes.append('archived' if archived else 'unarchived')
        act(db, actor.company_id, actor.id, 'updated reward', name,
            reason=' · '.join(changes) or None)
        return r
    # Create follows the matrix: a manager may create EMPLOYEES or BOTH
    # rewards (a BOTH reward is company-wide → admin-managed from birth),
    # never a MANAGERS-targeted one.
    if actor.role == 'MANAGER' and eligibility == 'MANAGERS':
        raise DomainError('FORBIDDEN', 'Managers cannot create manager-targeted rewards')
    r = Reward(company_id=actor.company_id, name=name, description=description,
               cost=cost, stock=stock, active=active, category=category,
               eligibility=eligibility, created_by=actor.id,
               per_user_limit=per_user_limit, available_from=available_from,
               available_until=available_until, archived=archived)
    db.add(r)
    db.flush()
    apply_executors(r)
    act(db, actor.company_id, actor.id, 'created reward', name)
    return r


def save_reward_category(db: Session, actor: User, *, category_id: Optional[str],
                         name: str, active: bool) -> RewardCategory:
    """N2.2 §1: one flat category level, admin-managed. Archiving never
    invalidates historical rewards — they keep the name string."""
    if actor.role != 'ADMIN':
        raise DomainError('FORBIDDEN', 'Reward categories are admin-managed')
    name = name.strip()
    if not name:
        raise DomainError('BAD_REQUEST', 'Category name is required')
    if category_id:
        c = db.scalar(select(RewardCategory).where(
            RewardCategory.id == category_id,
            RewardCategory.company_id == actor.company_id))
        if c is None:
            raise DomainError('NOT_FOUND', 'Category not found')
        was_active = c.active
        c.name, c.active = name, active
        act(db, actor.company_id, actor.id,
            'archived reward category' if was_active and not active else 'updated reward category', name)
        return c
    dup = db.scalar(select(RewardCategory).where(
        RewardCategory.company_id == actor.company_id,
        func.lower(RewardCategory.name) == name.lower()))
    if dup is not None:
        raise DomainError('BAD_REQUEST', 'A category with this name already exists')
    c = RewardCategory(company_id=actor.company_id, name=name, active=active)
    db.add(c)
    db.flush()
    act(db, actor.company_id, actor.id, 'created reward category', name)
    return c


def toggle_fulfill_permission(db: Session, actor: User, user_id: str) -> User:
    """N2.2 §6: the REWARD_FULFILL capability is admin-granted, separate from
    the system Role, and grants nothing else. Admins never carry it (they
    fulfill by office). Revoking strips the user's executor seats."""
    if actor.role != 'ADMIN':
        raise DomainError('FORBIDDEN', 'Fulfillment permission is admin-granted')
    u = get_user(db, actor.company_id, user_id)
    if u.role == 'ADMIN':
        raise DomainError('FORBIDDEN', 'Admins fulfill by office and never carry the flag')
    u.can_fulfill_rewards = not u.can_fulfill_rewards
    if not u.can_fulfill_rewards:
        db.query(RewardExecutor).filter(
            RewardExecutor.company_id == actor.company_id,
            RewardExecutor.user_id == u.id).delete()
    act(db, actor.company_id, actor.id,
        'granted reward fulfillment permission' if u.can_fulfill_rewards
        else 'revoked reward fulfillment permission', u.name)
    return u


# ── notifications & preferences ─────────────────────────────────────────────
# Stricter than the TS reducer on purpose: notice mutations are scoped to the
# actor's OWN notices (the frontend only ever touches its own). This closes a