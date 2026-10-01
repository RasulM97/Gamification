"""Six neutral count-based detectors; provider payloads are never inspected."""
from hashlib import sha256
import json
from .contracts import SEVERITY
from .queries import snapshot, LIMIT


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def evaluate(db, candidate, source, settings):
    findings = []
    actor, subject = source.actor_id, source.subject_id
    keys = set()
    for name, config in settings.items():
        window = config['windowMs']
        if name in ('REPEAT_PAIR_CONCENTRATION', 'RECIPROCAL_PAIR_BURST') and actor and subject:
            keys.add((window, actor, subject))
            if name == 'RECIPROCAL_PAIR_BURST': keys.add((window, subject, actor))
        if name == 'ACTOR_VELOCITY' and actor: keys.add((window, actor, None))
        if name == 'RECIPIENT_VELOCITY' and subject: keys.add((window, None, subject))
    cache, equivalent = snapshot(db, source, candidate, sorted(keys, key=str))
    def rows(window, actor=None, subject=None):
        key = (window, actor, subject)
        return cache[key]
    for name, config in sorted(settings.items()):
        window, threshold = config['windowMs'], config['threshold']
        actor, subject = source.actor_id, source.subject_id
        evidence = {'threshold': threshold}
        samples = []
        if name == 'SELF_BENEFIT':
            if not config['prohibited']: continue
            count = int(actor is not None and actor == subject)
        elif name == 'REPEATED_EQUIVALENT_INCENTIVE':
            count = len(equivalent)
            evidence.update(basis='SAME_CANONICAL_ACTION_AND_INCENTIVE_DATA', candidateIds=equivalent[:10])
        elif name == 'RECIPROCAL_PAIR_BURST':
            if not actor or not subject or actor == subject: continue
            forward, reverse = rows(window, actor, subject), rows(window, subject, actor)
            count = min(len(forward), len(reverse))
            evidence.update(forwardCount=len(forward), reverseCount=len(reverse))
            samples = forward[:5] + reverse[:5]
        elif name == 'REPEAT_PAIR_CONCENTRATION':
            if not actor or not subject: continue
            matched = rows(window, actor, subject)
            count, samples = len(matched), matched[:10]
        elif name == 'ACTOR_VELOCITY':
            if not actor: continue
            matched = rows(window, actor=actor)
            count, samples = len(matched), matched[:10]
        else:
            if not subject: continue
            matched = rows(window, subject=subject)
            count, samples = len(matched), matched[:10]
        if count < threshold: continue
        evidence.update(count=count, countSaturated=count == LIMIT,
                        eventIds=[row.id for row in samples])
        findings.append(dict(findingType=name, outcome=config['outcome'], eventId=source.id,
                             subjectUserId=subject, relatedUserId=actor,
                             windowStart=max(0, source.occurred_at-window), windowEnd=source.occurred_at,
                             evidence=evidence))
    outcome = max((finding['outcome'] for finding in findings), key=SEVERITY.get, default='CLEAR')
    # Hash the entire bounded history, not only illustrative samples. Changes to
    # relevant arrived history yield new immutable evidence on explicit refresh.
    history_hash = digest(sorted((str(key), [(r.dedupe_key, r.occurred_at) for r in value])
                                for key, value in cache.items()))
    return outcome, findings, history_hash
