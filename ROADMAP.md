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
| **MyCareersFuture** | 1 ✅ | Primary SG job source | Public API (`api.mycareersfuture.gov.sg`) | Low |
| **LinkedIn** | 1 (jobs, optional) | Supplemental jobs only | 3rd-party (Apify) or free guest endpoint | **High (ToS)** — read-only, throttle. Not required for outreach. |
| **HubSpot** | 3 | CRM / tracking backbone (companies, contacts, application pipeline) | OAuth (MCP available) | Low |
| **Hunter.io** | 4 | Recruiter + hiring-manager people & verified emails (Domain Search) | `HUNTER_API_KEY` | Low |
| **Gmail** | 4 | Outreach drafts (human-approved send) | OAuth (compose scope) | Med — drafts only at first |
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

### Phase 4 — Outreach track (Hunter.io + Gmail), parallel to applying
**Goal:** for every *qualified* job (so depends on Phase 2 scoring), email **both** a recruiter
and the hiring manager at the company — concurrently with the application.
**People + email source:** Hunter.io **Domain Search** returns people with roles + verified
emails for a company domain — filter for recruiter/talent and hiring-manager roles. (No LinkedIn
needed for this track.) Decision: Hunter.io for emails.
**Send:** Gmail **drafts** — system creates personalized, role-specific drafts (HM vs recruiter
get different angles); **user approves & sends**. Throttled. No auto-send until deliverability is
tuned. Decision: Gmail drafts, human-approved.
**Builds:** `network/email_finder.py` (Hunter client, injectable HTTP), `network/outreach.py`
(draft templates + Gmail draft creation), contact dedupe + daily outreach cap (15).
**Keys needed:** `HUNTER_API_KEY` in `.env`; Gmail OAuth (compose scope).
**Exit:** for a sample qualified job, the system produces personalized Gmail **drafts** to a
recruiter and a hiring manager — nothing sent automatically.

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

### Phase 8 — LinkedIn job-poster networking
**Goal:** beyond Hunter's generic company contacts, find the **specific person who posted the
role on LinkedIn** (the hiring manager or recruiter who put up the listing) so the user can reach
out to *them* directly.
**Source:** Apify LinkedIn Jobs actor (or public guest data) returns the job poster's name, title,
and profile URL. Classify recruiter vs hiring manager (reuse `network.email_finder._classify`).
LinkedIn gives no email — optionally enrich via Hunter Email Finder (name + company domain), else
the user messages them on LinkedIn.
**Builds:** `network/linkedin_poster.py` (`LinkedInPosterFinder`, injectable HTTP), feeds the
poster as a Contact into the Track-2 outreach drafting.
**Keys needed:** `APIFY_TOKEN` (LinkedIn). Build against mocks now; live when added.
**Exit:** for a sample LinkedIn job, the poster is identified, classified, and turned into a
Contact ready for outreach. Tested against a mocked Apify response.

## Cross-cutting guardrails (apply every phase)

- Exclusion gate runs before any scoring or outbound action.
- All outward actions (`apply`, `email`) default to `DRY_RUN`/draft; live mode is opt-in.
- No secrets in code — `.env` only. No hardcoded company lists/thresholds — config only.
- Throttle + respect robots/ToS on LinkedIn and MCF; read-only where possible.
