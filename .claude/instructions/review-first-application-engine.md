# Review-first application engine — mandatory instruction set

These rules govern every feature, agent, CLI command, API route, browser workflow, and UI
action that prepares or opens a job application. Safety rules are product requirements.

## Product outcome

Help the applicant move quickly without applying with the wrong vacancy, résumé, answers, or
identity. The system may prepare and autofill an application, but the applicant owns the final
employer Submit action.

Required flow:

`eligible → prepared → review_passed → sheets_synced → approved → autofill_ready → submitted_manual`

Alternate states: `review_blocked`, `approval_expired`, `approval_revoked`, `captcha_required`,
`submission_unknown`, and `withdrawn`.

Never skip, reorder, or infer a state transition. Never treat opening or autofilling a form as
proof that it was submitted.

## Immutable application package

Before approval, create one immutable package that binds:

- stable local job ID and dedupe key;
- company, title, canonical vacancy URL, employer form URL, and ATS/provider;
- SHA-256 of the complete vacancy description;
- canonical answer map and its SHA-256;
- exact cover-letter text and its SHA-256;
- exact local résumé path, byte length, and full-file SHA-256;
- authoritative master-resume evidence IDs when available;
- explicit salary-review result, schema version, and timestamp.

## Two-page résumé gate

Every master and vacancy-specific résumé must render to exactly two pages. A filename, Word page
break, page-count estimate, or `two-page-targeted` label is not evidence. Render the exact DOCX to
PDF (or inspect the exact final PDF), count PDF pages, and record `resume_page_count = 2` in the
immutable package and Google Sheets row.

Fail closed when rendering is unavailable, the PDF is unreadable, or the count is anything other
than two. Re-run the gate after every content, font, spacing, margin, template, or format change.
Approval and browser autofill must repeat the check against the current artifact.

## Deterministic PDF-only submission contract

DOCX is an editing source only. Every artifact that enters an immutable application package,
Google Drive archive, Google Sheets `Resume File`/`Resume Used` record, or employer file input must
be the same final `.pdf` file. Enforce this through `apply.resume_artifact.require_final_resume_pdf`
at every I/O boundary. It checks the case-insensitive `.pdf` suffix, file existence, and `%PDF-`
byte signature. Never rename DOCX bytes to `.pdf`, never package or upload DOCX, and never fall back
to another résumé when the PDF check fails. A failure blocks the application before browser launch.

Do not achieve two pages by making the résumé unreadable, clipping content, hiding text, shrinking
critical evidence, or changing verified claims. After the mechanical page-count gate passes, render
both pages to PNG and visually inspect every page for legibility, balanced density, clean breaks,
clipping, overlap, missing glyphs, and orphaned headings. Page count is necessary but not sufficient.
Persist both page previews and an append-only visual-QA receipt bound to the exact résumé SHA-256,
page count, reviewer, and timestamp. Approval and opening require that current receipt.

Derive the package ID from canonical JSON containing every bound field. Any changed byte or
field creates a new package. Stored packages are append-only. Never derive artifact integrity
from a filename, short label, or user-supplied hash.

The master résumé and master cover letter are separate authoritative sources. Tailoring may select
or assemble verified blocks from them, but must not rewrite claims, invent evidence, alter metrics,
or silently replace packaged artifacts. Upload only the exact résumé bytes whose hash appears in
the approved package, and derive vacancy-specific cover letters only from approved master sections.

The master cover letter must contain user-approved reusable blocks for: opening/value proposition,
leadership and delivery evidence, technical/data-science evidence, regulated-industry fit, a
company/role motivation placeholder, and closing. Store provenance to verified résumé evidence IDs
for every factual claim. Vacancy tailoring may select blocks and fill the motivation section, but
must not introduce a new factual claim without explicit user review.

When the user announces a new master résumé, immediately invalidate all unsubmitted derived résumé
and cover-letter artifacts and packages from the prior master. Do not infer that a similarly named
or recently generated file is the new master. Require the actual new file/path, verify it, rebuild
its evidence manifest, then create and obtain approval for an updated master cover letter before
generating fresh vacancy-specific packages.

## Deterministic review

Run deterministic review when preparing, approving, and opening a package. Block on:

- package, vacancy, answer, cover-letter, or résumé hash mismatch;
- missing/unreadable résumé or invalid employer form URL;
- missing name, email, or phone;
- password, secret, API key, session token, or authentication data in package fields;
- unsupported or invented résumé/cover-letter claims;
- unresolved salary floor;
- changed vacancy description, URL, job ID, or dedupe key;
- missing Google Sheets persistence receipt;
- failed pagination/render verification for a generated résumé.

AI review is additive and advisory. It may flag unclear answers, weak fit, unsupported claims, or
tone problems, but cannot override a deterministic blocker. Show all findings in plain language.

