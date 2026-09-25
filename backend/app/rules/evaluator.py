"""Pure Rule evaluation using the shared E4 predicate semantics."""
from ..canonical_events.contracts import StoredEvent
from ..domain import DomainError
from ..safe_predicates.evaluator import compare, read_field as read_value
from .contracts import Evaluation
from .validation import definition


def read_field(event: StoredEvent, path: str):
    fields = {'type': event.type, 'sourceKind': event.source_kind,
              'schemaVersion': event.schema_version, 'actorId': event.actor_id,
              'subjectId': event.subject_id, 'payload': event.payload}
    return read_value(fields, path)


def evaluate(rule: dict, event: StoredEvent) -> Evaluation:
    try:
        rule = definition(rule)
    except DomainError:
        return Evaluation('INVALID')
    if not rule['active'] or rule['eventType'] != event.type:
        return Evaluation('NOT_MATCHED')
    matched = 0
    for condition in rule['conditions']:
        if not compare(read_field(event, condition['field']), condition['op'], condition['value']):
            return Evaluation('NOT_MATCHED', matched)
        matched += 1
    return Evaluation('MATCHED', matched)
