"""Guard must run before importing application DB configuration or resetting tables."""
from sqlalchemy.engine import make_url


def guard(url):
    parsed = make_url(url)
    if (parsed.get_backend_name() != 'postgresql' or parsed.database != 'cve_synthetic_test'
            or parsed.query):
        raise ValueError('Synthetic runner requires explicit disposable cve_synthetic_test without URL options')
    return parsed
