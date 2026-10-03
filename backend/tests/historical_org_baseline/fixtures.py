"""Versioned data writers for schemas that predate optional scope columns.

Migration tests must seed the old schema with old-shaped records, not execute
new ORM columns against a database which deliberately has not been upgraded.
No SQL statements, results, constraints or migration operations are intercepted.
After upgrade, these adapters delegate to the current production services.
"""
import sys
from functools import wraps
import sqlalchemy as sa
from sqlalchemy.orm import registry
from app.models import Task
from app.rules.model import Rule
from app.policies.model import Policy
from app.domain import DomainError
from . import rules, policies


def install(monkeypatch):
    from app.rules import service as rule_service
    from app.policies import service as policy_service
    from app.approvals import authorization
    from app.organization import service as organization
    from app import seed
    mapped={}

    def modern(db):
        return 'teams' in sa.inspect(db.connection()).get_table_names()

    def historical_model(db,current):
        key=(str(db.bind.url),current.__tablename__)
        if key not in mapped:
            table=sa.Table(current.__tablename__,sa.MetaData(),autoload_with=db.connection())
            for column in table.columns:
                old=current.__table__.columns[column.name]
                if old.default is not None:column.default=old.default
            cls=type('Historical'+current.__name__,(),{})
            mapping=registry();mapping.map_imperatively(cls,table)
            mapped[key]=(cls,mapping)
        return mapped[key][0]

    replacements={}
    for current_module,frozen,current_model,names in (
        (rule_service,rules,Rule,('create_rule','evaluate_event')),
        (policy_service,policies,Policy,('create_policy','evaluate_candidate'))):
        for name in names:
            original=getattr(current_module,name)
            def build(original=original,frozen=frozen,current_model=current_model,name=name):
                @wraps(original)
                def call(db,*args,**kwargs):
                    if modern(db):return original(db,*args,**kwargs)
                    setattr(frozen,current_model.__name__,historical_model(db,current_model))
                    return getattr(frozen,name)(db,*args,**kwargs)
                return call
            replacements[original]=build()

    original_seed=seed.run
    def seed_old(db):
        if modern(db):return original_seed(db)
        previous=seed.Task
        try:
            old_task=historical_model(db,Task)
            def insert_task(**values):
                # Separate historical mapper registries have no ORM dependency
                # ordering with current child models. Persist parents explicitly.
                db.flush()
                row=old_task(**values)
                db.add(row)
                db.flush([row])
                return row
            seed.Task=insert_task
            return original_seed(db)
        finally:seed.Task=previous
    replacements[original_seed]=seed_old

    original_scope=organization.event_scope
    def historical_scope(db,*args):
        return original_scope(db,*args) if modern(db) else {'kind':'COMPANY'}
    replacements[original_scope]=historical_scope
    original_authority=authorization.require_authority
    def historical_authority(db,actor,request):
        if modern(db):return original_authority(db,actor,request)
        if actor.role!='ADMIN' and request.required_authority!='MANAGER_OR_ADMIN':
            raise DomainError('APPROVAL_FORBIDDEN','Required approval authority not held')
    replacements[original_authority]=historical_authority

    # Update imported aliases in collected migration fixtures as well as modules.
    for module in list(sys.modules.values()):
        if not getattr(module,'__name__','').startswith(('app.','tests.','test_')):continue
        if '.historical_org_baseline' in module.__name__:continue
        for name,value in list(vars(module).items()):
            if callable(value) and any(value is original for original in replacements):
                monkeypatch.setattr(module,name,replacements[value])
