"""Run: python -m app.provision_company --company NAME --admin-name NAME --admin-email EMAIL."""
import argparse
import getpass
import json
import sys

from sqlalchemy.exc import IntegrityError

from .db import session_scope
from .domain import DomainError
from .provisioning import provision_company


def main():
    parser = argparse.ArgumentParser(description='Provision one empty pilot company and its initial Admin')
    parser.add_argument('--company', required=True)
    parser.add_argument('--admin-name', required=True)
    parser.add_argument('--admin-email', required=True)
    parser.add_argument('--password-stdin', action='store_true', help='Read one password from protected stdin; never pass it as an argument')
    args = parser.parse_args()
    password = sys.stdin.readline().rstrip('\r\n') if args.password_stdin else getpass.getpass('Initial Admin password: ')
    if not args.password_stdin and password != getpass.getpass('Confirm password: '):
        parser.error('Passwords do not match')
    try:
        with session_scope() as db:
            company, admin, created = provision_company(db, company_name=args.company,
                admin_name=args.admin_name, admin_email=args.admin_email, password=password)
            summary = {'companyId': company.id, 'adminId': admin.id, 'created': created}
    except (DomainError, IntegrityError):
        parser.exit(1, 'Provisioning refused: check input or existing company/login conflicts.\n')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
