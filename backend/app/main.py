"""CVE backend entrypoint (M1).

Serves the JSON API under /api and, when the built frontend exists
(static dir), the React SPA for every other path — one deployable unit.

Schema ownership: Alembic (`alembic upgrade head` in the entrypoint).
Development mode may seed an empty database. Pilot startup never seeds;
the explicit provisioning CLI establishes its initial company and Admin.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text

from .capabilities.routes import router as capabilities_router
from .organization.routes import router as organization_router
from .config import settings
from .db import engine, session_scope
from .domain import DomainError
from .models import Company
from .routes import router
from .workspace_routes import router as workspace_router
from .onboarding_routes import router as onboarding_router
from .ingestion.routes import router as ingestion_router
from .rules.routes import router as rules_router
from .policies.routes import router as policies_router
from .approvals.routes import router as approvals_router
from .economic_effects.routes import router as economic_router
from .collaboration.routes import router as collaboration_router
from .github_connector.routes import router as github_router
from .slack_connector.routes import router as slack_router
from .notifications.approval_push import register as register_approval_push

# WS1: approvals publishes request creation; notifications pushes (approvals
# never imports notifications — dependency boundary is test-enforced).
register_approval_push()
from .shadow.routes import router as shadow_router
from .incentive_safety.routes import router as safety_router
from .provenance.routes import router as provenance_router
from .attention.routes import router as attention_router

STATIC_DIR = os.environ.get('CVE_STATIC_DIR') or str(
    Path(__file__).resolve().parents[2] / 'dist')

_ERROR_STATUS = {'EVENT_RECORDING_FAILED': 503, 'REVIEW_AUTHORITY_REQUIRED': 403, 'FORBIDDEN': 403, 'NOT_FOUND': 404, 'VALIDATION': 422,
                 'UPLOAD_REJECTED': 422, 'CAPACITY_REACHED': 409, 'BAD_STATE': 409,
                 'OUT_OF_STOCK': 409, 'INSUFFICIENT_FUNDS': 409,
                 'LIMIT_REACHED': 409, 'NO_CHANGE': 409}
_ERROR_STATUS.update(WEBHOOK_AUTH_FAILED=401, INGRESS_UNAVAILABLE=503,
                     INVALID_EVENT_ENVELOPE=422, INVALID_EVENT_TYPE=422,
                     NORMALIZATION_FAILED=422, PAYLOAD_TOO_LARGE=413,
                     UNSUPPORTED_EVENT_MEDIA=415)
_ERROR_STATUS.update(INVALID_RULE=422, INVALID_CONDITION=422, INVALID_OUTCOME=422,
                     RULE_NOT_FOUND=404, CANDIDATE_CONFLICT=409,
                     RULE_EVALUATION_LIMIT=409, RULES_UNAVAILABLE=503)
_ERROR_STATUS.update(INVALID_POLICY=422, INVALID_POLICY_CONDITION=422, INVALID_POLICY_DECISION=422,
                     POLICY_NOT_FOUND=404, POLICY_EVALUATION_CONFLICT=409,
                     POLICY_EVALUATION_LIMIT=409, POLICIES_UNAVAILABLE=503)
_ERROR_STATUS.update(APPROVAL_NOT_REQUIRED=409, APPROVAL_NOT_FOUND=404, APPROVAL_FORBIDDEN=403,
                     SELF_APPROVAL_FORBIDDEN=403, APPROVAL_ALREADY_DECIDED=409,
                     INVALID_APPROVAL_DECISION=422, INVALID_APPROVAL_FILTER=422,
                     APPROVER_INACTIVE=403, APPROVALS_UNAVAILABLE=503)
_ERROR_STATUS.update(ECONOMIC_EFFECT_NOT_ELIGIBLE=409, ECONOMIC_EFFECT_ALREADY_EXISTS=409,
                     ECONOMIC_BENEFICIARY_MISSING=422, ECONOMIC_AMOUNT_INVALID=422,
                     LEGACY_ECONOMIC_SOURCE=409, ECONOMIC_EFFECT_NOT_FOUND=404,
                     ECONOMIC_EFFECT_ALREADY_REVERSED=409, ECONOMIC_REVERSAL_FORBIDDEN=403,
                     ECONOMIC_ENGINE_UNAVAILABLE=503)
_ERROR_STATUS.update(COLLABORATION_UNAVAILABLE=503)
_ERROR_STATUS.update(SHADOW_UNAVAILABLE=503)
_ERROR_STATUS.update(SAFETY_UNAVAILABLE=503, CAPABILITY_DISABLED=409,
                     CAPABILITY_REQUIRED=409, CAPABILITIES_UNAVAILABLE=503)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.dev_mode:
        from .seed import seed_if_empty
        with session_scope() as db:
            seed_if_empty(db)
    elif len(settings.jwt_secret.encode()) < 32 or settings.jwt_secret == 'dev-only-insecure-secret-change-me':
        raise RuntimeError('Pilot requires an explicit strong CVE_JWT_SECRET (at least 32 bytes)')
    yield


app = FastAPI(title='CVE API', version='1.0.0', lifespan=lifespan)
app.include_router(capabilities_router)
app.include_router(organization_router)

app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list,
                   allow_methods=['*'], allow_headers=['*'])


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError):
    return JSONResponse(status_code=_ERROR_STATUS.get(exc.code, 409),
                        content={'code': exc.code, 'message': exc.message, **exc.details})


from .auth_routes import router as auth_router
from .integrity_routes import router as integrity_router
app.include_router(auth_router)
app.include_router(integrity_router)
app.include_router(router)
app.include_router(workspace_router)
app.include_router(onboarding_router)
app.include_router(ingestion_router)
app.include_router(rules_router)
app.include_router(policies_router)
app.include_router(approvals_router)
app.include_router(economic_router)
app.include_router(collaboration_router)
app.include_router(github_router)
app.include_router(slack_router)
app.include_router(shadow_router)
app.include_router(safety_router)
app.include_router(provenance_router)
app.include_router(attention_router)


@app.get('/api/health')
def health():
    with engine.connect() as conn:
        conn.execute(text('SELECT 1'))
    return {'ok': True}


if os.path.isdir(STATIC_DIR):
    @app.get('/activate', include_in_schema=False)
    def activation_page():
        return FileResponse(Path(STATIC_DIR) / 'index.html', headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})

    app.mount('/', StaticFiles(directory=STATIC_DIR, html=True), name='spa')
