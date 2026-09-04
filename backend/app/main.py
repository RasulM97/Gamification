"""CVE backend entrypoint (M1).

Serves the JSON API under /api and, when the built frontend exists
(static dir), the React SPA for every other path — one deployable unit.

Schema ownership: Alembic (`alembic upgrade head` in the entrypoint).
On a completely empty database the Aster Dynamics demo seed is inserted so
the product is immediately explorable; seeding never touches existing data.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text

from .config import settings
from .db import engine, session_scope
from .domain import DomainError
from .models import Company
from .routes import router

STATIC_DIR = os.environ.get('CVE_STATIC_DIR') or str(
    Path(__file__).resolve().parents[2] / 'dist')

_ERROR_STATUS = {'FORBIDDEN': 403, 'NOT_FOUND': 404, 'VALIDATION': 422,
                 'UPLOAD_REJECTED': 422, 'CAPACITY': 409, 'BAD_STATE': 409,
                 'OUT_OF_STOCK': 409, 'INSUFFICIENT_FUNDS': 409,
                 'NO_CHANGE': 409}


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .seed import seed_if_empty
    with session_scope() as db:
        seed_if_empty(db)
    yield


app = FastAPI(title='CVE API', version='1.0.0', lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list,
                   allow_methods=['*'], allow_headers=['*'])


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError):
    return JSONResponse(status_code=_ERROR_STATUS.get(exc.code, 409),
                        content={'code': exc.code, 'message': exc.message})


app.include_router(router)


@app.get('/api/health')
def health():
    with engine.connect() as conn:
        conn.execute(text('SELECT 1'))
    return {'ok': True}


if os.path.isdir(STATIC_DIR):
    app.mount('/', StaticFiles(directory=STATIC_DIR, html=True), name='spa')
