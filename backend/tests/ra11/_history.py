"""Shared, fail-closed RA-1.1 journal/audit contract.

Legacy records may omit timestamps, diagnostic fields and audit invocation
IDs. A historical collector status may be recovered only from its matching
completed journal invocation, including coll_rc; never from today's mutable
results.json. Failure markers remain failures even without diagnostic fields.
"""
import json
from pathlib import Path

GATES = ('regression_tests.py', 'oracle_tests.py', 'smoke.py')
EXPERIMENTS = {
    'e1': 'e1_freeze.py', 'e1b': 'e1b_mechanism.py', 'e2': 'e2_upgrade.py',
    'e3': 'e3_auth_pool.py', 'e4': 'e4_lock_order.py',
    'e5': 'e5_commit_outcomes.py', 'e6': 'e6_orphans.py',
    'e7': 'e7_races.py', 'e7r6': 'e7_r6.py',
}
STEPS = {*GATES, *EXPERIMENTS, '_results.py'}
STATUSES = ('COMPLETE', 'PARTIAL', 'FAILED', 'REFUSED')
RESULT_STATUS = {0: 'COMPLETE', 3: 'PARTIAL'}
MARKERS = ('halt', 'refused', 'run_failed')
JOURNAL_TYPES = ('invocation_started', 'invocation_completed',
                 'step_started', 'step_completed')


def identity(value):
    return isinstance(value, str) and bool(value.strip())


def read_records(path, family):
    """Preserve parse/encoding failures as data for the common validator."""
    path = Path(path)
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except (OSError, UnicodeError) as exc:
        return [{'corrupt': family, 'detail': str(exc)}]
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except (ValueError, RecursionError):
            rows.append({'corrupt': family, 'detail': line[:200]})
    return rows


def validate_record(row, family):
    """One structural contract used by orchestration and collection.

    None is a documented timeout return code: valid shape, failed outcome.
    bool is never an integer return code. Unknown types fail closed.
    """
    if not isinstance(row, dict):
        return 'record must be an object'
    if 'corrupt' in row or row.get('j') == 'corrupt':
        return 'unreadable record'
    if family == 'journal':
        kind = row.get('j')
        if kind not in JOURNAL_TYPES:
            return 'unknown journal type'
        if not identity(row.get('inv')):
            return 'missing/invalid invocation identity'
        if kind == 'invocation_started':
            if not identity(row.get('rid')):
                return 'missing/invalid run identity'
        elif kind == 'invocation_completed':
            if row.get('status') not in STATUSES:
                return 'missing/invalid completion status'
            if 'coll_rc' in row and not returncode_valid(row['coll_rc']):
                return 'invalid collector return code'
        elif not isinstance(row.get('step'), str) or row['step'] not in STEPS:
            return 'missing/unknown step identity'
        needs_rc = kind == 'step_completed'
    else:
        step = row.get('step')
        if not isinstance(step, str) or step not in STEPS | set(MARKERS) | {'gates'}:
            return 'missing/unknown audit step'
        if 'inv' in row and not identity(row['inv']):
            return 'invalid audit invocation identity'
        # Old failure markers already determine failure without an exit code.
        needs_rc = step not in MARKERS or 'returncode' in row
    if needs_rc and ('returncode' not in row
                     or not returncode_valid(row['returncode'])):
        return 'missing/invalid return code'
    if 'inspection' in row and row['inspection'] is not None:
        insp = row['inspection']
        if not isinstance(insp, dict):
            return 'invalid inspection'
        if any(type(insp.get(k)) is not bool for k in
               ('invalid', 'cleanup_failed', 'missing_classification')):
            return 'incomplete inspection verdict'
        if not isinstance(insp.get('harness_errors'), list):
            return 'invalid harness error list'
    return None


def returncode_valid(rc):
    return rc is None or type(rc) is int


def result_ok(rc, status):
    return type(rc) is int and rc in RESULT_STATUS and status == RESULT_STATUS[rc]


def classification_valid(record):
    """Required recorded verdict fields; diagnostic/timing fields are optional."""
    return (isinstance(record, dict)
            and record.get('harness_validity') in ('VALID', 'INVALID', 'INCONCLUSIVE')
            and all(identity(record.get(k)) for k in
                    ('experiment', 'product_observation', 'causal_claim')))


