"""Focused listener-ownership reproduction (P2).

The independent reviewer observed 27/28 oracle passes with the
listener-ownership test failing in their environment; this machine passes
28/28. This probe is the focused reproduction: it binds an ephemeral
loopback listener, runs lab.verify_port_owner for the owning PID and for a
foreign PID, and dumps the complete environment diagnostic so the failure
can be classified:

  - own_accepted=False with socket_visible=False or error set
      -> ENVIRONMENTAL: psutil.net_connections cannot enumerate socket
         ownership in this environment (platform/permission limitation).
         verify_port_owner fails CLOSED in that case (returns False), so
         false ownership ACCEPTANCE remains impossible — the failure mode
         is a false rejection, never a false acceptance.
  - own_accepted=False with owners=[<a different pid>]
      -> REAL DEFECT: the socket is visibly owned by another process and
         the ownership check is broken. Report the JSON.
  - foreign_rejected=False
      -> REAL DEFECT (false acceptance) — the most serious outcome;
         report the JSON.

Usage:  python _listener_probe.py   (from anywhere; exits 0 when the
ownership oracle behaves correctly in this environment, 1 otherwise)
"""
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lab  # noqa: E402


def main():
    # bind an ephemeral loopback port (no fixed port -> no collision risk)
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('127.0.0.1', 0))
    s.listen(1)
    port = s.getsockname()[1]
    foreign = subprocess.Popen([sys.executable, '-c',
                                'import time; time.sleep(30)'])
    time.sleep(0.5)
    import os
    try:
        own_pid = os.getpid()
        own_ok = lab.verify_port_owner(port, own_pid)
        foreign_ok = lab.verify_port_owner(port, foreign.pid)
        report = {
            'port': port,
            'own_pid': own_pid,
            'foreign_pid': foreign.pid,
            'own_accepted': own_ok,
            'foreign_rejected': not foreign_ok,
            'debug_own': lab.port_owner_debug(port, own_pid),
            'debug_foreign': lab.port_owner_debug(port, foreign.pid),
        }
        if own_ok and not foreign_ok:
            report['verdict'] = 'ORACLE CORRECT in this environment'
        elif not own_ok and not report['debug_own']['socket_visible']:
            report['verdict'] = ('ENVIRONMENTAL: socket ownership not '
                                 'enumerable here; the oracle fails CLOSED '
                                 '(false rejection, never false '
                                 'acceptance)')
        elif not own_ok:
            report['verdict'] = ('REAL DEFECT: owning socket visible but '
                                 'rejected — report this JSON')
        else:
            report['verdict'] = ('REAL DEFECT: FALSE ACCEPTANCE of a '
                                 'foreign pid — report this JSON')
        print(json.dumps(report, indent=2))
        sys.exit(0 if report['verdict'] == 'ORACLE CORRECT in this '
                 'environment' else 1)
    finally:
        foreign.kill()
        foreign.wait(timeout=10)
        s.close()


if __name__ == '__main__':
    main()
