# Phase 9 — 15-week Job Search OKR operating system

Build a dedicated, local-first `job-okr` CLI for the campaign from 2026-07-20 through
2026-11-01 (Asia/Singapore). It must coexist with the existing job pipeline and preserve all
dry-run/application approval gates.

## Required outcomes

- Deterministic weekly schedule: weekday commute review only, 12:15–12:45 coffee chats,
  Mon/Wed coding, Tue/Thu targeted applications, Saturday deep work and mock/sourcing,
  Sunday portfolio/review/post. Never plan production during 09:00–18:00 except lunch.
- Weekly tracking for 5 coffee chats, 10 targeted applications, 1 LinkedIn post, 180 coding
  minutes, 120 stats/deep minutes, and 450 commute-review minutes, plus support blocks.
- Planned full weekend rest on Aug 22–23 and Sep 26–27, with weekend blocks suppressed and
  baseline versus rest-adjusted expectations reported separately.
- Date-authoritative strategy checkpoints: Aug 10 targeting/resume diagnostic if interviews
  have not landed; Aug 31 Saturday PM becomes mocks; Sep 21 applications fall to five and
  referrals rise if no offer is in play; Oct 12 stops new applications and focuses on closing.
- SQLite audit trail for activities, job status changes, learning gaps, follow-ups, and weekly
  review snapshots. The review must answer all five supplied checklist items.
- Every interview/challenge gap is durably stored first and immediately appended to a
  configured Drive-synced Markdown note. Failed sync remains visible and retryable.
- Application materials select/reorder immutable master-resume blocks verbatim. They may not
  invent or rewrite bullet text; provenance and hashes must be retained and invalid sources
  must fail closed.
- Register `job-okr`, document practical commands, and provide comprehensive offline tests.

## Implementation request for MiMo

Focus on a clean service/CLI layer over the calendar, strategy, and persistence components.
Return proposed Python for `okr/service.py` and `okr_cli.py`, including validation and readable
terminal output. Do not perform network calls, send messages, submit applications, or expose
secrets. Flag ambiguities instead of silently changing the rules.
