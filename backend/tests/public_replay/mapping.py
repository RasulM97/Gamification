"""Provider-specific test mapping; identities are already pseudonymized."""
from datetime import datetime
from functools import lru_cache
import json
import hashlib
from pathlib import Path

TYPES = dict(merged='external.repository.merged', closed='external.pull_request.closed',
             review='external.review.submitted', issue_closed='external.issue.closed',
             issue_reopened='external.issue.reopened', push='external.repository.pushed')


def envelope(record):
    specimen = record['specimen']
    raw = specimen['payload']
    obj = raw.get('pull_request') or raw.get('issue') or raw.get('review') or {}
    payload = dict(family=record['family'], action=raw.get('action'),
        repository=dict(id=(specimen.get('repo') or {}).get('id')),
        actor=dict(type=(specimen.get('actor') or {}).get('type'),
                   present=specimen.get('actor') is not None),
        state=obj.get('state'), merged=obj.get('merged'),
        labels=[dict(id=v.get('id')) for v in obj.get('labels') or []],
        hasLabels=bool(obj.get('labels')), draft=obj.get('draft'),
        commitsCount=raw.get('size', obj.get('commits')),
        reviewState=(raw.get('review') or {}).get('state'),
        hasEvidence=True)
    return dict(eventType=TYPES[record['family']], sourceEventId=str(specimen['id']),
        occurredAt=int(datetime.fromisoformat(specimen['created_at'].replace('Z', '+00:00')).timestamp()*1000),
        payload=payload, evidence=[dict(kind='public-replay', reference=record['sourceRecordRef'])])


def canonical(record, source_id, subject_id=None):
    # Frozen, pre-normalized mapping is independently consumable; no normalizer call.
    from app.canonical_events.contracts import EventInput
    body = frozen()[record['sourceRecordRef']]
    return EventInput(type=body['eventType'], schema_version=1, source_kind='GENERIC_WEBHOOK',
        source_id=source_id, source_event_id=body['sourceEventId'], subject_id=subject_id,
        occurred_at=body['occurredAt'], payload=body['payload'], evidence=body['evidence'])


@lru_cache(maxsize=1)
def frozen():
    path=Path(__file__).parent/'mappings/canonical-v1.jsonl'
    return {row['sourceRecordRef']:row['envelope'] for row in
            (json.loads(line) for line in path.read_text(encoding='utf-8').splitlines())}


def freeze():
    from .corpus import load, encode
    records,_=load()
    path=Path(__file__).parent/'mappings/canonical-v1.jsonl'
    if path.exists(): raise SystemExit('Frozen canonical mapping already exists')
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(b''.join(encode(dict(sourceRecordRef=r['sourceRecordRef'],envelope=envelope(r)))+b'\n' for r in records))
    manifest_path=Path(__file__).parent/'manifests/corpus-v1.json'
    manifest=json.loads(manifest_path.read_text())
    manifest['canonicalFixtureSha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')


def rules():
    specs = []
    for family, kind in TYPES.items():
        if family == 'push': continue  # A real, intentional zero-match family.
        specs.append(dict(name='Replay '+family, active=True, eventType=kind, priority=0,
            conditions=[dict(field='payload.hasEvidence', op='EQ', value=True)],
            outcome=dict(kind='INCENTIVE', data=dict(proposedReward=10 if family=='merged' else 20,
                                                   reasonCode='PUBLIC_REPLAY_TEST', approvalHint='MANAGER'))))
    specs.append(dict(name='Replay labeled merge', active=True, eventType=TYPES['merged'], priority=1,
        conditions=[dict(field='payload.hasLabels', op='EQ', value=True)],
        outcome=dict(kind='INCENTIVE', data=dict(proposedReward=5, reasonCode='PUBLIC_REPLAY_TEST', approvalHint='MANAGER'))))
    return specs


def policies():
    # Test-owned governance; no reward inference from public text or identities.
    specs = [dict(name='Replay '+family, active=True, candidateKind='INCENTIVE', eventType=TYPES[family],
                 conditions=([dict(field='candidate.data.proposedReward',op='GT',value=5)] if family=='merged' else []), decision=decision, priority=0)
            for family,decision in [('merged','REQUIRE_APPROVAL'), ('review','ALLOW'),
                                    ('closed','BLOCK'), ('issue_closed','SHADOW_ONLY')]]
    specs.append(dict(name='Replay small merge',active=True,candidateKind='INCENTIVE',eventType=TYPES['merged'],
        conditions=[dict(field='candidate.data.proposedReward',op='LTE',value=5)],decision='ALLOW',priority=0))
    return specs


def expected(record):
    family = record['family']
    count = 0 if family=='push' else 1+int(family=='merged' and envelope(record)['payload']['hasLabels'])
    decision = dict(merged='REQUIRE_APPROVAL', review='ALLOW', closed='BLOCK',
                    issue_closed='SHADOW_ONLY', issue_reopened='REQUIRE_APPROVAL', push=None)[family]
    return count, decision


if __name__=='__main__': freeze()
