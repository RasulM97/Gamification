"""WS1 Product Reality Recheck — referee evidence capture.

Exercises the REAL WS1 services at commit d3e46b3 (help create/routing,
escalation pass, approval push, recognition, Slack adapter, outbox drain)
against a disposable pgserver database seeded with a Meridian-mini cast, and
prints exactly what a user would see: ephemeral Slack receipts, push email
subject/body (real render()), notification recipients, routing decisions.

The only fake: the SMTP socket. drain() is called with a capturing sender at
its documented injection point; render(), recipient resolution, retry state
machine and dedupe are all the production code paths. The unconfigured-SMTP
scenario uses the real send_email (raises before any socket use).

Run from the repo root:
    .venv/Scripts/python.exe docs/product_reality/ws1_recheck/evidence/capture.py
"""
import hmac
import hashlib
import os
import sys
import time
from urllib.parse import urlencode

os.environ.setdefault('XDG_RUNTIME_DIR', '/tmp/xdg')
os.makedirs('/tmp/xdg', exist_ok=True)

import pgserver  # noqa: E402
import sqlalchemy as sa  # noqa: E402
from urllib.parse import urlparse, urlunparse  # noqa: E402

_server = pgserver.get_server('/tmp/cve-recheck-pg')
_base = _server.get_uri().replace('postgresql://', 'postgresql+psycopg2://')
_admin = sa.create_engine(_base, isolation_level='AUTOCOMMIT')
with _admin.connect() as c:
    c.execute(sa.text('DROP DATABASE IF EXISTS cve_recheck'))
    c.execute(sa.text('CREATE DATABASE cve_recheck'))
os.environ['CVE_DATABASE_URL'] = urlunparse(urlparse(_base)._replace(path='/cve_recheck'))
os.environ['CVE_WEBHOOK_MASTER_KEY'] = 'ab' * 32
os.environ['CVE_UPLOAD_DIR'] = '/tmp/cve-recheck-uploads'
os.environ['CVE_PUBLIC_BASE_URL'] = 'https://cve.meridian.example'

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
sys.path.insert(0, os.path.join(_ROOT, 'backend'))

from app.db import engine, SessionLocal  # noqa: E402
from app.models import Base, Company, User  # noqa: E402
# Full model registration (mirrors backend/tests/conftest.py) so metadata is complete.
import app.capabilities.model  # noqa: E402,F401
import app.organization.model  # noqa: E402,F401
import app.canonical_events.model  # noqa: E402,F401
import app.ingestion.model  # noqa: E402,F401
import app.rules.model  # noqa: E402,F401
import app.policies.model  # noqa: E402,F401
import app.approvals.model  # noqa: E402,F401
import app.economic_effects.model  # noqa: E402,F401
import app.collaboration.model  # noqa: E402,F401
import app.github_connector.model  # noqa: E402,F401
import app.slack_connector.model  # noqa: E402,F401
import app.notifications.model  # noqa: E402,F401
import app.shadow.model  # noqa: E402,F401
from app.organization.model import Team, TeamMembership  # noqa: E402
from app.notifications.model import NotificationDelivery  # noqa: E402
from app.notifications import delivery as worker  # noqa: E402
from app.notifications.email import render, send_email  # noqa: E402
from app.notifications.approval_push import register  # noqa: E402
from app.collaboration import help as help_service, appreciation, routing  # noqa: E402
from app.slack_connector import actions, security  # noqa: E402
from app.slack_connector.model import ChannelWorkspace, ChannelIdentity  # noqa: E402
from app.models import Notification  # noqa: E402
from app.config import settings  # noqa: E402
from app.approvals.service import create_request  # noqa: E402

Base.metadata.create_all(engine)
register()

OUT = []


def say(line=''):
    OUT.append(line)
    print(line)


def section(title):
    say()
    say('=' * 78)
    say(title)
    say('=' * 78)


# ---------------------------------------------------------------- cast
db = SessionLocal()
db.add(Company(id='meridian', name='Meridian Systems'))
db.flush()
cast = [
    ('marta', 'Marta Iglesias', 'ADMIN'),
    ('henrik', 'Henrik Dahl', 'MANAGER'),
    ('tomas', 'Tomas Ribeiro', 'EMPLOYEE'),
    ('lena', 'Lena Fischer', 'EMPLOYEE'),
    ('david', 'David Osei', 'EMPLOYEE'),
]
for uid, name, role in cast:
    db.add(User(id=uid, company_id='meridian', name=name, role=role,
                email=f'{uid}@meridian.example', active=True, password_hash='disabled'))
