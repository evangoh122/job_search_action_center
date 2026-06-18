# Job Search Action Center — Master Plan

> Single source of truth. The other files (`coder_instructions.md`, `Target-list.json`,
> `Jobsearch.md`) are subordinate to this. Where they conflict, this wins.

## 1. Goal

Automate the discovery, scoring, and pursuit of roles that fit a **Data/AI + Finance hybrid**
profile: Data Science / ML / AI / Solutions Architecture / Data & AI Governance roles,
**both** at pure data/AI companies **and** inside banking/finance firms (e.g. "AI Transformation
Lead @ JPMorgan").

The system never acts on its own where the cost of a mistake is high — see the tiers below.

## 2. Hard exclusion gate (runs FIRST, before scoring)

Current employer & affiliates — never apply, email, scrape, or contact:

- SMBC / Sumitomo Mitsui Banking Corporation
- Sumitomo Mitsui Financial Group (SMFG)
- SMBC Nikko Securities
- JRI / Japan Research Institute

A job matching any of these is dropped and logged. This list lives in **one** place
(`config/exclusions.json`) and is imported by every component. (Today it's duplicated in
`coder_instructions.md` and *missing* from `Target-list.json` — fix in §7.)

## 3. Three automation tiers (the key design)

Routing is decided **after** scoring and the exclusion gate.

| Tier | Trigger | Action | Human role |
|------|---------|--------|-----------|
| **A — Auto-apply** | `final_score ≥ 92` AND simple ATS (Greenhouse/Lever/Workday-easy) AND role title in allowlist AND under daily cap | Tailor resume → submit automatically | Review log after |
| **B — Draft & review** | `78 ≤ final_score < 92`, OR high score on a complex/login-walled ATS | Tailor resume + cover note → push to review queue | Approve & click submit |
| **C — Networking** | Strategically interesting company but weak/no direct-apply path, or `final_score < 78` at a priority-1/2 target | Identify people to reach (recruiters, hiring managers, alumni, 2nd-degree) → draft outreach | Send / personalize |

Rationale: auto-apply only where the ATS is low-risk and the match is near-certain; everything
else stays human-in-the-loop. This is what keeps the system from torching your reputation or
getting accounts banned.

## 4. Pipeline

```
sources → normalize → EXCLUDE gate → score → route (A/B/C) → act → track
```

1. **Sources** — LinkedIn (Apify Advanced Job Search API), Workday scrapers, company boards.
   Apply the 24h freshness filter at the source to build the "HOT" list.
2. **Normalize** — canonical company name + alias table; dedupe by (company, title, location).
3. **Exclude** — §2 gate.
4. **Score** — §5.
5. **Route** — §3.
6. **Act** — apply / draft / find-people, per tier.
7. **Track** — persist every job seen and its state (see §6).

## 5. Scoring — make "90% match" actually computable

The current `scoring_weights` blocks each sum to 1.0, but nothing combines them. Define:

```
final_score = 100 * (0.65 * skills_match + 0.35 * company_match)
if posted_within_24h: final_score = min(100, final_score + 5)   # freshness boost
```

- `skills_match` and `company_match` are each computed from their existing weight blocks (0–1).
- Skills dominate (0.65) because fit matters more than brand.
- **One** global threshold table — remove the per-category `auto_apply_threshold` (85/90/92)
  values that currently conflict with the global `min_match_threshold: 90`. Tiers in §3 are the
  only thresholds.

## 6. State & tracking

A small datastore (SQLite to start) with one row per job:
`id, source, company_canonical, title, url, ats_type, posted_at, score, tier, status,
applied_at, notes`. Status: `new → queued → drafted → applied → interview → closed`.
Enforces dedupe and the daily caps. Networking contacts get a parallel table.

Daily caps (replace the single `max_applications_per_day: 20`):
auto-apply ≤ 10, drafts ≤ 25, outreach ≤ 15.

## 7. Concrete fixes to existing files

1. **`Target-list.json`** — replace the placeholder `excluded_companies`
   (`FakeDataCorp`, `ScamAI`, `UnreliableSolutions`) with the real §2 employer exclusions,
   or better: delete that block and point to `config/exclusions.json`.
2. **Exclusion function bug** — the bidirectional substring match
   (`excluded in company_lower OR company_lower in excluded`) false-positives on short tokens
   like `"JRI"`. Switch to normalized canonical-name + alias exact matching. Also `logger` is
   referenced but never defined.
3. **`coder_instructions.md`** — reframe from "Banking/Finance only" to the hybrid scope in §1,
   and stop hardcoding the company lists there (they belong in `Target-list.json`).
4. **`.claude/ROLE.md` + `REVIEW-deepseek.md`** — these describe a *different* project
   (graph-RAG / SEC EDGAR / `edgartools`). Remove or rewrite for this system, or they'll
   misdirect all three AIs.
5. **`Target-list.json`** — drop "Credit Suisse" (absorbed into UBS).
6. **`Jobsearch.md`** — this is research notes, not spec. Fold the useful bits (Apify 24h
   param, `dateSincePosted=24hr`, Workday `posted_after`) into §4 and archive the file.

## 8. Three-AI division of labor (corrected)

- **Claude (Architect)** — owns this plan, the pipeline contracts, scoring spec, exclusion gate.
- **MIMO (Coder)** — implements sources, scoring, routing, application & networking modules.
- **DeepSeek (Reviewer)** — reviews against this plan: exclusion correctness first, then ToS
  safety of Tier A, then code quality.

## 9. Open decisions

- Which ATSes count as "simple" enough for Tier A auto-apply?
- Resume tailoring: template-swap vs. LLM-rewrite per job?
- Networking outreach: fully drafted-and-sent, or always human-approved?
