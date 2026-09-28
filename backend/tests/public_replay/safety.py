"""Run before importing application configuration, and again before any reset."""
from sqlalchemy.engine import make_url


def guard(url):
    parsed = make_url(url)
    if (parsed.get_backend_name() != 'postgresql' or parsed.database != 'cve_public_replay_test'
            or parsed.query or parsed.host != 'cve-e71-db'):
        raise ValueError('Replay requires dedicated cve-e71-db/cve_public_replay_test without URL options')
    return parsed
