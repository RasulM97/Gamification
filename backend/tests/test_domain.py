"""Pure domain-rule parity tests — the same invariants the 114 Vitest cases
freeze on the TS side, verified against the Python port."""
from app.domain import (
    UploadCandidate, can_see_task, claim_penalty, normalize_deadline,
    partial_payout, role_fits, validate_attachments,
)


def test_partial_payout_formula_half_step():
    assert partial_payout(40, 20) == 8
    assert partial_payout(30, 15) == 4.5
    assert partial_payout(37, 33) == 12.5   # ceil(12.21*2)/2
    assert partial_payout(10, 5) == 0.5
    assert partial_payout(12, 0) == 0


def test_claim_penalty_priority_scaled():
    assert claim_penalty('NONE') == 5
    assert claim_penalty('NORMAL') == 5
    assert claim_penalty('IMPORTANT') == 7.5
    assert claim_penalty('URGENT') == 10


def test_normalize_deadline_canonical_date_only():
    assert normalize_deadline('2026-09-05') == '2026-09-05'
    assert normalize_deadline('2026-09-05T17:00:00.000Z') == '2026-09-05'
    assert normalize_deadline(None) is None
    assert normalize_deadline('') is None
    assert normalize_deadline('garbage') is None


def test_role_fits_admin_never_owns_work():
    assert role_fits('EMPLOYEES', 'EMPLOYEE')
    assert not role_fits('EMPLOYEES', 'MANAGER')
    assert role_fits('MANAGEMENT', 'MANAGER')
    assert not role_fits('MANAGEMENT', 'EMPLOYEE')
    assert role_fits('PRIVATE', 'EMPLOYEE')
    assert role_fits('PRIVATE', 'MANAGER')
    for aud in ('EMPLOYEES', 'MANAGEMENT', 'PRIVATE'):
        assert not role_fits(aud, 'ADMIN')


def test_visibility_rules():
    # employees: EMPLOYEES-audience yes, MANAGEMENT no, PRIVATE only if involved
    assert can_see_task('EMPLOYEES', None, None, 'EMPLOYEE', 'u-x')
    assert not can_see_task('MANAGEMENT', None, None, 'EMPLOYEE', 'u-x')
    assert not can_see_task('PRIVATE', 'u-y', None, 'EMPLOYEE', 'u-x')
    assert can_see_task('PRIVATE', 'u-x', None, 'EMPLOYEE', 'u-x')
    assert can_see_task('PRIVATE', None, 'u-x', 'EMPLOYEE', 'u-x')
    # management sees everything
    assert can_see_task('MANAGEMENT', None, None, 'MANAGER', 'u-x')
    assert can_see_task('PRIVATE', 'u-y', None, 'MANAGER', 'u-x')


def test_upload_policy():
    big = 11 * 1024 * 1024
    cases = [
        ([UploadCandidate('evil.exe', 10, '')], 'executable'),
        ([UploadCandidate('run.sh', 10, 'application/x-sh')], 'executable'),
        ([UploadCandidate('notes.txt', 10, 'application/javascript')], 'content type'),
        ([UploadCandidate('../etc/passwd', 10, 'text/plain')], 'invalid file name'),
        ([UploadCandidate('a/b.txt', 10, 'text/plain')], 'invalid file name'),
        ([UploadCandidate('big.pdf', big, 'application/pdf')], 'per-file limit'),
        ([UploadCandidate('a.pdf', 9 * 1024 * 1024, 'application/pdf'),
          UploadCandidate('b.pdf', 9 * 1024 * 1024, 'application/pdf'),
          UploadCandidate('c.pdf', 9 * 1024 * 1024, 'application/pdf')], 'total'),
    ]
    for files, frag in cases:
        errors = validate_attachments(files, 10, 25)
        assert errors, files
        assert frag in ' '.join(errors)
    assert validate_attachments([UploadCandidate('ok.pdf', 100, 'application/pdf')], 10, 25) == []
