"""Deterministic Aster Dynamics seed (M1 §11) — the same pilot scenario as
src/domain/seed.ts, now with real auth columns (email + bcrypt hash) and real
stored files for every seed attachment (small placeholders, so /api/files
works end-to-end from the first boot).

Idempotent: runs only when the companies table is empty.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Activity, Attachment, Company, CompanySettings, Contribution,
    LedgerTransaction, Notification, Redemption, Reward, Submission, Task,
    TaskCycle, User, now_ms,
)
from .security import hash_password
from .storage import storage

H = 3600e3
D = 24 * H
DEMO_PASSWORD = 'demo1234'


def _placeholder(name: str) -> bytes:
    if name.lower().endswith('.pdf'):
        return b'%PDF-1.4\n% CVE demo placeholder for ' + name.encode() + b'\n'
    return f'CVE demo placeholder file: {name}\n'.encode()


def seed_if_empty(db: Session) -> bool:
    if db.scalar(select(Company).limit(1)) is not None:
        return False
    run(db)
    return True


def run(db: Session) -> None:
    now = now_ms()
    dl = lambda d: date.today() + timedelta(days=d)  # noqa: E731

    co = Company(id='co-aster', name='Aster Dynamics', seq=100)
    db.add(co)
    db.add(CompanySettings(company_id=co.id, max_file_size_mb=10,
                           max_submission_total_mb=25))

    pw_hash = hash_password(DEMO_PASSWORD)  # one real bcrypt hash, shared by demo users

    def user(id, name, role, position):
        return User(id=id, company_id=co.id, name=name,
                    email=f'{name.split()[0].lower()}@aster.demo', role=role,
                    position=position, password_hash=pw_hash,
                    notif_muted=[])

    db.add_all([
        user('u-dana', 'Dana Cole', 'ADMIN', 'Operations Director'),
        user('u-marcus', 'Marcus Webb', 'MANAGER', 'Sales Team Lead'),
        user('u-priya', 'Priya Nair', 'EMPLOYEE', 'Sales Associate'),
        user('u-jonas', 'Jonas Berg', 'EMPLOYEE', 'Field Coordinator'),
        user('u-aisha', 'Aisha Khan', 'EMPLOYEE', 'Business Analyst'),
    ])

    def brief(task_id, files):
        for name, size, typ in files:
            db.add(Attachment(company_id=co.id, task_id=task_id, kind='brief',
                              name=name, size=size, type=typ,
                              storage_path=storage.save(co.id, name, _placeholder(name)),
                              created_at=now))

    def sub_atts(sub_id, task_id, files, at):
        for name, size, typ in files:
            db.add(Attachment(company_id=co.id, task_id=task_id, submission_id=sub_id,
                              kind='submission', name=name, size=size, type=typ,
                              storage_path=storage.save(co.id, name, _placeholder(name)),
                              created_at=at))

    def task(**kw) -> Task:
        t = Task(company_id=co.id, **kw)
        db.add(t)
        return t

    # ── tasks (mirrors seed.ts 1:1) ──────────────────────────────────────
    task(id='t-audit', title='Q3 inventory audit', reward=40,
         description='Full physical count of warehouse A stock against the ERP ledger. Reconcile variances over 2% and document root causes. Deliverable: signed variance report.',
         priority='IMPORTANT', deadline=dl(-6), audience='EMPLOYEES',
         assign_mode='ALL_EMPLOYEES', assignee_id=None, instructions=None,
         status='APPROVED', owner_id=None, cycle=2, verified=100, reported=0, paid=40,
         created_at=now - 40 * D, updated_at=now - 5 * D, created_by='u-marcus')
    brief('t-audit', [('warehouse-A-map.pdf', 890_000, 'application/pdf')])
    db.add_all([
        Submission(id='s1', company_id=co.id, task_id='t-audit', cycle=2, user_id='u-priya',
                   note='Aisles 1–6 counted and reconciled; variance sheet attached. Pulling me onto the client escalation — handing the rest over.',
                   reported_pct=45, at=now - 9 * D, outcome='HANDED_OFF',
                   reviewer_id='u-marcus', review_note='Pulled onto a client escalation mid-audit',
                   reviewed_at=now - 9 * D),
        Submission(id='s2', company_id=co.id, task_id='t-audit', cycle=2, user_id='u-jonas',
                   note='Remaining aisles counted, root causes documented. Signed variance report attached.',
                   reported_pct=100, at=now - 5 * D, outcome='APPROVED',
                   reviewer_id='u-marcus', review_note=None, reviewed_at=now - 5 * D),
        Contribution(id='c1', company_id=co.id, task_id='t-audit', cycle=2, employee_id='u-priya',
                     reported_pct=45, accepted_pct=20, payout=8, decision='HANDOFF',
                     reason='Pulled onto a client escalation mid-audit', at=now - 9 * D),
        Contribution(id='c2', company_id=co.id, task_id='t-audit', cycle=2, employee_id='u-jonas',
                     reported_pct=100, accepted_pct=80, payout=32, decision='APPROVED',
                     reason='Work approved', at=now - 5 * D),
        TaskCycle(company_id=co.id, task_id='t-audit', cycle=1, opened_at=now - 40 * D,
                  closed_at=now - 33 * D, outcome='APPROVED', paid=40, verified=100),
        TaskCycle(company_id=co.id, task_id='t-audit', cycle=2, opened_at=now - 12 * D,
                  closed_at=now - 5 * D, outcome='APPROVED', paid=40, verified=100),
    ])
    sub_atts('s1', 't-audit', [('variance-aisles-1-6.xlsx', 210_000,
             'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')], now - 9 * D)
    sub_atts('s2', 't-audit', [('variance-report-signed.pdf', 1_100_000, 'application/pdf')], now - 5 * D)

    task(id='t-northstar', title='Client onboarding pack — Northstar Labs', reward=37,
         description='Prepare the full onboarding pack for Northstar Labs: welcome deck, contract checklist, account provisioning form and the first-week meeting schedule.',
         priority='URGENT', deadline=dl(1), audience='EMPLOYEES',
         assign_mode='ALL_EMPLOYEES', assignee_id=None, instructions=None,
         status='SUBMITTED', owner_id='u-priya', cycle=1, verified=0, reported=100, paid=0,
         submission_note='All four documents attached. The provisioning form is pre-filled with their details — needs one compliance look at section 3.',
         submitted_at=now - 5 * H,
         created_at=now - 2 * D, updated_at=now - 5 * H, created_by='u-marcus')
    north_files = [('welcome-deck.pdf', 2_400_000, 'application/pdf'),
                   ('contract-checklist.xlsx', 180_000,
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                   ('provisioning-form.pdf', 640_000, 'application/pdf')]
    db.add(Submission(id='s3', company_id=co.id, task_id='t-northstar', cycle=1, user_id='u-priya',
                      note='All four documents attached. The provisioning form is pre-filled with their details — needs one compliance look at section 3.',
                      reported_pct=100, at=now - 5 * H, outcome='PENDING'))
    sub_atts('s3', 't-northstar', north_files, now - 5 * H)
    db.add(TaskCycle(company_id=co.id, task_id='t-northstar', cycle=1, opened_at=now - 2 * D))

    task(id='t-commission', title='Quarterly commission reconciliation', reward=30,
         description='Reconcile Q3 commission payouts against closed-won deals in the CRM. Flag any rep-level discrepancy above $500 with supporting evidence.',
         priority='NORMAL', deadline=dl(4), audience='EMPLOYEES',
         assign_mode='SPECIFIC_EMPLOYEE', assignee_id=None, instructions=None,
         status='IN_PROGRESS', owner_id='u-jonas', cycle=1, verified=20, reported=35, paid=6,
         created_at=now - 8 * D, updated_at=now - 20 * H, created_by='u-dana')
    db.add_all([
        Submission(id='s4', company_id=co.id, task_id='t-commission', cycle=1, user_id='u-priya',
                   note='Deal-level extract is done — discrepancies over $500 flagged in the attached sheet. Field verification still open.',
                   reported_pct=25, at=now - 3 * D, outcome='HANDED_OFF',
                   reviewer_id='u-marcus', review_note='Deal-level extract done; field verification needed',
                   reviewed_at=now - 3 * D),
        Contribution(id='c3', company_id=co.id, task_id='t-commission', cycle=1, employee_id='u-priya',
                     reported_pct=25, accepted_pct=20, payout=6, decision='HANDOFF',
                     reason='Deal-level extract done; field verification needed', at=now - 3 * D),
        TaskCycle(company_id=co.id, task_id='t-commission', cycle=1, opened_at=now - 8 * D,
                  paid=6, verified=20),
    ])
    sub_atts('s4', 't-commission', [('commission-discrepancies.xlsx', 150_000,
             'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')], now - 3 * D)

    task(id='t-recount', title='Urgent inventory recount — Warehouse B', reward=25,
         description='Auditors flagged a 6% variance in Warehouse B. Full recount of aisles 1–14, photo evidence per aisle, same-day variance memo.',
         priority='URGENT', deadline=dl(0), audience='EMPLOYEES',
         assign_mode='ALL_EMPLOYEES', assignee_id=None,
         status='OPEN', owner_id=None, cycle=1, verified=0, reported=0, paid=0,
         created_at=now - 7 * H, updated_at=now - 7 * H, created_by='u-dana')
    db.add(TaskCycle(company_id=co.id, task_id='t-recount', cycle=1, opened_at=now - 7 * H))

    task(id='t-leads', title='Trade-show lead list cleanup', reward=20,
         description='Deduplicate the 480 leads from ExpoWest, enrich missing company fields, and tag each lead with region and product interest.',
         priority='NORMAL', deadline=dl(3), audience='EMPLOYEES',
         assign_mode='SPECIFIC_EMPLOYEE', assignee_id=None, instructions=None,
         status='REJECTED', owner_id='u-aisha', cycle=1, verified=0, reported=90, paid=0,
         submission_note='Deduplication done, 412 unique leads remain. Enrichment in progress.',
         rejection_reason='Duplicates remain in rows 200–260 and 40 leads have no region tag. Please finish enrichment before resubmitting.',
         submitted_at=now - 26 * H,
         created_at=now - 4 * D, updated_at=now - 26 * H, created_by='u-marcus')
    db.add_all([
        Submission(id='s5', company_id=co.id, task_id='t-leads', cycle=1, user_id='u-aisha',
                   note='Deduplication done, 412 unique leads remain. Enrichment in progress.',
                   reported_pct=90, at=now - 26 * H, outcome='REJECTED',
                   reviewer_id='u-marcus',
                   review_note='Duplicates remain in rows 200–260 and 40 leads have no region tag. Please finish enrichment before resubmitting.',
                   reviewed_at=now - 26 * H),
        TaskCycle(company_id=co.id, task_id='t-leads', cycle=1, opened_at=now - 4 * D),
    ])
    sub_atts('s5', 't-leads', [('leads-cleaned.csv', 310_000, 'text/csv')], now - 26 * H)

    task(id='t-crm', title='Update CRM pipeline stages', reward=15,
         description='Migrate the sales pipeline to the new 5-stage model agreed in QBR. Remap open opportunities and archive stale ones older than 90 days.',
         priority='NORMAL', deadline=dl(6), audience='EMPLOYEES',
         assign_mode='SPECIFIC_EMPLOYEE', assignee_id=None, instructions=None,
         status='IN_PROGRESS', owner_id='u-jonas', cycle=1, verified=0, reported=40, paid=0,
         created_at=now - 3 * D, updated_at=now - 9 * H, created_by='u-marcus')
    db.add(TaskCycle(company_id=co.id, task_id='t-crm', cycle=1, opened_at=now - 3 * D))

    task(id='t-pricing', title='Competitor pricing snapshot', reward=12,
         description='Collect current list prices for the 8 named competitors across our three core SKUs. One-page comparison table, sources linked.',
         priority='IMPORTANT', deadline=dl(5), audience='EMPLOYEES',
         assign_mode='ALL_EMPLOYEES', assignee_id=None, instructions=None,
         status='OPEN', owner_id=None, cycle=1, verified=0, reported=0, paid=0,
         created_at=now - 30 * H, updated_at=now - 30 * H, created_by='u-marcus')
    db.add(TaskCycle(company_id=co.id, task_id='t-pricing', cycle=1, opened_at=now - 30 * H))

    task(id='t-policy', title='Expense policy one-pager', reward=10,
         description='Turn the 14-page expense policy into a one-page visual summary employees actually read. Design review with Dana before publishing.',
         priority='NONE', deadline=dl(9), audience='EMPLOYEES',
         assign_mode='SPECIFIC_EMPLOYEE', assignee_id='u-priya', instructions=None,
         status='OPEN', owner_id=None, cycle=1, verified=0, reported=0, paid=0,
         created_at=now - 8 * H, updated_at=now - 8 * H, created_by='u-dana')
    db.add(TaskCycle(company_id=co.id, task_id='t-policy', cycle=1, opened_at=now - 8 * H))

    task(id='t-incentive', title='Q4 sales incentive plan', reward=50,
         description='Design the Q4 incentive plan for the sales team: quota multipliers, accelerator tiers and the Coin budget per tier. Deliverable: one-page plan plus a budget worksheet, reviewed in the ops sync. Visible to management only.',
         priority='IMPORTANT', deadline=dl(7), audience='MANAGEMENT',
         assign_mode='SPECIFIC_EMPLOYEE', assignee_id='u-marcus', instructions=None,
         status='OPEN', owner_id=None, cycle=1, verified=0, reported=0, paid=0,
         created_at=now - 3 * H, updated_at=now - 3 * H, created_by='u-dana')
    db.add(TaskCycle(company_id=co.id, task_id='t-incentive', cycle=1, opened_at=now - 3 * H))

    task(id='t-contracts', title='Archive 2024 contracts', reward=18,
         description='Move all 2024 signed contracts to cold storage with correct retention labels. Export the index spreadsheet first.',
         priority='NONE', deadline=None, audience='EMPLOYEES',
         assign_mode='ALL_EMPLOYEES', assignee_id=None, instructions=None,
         status='CANCELLED', owner_id=None, cycle=1, verified=0, reported=0, paid=0,
         created_at=now - 15 * D, updated_at=now - 6 * D, created_by='u-dana')
    db.add(TaskCycle(company_id=co.id, task_id='t-contracts', cycle=1,
                     opened_at=now - 15 * D, closed_at=now - 6 * D,
                     outcome='CANCELLED', paid=0, verified=0))

    # ── ledger (l2–l4 intentional pre-seed history) ──────────────────────
    db.add_all([
        LedgerTransaction(id='l9', company_id=co.id, at=now - 5 * H, user_id='u-priya', type='REDEMPTION', amount=-30, ref='Reward redemption — Lunch voucher'),
        LedgerTransaction(id='l8', company_id=co.id, at=now - 1 * D, user_id='u-jonas', type='REDEMPTION', amount=-60, ref='Reward redemption — Company hoodie'),
        LedgerTransaction(id='l7', company_id=co.id, at=now - 3 * D, user_id='u-priya', type='TASK_PARTIAL_REWARD', amount=6, ref='Partial reward (20%) — Quarterly commission reconciliation', task_id='t-commission', cycle=1),
        LedgerTransaction(id='l6', company_id=co.id, at=now - 5 * D, user_id='u-jonas', type='TASK_REWARD', amount=32, ref='Task reward — Q3 inventory audit', task_id='t-audit', cycle=2),
        LedgerTransaction(id='l5', company_id=co.id, at=now - 9 * D, user_id='u-priya', type='TASK_PARTIAL_REWARD', amount=8, ref='Partial reward (20%) — Q3 inventory audit', task_id='t-audit', cycle=2),
        LedgerTransaction(id='l4', company_id=co.id, at=now - 14 * D, user_id='u-aisha', type='TASK_REWARD', amount=20, ref='Task reward — Sales ops handbook refresh'),
        LedgerTransaction(id='l3', company_id=co.id, at=now - 20 * D, user_id='u-priya', type='TASK_REWARD', amount=45, ref='Task reward — Spring campaign recap'),
        LedgerTransaction(id='l2', company_id=co.id, at=now - 26 * D, user_id='u-jonas', type='TASK_REWARD', amount=38, ref='Task reward — Distributor visit program'),
        LedgerTransaction(id='l1', company_id=co.id, at=now - 33 * D, user_id='u-jonas', type='TASK_REWARD', amount=40, ref='Task reward — Q3 inventory audit (cycle 1)', task_id='t-audit', cycle=1),
    ])

    # ── rewards & redemptions ────────────────────────────────────────────
    db.add_all([
        Reward(id='rw-lunch', company_id=co.id, name='Lunch voucher', description='€25 voucher for the bistro downstairs. Valid any weekday.', cost=30, stock=10, active=True, category='Perks'),
        Reward(id='rw-hoodie', company_id=co.id, name='Company hoodie', description='The good one — heavyweight, embroidered logo. All sizes.', cost=60, stock=4, active=True, category='Swag'),
        Reward(id='rw-coffee', company_id=co.id, name='Coffee subscription — 1 month', description='One month of the good beans, delivered to your desk.', cost=45, stock=None, active=True, category='Perks'),
        Reward(id='rw-parking', company_id=co.id, name='Parking spot — 1 week', description='The reserved spot by the entrance, for a full week.', cost=25, stock=2, active=True, category='Perks'),
        Reward(id='rw-halfday', company_id=co.id, name='Half-day off', description='An afternoon on the house. Coordinate with your manager.', cost=120, stock=3, active=True, category='Time'),
        Reward(id='rw-conf', company_id=co.id, name='Conference ticket', description='Ticket to the annual industry summit, travel not included.', cost=300, stock=1, active=False, category='Growth'),
        Redemption(id='r2', company_id=co.id, user_id='u-priya', reward_id='rw-lunch', cost=30, status='PENDING', at=now - 5 * H),
        Redemption(id='r1', company_id=co.id, user_id='u-jonas', reward_id='rw-hoodie', cost=60, status='FULFILLED', at=now - 1 * D),
    ])

    # ── notices & activity ───────────────────────────────────────────────
    db.add_all([
        Notification(id='n7', company_id=co.id, user_id='u-marcus', level='ACTION_REQUIRED', category='Assignments', text='New assignment — Q4 sales incentive plan (worth 50 Coins). Accept or decline.', task_id='t-incentive', pri='IMPORTANT', at=now - 3 * H),
        Notification(id='n6', company_id=co.id, user_id='u-marcus', level='ACTION_REQUIRED', category='Reviews', text='Submission ready for review — Client onboarding pack — Northstar Labs by Priya Nair.', task_id='t-northstar', at=now - 5 * H),
        Notification(id='n5', company_id=co.id, user_id='u-marcus', level='ACTION_REQUIRED', category='Rewards', text='Reward fulfillment needed — Lunch voucher for Priya Nair (30 Coins).', at=now - 5 * H, redemption_id='r2'),
        Notification(id='n5b', company_id=co.id, user_id='u-dana', level='ACTION_REQUIRED', category='Reviews', text='Submission ready for review — Client onboarding pack — Northstar Labs by Priya Nair.', task_id='t-northstar', at=now - 5 * H),
        Notification(id='n4', company_id=co.id, user_id='u-aisha', level='IMPORTANT', category='Tasks', text='Urgent task available — Urgent inventory recount — Warehouse B (worth 25 Coins), posted by Dana Cole. First valid claim wins.', task_id='t-recount', pri='URGENT', at=now - 7 * H),
        Notification(id='n3', company_id=co.id, user_id='u-priya', level='ACTION_REQUIRED', category='Assignments', text='New assignment — Expense policy one-pager (worth 10 Coins). Accept or decline.', task_id='t-policy', at=now - 8 * H),
        Notification(id='n2', company_id=co.id, user_id='u-aisha', level='ACTION_REQUIRED', category='Tasks', text='Rework required — Trade-show lead list cleanup. Reason: duplicates remain in rows 200–260…', task_id='t-leads', at=now - 26 * H, read=True),
        Notification(id='n1', company_id=co.id, user_id='u-jonas', level='IMPORTANT', category='Economy', text='Approved — Q3 inventory audit. +32 Coins credited to your wallet.', task_id='t-audit', at=now - 5 * D, read=True),
    ])
    db.add_all([
        Activity(id='a10', company_id=co.id, at=now - 3 * H, actor_id='u-dana', action='created task', object='Q4 sales incentive plan', task_id='t-incentive', cycle=1),
        Activity(id='a9', company_id=co.id, at=now - 5 * H, actor_id='u-priya', action='submitted work for review', object='Client onboarding pack — Northstar Labs', task_id='t-northstar', cycle=1),
        Activity(id='a8', company_id=co.id, at=now - 5 * H, actor_id='u-priya', action='redeemed reward', object='Lunch voucher', econ='-30 Coins'),
        Activity(id='a7', company_id=co.id, at=now - 7 * H, actor_id='u-dana', action='created task', object='Urgent inventory recount — Warehouse B', task_id='t-recount', cycle=1),
        Activity(id='a6', company_id=co.id, at=now - 8 * H, actor_id='u-dana', action='created task', object='Expense policy one-pager', task_id='t-policy', cycle=1),
        Activity(id='a5', company_id=co.id, at=now - 20 * H, actor_id='u-jonas', action='reported progress', object='Quarterly commission reconciliation — 35% (self-reported)', task_id='t-commission', cycle=1),
        Activity(id='a4', company_id=co.id, at=now - 26 * H, actor_id='u-marcus', action='rejected submission', object='Trade-show lead list cleanup', task_id='t-leads', reason='Duplicates remain in rows 200–260 and 40 leads have no region tag.', cycle=1),
        Activity(id='a3', company_id=co.id, at=now - 3 * D, actor_id='u-marcus', action='handed off (20% accepted)', object='Quarterly commission reconciliation', task_id='t-commission', reason='Deal-level extract done; field verification needed', econ='+6 Coins', cycle=1),
        Activity(id='a2', company_id=co.id, at=now - 5 * D, actor_id='u-marcus', action='approved work', object='Q3 inventory audit', task_id='t-audit', econ='+32 Coins', cycle=2),
        Activity(id='a1', company_id=co.id, at=now - 9 * D, actor_id='u-marcus', action='handed off (20% accepted)', object='Q3 inventory audit', task_id='t-audit', reason='Pulled onto a client escalation mid-audit', econ='+8 Coins', cycle=2),
    ])
    db.flush()
