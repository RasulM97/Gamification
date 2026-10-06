"""WS1 email rendering + SMTP send for the three approved push classes.

Templates are deterministic plain text built from intent params — business
language only, no Rule/Policy/Safety internals, no generated prose.
"""
import smtplib
from email.message import EmailMessage
from ..config import settings
from ..domain import DomainError
from .model import NotificationDelivery


def render(row: NotificationDelivery, recipient_name: str, actor_name: str | None) -> tuple[str, str]:
    p = row.params or {}
    link = settings.public_base_url.rstrip('/')
    if row.push_class == 'RECOGNITION_RECEIVED':
        who = actor_name or 'A manager'
        subject = f'{who} recognized your work'
        body = (f"Hi {recipient_name},\n\n{who} gave you formal recognition"
                + (f":\n\n\"{p.get('reason', '')}\"\n" if p.get('reason') else '.\n')
                + f"\nView it in CVE: {link}\n")
    elif row.push_class == 'INCENTIVE_APPROVAL_ACTION_REQUIRED':
        subject = 'An incentive decision is waiting for you'
        amount = p.get('amount')
        whom = p.get('subjectName') or 'a team member'
        body = (f"Hi {recipient_name},\n\nAn incentive"
                + (f' of {amount} coins' if isinstance(amount, (int, float)) else '')
                + f' for {whom} is waiting for your decision.'
                + f"\n\nReview and decide in CVE: {link}\n"
                + '\nNote: this link never authorizes the decision itself — CVE re-checks your current authority when you act.\n')
    elif row.push_class == 'HELP_REQUEST_ACTION_REQUIRED':
        who = p.get('requesterName') or actor_name or 'A colleague'
        subject = f'{who} is asking for help'
        body = (f"Hi {recipient_name},\n\n{who} needs help"
                + (f":\n\n\"{p.get('title', '')}\"\n" if p.get('title') else '.\n')
                + (f"\nContext: {p.get('scopeName')}\n" if p.get('scopeName') else '')
                + f"\nYou can accept the request in CVE: {link}\n")
    else:  # locked taxonomy — unreachable unless push.py is widened without approval
        raise DomainError('VALIDATION', 'Unknown outbound push class')
    return subject, body


def send_email(to_address: str, subject: str, body: str, message_id: str) -> None:
    """One SMTP attempt. Raises on any failure — the worker owns retry."""
    if not settings.smtp_host:
        raise DomainError('OUTBOUND_UNCONFIGURED', 'Outbound email is not configured')
    message = EmailMessage()
    message['From'] = settings.smtp_from
    message['To'] = to_address
    message['Subject'] = subject
    # Deterministic Message-ID: a crash-retried delivery carries the SAME id,
    # so MTAs/clients can dedupe the single unavoidable at-least-once window.
    message['Message-ID'] = f'<{message_id}@cve-outbound>'
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