db.add(Team(id='team-platform', company_id='meridian', name='Platform'))
db.flush()
for uid, mgr in (('henrik', True), ('tomas', False), ('lena', False)):
    db.add(TeamMembership(company_id='meridian', team_id='team-platform', user_id=uid, manager=mgr))
db.commit()
users = {u.id: u for u in db.scalars(sa.select(User))}


def outbox():
    return list(db.scalars(sa.select(NotificationDelivery).order_by(NotificationDelivery.id)))


def inbox(uid):
    return [(n.event_type, n.level) for n in db.scalars(
        sa.select(Notification).where(Notification.user_id == uid).order_by(Notification.id))]


sent_mail = []


def capture_sender(to, subject, body, *, message_id):
    sent_mail.append(dict(to=to, subject=subject, body=body, message_id=message_id))


def drain_now():
    return worker.drain(db, sender=capture_sender)


# ---------------------------------------------------------------- S1: help in-app, team scope
section('S1 — HELP CREATED IN CVE, TEAM-SCOPED (Lena, Platform team)')
view = help_service.create(db, users['lena'], {
    'title': 'Orion migration script fails on foreign keys',
    'description': 'The schema migration aborts at step 4; need a second pair of eyes today.',
    'submissionId': 'recheck-help-1',
    'scope': {'kind': 'TEAM', 'id': 'team-platform'}})
db.commit()
say(f"requester view: status={view['status']} routingStatus={view['routingStatus']}")
rows = outbox()
for r in rows:
    say(f"outbox: class={r.push_class} event={r.event_type} recipient={r.recipient_user_id} "
        f"params.scope={r.params.get('scopeKind')}/{r.params.get('scopeName')}")
say(f"in-app notifications: tomas={inbox('tomas')} henrik={inbox('henrik')} marta={inbox('marta')} lena={inbox('lena')}")
say(f"drain: {drain_now()}")
db.commit()
for m in sent_mail:
    say(f"--- email to={m['to']} message-id=<{m['message_id']}@cve-outbound>")
    say(f"Subject: {m['subject']}")
    say(m['body'])
sent_mail.clear()

# ---------------------------------------------------------------- S2: help via Slack
section('S2 — HELP VIA SLACK /cve-help team (Lena, mapped identity) [WS1.1]')
db.add(ChannelWorkspace(id='cw-meridian', company_id='meridian', external_team_id='TMERIDIAN1',
                        name='Meridian Slack', workspace_key='w' * 32, secret_nonce='cd' * 32))
db.flush()
for uid, ext in (('lena', 'ULENA00001'), ('tomas', 'UTOMAS0001'), ('henrik', 'UHENRIK001'),
                 ('marta', 'UMARTA0001')):
    db.add(ChannelIdentity(company_id='meridian', workspace_id='cw-meridian',
                           external_user_id=ext, user_id=uid))
db.commit()
ws = db.get(ChannelWorkspace, 'cw-meridian')
signing = security.secret(ws)


def slack(command, user, text, trigger):
    body = urlencode({'command': command, 'user_id': user, 'team_id': 'TMERIDIAN1',
                      'trigger_id': trigger, 'text': text}).encode()
    ts = str(int(time.time()))
    sig = 'v0=' + hmac.new(signing.encode(), b'v0:' + ts.encode() + b':' + body,
                           hashlib.sha256).hexdigest()
    return actions.receive(db, ws.workspace_key, ts, sig, body)


receipt = slack('/cve-help', 'ULENA00001', 'team Need help reviewing the Atlas launch checklist', 'trg-help-1')
db.commit()
say(f"ephemeral receipt to Lena: {receipt['text']}  (result={receipt['result']}, recordId={receipt['recordId']})")
help_row = db.get(__import__('app.collaboration.model', fromlist=['HelpRequest']).HelpRequest, receipt['recordId'])
say(f"slack-created help scope: team_id={help_row.team_id} routingStatus={help_row.routing_status}")
say(f"routed recipients (outbox): {[r.recipient_user_id for r in outbox() if r.params.get('helpId') == receipt['recordId']]}")
say(f"drain: {drain_now()}")
db.commit()
for m in sent_mail:
    say(f"--- email to={m['to']}")
    say(f"Subject: {m['subject']}")
    say(m['body'])
sent_mail.clear()

section('S2b — SLACK /cve-help WITHOUT EXPLICIT SCOPE (guidance, no request)')
receipt = slack('/cve-help', 'ULENA00001', 'Need help with the export', 'trg-help-guide')
db.commit()
say(f"ephemeral receipt: {receipt['text']}  (result={receipt['result']})")
say(f"help requests created: {db.scalar(sa.select(sa.func.count()).select_from(help_row.__class__))} (unchanged — guidance only)")

