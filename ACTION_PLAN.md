# Job Application Action Plan

> **Authoritative safety rule:** automated final submission is permanently disabled. The
> `Prepare application package` workflow and `application_cli.py` only build an exact,
> immutable package, run a deterministic review, archive the résumé to Google Drive, and sync
> the package to Google Sheets. A human must separately `approve` the package, then `open` it to
> autofill a visible local browser — the human clicks the employer's Submit button themselves.
> No automation, workflow, or script clicks it. Running `runner.py` locally or on the daily
> schedule only performs draft discovery and must not prepare, approve, or submit anything.

## Current Readiness

- Automation build is usable: `python -m pytest -q` passes with 157 tests.
- Daily job pull pipeline exists and can write to Google Sheets when credentials are valid.
- Local tracker contains 146 jobs.
- Current local queue: 15 Tier B jobs, 0 Tier A jobs, 131 below-tier jobs.
- Existing draft queue: 28 application drafts and 2 outreach drafts.
- Resume source exists locally in `resume/` and private achievement material exists in `data/`.

## Outstanding Before Applying

1. Review and approve the current application drafts.
   - Start with the 15 Tier B jobs in `data/jobs.sqlite`.
   - The strongest current matches are Accenture, Deloitte, GovTech, Synechron, UOB, Bank of Singapore, and Accenture public-services roles.
   - Update each job status after action so the tracker stops treating everything as `new`.

2. Refresh today's job feed.
   - Run `python runner.py` or `python -m runner`.
   - Confirm the Google Sheet receives new rows.
   - Check `data/new_roles.json` after the run.

3. Fix or verify live integration credentials.
   - Apify/LinkedIn previously returned `403 Forbidden`; verify the actor/token still has access.
   - Gmail network scraping previously returned `403 Forbidden`; refresh OAuth scopes/token if networking contact scraping matters.
   - Hunter, HubSpot, Google Sheets, Telegram, applicant profile, and resume URL variables are present in `.env`, but live behavior still needs a fresh run confirmation.

4. Finalize application package hygiene.
   - Use the naming convention from `HANDOFF.md`: `Evan_Resume{mmddyyyy}_{COMPANY_ABBR}.docx`.
   - Ensure each package includes email, phone, LinkedIn, GitHub, location, and resume link.
   - Save the application link back to the Google Sheet row.

5. Decide live-apply posture.
   - Keep `AUTO_APPLY_LIVE` off for ordinary local and scheduled runs. Use only the protected
     exact-vacancy workflow for any approved live attempt after at least 5 packages are reviewed.
   - Current queue has no Tier A jobs, so the immediate workflow is draft-review-submit.

## First 48 Hours

1. Run the pipeline and refresh the sheet.
2. Review the top 10 Tier B jobs by score.
3. Build or validate a tailored resume for each top role.
4. Submit 5 high-confidence applications manually.
5. Send or approve outreach drafts for those same 5 companies.
6. Mark statuses in the tracker/sheet: `drafted`, `applied`, `outreach_sent`, or `closed`.

## First Week Cadence

- Daily morning: run the job pull and check top matches.
- Daily application block: submit 5-8 high-quality applications, not more until tracking is clean.
- Daily outreach block: contact recruiter/hiring manager for every submitted application where contact data is available.
- End of day: update statuses, links, and notes in the sheet.
- Weekly review: remove stale/low-fit roles, tune keywords, and add missing target companies.

## Immediate Priority List

1. Accenture Southeast Asia - Data SME - score 87.2.
2. Deloitte - T&T Senior Consultant, AI & Data - score 87.2.
3. Accenture Southeast Asia - Full Stack AI Engineer Senior Manager - score 87.2.
4. GovTech Singapore - Senior / Data Engineer (AGC) - score 83.4.
5. Synechron - Data Architect - score 83.4.
6. UOB - First VP, GenAI Engineer/Scientist Lead - score 81.5.
7. Bank of Singapore - Team Lead, Data Science & Advanced Analytics VP - score 80.7.
8. Accenture Southeast Asia - Data Engineering/Architecture Manager - score 79.6.

## Commands

```powershell
python -m pytest -q
python runner.py
Get-Content data\new_roles.json
```
