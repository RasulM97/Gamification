"""Pure severity reduction over explicit, immutable candidate/event context."""
import hashlib
import json
from ..domain import DomainError
from ..safe_predicates.evaluator import compare, read_field
from .contracts import DEFAULT_DECISION, GOVERNANCE_VERSION, SEVERITY, PolicyContext
from .validation import definition


def evaluate(policies: list[dict], context: PolicyContext) -> dict:
    candidate, event = context.candidate, context.event
    if candidate.company_id != event.company_id or candidate.canonical_event_id != event.id:
        raise DomainError('POLICY_EVALUATION_CONFLICT', 'Invalid policy context')
    fields = {'candidate': {'kind': candidate.kind, 'status': candidate.status,
        'ruleId': candidate.rule_id, 'ruleVersion': candidate.rule_version, 'data': candidate.data},
        'event': {'type': event.type, 'sourceKind': event.source_kind, 'sourceId': event.source_id,
        'schemaVersion': event.schema_version, 'actorId': event.actor_id,
        'subjectId': event.subject_id, 'payload': event.payload}}
    evaluated = []
    for policy in sorted(policies, key=lambda p: (-p['definition']['priority'], p['id'])):
        spec = definition(policy['definition'])  # Corrupt persisted governance fails closed.
        if not spec['active'] or spec['candidateKind'] not in (None, candidate.kind) or spec['eventType'] not in (None, event.type):
            continue
        matched = 0
        for condition in spec['conditions']:
            if not compare(read_field(fields, condition['field']), condition['op'], condition['value']):
                break
            matched += 1
        evaluated.append(dict(id=policy['id'], version=policy['version'], definition=spec,
                              matched=matched == len(spec['conditions']), conditionsMatched=matched))
    matches = sorted((p for p in evaluated if p['matched']),
                     key=lambda p: (-SEVERITY[p['definition']['decision']], -p['definition']['priority'], p['id']))
    winner = matches[0] if matches else None
    identity = dict(governanceVersion=GOVERNANCE_VERSION, companyId=candidate.company_id,
                    candidateId=candidate.id, policies=evaluated)
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':'),
                                           ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    return dict(policySetFingerprint=fingerprint,
                effectiveDecision=winner['definition']['decision'] if winner else DEFAULT_DECISION,
                matchedPolicies=[{'id': p['id'], 'version': p['version'], 'decision': p['definition']['decision']} for p in matches],
                evaluatedPolicies=evaluated, explanation=dict(governanceVersion=GOVERNANCE_VERSION,
                    reason='MATCHED_POLICY' if winner else 'DEFAULT_GOVERNANCE',
                    winningPolicyId=winner['id'] if winner else None,
                    defaultDecision=DEFAULT_DECISION))