Every interview or coding-challenge gap found during review must be logged to Google Drive notes
on the same day. A failed write remains visibly pending and retries with an idempotency key.

## Google Sheets authority

Google Sheets is the operational application ledger. SQLite may cache jobs, but must not
authorize or prove an application action.

Before approval or browser launch:

1. Write the exact package to `Applications`, keyed by package ID rather than job ID.
2. Persist package, résumé, answer, and vacancy hashes, review verdict, and SGT timestamp.
3. Record a successful sync receipt bound to the exact package hash.
4. Fail closed if the authoritative read or write is unavailable.

Use versioned headers and narrow, formula-preserving updates. Keep append-only review, approval,
and event history. Package versions must never overwrite one another. Use explicit
`Asia/Singapore` timestamps.

## Google Drive résumé archive

After the exact résumé passes the two-page and integrity gates, but before Sheets sync or approval,
upload that exact file to the dedicated `Job Application Resumes` Drive folder. Name it:

`Evan_Goh_<Company_Name>_<YYYY-MM-DD>.pdf`

Normalize unsafe filename punctuation to underscores and calculate the date in `Asia/Singapore`.
Bind the uploaded file to the immutable application package ID and résumé SHA-256 using Drive
metadata. Retry idempotently by package ID; never create a different archive artifact for the same
package. Verify returned file ID, parent folder, byte length, hash metadata, and Drive URL.

Use user OAuth for an ordinary My Drive folder. Service-account authentication is valid only when
the destination is a Shared Drive folder and the API confirms a `driveId`. Download the archived
binary and recompute SHA-256 at sync, approval, and opening; caller-written metadata alone is not
proof of remote bytes.

The package's `Applications` row must store the Drive file ID, clickable Drive URL under
`Resume Used`, archive filename, résumé SHA-256, and page count. This is the authoritative record of
the résumé actually used for that role. Approval and browser autofill fail closed if the Drive
archive receipt or Sheet link is missing or does not match the package.

## Human approval

Approval must be explicit, limited to one exact package hash, bound to vacancy/résumé/answer
hashes, identified by a cryptographically random nonce, short-lived (30 minutes by default),
single-use, and revocable before use.

Before approval, display company, title, form URL, résumé filename/hash, answer hash, review
verdict, warnings, and expiry. Refuse approval unless deterministic review currently passes and
the exact package is durably synced to Sheets.

Changing any content invalidates approval. Consume approval before the browser opens. A failed or
abandoned browser attempt requires a new approval; never retry silently.

## Browser boundary

Browser automation may open the exact URL in a visible browser, fill packaged values, verify and
upload the exact résumé bytes, capture a screenshot, and pause for applicant review.

Browser automation must never:

- locate, press, or programmatically trigger the final Submit button;
- bypass CAPTCHA, MFA, login, rate limits, or access controls;
- store Workday or employer passwords in `.env`, Sheets, JSON, logs, or screenshots;
- reuse a session or approval for a different vacancy;
- report `submitted` based only on autofill or navigation.

The applicant clicks Submit. Require an explicit `record-submitted` or `record-unknown` action.
When confirmation is uncertain, use `submission_unknown` and never retry automatically.

## UI contract

The UI lists jobs and packages from Google Sheets. Use truthful actions: `Prepare package`,
`Review package`, `Approve once`, `Open and autofill`, and `Record submitted`. Never label
preparation or autofill `Apply automatically`. Disable invalid actions and explain the blocker.

Kimi K3 owns visual and interaction design. Implementation agents preserve Kimi's approved
design contract while enforcing every invariant here. Visual design cannot weaken safety.

## Required verification

Test changed vacancy/answers/résumé bytes, one-page and three-page rejection, unreadable PDFs,
archive filename/date normalization, Drive hash/size/parent verification, idempotent Drive retry,
missing Drive/Sheets sync, review blockers, expired/revoked/consumed approvals, single-use launch,
uploaded artifact hash, absence of final-submit clicks,
append-only package versions, formula preservation, SGT timestamps, credential exclusion,
Python/TypeScript contract parity, and disabled legacy/background live submission.

Run focused safety tests and the complete repository suite. Request independent agent review for
application, approval, browser, credential, or Sheets-authority changes. Reviewers must report
verified findings with exact file references and cross-check assumptions against implemented code.

## Implementation map

- Engine: `apply/review_engine.py`
- CLI: `application_cli.py`
- Fill-only browser: `apply/browser_submitter.py`
- Sheets repository: `store/google_sheets_repo.py`
- Safety tests: `tests/test_review_engine.py`
- Two-page gate: `resume_page_gate.py` and `tests/test_resume_page_gate.py`
- Drive résumé archive: `store/google_drive_resume_archive.py`
- Review checklist: `.claude/reviews/phase-9-sheets-pipeline-instructions.md`