def journal_findings(records, current_inv=None):
    findings, invs = [], {}
    run_identity = None

    def fail(kind, **detail):
        findings.append({'kind': kind, **detail})

    for row in records:
        error = validate_record(row, 'journal')
        if error:
            fail('corrupt_journal', detail=error)
            continue  # malformed completion must not close anything
        kind, inv = row['j'], row['inv']
        if kind == 'invocation_started':
            if run_identity is not None and row['rid'] != run_identity:
                fail('journal_relationship', inv=inv, detail='run identity changed')
            run_identity = row['rid']
            if inv in invs:
                fail('journal_relationship', inv=inv, detail='duplicate invocation')
                continue
            invs[inv] = {'open': True, 'steps': {}, 'bad': False}
            continue
        state = invs.get(inv)
        if state is None or not state['open']:
            fail('journal_relationship', inv=inv, detail='record outside invocation')
            continue
        steps = state['steps']
        if kind == 'step_started':
            if (row['step'] in steps or '_results.py' in steps
                    or any(v is None for v in steps.values())):
                fail('journal_relationship', inv=inv, detail='duplicate/overlapping step')
                state['bad'] = True
            else:
                steps[row['step']] = None
        elif kind == 'step_completed':
            step = row['step']
            if step not in steps or steps[step] is not None:
                fail('journal_relationship', inv=inv, detail='orphan/duplicate completion')
                state['bad'] = True
                continue
            steps[step] = row
            rc = row['returncode']
            if ((step == '_results.py' and (type(rc) is not int or rc not in RESULT_STATUS))
                    or (step != '_results.py' and rc != 0)):
                fail('failed_step', step=step, returncode=rc)
                state['bad'] = True
            if step == '_results.py' and 'result_status' in row:
                if not result_ok(rc, row['result_status']):
                    fail('collector_classification', inv=inv)
                    state['bad'] = True
            insp = row.get('inspection') or {}
            if step in EXPERIMENTS and not insp:
                fail('failed_inspection', step=step, detail='missing inspection')
                state['bad'] = True
            if any(insp.get(k) for k in ('invalid', 'cleanup_failed',
                                         'harness_errors', 'missing_classification')):
                fail('failed_inspection', step=step, inspection=insp)
                state['bad'] = True
        else:
            status = row['status']
            if any(v is None for v in steps.values()):
                fail('journal_relationship', inv=inv, detail='completion with open steps')
                state['bad'] = True
            if status in ('FAILED', 'REFUSED'):
                fail('journal_' + status.lower(), inv=inv)
            else:
                coll = steps.get('_results.py')
                if (state['bad'] or not coll
                        or not result_ok(coll['returncode'], status)
                        or type(row.get('coll_rc')) is not int
                        or row['coll_rc'] != coll['returncode']
                        or ('result_status' in coll and coll['result_status'] != status)):
                    fail('collector_classification', inv=inv,
                         detail='healthy completion lacks consistent collector evidence')
            state['open'] = False
    for inv, state in invs.items():
        if inv != current_inv:
            if state['open']:
                fail('unfinished_invocation', inv=inv)
            for step, row in state['steps'].items():
                if row is None:
                    fail('unfinished_step', inv=inv, step=step)
    return findings


def audit_findings(records, journal=(), current_inv=None):
    findings = []
    # Recover legacy collector classifications only from a validated journal.
    legacy = []
    if not journal_findings(journal, current_inv=current_inv):
        ends = {r['inv']: r for r in journal
                if r.get('j') == 'invocation_completed'}
        for r in journal:
            if r.get('j') == 'step_completed' and r.get('step') == '_results.py':
                end = ends.get(r['inv'], {})
                legacy.append((r['inv'], r['returncode'], end.get('status')))
    collector_index = 0
    valid_journal = [r for r in journal if validate_record(r, 'journal') is None]
    starts = {r['inv'] for r in valid_journal if r['j'] == 'invocation_started'}
    completions = {(r['inv'], r['step']): r for r in valid_journal
                   if r['j'] == 'step_completed'}
    for row in records:
        error = validate_record(row, 'audit')
        if error:
            findings.append({'kind': 'corrupt_audit', 'detail': error})
            continue
        step = row['step']
        if 'inv' in row:
            other = completions.get((row['inv'], step))
            if (row['inv'] not in starts or (step in STEPS and
                    (other is None or row['returncode'] != other['returncode']
                     or (step == '_results.py' and 'result_status' in other
                         and row.get('result_status') != other['result_status'])))):
                findings.append({'kind': 'audit_journal_mismatch', 'step': step})
        if step in MARKERS:
            findings.append({'kind': 'audit_' + step, 'failed': row.get('failed')})
        elif step == '_results.py':
            status = row.get('result_status')
            if 'result_status' not in row and collector_index < len(legacy):
                inv, rc, saved = legacy[collector_index]
                if (row['returncode'] == rc
                        and ('inv' not in row or row['inv'] == inv)):
                    status = saved
            collector_index += 1
            if not result_ok(row['returncode'], status):
                findings.append({'kind': 'audit_collector_classification',
                                 'returncode': row['returncode'], 'status': status})
        elif row['returncode'] != 0:
            findings.append({'kind': 'audit_failed_step', 'step': step,
                             'returncode': row['returncode']})
    return findings
