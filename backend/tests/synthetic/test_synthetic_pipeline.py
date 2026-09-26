"""Small regular-CI gate; STANDARD is an explicit standalone command."""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
import sqlalchemy as sa
from .generator import Config, generate, dataset_digest, expected_rules, expected_policies, rule_specs
from .safety import guard


@pytest.mark.parametrize('url', [
    'postgresql://localhost/cve', 'postgresql://localhost/cve_test',
    'sqlite:///cve_synthetic_test', 'postgresql://localhost/cve_synthetic_test?options=-csearch_path=private',
])
def test_refuse_unsafe_database(url):
    with pytest.raises(ValueError):
        guard(url)


def test_generator_determinism_and_coverage():
    config = Config()
    events = generate(config)
    assert dataset_digest(config,events) == dataset_digest(replace(config,workers=1),generate(config))
    assert generate(replace(config,seed=config.seed+1)) != events
    assert len({e['payload']['logicalId'] for e in events}) == 10000
    assert sum(e['mode']=='raw' for e in events)==1000
    assert {c['op'] for r in rule_specs() for c in r['conditions']} == {'EQ','NEQ','GT','GTE','LT','LTE','IN','EXISTS'}
    decisions = set()
    match_counts = set()
    defaults = 0
    for event in events:
        rules = expected_rules(event)
        match_counts.add(len(rules))
        for index in rules:
            matches, decision = expected_policies(event,index)
            decisions.add(decision)
            defaults += not matches
    assert decisions == {'ALLOW','BLOCK','REQUIRE_APPROVAL','SHADOW_ONLY'}
    assert {0,1,2,3} <= match_counts and defaults > 0


def test_smoke_subprocess(tmp_path):
    # Parent conftest owns cve_test; the child is guarded before any app import.
    # Provision a second explicit disposable database, never reset the parent's DB.
    from app.db import engine
    url = os.environ.get('CVE_SYNTHETIC_DATABASE_URL')
    if not url:
        assert engine.url.database == 'cve_test', 'Explicit synthetic test URL required'
        admin = sa.create_engine(engine.url.set(database='postgres'), isolation_level='AUTOCOMMIT')
        with admin.connect() as conn:
            if not conn.scalar(sa.text("SELECT 1 FROM pg_database WHERE datname='cve_synthetic_test'")):
                conn.execute(sa.text('CREATE DATABASE cve_synthetic_test'))
        admin.dispose()
        # pgserver URLs use a host socket query; convert that to PGHOST for the
        # subprocess so the guard can reject arbitrary URL connection options.
        query = dict(engine.url.query)
        assert set(query) <= {'host'}
        url = engine.url.set(database='cve_synthetic_test', query={}).render_as_string(hide_password=False)
    else:
        query = {}
    guard(url)
    output = tmp_path/'smoke.json'
    env = dict(os.environ, CVE_SYNTHETIC_DATABASE_URL=url, PYTHONDONTWRITEBYTECODE='1')
    if query.get('host'):
        env['PGHOST'] = query['host']
    command = [sys.executable, '-m', 'tests.synthetic.runner', '--preset', 'smoke',
               '--workers', '1', '--output', str(output)]
    completed = subprocess.run(command, cwd=Path(__file__).resolve().parents[2], env=env,
                               capture_output=True, text=True, timeout=180)
    assert completed.returncode == 0, completed.stdout+completed.stderr
    result = json.loads(output.read_text())
    assert result['status'] == 'PASS' and result['database_rows']['canonical_events'] == 500
    assert result['provenance']['candidates'] == result['provenance']['decisions'] == 100
