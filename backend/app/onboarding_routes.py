"""Admin-only setup endpoints and public one-time activation."""
import hashlib
import secrets
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, StrictInt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import get_db
from .domain import DomainError
from .models import Company, User, now_ms
from .security import current_user, require_admin
from .pilot_accounts import new_person, activate, display_name
from .onboarding import readiness, begin, complete
from .routes import mutate

router = APIRouter(prefix='/api')


def admin_company(db, actor):
    require_admin(actor)
    return db.scalar(select(Company).where(Company.id == actor.company_id).with_for_update())


class CompanyIn(BaseModel):
    name: str = Field(max_length=200)


class PersonIn(BaseModel):
    name: str = Field(max_length=120)
    email: str = Field(max_length=200)
    role: str
    position: str = Field(default='', max_length=120)
    capacity: StrictInt = 2


class ActivationIn(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    password: str = Field(min_length=6, max_length=72)
    weakConfirmed: bool = False


@router.get('/onboarding/readiness')
def get_readiness(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    require_admin(actor)
    return readiness(db, db.get(Company, actor.company_id))


@router.post('/onboarding/begin')
def start(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return mutate(db, actor, 'onboarding_begin', actor.company_id,
                  lambda: begin(admin_company(db, actor)))


@router.patch('/company')
def save_company(body: CompanyIn, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    def save():
        company = admin_company(db, actor)
        company.name = display_name(body.name, 200)
        begin(company)
    return mutate(db, actor, 'company_update', actor.company_id, save)


@router.post('/onboarding/complete')
def finish(actor: User = Depends(current_user), db: Session = Depends(get_db)):
    return mutate(db, actor, 'onboarding_complete', actor.company_id,
                  lambda: complete(db, admin_company(db, actor)))


@router.post('/users')
def create_person(body: PersonIn, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    token = None
    def create():
        nonlocal token
        company = admin_company(db, actor)
        try:
            _, token = new_person(db, company.id, **body.model_dump())
        except IntegrityError:
            raise DomainError('VALIDATION', 'Login unavailable') from None
        begin(company)
    state = mutate(db, actor, 'person_create', actor.company_id, create)
    return {'state': state, 'activationToken': token}


@router.post('/users/{user_id}/activation')
def reissue(user_id: str, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    token = None
    def issue():
        nonlocal token
        admin_company(db, actor)
        user = db.scalar(select(User).where(User.id == user_id, User.company_id == actor.company_id).with_for_update())
        if not user: raise DomainError('NOT_FOUND', 'Person not found')
        if not user.activation_hash: raise DomainError('BAD_STATE', 'Account is already active')
        token = secrets.token_urlsafe(32)
        user.activation_hash = hashlib.sha256(token.encode()).hexdigest()
        user.activation_expires_at = now_ms() + 86400000
    state = mutate(db, actor, 'activation_reissue', user_id, issue)
    return {'state': state, 'activationToken': token}


@router.post('/auth/activate')
def activate_account(body: ActivationIn, db: Session = Depends(get_db)):
    try:
        activate(db, body.token, body.password, body.weakConfirmed)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {'ok': True}


@router.get('/auth/password-policy')
def password_policy():
    from .password_policy import policy
    return policy()
