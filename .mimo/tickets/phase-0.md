# MIMO Ticket — Phase 0: Foundation & Exclusion Gate

Read `PLAN.md`, `ROADMAP.md`, and `.mimo/coder_instructions.md` first. Implement **only** Phase 0.
Stop for review when the exit criteria are met. Do not start Phase 1.

## Build

1. **Project skeleton**
   - `pyproject.toml` (Python 3.11+), deps: `pydantic`, `sqlalchemy`, `python-dotenv`,
     `httpx`, `pytest`, `structlog`.
   - Package layout per `coder_instructions.md §3` (`sources/`, `store/`, `scoring.py`,
     `routing.py`, `exclusions.py`, `normalize.py`, `runner.py`).

2. **Typed models** (`models.py`)
   - `RawJob`, `Job` (with `company_canonical`, `dedupe_key`, `score`, `tier`, `status`,
     `ats_type`, `posted_at`, `url`), `Contact`. Pydantic, no `Any` on public fields.

3. **Storage** (`store/repository.py`)
   - Repository interface + `SqliteRepository`. CRUD for jobs + contacts, dedupe on `dedupe_key`,
     daily-cap counters.

4. **Config + logging**
   - `.env` loader (no secrets in code). `config.py` loads `Target-list.json` and
     `config/exclusions.json`. structlog setup.

5. **Exclusion gate** (`exclusions.py`)
   - Implement exactly the FIXED canonical/alias matcher from `coder_instructions.md §3`.
   - Loads `config/exclusions.json`.

6. **`runner.py` stub** — wires the pipeline order with no-op sources for now.

## Tests (required)

- `test_exclusions.py`: assert excluded → `SMBC`, `Sumitomo Mitsui Banking Corp`, `SMFG`,
  `SMBC Nikko`, `JRI`, `Japan Research Institute`. Assert NOT excluded → `JR Industries`,
  `Smbcorp Tech`, `Mitsui Chemicals`, `Research Institute of America`, `""`.
- `test_repository.py`: insert/get/dedupe + daily-cap counter.

## Exit criteria

- `pytest` green. Exclusion false-positive tests pass. Repo dedupe works.
- `python -m runner` runs end-to-end (no-op) without error.
- No secrets, no hardcoded company lists, no hardcoded thresholds.

## Questions to answer before coding (from `coder_instructions.md §6`)

1. Simple ATS allowlist for Tier A? (proposed: Greenhouse, Lever)
2. Resume tailoring: template-swap or LLM-rewrite?
3. Outreach: always human-approved, or auto-send for some?
