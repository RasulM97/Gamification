# cross-user write path the client-side engine could not enforce.


def _own_notice(db: Session, actor: User, notice_id: str) -> Notification:
    n = db.scalar(select(Notification).where(
        Notification.id == notice_id, Notification.company_id == actor.company_id,
        Notification.user_id == actor.id))
    if n is None:
        raise DomainError('NOT_FOUND', 'Notification not found')
    return n


def mark_read(db: Session, actor: User, notice_id: str) -> None:
    _own_notice(db, actor, notice_id).read = True


def mark_all_read(db: Session, actor: User) -> None:
    db.query(Notification).filter(
        Notification.company_id == actor.company_id,
        Notification.user_id == actor.id, Notification.read.is_(False)
    ).update({'read': True})


def archive_notice(db: Session, actor: User, notice_id: str) -> None:
    n = _own_notice(db, actor, notice_id)
    n.archived = True
    n.read = True


def archive_all_read(db: Session, actor: User) -> None:
    db.query(Notification).filter(
        Notification.company_id == actor.company_id,
        Notification.user_id == actor.id, Notification.read.is_(True),
        Notification.archived.is_(False)
    ).update({'archived': True})


def toggle_notif_mute(db: Session, actor: User, level: str) -> None:
    if level not in MUTABLE_LEVELS:
        raise DomainError('FORBIDDEN', 'Only low-priority levels can be muted')
    cur = list(actor.notif_muted or [])
    actor.notif_muted = [l for l in cur if l != level] if level in cur else [*cur, level]


def update_settings(db: Session, actor: User, *, max_file_size_mb: int,
                    max_submission_total_mb: int) -> CompanySettings:
    if actor.role != 'ADMIN':
        raise DomainError('FORBIDDEN', 'Company policy is admin-only')
    s = settings_of(db, actor.company_id)
    s.max_file_size_mb = max(1, min(100, _round(max_file_size_mb)))
    s.max_submission_total_mb = max(1, min(500, _round(max_submission_total_mb)))
    act(db, actor.company_id, actor.id, 'updated upload policy',
        f'{s.max_file_size_mb} MB/file · {s.max_submission_total_mb} MB/submission')
    return s
