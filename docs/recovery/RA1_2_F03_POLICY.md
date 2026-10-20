# F03 disposition — founder clarification

F03 is a pending product-policy / manager-workflow question, **not a confirmed
authorization bypass**. No authorization rule is changed.

Observed operation: a manager creates a rewarded task in their managed unit;
an employee claims and submits it; that manager (or another manager of the unit)
attempts `POST /api/tasks/{id}/approve`. Positive payout is refused with
`403 ECONOMIC_AUTHORITY_REQUIRED`. An Admin can approve the same submission.
Stage 2 `stage2-20261020-c9c56df-7b31`, E7 R4, verifies these exact outcomes.
See `task_access.py::require_payout_authority` and
`test_task_lite_ws4b.py::test_manager_authored_rewarded_task_approve_requires_admin`.

Missing capability for later product review: a defined, authorized manager
decision/delegation workflow for manager-authored rewarded work, including who
may authorize its economic promise and who executes the payout. There is no
approved new policy, threshold, delegation or split approval/payout workflow.
These are not introduced by RA-1.2.

Founder direction: retain Admin-only economic authority for manager-authored
rewarded tasks and all existing `403 ECONOMIC_AUTHORITY_REQUIRED` safeguards.
F03 does not block the independently authorized F02/E6 remediation.
