"""RA-1.1 oracle & safety regression tests (Gate A negatives + Gate B
adversarial detector tests). No database required; fast; deterministic.

Run: python oracle_tests.py
Exits non-zero on any failure. These tests gate the experiment suite
(run_all.py runs them first and stops on failure).
"""
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402

RESULTS = []


def check(name, cond, detail=''):
    RESULTS.append((name, bool(cond), detail))
    print(('PASS' if cond else 'FAIL'), name, detail)


def probes(seq, start=1000.0, step=100.0):
    return [{'t_ms': start + i * step, 'ok': ok} for i, ok in enumerate(seq)]


# ── Gate B adversarial detector tests ────────────────────────────────────────

# 1. Three failed probes followed by three successful probes MUST NOT be
#    classified as non-recovered.
r = lab.detect_wedge(probes([True] * 5 + [False] * 3 + [True] * 3),
                     process_alive=True, window=(1500.0, 2000.0),
                     latches_released=True)
check('detector: recovery after failures is not non-recovery',
      not r['non_recovery_observed'] and r['loop_oks_in_window'] == 3)

# 2. A dead process MUST NOT be classified as alive-but-wedged.
r = lab.detect_wedge(probes([True] * 3 + [False] * 6),
                     process_alive=False, window=(1300.0, 1900.0),
                     latches_released=True)
check('detector: dead process is never wedged', not r['non_recovery_observed'])

# 3. Two ordinary connection exceptions MUST NOT imply a wedge.
r = lab.detect_wedge(probes([True] * 3 + [False] * 2 + [True] * 0),
                     process_alive=True, window=(1300.0, 1500.0),
                     latches_released=True)
check('detector: two failures below threshold', not r['non_recovery_observed'])

# 4. Missing lock observations MUST NOT produce lock-causality CONFIRMED.
#    (detector reports progression only; assess_wedge reports
#    lock_causality_evidence_present — tested with real files below in the
#    fresh-evidence case: no pg_locks events -> False)
td = Path(tempfile.mkdtemp(prefix='ra11-oracle-'))
ev = lab.Evidence(td)
ev.event('probe', probe='loop', ok=True, ms=1.0)
for _ in range(4):
    ev.event('probe', probe='loop', ok=False, ms=5000.0)
t_end = (time.perf_counter() - ev.t0) * 1000 + 10
res = lab.assess_wedge(ev, proc=None, window_start_ms=0.0,
                       window_end_ms=t_end)
check('detector: missing lock observations -> no lock causality evidence',
      res['lock_causality_evidence_present'] is False)
check('detector: dead/missing proc (None) -> no non-recovery',
      res['non_recovery_observed'] is False)
ev.finish()

# 5. An injected latch that remains held MUST NOT prove self-sustaining
#    non-recovery.
r = lab.detect_wedge(probes([True] * 3 + [False] * 6),
                     process_alive=True, window=(1300.0, 1900.0),
                     latches_released=False)
check('detector: held latch invalidates self-sustaining claim',
      not r['non_recovery_observed'])

# 6. Positive sanity: healthy before, alive, >=3 consecutive fails in window,
#    no recovery, latches released -> non-recovery observed.
r = lab.detect_wedge(probes([True] * 3 + [False] * 5),
                     process_alive=True, window=(1300.0, 1800.0),
                     latches_released=True)
check('detector: genuine bounded non-recovery detected',
      r['non_recovery_observed'] is True)

# 7. Historical failures before the window never count (recovery between).
r = lab.detect_wedge(probes([False] * 10 + [True] * 3 + [True] * 3),
                     process_alive=True, window=(2300.0, 2600.0),
                     latches_released=True)
check('detector: pre-window failures do not count',
      not r['non_recovery_observed'])


# ── Gate A negative safety tests ─────────────────────────────────────────────

# 8. Historical run directory deletion is refused and nothing is deleted.
hist = lab.OUT_ROOT / 'final-20261012'
probe_file = hist / 'e1' / 'events.jsonl'
existed = probe_file.exists()
refused = False
try:
    lab.safe_rmtree(hist, lab.OUT_ROOT / 'oracle-negative-test')
except ValueError:
    refused = True
check('safety: historical run dir deletion refused', refused)
check('safety: historical evidence untouched',
      not existed or probe_file.exists())

# 9. Cluster creation inside a previous run's directory is refused.
refused = False
try:
    lab.DisposablePG(lab.OUT_ROOT / 'final-20261012' / 'e1' / 'pg',
                     db_tag='neg', run_dir=lab.OUT_ROOT / 'oracle-negative-test')
except ValueError:
    refused = True
check('safety: cluster outside current run refused', refused)

# 10. Evidence on an existing events.jsonl refuses append (isolation).
refused = False
try:
    lab.Evidence(td)  # td already has events.jsonl from test 4
except FileExistsError:
    refused = True
check('safety: second Evidence on same dir refused', refused)

# 11. Port ownership discriminates: a socket owned by THIS process must be
#     accepted for this PID and rejected for an unrelated PID tree.
import os as _os
own = socket.socket()
own.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
own.bind(('127.0.0.1', 8979))
own.listen(1)
foreign = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
time.sleep(0.5)
check('safety: own listener accepted for own pid',
      lab.verify_port_owner(8979, _os.getpid()) is True)
check('safety: own listener rejected for unrelated pid tree',
      lab.verify_port_owner(8979, foreign.pid) is False)
foreign.kill()
foreign.wait(timeout=10)
own.close()

# 12. Unbound port is not "owned".
check('safety: unbound port not owned', lab.verify_port_owner(8978, 1234) is False)

# 13. Watchdog expiration: fires, kills the whole owned tree incl. the
#     interpreter grandchild, and closes the application listener.
ev2 = lab.Evidence(td / 'watchdog')
child = subprocess.Popen(
    [lab.PY, '-c',
     "import socket,time;s=socket.socket();s.setsockopt(socket.SOL_SOCKET,"
     "socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',8977));s.listen(1);"
     "time.sleep(300)"])
wd = lab.Watchdog(child, 3.0, ev2)
time.sleep(6.0)
dead = child.poll() is not None
port_closed = not lab.wait_port(8977, timeout=2.0)
ev2.event('watchdog_test_done', fired=wd.fired, dead=dead,
          port_closed=port_closed)
ev2.finish()
check('safety: watchdog fired and killed owned tree', wd.fired and dead)
check('safety: application listener closed after watchdog', port_closed)

import shutil
shutil.rmtree(td, ignore_errors=True)

failed = [n for n, ok, _ in RESULTS if not ok]
print(f'\n{len(RESULTS) - len(failed)}/{len(RESULTS)} oracle/safety tests passed')
if failed:
    print('FAILED:', failed)
    sys.exit(1)
print('ALL ORACLE + SAFETY TESTS PASS')
