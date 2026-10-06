"""WS1 lifecycle publication: approvals never imports its subscribers.

The approvals package has a hard dependency boundary (test_approvals.py):
it may not import notifications. Subscribers (e.g. the WS1 push fan-out in
notifications.approval_push) register here at app/test bootstrap instead.
"""
# Listeners: fn(db, intents) -> None, where intents are plain dicts produced
# by approvals.notify.request_intents. Called in the same transaction as
# request creation, only when a new row was actually inserted.
REQUEST_CREATED = []
