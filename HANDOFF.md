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

## Resume / application-package instructions
- For future coding tasks: prefer MiMo for implementation when callable, DeepSeek for review, then
  Codex performs final validation. Before merging GitHub work, wait for CodeRabbit PR validation
  where available.
- For any new resume achievement or application-package point, interview Evan before finalising it.
  Capture:
  - `keyword`: target skill/role signal.
  - `X`: outcome/result.
  - `Y`: metric/scale/adoption/money/time saved/users/coverage.
  - `Z`: method/tools/model/product/workflow/stakeholder action.
  - role fit: which resume variants should use it.
  - disclosure constraints: employer/client names and confidential details.
- Store private resume source material under ignored local paths such as `data/` or `resume/`.
  Do not commit personal CV files or local achievement banks unless explicitly requested.
- For every new application package, name the resume file
  `Evan_Resume{mmddyyyy}_{COMPANY_ABBR}`, e.g. `Evan_Resume07122026_DBS.docx`.
- Save the application link in the Google Sheet application/job row.
- Put Evan's GitHub link and resume link in the resume header/contact block alongside email,
  phone, LinkedIn, and location.
