# MiMo Ticket — Phase 2: Scoring & Routing

Implements `PLAN.md §5` (scoring) and §3 (two parallel tracks). Score every job, then decide the
apply tier AND whether outreach fires.

## Build
- `scoring.py`: skills_match, company_match, final_score (formula from PLAN.md §5),
  title_on_allowlist. Loads keywords/targets from `Target-list.json` via `config.load_targets()`.
- `routing.py`: `apply_tier(job) -> "A"|"B"|None` and `should_outreach(job) -> bool`.
- Tests for both.

## Exit
- final_score in [0,100]; senior role at a target company scores high, irrelevant scores low.
- Greenhouse/Lever + score≥92 + allowlisted title -> "A"; MyCareersFuture -> never "A" (login wall).
- score≥78 -> outreach True (parallel track); below -> no apply tier, no outreach.
- tests green.
