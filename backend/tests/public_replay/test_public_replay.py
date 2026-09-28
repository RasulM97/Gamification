"""Offline contract gates; network acquisition is never part of pytest."""
import ast
from copy import deepcopy
from datetime import datetime
import hashlib
from pathlib import Path
import pytest
from .corpus import load, Sanitizer, family
from .mapping import envelope, frozen, expected, TYPES
from .safety import guard
from app.ingestion.contracts import RawEvent
from app.ingestion.normalizers import GenericWebhookNormalizer


def test_frozen_corpus_offline_normalization_and_mapping():
    records,manifest=load()
    assert manifest['recordsSelected']==1100
    assert set(TYPES)=={r['family'] for r in records}
    canonical=frozen()
    assert len(canonical)==len(records)
    for record in records:
        body=envelope(record)
        assert canonical[record['sourceRecordRef']]==body
        normalized=GenericWebhookNormalizer('test-source').normalize(RawEvent(
            body['eventType'],body['occurredAt'],body['payload'],body['evidence'],body['sourceEventId']))
        assert normalized.subject_id is None and normalized.actor_id is None
        assert normalized.payload==body['payload'] and normalized.type==body['eventType']
        assert expected(record)[0]>=0


def test_sanitizer_keeps_shape_and_drops_personal_content():
    clean=Sanitizer().clean(dict(user=dict(id=23,login='Person',email='person@example.org'),
        body='private text',state='APPROVED',mergeable=None,labels=[],url='https://example.org/person'))
    assert clean['user']['id']==1 and clean['user']['login'].startswith('ext_')
    assert 'email' not in clean['user'] and clean['state']=='APPROVED'
    assert clean['mergeable'] is None and clean['labels']==[]
    assert clean['url'].startswith('https://public-replay.invalid/')
    assert 'private text' not in clean['body']


def test_review_api_created_is_not_webhook_submitted_assumption():
    for action in ('created','submitted'):
        assert family(dict(type='PullRequestReviewEvent',payload=dict(action=action,
            review=dict(submitted_at='2025-01-15T12:00:00Z'))))=='review'
    assert family(dict(type='PullRequestReviewEvent',payload=dict(action='created',review={}))) is None


@pytest.mark.parametrize('url',[
    'postgresql://localhost/cve','postgresql://cve-e71-db/cve_test',
    'postgresql://production/cve_public_replay_test','sqlite:///cve_public_replay_test',
    'postgresql://cve-e71-db/cve_public_replay_test?options=-csearch_path=private'])
def test_disposable_database_guard(url):
    with pytest.raises(ValueError): guard(url)


def test_no_production_replay_imports():
    for path in (Path(__file__).parents[2]/'app').rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node,ast.ImportFrom): assert 'public_replay' not in (node.module or '')
            if isinstance(node,ast.Import): assert all('public_replay' not in n.name for n in node.names)


def test_timestamp_equivalent_offsets_are_test_perturbations():
    # These formats are explicitly synthetic variations, not claimed archive specimens.
    samples=['2025-01-15T12:00:00.123+00:00','2025-01-15T13:00:00.123+01:00']
    values=[int(datetime.fromisoformat(v).timestamp()*1000) for v in samples]
    assert values[0]==values[1]
    raw=RawEvent('external.repository.merged',values[0],{},source_event_id='offset-probe')
    assert GenericWebhookNormalizer('source').normalize(raw).occurred_at==values[0]


def test_adapter_ignores_extra_fields_and_handles_null_actor_probe():
    records,_=load()
    record=deepcopy(next(r for r in records if r['family']=='merged'))
    before=envelope(record)
    record['specimen']['payload']['unknownProviderExtension']={'largeText':'x'*40000}
    assert envelope(record)==before  # No unbounded provider payload forwarding.
    record['specimen']['actor']=None
    after=envelope(record)
    assert after['payload']['actor']=={'type':None,'present':False}
    normalized=GenericWebhookNormalizer('test-source').normalize(RawEvent(
        after['eventType'],after['occurredAt'],after['payload'],after['evidence'],after['sourceEventId']))
    assert normalized.actor_id is None
