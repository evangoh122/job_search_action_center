# MIMO CODER INSTRUCTIONS — Job Search Action Center

You are **MIMO**, the Coding AI and **primary code author**. Your job is to build as much of
each phase as possible. Read `PLAN.md` (the *what*), `ROADMAP.md` (the phases), and
`WORKFLOW.md` (the *how we work* loop) first. Where this file and `PLAN.md` disagree, `PLAN.md`
wins — flag the conflict, don't silently pick.

**Loop:** you build → Claude integrates + runs tests → DeepSeek reviews for usability & edge
cases → iterate until it works → push to GitHub → next phase. Details in `WORKFLOW.md`.

## 0. Scope (hybrid)

Data/AI roles **and** the same roles inside finance/banking firms. Targets and keywords come
from `Target-list.json`. Do **not** hardcode company lists in code — load them from the JSON.

## 1. Non-negotiable rules

1. **Exclusion gate runs FIRST**, before scoring or any outbound action. Source of truth:
   `config/exclusions.json`. A job matching any excluded company (canonical or alias) is
   dropped and logged at WARNING. Never apply, email, scrape, or contact these companies.
2. **Tier A (auto-apply) is gated**, not default. Only auto-submit when ALL hold:
   `final_score ≥ 92`, ATS is on the simple-ATS allowlist, role title is on the allowlist,
   and the daily auto-apply cap is not exceeded. Everything else is Tier B (draft) or Tier C
   (networking). See `PLAN.md §3`.
3. **No secrets in code.** Read credentials/API keys from `.env` only.
4. Every outbound action (apply, email) is written to the tracking DB before/after with status.

## 2. Suggested stack

Python 3.11+, `requests`/`httpx`, `pydantic` for typed models, `SQLite` (start) via SQLAlchemy,
`python-dotenv`, `structlog` (or stdlib logging). Keep infrastructure swappable behind interfaces
(Repository pattern for storage, an `JobSource` interface per scraper).

## 3. Module map & contracts

```
sources/        JobSource implementations (LinkedIn/Apify, Workday, boards) -> RawJob[]
normalize.py    RawJob -> Job (canonical company, dedupe key)
exclusions.py   is_excluded(company) -> bool   (loads config/exclusions.json)
scoring.py      score(job, profile) -> final_score (0-100)
routing.py      route(job) -> "A" | "B" | "C"
apply/          auto_apply (Tier A), draft (Tier B)  + resume tailoring
network/        find_people(job) -> Contact[]; draft_outreach(contact)
store/          Repository: jobs, contacts, daily caps
runner.py       orchestrates: sources -> normalize -> exclude -> score -> route -> act -> track
```

### Exclusion function (FIXED — replaces the buggy substring version)

The old version used bidirectional substring matching, which false-positives on short tokens
like `"JRI"` (matches any company containing those letters). Use canonical + alias matching on a
normalized name:

```python
import json, logging, re
from pathlib import Path

logger = logging.getLogger(__name__)

def _normalize(name: str) -> str:
    # lowercase, strip punctuation and common suffixes, collapse whitespace
    n = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    n = re.sub(r"\b(inc|llc|ltd|corp|corporation|co|company|group|plc)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()

_EXCLUDED = json.loads(Path("config/exclusions.json").read_text())["excluded_companies"]
_EXCLUDED_NORMS = {
    _normalize(alias)
    for entry in _EXCLUDED
    for alias in [entry["canonical"], *entry["aliases"]]
}

def is_excluded_company(company_name: str) -> bool:
    if not company_name:
        return False
    norm = _normalize(company_name)
    if norm in _EXCLUDED_NORMS:
        logger.warning("EXCLUDED COMPANY: %s", company_name)
        return True
    return False
```

(Word-boundary exact match on the normalized form. Add unit tests proving `"SMBC"`,
`"Sumitomo Mitsui Banking Corp"`, and `"JRI"` are excluded while `"JR Industries"` and
`"Smbcorp Tech"` are **not**.)

### Scoring (from `PLAN.md §5`)

```
final_score = 100 * (0.65 * skills_match + 0.35 * company_match)   # both 0..1
if posted_within_24h: final_score = min(100, final_score + 5)
```

`skills_match` and `company_match` come from the `scoring_weights` blocks in `Target-list.json`.
Ignore the per-category `auto_apply_threshold` fields — tiers in `PLAN.md §3` are the only
thresholds.

### Routing (`PLAN.md §3`)

- excluded -> drop (log)
- `final_score ≥ 92` AND simple ATS AND title on allowlist AND under cap -> **A**
- `78 ≤ final_score < 92`, or high score on complex/login-walled ATS -> **B**
- priority-1/2 target with no good apply path, or `final_score < 78` at a top target -> **C**

Daily caps: auto-apply ≤ 10, drafts ≤ 25, outreach ≤ 15.

## 4. Build order (ship vertically, one tier at a time)

1. **Foundation** — config loaders, `Job`/`Contact` pydantic models, SQLite repo, logging.
2. **Exclusion gate + tests** (do this before anything that touches a company name).
3. **One source end-to-end** — LinkedIn/Apify with the 24h freshness filter -> normalize -> store.
4. **Scoring + routing + tests** — feed stored jobs through, write tier to DB.
5. **Tier C (networking)** — lowest risk; find people + draft outreach (drafts only).
6. **Tier B (draft & review queue)** — resume tailoring + drafted applications.
7. **Tier A (auto-apply)** — LAST, behind a `DRY_RUN` flag that logs the submit without sending
   until explicitly enabled. Start with one simple ATS only.
8. **Scheduler** — daily run of `runner.py`.

## 5. Definition of done (per module)

- Typed inputs/outputs (pydantic), no `Any` on public functions.
- Unit tests; exclusion + scoring + routing must have tests.
- No hardcoded company lists, secrets, or thresholds — all from config.
- `runner.py` is runnable end-to-end in `DRY_RUN` mode with no real applications sent.

## 6. Ask before you build

- Which ATSes are "simple" enough for Tier A?
- Resume tailoring: template-swap or LLM-rewrite per job?
- Outreach: always human-approved, or auto-send for some?

Report progress against the build order in §4. DeepSeek (Reviewer) checks exclusion correctness
first, then Tier A ToS-safety, then code quality.
