"""Explicit acquisition and conservative structural sanitization (stdlib only)."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import urllib.request

PUBLIC_REPLAY_CORPUS_VERSION = 1
ROOT = Path(__file__).parent
URL = 'https://data.gharchive.org/2025-01-15-12.json.gz'
QUOTAS = dict(merged=250, closed=200, review=200, issue_closed=200, issue_reopened=50, push=200)
ENUMS = {'PullRequestEvent', 'PullRequestReviewEvent', 'IssuesEvent', 'PushEvent',
         'closed', 'open', 'opened', 'reopened', 'created', 'submitted', 'approved', 'changes_requested',
         'commented', 'pending', 'dismissed', 'User', 'Bot', 'Organization', 'public',
         'private', 'none', 'clean', 'dirty', 'unknown', 'unstable', 'blocked', 'behind',
         'APPROVED', 'CHANGES_REQUESTED', 'COMMENTED', 'PENDING', 'DISMISSED'}
ENUM_KEYS = {'type', 'action', 'state', 'mergeable_state', 'visibility', 'author_association'}
SAFE_ASSOCIATIONS = {'OWNER', 'MEMBER', 'COLLABORATOR', 'CONTRIBUTOR', 'FIRST_TIMER',
                     'FIRST_TIME_CONTRIBUTOR', 'NONE', 'MANNEQUIN'}


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def family(event):
    payload = event.get('payload') or {}
    kind, action = event.get('type'), payload.get('action')
    if kind == 'PullRequestEvent' and action == 'closed':
        return 'merged' if (payload.get('pull_request') or {}).get('merged') is True else 'closed'
    if kind == 'PullRequestReviewEvent' and action in ('created', 'submitted'):
        if (payload.get('review') or {}).get('submitted_at'): return 'review'
    if kind == 'IssuesEvent' and action in ('closed', 'reopened'): return 'issue_'+action
    if kind == 'PushEvent': return 'push'
    return None


class Sanitizer:
    def __init__(self):
        self.identities = {}

    def alias(self, value):
        key = (type(value).__name__, str(value))
        if key not in self.identities: self.identities[key] = len(self.identities)+1
        return self.identities[key]

    def clean(self, value, key=''):
        if isinstance(value, dict):
            return {k: self.clean(v, k) for k,v in value.items()
                    if re.sub('[^a-z]', '', k.lower()) not in
                    {'email', 'authorization', 'token', 'accesstoken', 'secret', 'password', 'headers', 'ip'}}
        if isinstance(value, list): return [self.clean(v, key) for v in value]
        if value is None or isinstance(value, bool): return value
        if key == 'id' or key.endswith('_id'):
            number = self.alias(value)
            return number if isinstance(value, (int, float)) else f'id_ext_{number:06d}'
        if isinstance(value, (int, float)): return value
        if isinstance(value, str):
            if key in ENUM_KEYS and value in ENUMS | SAFE_ASSOCIATIONS: return value
            if re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)', value): return value
            if not value: return ''
            if key.endswith('url') or value.startswith(('https://', 'http://', 'git://')):
                return f'https://public-replay.invalid/ref/{self.alias(value)}'
            if key in {'body', 'title', 'message', 'description', 'bio'}:
                return f'[removed public text; original UTF8 bytes={len(value.encode())}]'
            return f'ext_{self.alias(value):06d}'
        raise ValueError('Unexpected JSON value')


def validate_corpus(records):
    assert len(records) >= 500
    assert len({r['sourceRecordRef'] for r in records}) == len(records)
    assert set(QUOTAS) <= {r['family'] for r in records}
    for record in records:
        assert record['family'] == family(record['specimen'])
        text = encode(record).decode()
        assert not re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|gh[pousr]_[A-Za-z0-9]{15,}|github_pat_|-----BEGIN .*PRIVATE KEY', text)
        assert not re.search(r'"(?:authorization|access_token|webhook_secret|email)"\s*:', text, re.I)
        def check(value):
            if isinstance(value,dict):
                for child in value.values(): check(child)
            elif isinstance(value,list):
                for child in value: check(child)
            elif isinstance(value,str):
                assert value in ENUMS | SAFE_ASSOCIATIONS | {''} or re.fullmatch(
                    r'(?:ext_|id_ext_)\d+|https://public-replay\.invalid/ref/\d+|'
                    r'\[removed public text; original UTF8 bytes=\d+\]|'
                    r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)',value)
        check(record['specimen'])


def load():
    raw = (ROOT/'sanitized/corpus-v1.jsonl').read_bytes()
    manifest = json.loads((ROOT/'manifests/corpus-v1.json').read_text())
    assert hashlib.sha256(raw).hexdigest() == manifest['sha256']
    if 'canonicalFixtureSha256' in manifest:
        assert hashlib.sha256((ROOT/'mappings/canonical-v1.jsonl').read_bytes()).hexdigest()==manifest['canonicalFixtureSha256']
    records = [json.loads(line) for line in raw.splitlines()]
    validate_corpus(records)
    return records, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    if args.download:
        args.raw.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(URL, args.raw)
    target = ROOT/'sanitized/corpus-v1.jsonl'
    if target.exists(): raise SystemExit('Frozen version exists; create an intentional new corpus version')
    records, counts, sanitizer = [], Counter(), Sanitizer()
    observed = Counter()
    with gzip.open(args.raw, 'rb') as stream:
        for number, line in enumerate(stream, 1):
            event = json.loads(line)
            kind = family(event)
            observed[kind or 'other'] += 1
            if kind and counts[kind] < QUOTAS[kind]:
                records.append(dict(sourceRecordRef=f'gharchive-2025-01-15-12/line-{number}',
                    family=kind, rawBytes=len(line.rstrip(b'\r\n')),
                    rawRecordSha256=hashlib.sha256(line).hexdigest(), specimen=sanitizer.clean(event)))
                counts[kind] += 1
    validate_corpus(records)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = b''.join(encode(record)+b'\n' for record in records)
    target.write_bytes(data)
    manifest = dict(corpusVersion=1, sanitizationVersion=1, source='GH Archive public GitHub Events API hour',
        sourceUrl=URL, sourceReference='https://www.gharchive.org/',
        retrievedAt=datetime.fromtimestamp(args.raw.stat().st_mtime,timezone.utc).isoformat(),
        sanitizedAt=datetime.now(timezone.utc).isoformat(),
        publicAccessBasis='Public unauthenticated archive of public GitHub activity',
        usageNote='Archive code MIT / website CC-BY-4.0 are not dataset licenses. Third-party rights may apply. '
                  'Tracked subset retains factual structure, dates, enums, counts; identities pseudonymized and expressive text removed. '
                  'Raw archive remains ignored local evidence, not redistributed.',
        recordsRetrieved=number, recordsSelected=len(records), recordsSanitized=len(records),
        observedFamilies=dict(observed), eventFamilies=dict(counts),
        rawArchiveSha256=hashlib.sha256(args.raw.read_bytes()).hexdigest(), sha256=hashlib.sha256(data).hexdigest())
    (ROOT/'manifests').mkdir(exist_ok=True)
    (ROOT/'manifests/corpus-v1.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__': main()
