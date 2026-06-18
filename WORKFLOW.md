# Build Workflow — the autonomous loop

How the three-tier system runs each phase of `ROADMAP.md`. Source of truth for *how we work*
(the *what* lives in `PLAN.md`).

## Roles

- **Claude (Architect)** — owns `PLAN.md` / `ROADMAP.md`, cuts the phase ticket, integrates
  MiMo's code, verifies every DeepSeek finding (the reviewer hallucinates — never apply a
  finding without confirming it against the code), and decides PASS.
- **MiMo (Coder)** — builds as much of the phase as possible. The primary author of code.
- **DeepSeek (Reviewer)** — reviews each build for **usability and edge cases**, not vibes.

## Loop (repeat per phase)

1. **Ticket** — Architect writes `.mimo/tickets/phase-N.md` from `ROADMAP.md`.
2. **Build** — MiMo implements the ticket, producing as many modules as it can in one pass.
3. **Integrate + test** — Architect lands MiMo's code, runs `pytest`. Failing tests bounce
   straight back to MiMo.
4. **Review** — DeepSeek reviews for usability + edge cases against
   `.claude/reviews/phase-N-checklist.md`. Architect filters out false findings; real ones go
   back to MiMo.
5. **Iterate** — repeat 2–4 **until it works**: tests green, no open BLOCKER/MAJOR findings.
6. **Ship** — commit and **push to GitHub** (`origin/main`), one commit per phase:
   `git add -A && git commit -m "phase N: <summary>" && git push`.
7. **Compact** — compact context when it runs long (after each phase, or sooner if needed),
   then continue with the next phase. State carries via `PLAN.md`, `ROADMAP.md`, and the
   committed code — nothing important lives only in chat.

## Hard rules (every iteration)

- `.env` is gitignored and **never** committed. Verify before each push.
- Exclusion gate runs before scoring / any outbound action.
- All outward actions default to `DRY_RUN` / draft; live mode is opt-in.
- No secrets, hardcoded company lists, or thresholds in code — config only.
- Don't start phase N+1 until phase N is pushed.

## Status

- **Phase 0** — Foundation + exclusion gate ✅ shipped
- **Phase 1** — MyCareersFuture source ✅ shipped (live, no token)
- **Phase 2** — Scoring + routing (two parallel tracks) ✅ shipped
- **Phase 3** — HubSpot tracking backbone ✅ shipped (mock-tested; needs `HUBSPOT_TOKEN` for live)
- 40 tests passing. Next: Phase 4 (Hunter.io + Gmail outreach) — needs `HUNTER_API_KEY` + Gmail auth.
