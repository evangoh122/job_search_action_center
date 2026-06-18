# Job Search Action Center — Phased Roadmap

Source of truth: `PLAN.md`. This file sequences the build into phases and maps each external
integration to the phase that introduces it. Subordinate to `PLAN.md`.

## The build loop (per phase)

```
Claude (Architect)  ->  cuts ticket   ->  .mimo/tickets/phase-N.md
MIMO  (Coder)       ->  implements     ->  code + tests
DeepSeek (Reviewer) ->  reviews        ->  against .claude/reviews/phase-N-checklist.md
Claude (Architect)  ->  verifies vs PLAN.md contracts  ->  approve / re-ticket
```

Each phase ships **vertically and runnable** (in `DRY_RUN` where it acts outward). Don't start
phase N+1 until N is approved.

## Integration map

| Integration | Phase | Purpose | Auth / access | Risk |
|-------------|-------|---------|---------------|------|
| **MyCareersFuture** | 1 | Primary SG job source | Public API (`api.mycareersfuture.gov.sg`) | Low |
| **LinkedIn** | 1 (jobs), 4 (people) | Jobs + networking targets | 3rd-party (Apify) — no official API | **High (ToS)** — read-only, throttle, human-in-loop |
| **HubSpot** | 3 | CRM / tracking backbone (companies, contacts, application pipeline) | OAuth (MCP available) | Low |
| **Gmail** | 4 | Outreach drafts/sends | OAuth (MCP available) | Med — drafts first, send behind approval |
| **Greenhouse / Lever** | 6 | Tier-A auto-apply targets | Public application endpoints | **High** — `DRY_RUN` first, simple ATS only |

## Phases

### Phase 0 — Foundation & exclusion gate
**Goal:** project skeleton, typed models, storage repo, config loaders, logging, and the
**exclusion gate with tests** (must exist before anything touches a company name).
**Builds:** `Job`/`Contact` models, SQLite repo (Repository pattern), `.env` loader,
`exclusions.py` (the fixed canonical/alias matcher), `runner.py` stub.
**Exit:** `is_excluded_company` passes the SMBC/JRI/false-positive test suite; repo CRUD tested.

### Phase 1 — Sourcing (MyCareersFuture first, then LinkedIn)
**Goal:** pull jobs end-to-end → normalize → exclude → store. Start with **MyCareersFuture**
(low-risk, SG-focused, has an API). Add LinkedIn via Apify behind the same `JobSource` interface.
**Builds:** `JobSource` interface, `MyCareersFutureSource`, `LinkedInSource`, `normalize.py`
(canonical company + dedupe key), 24h freshness filter at source.
**Exit:** a real MCF pull lands deduped, exclusion-filtered jobs in the DB; LinkedIn read-only,
throttled.

### Phase 2 — Scoring & routing
**Goal:** make "90% match" computable and assign tiers.
**Builds:** `scoring.py` (formula from `PLAN.md §5`), `routing.py` (A/B/C per `PLAN.md §3`),
daily-cap enforcement.
**Exit:** stored jobs get a `final_score` and a tier; scoring + routing unit-tested.

### Phase 3 — HubSpot tracking backbone
**Goal:** replace/augment the SQLite tracker with **HubSpot** as the CRM. Companies → Company
objects, jobs → a custom object or Deals, contacts → Contacts, application stage → pipeline
stages (`new → queued → drafted → applied → interview → closed`).
**Builds:** `store/hubspot_repo.py` behind the existing Repository interface; sync job.
**Exit:** a scored job appears in HubSpot with the right stage; idempotent sync (no dupes).

### Phase 4 — Tier C: networking (LinkedIn + HubSpot + Gmail)
**Goal:** lowest-risk outbound first. For target companies, identify people to reach
(recruiters, hiring managers, alumni, 2nd-degree), store as HubSpot contacts, **draft** Gmail
outreach.
**Builds:** `network/find_people.py` (LinkedIn, read-only), `network/outreach.py` (Gmail
drafts), contact dedupe.
**Exit:** for a sample company, contacts land in HubSpot and a personalized Gmail **draft**
exists — nothing sent automatically.

### Phase 5 — Tier B: drafted applications
**Goal:** resume tailoring + drafted applications into a review queue.
**Builds:** `apply/tailor.py` (resume/cover tailoring), `apply/draft.py`, review-queue view.
**Exit:** a Tier-B job produces a tailored draft in HubSpot stage `drafted`; you approve to apply.

### Phase 6 — Tier A: gated auto-apply
**Goal:** auto-submit ONLY for `score ≥ 92` + simple ATS (Greenhouse/Lever) + title allowlist +
under cap. Ships behind a `DRY_RUN` flag that logs the submit without sending until you enable it.
**Builds:** `apply/auto_apply.py`, ATS adapters (Greenhouse, Lever), cap guard.
**Exit:** `DRY_RUN` produces a complete would-submit log for one ATS; live submit stays disabled
until explicitly turned on.

### Phase 7 — Scheduler & reporting
**Goal:** daily automated run + a digest.
**Builds:** scheduled `runner.py` (SG timezone), daily summary (new jobs, tiers, drafts, sends).
**Exit:** one unattended daily run produces the digest with caps respected.

## Cross-cutting guardrails (apply every phase)

- Exclusion gate runs before any scoring or outbound action.
- All outward actions (`apply`, `email`) default to `DRY_RUN`/draft; live mode is opt-in.
- No secrets in code — `.env` only. No hardcoded company lists/thresholds — config only.
- Throttle + respect robots/ToS on LinkedIn and MCF; read-only where possible.
