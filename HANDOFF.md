# HANDOFF — continue-point for a new instance

A fresh session can resume the whole project from this file + git. Goal: complete all phases of
`ROADMAP.md`, MiMo builds / DeepSeek reviews (`WORKFLOW.md`), push after each phase, never commit
`.env`. After every 7th phase, refresh this file and continue.

## State (as of last update)
- Branch `main` pushed to `origin` (evangoh122/job_search_action_center).
- **Phases 0–8 complete & pushed.** 70 tests passing (`python -m pytest -q`).
- Live daily run works: `python -m runner` pulls real SG jobs, scores, routes, prints a digest.

## Architecture (built)
sources (MyCareersFuture, live) → normalize → **exclusion gate** (SMBC/JRI, fail-closed) →
scoring → routing into **two parallel tracks**:
- Track 1 Apply: Tier A auto-apply (Greenhouse/Lever, **DRY_RUN default**), Tier B draft→review queue.
- Track 2 Outreach: Hunter.io people/emails → Gmail drafts (human-approved). Daily caps enforced.

## How to continue the loop
1. Pick next phase from `ROADMAP.md`. Write `.mimo/tickets/phase-N.md`.
2. Drive MiMo via its API (model `mimo-v2.5-pro`, `thinking:{type:disabled}`, Anthropic endpoint
   `token-plan-sgp.xiaomimimo.com/anthropic`, key `MIMO_API_KEY` in `.env`). MiMo tends to omit
   required Job fields (`source`,`dedupe_key`) in tests and sometimes redefines models — integrate
   and fix.
3. DeepSeek reviews (model `deepseek-chat`, `api.deepseek.com/anthropic`, `DEEPSEEK_API_KEY`).
   **Verify every finding** — it hallucinates; reject false ones, apply real ones.
4. `python -m pytest -q` green → commit `phase N: ...` → `git push`. Update this file + WORKFLOW.md.

## Next up
- All planned phases (0–8) are complete. Future ideas if the goal extends: email enrichment of
  LinkedIn posters via Hunter; an approval UI for the draft queues; richer job descriptions
  (LinkedIn/ATS sources) so more jobs cross the 78 score floor.

## Live keys (all optional; degrades gracefully) — in `.env`, never committed
`HUNTER_API_KEY`, `GMAIL_TOKEN`, `HUBSPOT_TOKEN`, `APIFY_TOKEN`, `AUTO_APPLY_LIVE=true`,
`APPLICANT_NAME/EMAIL/RESUME_URL`.