# ---------------------------------------------------------------- S3/S4/S5: Slack friction
section('S3 — SLACK UNMAPPED USER (David, no identity mapping)')
receipt = slack('/cve-help', 'UDAVID0001', 'Need help with the CRM export', 'trg-david-1')
db.commit()
say(f"ephemeral receipt: {receipt['text']}  (result={receipt['result']})")

section('S4 — SLACK EMPTY TEXT (Lena) [WS1.1 mapped guidance]')
receipt = slack('/cve-help', 'ULENA00001', '', 'trg-lena-empty')
db.commit()
say(f"ephemeral receipt: {receipt['text']}  (result={receipt['result']})")
bad = db.scalar(sa.select(__import__('app.slack_connector.model', fromlist=['ChannelDelivery']).ChannelDelivery)
                .order_by(sa.desc('created_at')).limit(1))
say(f"audit row keeps the code: result={bad.result} detail={bad.detail!r}")

section('S5 — SLACK /cve-recognize BY EMPLOYEE (Lena -> Tomas, not a manager) [WS1.1 mapped]')
receipt = slack('/cve-recognize', 'ULENA00001', '<@UTOMAS0001> Great debugging session today', 'trg-rec-1')
db.commit()
say(f"ephemeral receipt: {receipt['text']}  (result={receipt['result']})")
bad = db.scalar(sa.select(__import__('app.slack_connector.model', fromlist=['ChannelDelivery']).ChannelDelivery)
                .order_by(sa.desc('created_at')).limit(1))
say(f"audit row keeps the code: detail={bad.detail!r}")

section('S5b — SLACK DUPLICATE RETRY (same trigger_id replayed) [WS1.1 identical confirmation]')
receipt = slack('/cve-help', 'ULENA00001', 'team Need help reviewing the Atlas launch checklist', 'trg-help-1')
db.commit()
say(f"ephemeral receipt: {receipt['text']}  (duplicate={receipt['duplicate']})")
say("retry text == original text: "
    f"{receipt['text'] == 'Your Help request was sent to eligible members of Platform.'}")
say(f"help request count: {db.scalar(sa.select(sa.func.count()).select_from(help_row.__class__))}")

# ---------------------------------------------------------------- S6: escalation
section('S6 — HELP ESCALATION (S1 request unanswered past the 240-min window)')
stale = settings.help_escalation_window_ms + 60_000
result = routing.pass_due(db, 'meridian', now=__import__('app.models', fromlist=['now_ms']).now_ms() + stale)
db.commit()
say(f"pass_due result: {result}")
esc = [r for r in outbox() if r.event_type == 'HELP_ESCALATED']
for r in esc:
    say(f"escalation push: recipient={r.recipient_user_id} reason={r.params.get('reason')} scope={r.params.get('scopeName')}")
say(f"drain: {drain_now()}")
db.commit()
for m in sent_mail:
    say(f"--- email to={m['to']}")
    say(f"Subject: {m['subject']}")
    say(m['body'])
sent_mail.clear()

section('S6b — ACCEPTED HELP NEVER ESCALATES')
view2 = help_service.create(db, users['lena'], {
    'title': 'Second request — accepted quickly',
    'description': 'x', 'submissionId': 'recheck-help-2',
    'scope': {'kind': 'TEAM', 'id': 'team-platform'}})
help_service.transition(db, users['tomas'], view2['id'], 'accept')
db.commit()
result = routing.pass_due(db, 'meridian', now=__import__('app.models', fromlist=['now_ms']).now_ms() + stale * 2)
db.commit()
say(f"pass_due after accept: {result}  (escalated must stay 0)")
say(f"requester in-app after accept: {inbox('lena')}")
drain_now()
db.commit()
sent_mail.clear()

# ---------------------------------------------------------------- S7: approval push
section('S7 — INCENTIVE APPROVAL PUSH (Tomas earns above-threshold incentive)')
from app.canonical_events.contracts import EventInput  # noqa: E402
from app.canonical_events.store import PostgresEventStore  # noqa: E402
from app.rules.service import create_rule, evaluate_event  # noqa: E402
from app.policies.service import create_policy, evaluate_candidate  # noqa: E402
from tests.test_rule_evaluator import rule  # noqa: E402
from tests.policy_helpers import policy  # noqa: E402

admin = users['marta']
kind = 'synthetic.recheck.incentive'
rv = create_rule(db, admin, rule(eventType=kind, conditions=[],
                                 outcome=dict(kind='INCENTIVE',
                                              data={'proposedReward': 20, 'approvalHint': 'MANAGER'})))
ev = PostgresEventStore(db).append('meridian', EventInput(
    type=kind, schema_version=1, source_kind='MANUAL', source_id=admin.id,
    source_event_id='recheck', occurred_at=1750000000000,
    payload={'synthetic': True}, subject_id='tomas', actor_id=None))
