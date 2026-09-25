"""Shared predicate safety plus Policy-only configuration validation."""
import ast
from pathlib import Path
import pytest
from app.domain import DomainError
from app.policies.validation import definition
from tests.policy_helpers import policy


@pytest.mark.parametrize('field', ['candidate.__class__', 'candidate.data.__proto__', 'event.payload.constructor',
    'event.payload.prototype', 'event.payload.__dict__', 'candidate.data.a.b.c.d', 'event.payload.x()',
    'candidate.data[0]', 'event.companyId', 'candidate.data', 'candidate.data.x/y'])
def test_policy_unsafe_paths(field):
    with pytest.raises(DomainError) as error:
        definition(policy(conditions=[dict(field=field, op='EQ', value=1)]))
    assert error.value.code == 'INVALID_POLICY_CONDITION'


@pytest.mark.parametrize('changes,code', [
    ({'decision': 'AUTO_APPROVE'}, 'INVALID_POLICY_DECISION'),
    ({'decision': []}, 'INVALID_POLICY_DECISION'),
    ({'active': 1}, 'INVALID_POLICY'), ({'priority': True}, 'INVALID_POLICY'),
    ({'candidateKind': 'ALERT'}, 'INVALID_POLICY'), ({'eventType': 'external.*'}, 'INVALID_POLICY'),
    ({'companyId': 'foreign'}, 'INVALID_POLICY'),
    ({'conditions': [dict(field='event.type', op='EXISTS', value=True)]*21}, 'INVALID_POLICY_CONDITION'),
    ({'conditions': [dict(field='event.type', op='EXEC', value='code')]}, 'INVALID_POLICY_CONDITION'),
    ({'conditions': [dict(field='event.type', op='IN', value=[1]*51)]}, 'INVALID_POLICY_CONDITION'),
    ({'conditions': [dict(field='event.payload.score', op='GT', value='10')]}, 'INVALID_POLICY_CONDITION'),
    ({'conditions': [dict(field='event.payload.score', op='EQ', value=float('inf'))]}, 'INVALID_POLICY_CONDITION'),
    ({'conditions': [dict(field='event.payload.score', op='EQ', value=10**13)]}, 'INVALID_POLICY_CONDITION'),
    ({'conditions': {'OR': []}}, 'INVALID_POLICY_CONDITION'),
])
def test_policy_invalid_definition(changes, code):
    with pytest.raises(DomainError) as error: definition(policy(**changes))
    assert error.value.code == code


@pytest.mark.parametrize('amount', [-0.5, 10000.5, 0.1+0.2, True, '20', None])
def test_policy_coin_thresholds_are_exact_and_bounded(amount):
    with pytest.raises(DomainError):
        definition(policy(conditions=[dict(field='candidate.data.proposedReward', op='GT', value=amount)]))


def test_policy_valid_limits():
    for amount in (0, 0.5, 10000):
        definition(policy(conditions=[dict(field='candidate.data.proposedReward', op='GTE', value=amount)]*20))
    definition(policy(conditions=[dict(field='event.payload.a.b.c', op='EXISTS', value=True)]))


def test_policy_dependency_boundaries():
    root = Path(__file__).parents[1]/'app'
    for path in root.rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            modules = ([node.module or ''] if isinstance(node, ast.ImportFrom) else
                       [n.name for n in node.names] if isinstance(node, ast.Import) else [])
            for module in modules:
                parts = set(module.split('.'))
                assert not {'golden', 'policy_golden', 'tests'} & parts, path
                if path.parent.name in ('rules', 'canonical_events', 'notifications', 'safe_predicates'):
                    assert 'policies' not in parts, path
                if path.parent.name == 'policies':
                    assert not parts & {'rule_services', 'task_services', 'reward_services', 'service_common',
                                        'notifications', 'requests', 'httpx', 'subprocess', 'importlib'}, path
                    assert module not in ('rules.evaluator', 'rules.service', 'rules.validation'), path
                if path.parent.name == 'safe_predicates':
                    assert not parts & {'rules', 'policies', 'canonical_events', 'sqlalchemy', 'models'}, path
            if path.parent.name in ('policies', 'safe_predicates') and isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in ('eval', 'exec', '__import__'), path
