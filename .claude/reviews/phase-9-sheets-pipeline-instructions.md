# Phase 9 — DeepSeek/MiMo Google Sheets and application-pipeline review

Implementation and review must follow
`.claude/instructions/review-first-application-engine.md`. If requirements differ, apply the
stricter safety rule and report the discrepancy.

Review the current repository as an adversarial systems reviewer. The UI is not permission to
weaken submission safety. Google Sheets must become the operational source of truth and SQLite
may be only a cache/outbox.

## Review surfaces

- `store/google_sheets_repo.py`
- `runner.py`
- `application_cli.py`
- `apply/auto_apply.py`
- `apply/browser_submitter.py`
- `apply/resume_models.py`, `resume_bank.py`, and `resume_builder.py`
- `web/worker/sheets.ts` and `web/worker/index.ts`
- related Python and web tests

## Required invariants

1. All live decisions read the authoritative Sheet; an unavailable authoritative read/write
   fails closed before any submission click.
2. Persist the immutable application package before submission. Never submit first and audit
   afterward.
3. Approval is one-time and binds the exact vacancy/form fingerprint, application-package
   hash, rendered-resume hash/version, answers, timestamp, and nonce.
4. The approved resume artifact is built from active, authoritative master blocks and the
   exact approved bytes/path are uploaded. Validation never invents a missing hash.
5. Status transitions are compare-and-set and append history. Treat every exception after the
   submit click as `submission_unknown`; it is terminal until manual reconciliation.
6. Python and TypeScript use one versioned Sheet schema and the same event/status vocabulary.
7. Sheet updates are narrow and formula-preserving; never rewrite a stale full row.
8. Every web API requires trusted owner identity plus same-origin/CSRF protection for writes.
9. Inputs have runtime schemas, length limits, ISO dates, Singapore timezone handling, and
   allowed status transitions.
10. Drive gap writes are durable, idempotent, retryable, and surface pending/overdue failures.
11. Applications and approvals use stable idempotency keys; concurrent requests cannot create
   duplicate authoritative records.
12. `Start application package` never means silent submission. The UI must require explicit
   exact-package approval and the protected visible-browser workflow.

## Mandatory tests

- changed vacancy/package/resume invalidates approval;
- approval is consumed once;
- pre-submit Sheet failure prevents the click;
- post-click exception becomes `submission_unknown` and never retries automatically;
- uploaded artifact hash equals the approved resume hash;
- narrow status update preserves formulas and concurrent fields;
- unauthenticated/cross-origin Worker calls are denied;
- Singapore dates at midnight, 07:59, and 08:00 SGT;
- Drive append failure remains pending and retry is idempotent;
- Python/TypeScript schema and status contracts match;
- concurrent duplicate writes reconcile to one authoritative record.

Report only verified findings as BLOCKER, MAJOR, or MINOR with exact file references and a
concrete fix. Do not recommend bypassing CAPTCHAs, MFA, access controls, or human review.
