# Job Search Action Center

A private, local-first tracker for finding Data/AI and finance roles, comparing listings
across job boards, and preventing duplicate applications.

The comparison workflow currently supports:

- MyCareersFuture (public search API)
- LinkedIn (optional Apify integration)
- eFinancialCareers Singapore (best effort; its human-verification layer may block automation)
- Existing Greenhouse and Workday sources in the full pipeline

## Duplicate protection

The same vacancy often has a different URL and slightly different title on every board. This
project merges exact company/title identities, then compares the full responsibilities and
requirements with character-level TF-IDF and shared multi-word phrase containment. The second
signal catches copied requirement blocks embedded inside a longer recruiter advert.
Write-up matches are review candidates rather than automatic merges, because recruiters may
reuse similar templates for genuinely different vacancies.
An existing status such as `drafted`, `applied`, or `interviewing` is preserved when listings
are refreshed and blocks another application action.

Matching is intentionally conservative and reviewable. See
[`docs/APPLICATION_TRACKING.md`](docs/APPLICATION_TRACKING.md) for the identity rule,
application-history import, statuses, and limitations.

## Quick start

Requirements: Python 3.11 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -q
```

Create a local `.env` only for integrations you intend to use:

```dotenv
JOBS_DB_PATH=data/jobs.sqlite
APIFY_TOKEN=
EFINANCIALCAREERS_LOCATION=Singapore
```

`.env`, databases, resumes, exports, tokens, and generated reports are ignored by Git.

## Compare the three boards safely

```powershell
python -m job_compare scan --max-age-days 7
Get-Content data\job_comparison.md
```

This command fetches and compares listings only. It does **not** submit applications,
generate outreach, or send notifications. If `APIFY_TOKEN` is absent, LinkedIn is skipped
and the other sources still run. A blocked source is reported and does not invalidate data
already stored from the other boards.

Description enrichment is enabled by default. Use `--titles-only` only when a faster,
less-complete scan is acceptable.

Rebuild the comparison report without network access:

```powershell
python -m job_compare report
```

Import applications made manually or through another platform:

```powershell
python -m job_compare import-history .\private\applications.csv
```

## Full automation pipeline

```powershell
python -m runner
```

The full pipeline discovers, scores, routes, stores, and optionally drafts actions. External
integrations are enabled only when their environment variables are present. Live auto-apply
is opt-in; keep `AUTO_APPLY_LIVE` unset or false until the generated packages have been
reviewed carefully.

Browser-assisted applications also require an explicit approval for each exact job. See
[`docs/AUTO_APPLICATION.md`](docs/AUTO_APPLICATION.md) for profile fields, Playwright setup,
approval commands, platform limitations, and the visible-browser-first rollout procedure.

High-level flow:

```text
job boards -> exclusion gate -> normalize/deduplicate -> score -> tracker
                                                    -> application draft (optional)
                                                    -> outreach draft (optional)
```

## Project layout

| Path | Purpose |
|---|---|
| `sources/` | Job-board and ATS collectors |
| `matching.py` | Cross-board identity and provenance merging |
| `job_compare.py` | Safe scan, report, and history-import CLI |
| `store/` | SQLite, Google Sheets, Airtable, and HubSpot repositories |
| `apply/` | Resume/application drafting and gated submission |
| `application_cli.py` | Review and manage per-job application approvals |
| `network/` | Optional outreach and notification integrations |
| `tests/` | Offline unit tests with injected HTTP fakes |
| `docs/` | Operating and private-repository guidance |

## Privacy and GitHub

This project is designed for a **private repository**. Before pushing, follow
[`docs/PRIVATE_REPOSITORY.md`](docs/PRIVATE_REPOSITORY.md). In particular, inspect staged
files and never commit `.env`, service-account files, application data, resumes, or SQLite
databases. Private visibility reduces exposure but is not a substitute for secret hygiene.

## Phone/Codespaces workflow

After the private repository is on GitHub, create a Codespace from **Code → Codespaces**.
The dev container installs the package and test dependencies. Add credentials only as
Codespaces secrets, never as files committed to the repository.

```powershell
python -m pytest -q
python -m job_compare report
```

Avoid running live scans from a Codespace unless its secrets and network usage are understood.
