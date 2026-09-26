"""Small governance lifecycle and deterministic authority resolution."""
AUTHORITIES = ('ADMIN', 'MANAGER_OR_ADMIN')
DECISIONS = ('APPROVED', 'REJECTED')
STATUSES = ('PENDING', *DECISIONS)


def required_authority(candidate_data):
    return 'MANAGER_OR_ADMIN' if candidate_data.get('approvalHint') == 'MANAGER' else 'ADMIN'
