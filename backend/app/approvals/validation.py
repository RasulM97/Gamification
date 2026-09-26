"""Strict, bounded commands. Notes are plain text and never logged."""
import json
import re
from ..domain import DomainError
from .contracts import DECISIONS


def invalid():
    raise DomainError('INVALID_APPROVAL_DECISION', 'Invalid approval command')


def command(value):
    if type(value) is not dict or not {'decision'} <= value.keys() <= {'decision','reasonCode','note'}:
        invalid()
    if type(value['decision']) is not str or value['decision'] not in DECISIONS:
        invalid()
    reason, note = value.get('reasonCode'), value.get('note')
    if reason is not None and (type(reason) is not str or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', reason)):
        invalid()
    if note is not None:
        if type(note) is not str or '\x00' in note:
            invalid()
        try:
            if len(note.encode('utf-8')) > 2048: invalid()
        except UnicodeError:
            invalid()
    return dict(decision=value['decision'], reasonCode=reason, note=note)


async def read_body(request):
    if request.headers.get('content-type', '').split(';',1)[0].strip().lower() != 'application/json':
        invalid()
    raw = bytearray()
    async for part in request.stream():
        if len(raw)+len(part)>4096: invalid()
        raw.extend(part)
    def pairs(items):
        result = {}
        for key,value in items:
            if key in result: raise ValueError()
            result[key] = value
        return result
    def constant(_): raise ValueError()
    try:
        return command(json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant))
    except (ValueError, UnicodeError, RecursionError):
        invalid()