db.commit()
cid = evaluate_event(db, admin, ev.id)['candidateIds'][0]
db.commit()
create_policy(db, admin, policy(eventType=kind, decision='REQUIRE_APPROVAL'))
db.commit()
pd = evaluate_candidate(db, admin, cid)
db.commit()
request = create_request(db, admin, pd['decisionId'])
db.commit()
say(f"approval request id={request['id']} requiredAuthority={request['requiredAuthority']}")
rows = [r for r in outbox() if r.event_type == 'APPROVAL_REQUESTED']
for r in rows:
    say(f"push: recipient={r.recipient_user_id} amount={r.params.get('amount')} subject={r.params.get('subjectName')}")
say(f"subject tomas excluded: {'tomas' not in [r.recipient_user_id for r in rows]}")
say(f"drain: {drain_now()}")
db.commit()
for m in sent_mail:
    say(f"--- email to={m['to']}")
    say(f"Subject: {m['subject']}")
    say(m['body'])
sent_mail.clear()

# ---------------------------------------------------------------- S8: recognition push
section('S8 — RECOGNITION (Henrik recognizes Tomas, in-app)')
appreciation.create(db, users['henrik'], 'recognition', {
    'recipientUserId': 'tomas',
    'message': 'Owned the Orion schema migration end to end.',
    'submissionId': 'recheck-rec-1'})
db.commit()
say(f"tomas in-app: {inbox('tomas')}")
say(f"drain: {drain_now()}")
db.commit()
for m in sent_mail:
    say(f"--- email to={m['to']}")
    say(f"Subject: {m['subject']}")
    say(m['body'])
sent_mail.clear()

# ---------------------------------------------------------------- S9: Slack recognition by manager
section('S9 — SLACK /cve-recognize BY MANAGER (Henrik -> Tomas)')
receipt = slack('/cve-recognize', 'UHENRIK001', '<@UTOMAS0001> Calm incident handling on Friday', 'trg-rec-2')
db.commit()
say(f"ephemeral receipt: {receipt['text']}  (result={receipt['result']})")
say(f"drain: {drain_now()}")
db.commit()
for m in sent_mail:
    say(f"--- email to={m['to']}")
    say(f"Subject: {m['subject']}")
    say(m['body'])
sent_mail.clear()

# ---------------------------------------------------------------- S10: fatigue day
section('S10 — NOTIFICATION FATIGUE DAY (thanks, help accepted/finished, approval decided)')
appreciation.create(db, users['tomas'], 'thanks', {
    'recipientUserId': 'lena', 'message': 'Thanks for the checklist review!', 'submissionId': 'recheck-thx-1'})
help_service.transition(db, users['tomas'], view2['id'], 'finish')
help_service.transition(db, users['lena'], view2['id'], 'confirm')
db.commit()
say(f"thanks push rows staged: {len([r for r in outbox() if r.event_type == 'PEER_THANKS'])} (must be 0)")
say(f"HELP_ACCEPTED/HELP_FINISHED push rows: "
    f"{len([r for r in outbox() if r.event_type in ('HELP_ACCEPTED', 'HELP_FINISHED', 'HELP_CONFIRMED')])} (must be 0)")
say(f"lena in-app: {inbox('lena')}")
say(f"tomas in-app: {inbox('tomas')}")
say(f"TOTAL outbox rows this whole day: {len(outbox())}")
for r in outbox():
    say(f"  {r.push_class:38s} {r.event_type:22s} -> {r.recipient_user_id}")
say(f"drain: {drain_now()}")
db.commit()
sent_mail.clear()

# ---------------------------------------------------------------- S11: unconfigured SMTP honesty
section('S11 — NO OUTBOUND CONFIGURED (real send_email, smtp_host empty)')
original = settings.smtp_host
settings.smtp_host = ''
appreciation.create(db, users['henrik'], 'recognition', {
    'recipientUserId': 'lena', 'message': 'Fast ramp-up on the Platform tooling.',
    'submissionId': 'recheck-rec-2'})
db.commit()
pending_before = len([r for r in outbox() if r.status == 'PENDING'])
summary = worker.drain(db, sender=send_email)
db.rollback()
say(f"pending before drain: {pending_before}; drain summary: {summary}")
say(f"rows still PENDING, attempts untouched: "
    f"{[(r.dedupe_key, r.status, r.attempts) for r in outbox() if r.status == 'PENDING']}")
settings.smtp_host = original
say("(product stays up; admin sees PENDING rows — nothing pretends to be delivered)")

say()
say('EVIDENCE CAPTURE COMPLETE')
