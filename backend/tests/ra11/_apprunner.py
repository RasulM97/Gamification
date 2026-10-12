"""RA-1.1 app launcher: runs the real app under uvicorn with workers=1 and
attaches test-only SQLAlchemy pool listeners that append checkout/checkin
events as JSON lines to RA11_POOL_LOG (Gate 2: actual connection
checkout/checkin events from inside the app process, labeled test-only).

Launched ONLY by lab.spawn_app. Never used in production paths. Environment
(CVE_*) is provided by lab.app_env before this process starts.
"""
import json
import os
import sys
import threading
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

_T0 = time.perf_counter()
_LOG_PATH = os.environ.get('RA11_POOL_LOG')
_LOCK = threading.Lock()


def _pool_log(event: str, conn_id: int):
    if not _LOG_PATH:
        return
    try:
        with _LOCK:
            with open(_LOG_PATH, 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    't_ms': round((time.perf_counter() - _T0) * 1000, 2),
                    # shared wall-clock reference so pool events can be
                    # correlated with harness events (which carry t_epoch)
                    't_epoch': round(time.time(), 4),
                    'event': event, 'conn': conn_id,
                    'pid': os.getpid(), 'thread': threading.get_ident(),
                }) + '\n')
    except Exception:
        pass


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, required=True)
    ap.add_argument('--log-level', default='warning')
    args = ap.parse_args()

    # worker configuration is fixed here; no inherited WEB_CONCURRENCY can
    # change it (lab.app_env also strips those variables).
    import app.db as app_db  # noqa: env already set by the harness
    from sqlalchemy import event

    @event.listens_for(app_db.engine, 'checkout')
    def _co(dbapi_conn, conn_rec, conn_proxy):
        _pool_log('checkout', id(dbapi_conn))

    @event.listens_for(app_db.engine, 'checkin')
    def _ci(dbapi_conn, conn_rec):
        _pool_log('checkin', id(dbapi_conn))

    @event.listens_for(app_db.engine, 'invalidate')
    def _inv(dbapi_conn, conn_rec, exception):
        _pool_log('invalidate', id(dbapi_conn))

    _pool_log('pool_listeners_attached', 0)

    import uvicorn
    from app.main import app
    config = uvicorn.Config(app, host=args.host, port=args.port,
                            log_level=args.log_level, workers=1)
    server = uvicorn.Server(config)
    server.run()


if __name__ == '__main__':
    main()
