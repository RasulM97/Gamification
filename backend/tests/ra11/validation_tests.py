"""Focused Stage 1 adversarial tests. No database, gates or experiments.

Run directly, or import run_tests(check) from the lightweight regression gate.
All E4 mutations start with a passing, complete reference; failed check names
are part of the assertions. These are current-contract tests, not emulations
of an older verifier signature.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import e4_lock_order as e4
import run_all as run
import lab


def traces():
    def adv(shared, key):
        suffix = '_shared' if shared else ''
        return (f'SELECT pg_advisory_xact_lock{suffix}'
                '(hashtextextended(%(key)s,0))', {'key': key})

    def row(table, identity, clause):
        return (f'SELECT {table}.id FROM {table} WHERE '
                f'{table}.company_id = %(company_id_1)s AND '
                f'{table}.id = %(id_1)s FOR {clause}',
                {'company_id_1': 'co-aster', 'id_1': identity})

    org = adv(False, 'cve-organization:co-aster')
    cap = adv(True, 'cve-capability:co-aster:TASK_LITE')
    shared = adv(True, 'cve-organization:co-aster')
    task = row('tasks', 't-e4-000', 'UPDATE')
    user = row('users', 'u-priya', 'SHARE')
    nku = row('users', 'u-priya', 'NO KEY UPDATE')

    def trace(pairs):
        return {'stmts': [s for s, _ in pairs],
                'params': [dict(p) for _, p in pairs],
                'conns': [11] * len(pairs), 'pids': [4242] * len(pairs),
                'tx_events': [{'event': 'begin', 'conn': 11, 'seq': 0},
                              {'event': 'rollback', 'conn': 11,
                               'seq': len(pairs)}], 'error': None}

    return dict(real=trace([org, cap, task, shared, user, shared, user, nku]),
                model=trace([org, cap, task, user, nku]),
                company_trace=trace([org, cap, task, shared, nku]))


KW = dict(actor_id='u-priya', company='co-aster',
          real_task_id='t-e4-000', model_task_id='t-e4-000',
          company_task_id='t-e4-000')


def verify(ts):
    return e4.verify_claim_capture(**ts, reductions=e4.CLAIM_SQL_REDUCTIONS,
                                   **KW)


def run_e4_tests(check):
    def mutation(name, edit, intended):
        reference = traces()
        check(name + ' reference', verify(reference)['equivalent'])
        changed = copy.deepcopy(reference)
        edit(changed)
        try:
            report = verify(changed)
            failed = {c['check'] for c in report['checks'] if not c['ok']}
            ok = report['equivalent'] is False and intended in failed
            # The rejection cannot be attributed to missing task identities.
            unrelated = {'real_task_bind', 'model_task_bind',
                         'company_task_bind'} - {intended}
            if intended == 'model_exact_order':
                unrelated.discard('model_task_bind')  # changed Task lock mode
            ok = ok and not (failed & unrelated)
            check(name, ok, 'failed checks=' + repr(sorted(failed)))
        except Exception as exc:
            check(name, False, 'uncontrolled exception: ' + repr(exc))

    def param(tag, index, key, value):
        return lambda ts: ts[tag]['params'][index].__setitem__(key, value)

    mutation('R25b model bind missing',
             lambda ts: ts['model']['params'][0].pop('key'),
             'model_advisory_x_org_key')
    mutation('R25c wrong capability',
             param('real', 1, 'key', 'cve-capability:co-aster:TASK_HEAVY'),
             'real_capability_shared_key')
    mutation('R25d wrong company predicate bind',
             param('real', 4, 'company_id_1', 'u-priya'),
             'matched_for_share_actor')
    mutation('R25e wrong NKU user', param('real', 7, 'id_1', 'u-marcus'),
             'real_nku_bind')
    mutation('R25f mixed connection',
             lambda ts: ts['real']['conns'].__setitem__(4, 12),
             'real_tx_identity')
    mutation('R25g commit between locks',
             lambda ts: ts['real']['tx_events'][-1].update(
                 event='commit', seq=4), 'real_tx_identity')
    mutation('R25h wrong task lock mode',
             lambda ts: ts['model']['stmts'].__setitem__(
                 2, ts['model']['stmts'][2].replace('FOR UPDATE', 'FOR SHARE')),
             'model_exact_order')
    for tag, index, expected in [('real', 0, 'real_advisory_x_org_key'),
                                  ('model', 1, 'model_capability_shared_key'),
                                  ('real', 3, 'reduction_identity')]:
        for seed in ('1', '', ':seed', '%(seed)s', '0)+1'):
            mutation(f'R27 {tag}/{index} seed {seed!r}',
                     lambda ts, t=tag, i=index, s=seed:
                     ts[t]['stmts'].__setitem__(i,
                         ts[t]['stmts'][i].replace(',0)', ',' + s + ')')),
                     expected)
    for field, value in [('seq', None), ('seq', '4'), ('seq', True),
                          ('seq', -1), ('seq', 999), ('conn', None),
                          ('conn', []), ('conn', ''), ('event', 'save')]:
        mutation(f'R27 malformed tx {field}={value!r}',
                 lambda ts, f=field, v=value:
                 ts['real']['tx_events'][-1].__setitem__(f, v),
                 'real_tx_identity')
    for field in ('seq', 'conn', 'event'):
        mutation('R27 missing tx ' + field,
                 lambda ts, f=field: ts['real']['tx_events'][-1].pop(f),
                 'real_tx_identity')
    mutation('R27 duplicate begin',
             lambda ts: ts['real']['tx_events'].insert(
                 1, {'event': 'begin', 'conn': 11, 'seq': 3}),
             'real_tx_identity')
    mutation('R27 unordered events',
             lambda ts: ts['real']['tx_events'].reverse(), 'real_tx_identity')
    mutation('R27 no begin',
             lambda ts: ts['real']['tx_events'].pop(0), 'real_tx_identity')
    mutation('R27 nonobject event',
             lambda ts: ts['real']['tx_events'].append(None),
             'real_tx_identity')
    mutation('R27 mixed backend',
             lambda ts: ts['real']['pids'].__setitem__(4, 4243),
             'real_tx_identity')
    check('R27 terminal rollback allowed', verify(traces())['equivalent'])
    named = traces()
    for tr in named.values():
        tr['stmts'] = [s.replace('%(key)s', ':key') for s in tr['stmts']]
    check('R27 canonical named advisory bind allowed', verify(named)['equivalent'])
    # Complete, well-formed transaction break, unlike a malformed event.
    split = traces()
    check('R27 split transaction reference', verify(split)['equivalent'])
    split['real']['tx_events'][1:1] = [
        {'event': 'commit', 'conn': 11, 'seq': 4},
        {'event': 'begin', 'conn': 11, 'seq': 4}]
    report = verify(split)
    check('R27 two transactions rejected', not report['equivalent'] and any(
        c['check'] == 'real_tx_identity' and not c['ok'] for c in report['checks']))


def clean_history(status='PARTIAL'):
    rc = 3 if status == 'PARTIAL' else 0
    return [{'j': 'invocation_started', 'inv': 'i1', 'rid': 'fixture'},
            {'j': 'step_started', 'inv': 'i1', 'step': '_results.py'},
            {'j': 'step_completed', 'inv': 'i1', 'step': '_results.py',
             'returncode': rc, 'result_status': status},
            {'j': 'invocation_completed', 'inv': 'i1', 'status': status,
             'coll_rc': rc}]


def run_history_tests(check):
    with tempfile.TemporaryDirectory(prefix='ra11-contract-') as tmp:
        directory = Path(tmp)
        audit = directory / 'run_all_log.json'

        def audit_findings(records):
            audit.write_text(''.join(json.dumps(r) + '\n' for r in records),
                             encoding='utf-8')
            return run.audit_failures(directory)

        def rejects(name, fn):
            try:
                findings = fn()
                check(name, bool(findings), repr(findings)[:220])
            except Exception as exc:
                check(name, False, 'uncontrolled exception: ' + repr(exc))

        for record in ({}, None, [], 2, 'bad', {'step': 'smoke.py'},
                       {'step': '_results.py', 'returncode': 1},
                       {'step': '_results.py', 'returncode': 0},
                       {'step': '_results.py', 'returncode': 3,
                        'result_status': 'COMPLETE'},
                       {'step': 'unknown', 'returncode': 0}):
            rejects('R28 audit ' + repr(record),
                    lambda r=record: audit_findings([r]))
        for record in ({}, None, [], 2, 'bad'):
            rejects('R28 journal ' + repr(record),
                    lambda r=record: run.journal_failures([r]))
        for status in (None, '', 'PASS', [], 0):
            rows = clean_history()
            rows[-1]['status'] = status
            rejects('R28 invalid completion status ' + repr(status),
                    lambda r=rows: run.journal_failures(r))
        cases = {}
        rows = clean_history(); del rows[-1]['status']
        cases['missing status'] = rows
        rows = clean_history(); del rows[2]['returncode']
        cases['missing returncode'] = rows
        rows = clean_history(); rows[2]['returncode'] = 1
        cases['collector failed'] = rows
        rows = clean_history(); rows[-1]['status'] = 'COMPLETE'
        cases['contradictory status'] = rows
        rows = clean_history(); rows.insert(2, dict(rows[1]))
        cases['duplicate step start'] = rows
        rows = clean_history(); rows.insert(3, dict(rows[2]))
        cases['duplicate step completion'] = rows
        rows = clean_history(); rows.pop(1)
        cases['orphan completion'] = rows
        rows = clean_history(); rows[2]['inv'] = 'other'
        cases['wrong invocation'] = rows
        rows = clean_history(); rows.insert(3, {'j': 'step_started',
                     'inv': 'i1', 'step': 'smoke.py'})
        cases['completion with open step'] = rows
        for name, rows in cases.items():
            rejects('R28 ' + name, lambda r=rows: run.journal_failures(r))
        check('R28 clean PARTIAL history', not run.journal_failures(clean_history()))
        check('R28 clean COMPLETE history',
              not run.journal_failures(clean_history('COMPLETE')))
        legacy = clean_history()
        del legacy[2]['result_status']
        check('R28 legacy completion classification recoverable',
              not run.journal_failures(legacy))
        (directory / 'journal.jsonl').write_text(
            ''.join(json.dumps(r) + '\n' for r in legacy), encoding='utf-8')
        check('R28 legacy audit collector agrees with journal',
              not audit_findings([{'step': '_results.py', 'returncode': 3}]))
        rejects('R28 audit contradicts journal', lambda: audit_findings([
            {'step': '_results.py', 'inv': 'i1', 'returncode': 0,
             'result_status': 'COMPLETE'}]))
        for step in ('halt', 'refused', 'run_failed'):
            rejects('R28 legacy ' + step,
                    lambda s=step: audit_findings([{'step': s}]))
        check('R28 legacy gate success', not audit_findings(
            [{'step': 'smoke.py', 'returncode': 0}]))

    # Real collector process over synthetic evidence: never calls a gate/DB.
    import uuid
    rid = 'reg-contract-' + uuid.uuid4().hex[:10]
    directory = lab.OUT_ROOT / rid
    try:
        (directory / 'e7').mkdir(parents=True)
        (directory / 'e7' / 'events.jsonl').write_text(json.dumps({
            'kind': 'classification', 'experiment': 'e7',
            'harness_validity': 'VALID', 'product_observation': 'EXPECTED_BEHAVIOR',
            'causal_claim': 'SUPPORTED', 'rationale': 'synthetic'}) + '\n',
            encoding='utf-8')
        (directory / 'journal.jsonl').write_text('', encoding='utf-8')
        for record in ({}, None, {'step': '_results.py', 'returncode': 1}):
            (directory / 'run_all_log.json').write_text(
                json.dumps(record) + '\n', encoding='utf-8')
            result = subprocess.run([sys.executable,
                str(Path(__file__).with_name('_results.py')), rid, '--expect=e7'],
                capture_output=True, text=True)
            path = directory / 'results.json'
            out = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            check('R28 collector controlled FAILED ' + repr(record),
                  result.returncode == 1 and out.get('run_status') == 'FAILED'
                  and 'Traceback' not in result.stderr, result.stderr[-180:])
        (directory / 'run_all_log.json').write_text('', encoding='utf-8')
        (directory / 'e7' / 'events.jsonl').write_text(json.dumps({
            'kind': 'classification', 'experiment': 'e7'}) + '\n', encoding='utf-8')
        result = subprocess.run([sys.executable,
            str(Path(__file__).with_name('_results.py')), rid, '--expect=e7'],
            capture_output=True, text=True)
        out = json.loads((directory / 'results.json').read_text(encoding='utf-8'))
        check('R28 incomplete experiment verdict cannot collect COMPLETE',
              result.returncode == 1 and out.get('run_status') == 'FAILED')
    finally:
        if directory.exists():
            for child in directory.iterdir():
                if child.is_dir():
                    lab.safe_rmtree(child, directory)
                else:
                    child.unlink()
            directory.rmdir()


def run_collection_tests(check):
    """Exercise the real collector/artifact handshake with synthetic steps.

    No gate or experiment script is run. The production orchestration code
    receives fake steps; only _results.py runs as a subprocess.
    """
    import uuid
    saved = {k: os.environ.get(k) for k in ('RA11_INVOCATION', 'RA11_ORCHESTRATED')}
    rid = 'reg-handshake-' + uuid.uuid4().hex[:10]
    directory = lab.OUT_ROOT / rid

    def synthetic(script, rid, timeout=900):
        if script == '_results.py':
            return run.run_step(script, rid, timeout=timeout)
        name = next((k for k, v in run.EXPERIMENTS.items() if v == script),
                    Path(script).stem)
        if script == 'oracle_tests.py':
            name = 'oracle'
        target = lab.OUT_ROOT / rid / name
        target.mkdir(parents=True, exist_ok=True)
        (target / 'events.jsonl').write_text(json.dumps({
            'kind': 'classification', 'experiment': name,
            'harness_validity': 'VALID', 'product_observation': 'EXPECTED_BEHAVIOR',
            'causal_claim': 'SUPPORTED', 'rationale': 'synthetic step'}) + '\n',
            encoding='utf-8')
        return {'returncode': 0, 'seconds': 0, 'tail': 'synthetic step'}

    try:
        first = run.execute(rid, ['e7'], run_step_fn=synthetic)
        data = json.loads((directory / 'results.json').read_text(encoding='utf-8'))
        check('R29 real collector clean PARTIAL', first['coll_rc'] == 3
              and data['run_status'] == 'PARTIAL')
        second = run.execute(rid, [n for n in run.EXPERIMENTS if n != 'e7'],
                             run_step_fn=synthetic, reuse_gates=True)
        data = json.loads((directory / 'results.json').read_text(encoding='utf-8'))
        check('R29 real collector continuation COMPLETE', not second['refused']
              and second['coll_rc'] == 0 and data['run_status'] == 'COMPLETE')

        # Failures in historical audit must survive three attempted reuses,
        # regardless of the journal appended by each refusal.
        with (directory / 'run_all_log.json').open('a', encoding='utf-8') as f:
            f.write('null\n')
        called = []

        def forbidden(*args, **kwargs):
            called.append(args)
            raise AssertionError('corrupt history started a step')

        for i in range(3):
            try:
                result = run.execute(rid, ['e7'], run_step_fn=forbidden,
                                     reuse_gates=True)
                check(f'R29 permanent refusal {i + 1}', result['refused'] and not called)
            except Exception as exc:
                check(f'R29 permanent refusal {i + 1}', False, repr(exc))

        # Fresh artifact checks, separate from old-versus-new behavior when
        # the old base does not expose the helper yet.
        validator = getattr(run, 'collected_status', None)
        if validator is not None:
            path = directory / 'validation-result.json'
            inv = data['invocation']
            for label, edit in [
                ('stale invocation', lambda d: d.update(invocation='old')),
                ('wrong status', lambda d: d.update(run_status='PARTIAL')),
                ('missing inventory', lambda d: d.pop('expected_inventory')),
                ('missing rollup', lambda d: d.pop('rollup')),
                ('contradictory missing', lambda d: d['rollup'].update(missing=['e7'])),
                ('invalid classification', lambda d: d['experiments']['e7'].update(
                    harness_validity='INVALID')),
            ]:
                path.write_text(json.dumps(data), encoding='utf-8')
                check('R29 artifact reference ' + label,
                      validator(path, rid, inv, 0) == 'COMPLETE')
                changed = copy.deepcopy(data)
                edit(changed)
                path.write_text(json.dumps(changed), encoding='utf-8')
                check('R29 artifact rejects ' + label,
                      validator(path, rid, inv, 0) is None)
            for raw in ('null', '{}', '{'):
                path.write_text(raw, encoding='utf-8')
                check('R29 malformed artifact ' + raw,
                      validator(path, rid, inv, 0) is None)
    finally:
        for k, value in saved.items():
            if value is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = value
        if directory.exists():
            for child in directory.iterdir():
                if child.is_dir():
                    lab.safe_rmtree(child, directory)
                else:
                    child.unlink()
            directory.rmdir()


def run_tests(check):
    run_e4_tests(check)
    run_history_tests(check)
    run_collection_tests(check)


if __name__ == '__main__':
    outcomes = []

    def check(name, ok, detail=''):
        outcomes.append(bool(ok))
        print('PASS' if ok else 'FAIL', name, detail)

    run_tests(check)
    print(f'{sum(outcomes)}/{len(outcomes)} focused checks passed')
    sys.exit(0 if all(outcomes) else 1)
