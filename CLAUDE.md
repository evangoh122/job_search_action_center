# Job Search Action Center — Claude operating instructions

This file is the continuity entrypoint for Claude Code. Read it before making changes.

## First reads

1. `.claude/instructions/review-first-application-engine.md` — mandatory application safety contract.
2. `.claude/reviews/phase-9-sheets-pipeline-instructions.md` — adversarial review checklist.
3. `.claude/ROLE.md` — general architecture preferences. For application-engine work, this file
   and the review-first instruction set expand the older owned-file boundaries in `ROLE.md`.

If instructions conflict, preserve the stricter safety boundary and tell the user what conflicted.

## User goal

Build a Google-Sheets-backed job-search action center targeting an accepted data-science offer by
November 1, 2026. The frontend should list Sheet records and provide a practical workflow for
preparing applications. The master résumé and master cover letter are separate authoritative
sources; application content is assembled from verified blocks and is never casually rewritten.

Kimi K3 is the designated UI/UX designer. Do not independently redesign the visual system. Preserve
Kimi's design decisions while enforcing application safety and accessibility. DeepSeek and MiMo may
be used as adversarial reviewers of Sheets, pipeline, and implementation work.

## Non-negotiable application boundary

The supported workflow is:

`prepare exact package → deterministic review → Google Sheets sync → one-time human approval → visible browser autofill → human clicks Submit → record result`

Claude may review, implement, test, prepare, and autofill. Claude and all automation must never click
the employer's final Submit button, bypass CAPTCHA/MFA/login controls, or silently retry an uncertain
submission.

Never store employer passwords or browser-session secrets in application packages, Google Sheets,
source files, logs, screenshots, or `.env`; those belong in a password manager. Program API keys may
use the existing uncommitted `.env`, but must never enter packages, Sheets, source, logs, or
screenshots.

## Current implementation

- `apply/review_engine.py` — immutable package hashes, deterministic review, Sheets receipt,
  expiring single-use approval, tracker-snapshot revalidation (checked against the last SQLite
  discovery snapshot, not a live re-fetch of the employer posting — changes to the live posting
  between discovery and `open` are caught by the human's visual review at browser-open time, not
  by this automated gate), and browser-open gate.
- `application_cli.py` — commands: `eligible`, `prepare`, `show`, `review`, `approve`, `revoke`,
  `open`, `record-submitted`, and `record-unknown`.
- `apply/browser_submitter.py` — visible-browser fill-only boundary. It contains no final-submit
  click path.
- `apply/auto_apply.py` — legacy live behavior is hard-disabled.
- `runner.py` — background discovery is draft-only; `AUTO_APPLY_LIVE` is ignored.
- `store/google_sheets_repo.py` — Applications rows are keyed by package ID and include package,
  résumé, and answer hashes plus review verdict and SGT timestamp.
- `tests/test_review_engine.py` — tamper, expiry, revocation, replay, Sheets, and no-submit tests.
- `resume_page_gate.py` — may render DOCX editing sources for inspection, but application packaging
  requires the exact final two-page PDF and visual QA.
- `apply/resume_artifact.py` — shared deterministic PDF-only gate used by package preparation,
  Drive archival, Sheets metadata, and the visible browser upload boundary.
- `store/google_drive_resume_archive.py` — archives the exact résumé in the dedicated Drive folder
  as `Evan_Goh_<Company_Name>_<YYYY-MM-DD>` and binds the file to package ID and résumé hash.
- `data/google_drive_config.json` — local non-secret résumé archive folder ID and URL.

Baseline after the July 19, 2026 deterministic PDF-only harness: `py -3.14 -m pytest -q` passed 311 tests.

## Working-tree caution

The repository may contain user-owned and other-agent changes. Inspect `git status --short` before
editing. Preserve unrelated modifications and do not reset, discard, overwrite, or broadly reformat
them. Use targeted patches. Do not commit or publish unless the user asks.

## Validation

For application-engine changes, run:

```powershell
python -m pytest tests\test_review_engine.py tests\test_auto_apply.py tests\test_runner_auto_apply.py tests\test_google_sheets_repo.py -q
python -m pytest tests\test_resume_page_gate.py -q
python -m pytest tests\test_google_drive_resume_archive.py -q
python -m pytest -q
git diff --check
```

Also verify that `apply/browser_submitter.py` has no code that finds or clicks the employer's final
Submit control. Ask an independent agent to review changes affecting packages, approvals, browser
behavior, credentials, or Google Sheets authority, because the user explicitly requested agents to
check one another's work.

## Immediate application handoff

The current priority candidate is:

- Company: UOB
- Role: First VP, GenAI Engineer/Scientist Lead, Innovation Group
- Tracker score/tier: 81.5 / Tier B
- Dedupe key: `uob|first vp genai engineer scientist lead innovation group|4a3bd7d48519`
- URL: `https://www.linkedin.com/jobs/view/4379179473`
- Résumé status: BLOCKED pending the user's updated master résumé. The previous master
  `resume/Evan Goh - CV 051226.docx` and derived UOB artifacts under
  `outputs/applications/uob-genai-lead/` are stale and must not be packaged, approved, or uploaded.
- Cover-letter status: BLOCKED pending creation and user approval of an updated master cover
  letter based on the updated résumé. There is no authoritative master cover-letter file in the
  workspace. Do not treat automatically generated text in `apply/tailor.py` as the approved master.

Salary is unknown, the updated master résumé has not been added, and the updated master cover
letter has not been created and approved. Do not clear any blocker implicitly. Obtain the résumé,
verify/render it, create the master cover letter from verified résumé claims, obtain user approval
for that master, and only then create new vacancy-specific artifacts. Ask the user to confirm that
they reviewed salary uncertainty before using `prepare --salary-reviewed`. Show the exact package
and review findings before accepting application approval.

The dedicated archive folder is an ordinary My Drive folder. Local application automation must use
user OAuth via `GOOGLE_DRIVE_CLIENT_ID`, `GOOGLE_DRIVE_CLIENT_SECRET`, and a Drive-scoped
`GOOGLE_DRIVE_REFRESH_TOKEN`. A service account is permitted only with a Shared Drive folder; do not
claim that sharing an ordinary My Drive folder with a service account makes uploads reliable.
The current My Drive OAuth flow needs the full Drive scope to reach the pre-existing dedicated
folder. Keep these credentials local and use a dedicated Google identity if least-privilege
isolation is required; do not broaden the archive folder or expose the refresh token.

Example sequence only after the updated master résumé is installed, the master cover letter is
approved, new UOB artifacts are created, and the user explicitly clears salary review:

```powershell
python resume_page_gate.py "<new-verified-uob-resume.pdf>" --record-visual-qa --reviewer "Evan Goh"
python application_cli.py prepare "uob|first vp genai engineer scientist lead innovation group|4a3bd7d48519" --resume "<new-verified-uob-resume-path>" --salary-reviewed
python application_cli.py show <package-id>
python application_cli.py approve <package-id>
python application_cli.py open <package-id>
python application_cli.py record-submitted <package-id>
```

The exact final packaged artifact must currently be a PDF. DOCX may be used as an editing source,
but it must be rendered to PDF before the two-page gate and visual review. The harness rejects
DOCX and renamed non-PDF bytes before packaging, archival, Sheets sync, or employer upload.

`open` only fills and pauses. The user inspects the employer form and clicks Submit personally.
