# DeepSeek Review Checklist — Phase 0

Review MIMO's Phase 0 output against `PLAN.md` + `.mimo/tickets/phase-0.md`.
Review order: **exclusion correctness → safety → quality.** Block on any ❌.

## 1. Exclusion correctness (BLOCKING — highest priority)

- [ ] `exclusions.py` uses the canonical/alias matcher, NOT bidirectional substring matching.
- [ ] Loads from `config/exclusions.json` (single source of truth) — not a hardcoded list.
- [ ] `JRI` matches `JRI`/`Japan Research Institute` but NOT `JR Industries` / `Mitsui Chemicals`.
- [ ] `logger` is defined; an excluded hit logs at WARNING.
- [ ] Tests cover both positive (excluded) and negative (false-positive) cases.

## 2. Safety / contracts

- [ ] No secrets in code; credentials read from `.env` only.
- [ ] No hardcoded company lists or thresholds — all from `Target-list.json` / config.
- [ ] Repository pattern honored; storage swappable (so HubSpot can slot in at Phase 3).
- [ ] Exclusion gate is positioned to run BEFORE scoring/any outbound action in `runner.py`.

## 3. Code quality

- [ ] Pydantic models, type hints on public functions, no `Any` leakage.
- [ ] Dedupe key is stable and tested.
- [ ] `pytest` green; tests are meaningful, not placeholder asserts.

## Verdict

- **PASS** → Claude verifies vs `PLAN.md`, cuts Phase 1 ticket.
- **CHANGES** → list findings by severity; MIMO revises before Phase 1.
