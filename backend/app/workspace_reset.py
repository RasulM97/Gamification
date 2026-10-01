"""Admin-only, explicitly enabled development tool; no schema or seed changes."""
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from .config import settings
from .domain import DomainError
from .models import (Activity, Attachment, Company, Contribution, LedgerTransaction,
                     Notification, Redemption, Reward, RewardExecutor, Submission,
                     Task, TaskCycle, User)
from .serializers import bootstrap
from .storage import storage
from .workspace_files import WorkspaceFiles
from .capabilities.service import require
from .collaboration.model import PeerThanks, ManagerRecognition, HelpRequest

# Dependency order. All deletion predicates use the authenticated actor's company.
OPERATIONAL_MODELS = (Attachment, Contribution, TaskCycle, Submission,
                      RewardExecutor, Redemption, LedgerTransaction, Notification,
                      Activity, Task, Reward)


def clear_workspace(db: Session, actor: User) -> dict:
    if actor.role != 'ADMIN':
        raise DomainError('FORBIDDEN', 'Admin required')
    # The historical default is True; a destructive tool additionally requires
    # CVE_DEV_MODE (or Settings(dev_mode=...)) to have been explicitly supplied.
    if not settings.dev_mode or 'dev_mode' not in settings.model_fields_set:
        raise DomainError('FORBIDDEN', 'Destructive test tools are disabled')
    require(db, actor.company_id, 'TASK_LITE')
    company_id = actor.company_id
    files = WorkspaceFiles(storage.root, company_id)
    try:
        # Prevent concurrent writes from leaving half of a workflow across the
        # clear boundary. Locks last only for this transaction; no constraints
        # are disabled and no other tenant's rows are deleted.
        collaboration = (PeerThanks, ManagerRecognition, HelpRequest)
        tables = ', '.join(model.__tablename__ for model in (*OPERATIONAL_MODELS, *collaboration))
        db.execute(text(f'LOCK TABLE {tables} IN SHARE ROW EXCLUSIVE MODE'))
        if any(db.scalar(select(model.id).where(model.company_id == company_id).limit(1))
               for model in collaboration):
            raise DomainError('FORBIDDEN', 'Collaboration history cannot be cleared; use a separate test company')
        if db.scalar(select(LedgerTransaction.id).where(
                LedgerTransaction.company_id == company_id,
                LedgerTransaction.type.in_(('INCENTIVE_REWARD', 'INCENTIVE_REVERSAL'))).limit(1)):
            raise DomainError('FORBIDDEN', 'Issued economic history cannot be cleared; use a separate test company')
        # Transaction-local exception for the existing explicitly authorized
        # development reset. The DB guard never permits deletion of E7 rows.
        db.execute(text("SELECT set_config('cve.legacy_workspace_reset_company', :company_id, true)"),
                   {'company_id': company_id})
        paths = list(db.scalars(select(Attachment.storage_path).where(Attachment.company_id == company_id)))
        files.prepare(paths)
        for model in OPERATIONAL_MODELS:
            db.execute(delete(model).where(model.company_id == company_id))
        db.flush()
        result = bootstrap(db, db.get(Company, company_id), viewer=actor)
        db.commit()
    except Exception:
        db.rollback()
        raise
    files.cleanup()
    return result
