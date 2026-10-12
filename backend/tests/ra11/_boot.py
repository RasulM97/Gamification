"""RA-1.1 helper subprocess: create schema (Base.metadata) and run the demo
seed against the disposable database named by CVE_DATABASE_URL.

Runs as a separate process so app config binds to the disposable database
only. Never pointed at a non-disposable database — the harness verifies the
URL targets the experiment's own pgserver cluster before invoking this.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.db import engine  # noqa: E402
from app.db import session_scope  # noqa: E402
from app.models import Base  # noqa: E402

# Import every model module so metadata is complete (mirrors tests/conftest).
from app.capabilities.model import CompanyCapability, CapabilityChange  # noqa: F401,E402
from app.organization import model as organization_models  # noqa: F401,E402
from app.canonical_events.model import CanonicalEvent  # noqa: F401,E402
from app.ingestion.model import WebhookSource  # noqa: F401,E402
from app.rules.model import Rule, RuleCandidate  # noqa: F401,E402
from app.policies.model import Policy, PolicyDecision  # noqa: F401,E402
from app.approvals.model import ApprovalRequest, ApprovalDecision  # noqa: F401,E402
from app.economic_effects.model import EconomicEffect, EconomicReversal  # noqa: F401,E402
from app.collaboration.model import PeerThanks, ManagerRecognition, HelpRequest, HelpRouting  # noqa: F401,E402
from app.github_connector.model import GithubSource, GithubIdentity, GithubDelivery  # noqa: F401,E402
from app.slack_connector.model import ChannelWorkspace, ChannelIdentity, ChannelDelivery  # noqa: F401,E402
from app.notifications.model import NotificationDelivery  # noqa: F401,E402
from app.shadow.model import ShadowEvaluation  # noqa: F401,E402

from app.seed import run as seed_run  # noqa: E402

Base.metadata.create_all(engine)
with session_scope() as db:
    seed_run(db)
print('schema+seed complete')
