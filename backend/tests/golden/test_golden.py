"""One independently reset test per authored scenario and requested repetition."""
import ast
from pathlib import Path
import pytest
from .harness import check, load_scenarios, replay

SCENARIOS = load_scenarios()


@pytest.mark.parametrize('scenario', SCENARIOS, ids=lambda scenario: scenario['id'])
def test_golden(scenario, repetition, golden_db):
    replay(scenario, golden_db)


def test_dataset_contract_and_dependency_direction():
    assert 30 <= len(SCENARIOS) <= 50
    assert 5 <= sum(s['input']['kind'] == 'webhook' for s in SCENARIOS) <= 10
    assert {c['op'] for s in SCENARIOS for r in s['rules']
            for c in r['definition']['conditions'] if isinstance(c, dict)} >= {
                'EQ', 'NEQ', 'GT', 'GTE', 'LT', 'LTE', 'IN', 'EXISTS'}
    for scenario in SCENARIOS:
        assert {'canonical', 'matchedRules', 'nonMatchedRules', 'candidates', 'errors'} <= scenario['expected'].keys()
    for path in (Path(__file__).parents[2] / 'app').rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.ImportFrom):
                assert not {'golden', 'tests'} & set((node.module or '').split('.')), path
            elif isinstance(node, ast.Import):
                assert all(not {'golden', 'tests'} & set(n.name.split('.')) for n in node.names), path


def test_oracle_reports_typed_mismatch():
    check({'id': 'oracle'}, 'numeric representation', {'time': 10}, {'time': 10.0})
    with pytest.raises(pytest.fail.Exception, match='oracle :: candidates') as error:
        check({'id': 'oracle'}, 'candidates', [{'data': True}], [{'data': 1}])
    assert 'expected:' in str(error.value) and 'actual:' in str(error.value)
    with pytest.raises(pytest.fail.Exception):
        check({'id': 'oracle'}, 'order', ['rule-a', 'rule-b'], ['rule-b', 'rule-a'])
