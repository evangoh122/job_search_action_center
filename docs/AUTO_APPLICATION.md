# Browser-assisted applications

## Safety model

The application system has three independent gates:

1. The routing pipeline must classify the role as Tier A, or the applicant must explicitly
   approve that exact Tier-B role.
2. `AUTO_APPLY_LIVE=true` must explicitly enable live mode.
3. The exact job id or dedupe key must be present in the local approvals file.

Unapproved Tier-B roles remain draft-only. Dry-run remains the default. CAPTCHA, missing required questions, an unconfirmed success page,
or an unsupported form returns the role to human review and does not mark it applied.

Greenhouse and Lever expose application APIs for employers building their own careers sites,
but those submission endpoints require employer-owned API credentials. This project therefore
uses their public hosted forms through an optional local browser session.

## Install browser support

```powershell
python -m pip install -e ".[browser]"
python -m playwright install chromium
```

The browser profile is stored under ignored `data/browser_profile/`. Do not commit it because
it may contain authenticated sessions.

## Applicant profile

Set only in `.env`:

```dotenv
APPLICANT_NAME=
APPLICANT_EMAIL=
APPLICANT_PHONE=
APPLICANT_LOCATION=Singapore
APPLICANT_LINKEDIN=
APPLICANT_GITHUB=
APPLICANT_CURRENT_COMPANY=
APPLICANT_WORK_AUTHORIZATION=
APPLICANT_SPONSORSHIP_REQUIRED=
APPLICANT_NOTICE_PERIOD=
APPLICANT_SALARY_EXPECTATION=
RESUME_PATH=D:\private\resume.pdf
RESUME_URL=
APPLICATION_ANSWERS_JSON=data\application_answers.json
```

Copy `config/application_answers.example.json` to ignored `data/application_answers.json` and
use each form's visible question label as the JSON key. Never invent an answer; ambiguous or
unmatched questions remain for review.

## Review and approve jobs

```powershell
python -m application_cli eligible
python -m application_cli approve "<dedupe-key-from-the-list>"
python -m application_cli list
python -m application_cli revoke "<dedupe-key>"
```

The default approval file is ignored `data/application_approvals.json`.
`eligible` includes new, queued, drafted, and approved Tier-A/B roles. Explicit approval can
promote an existing draft to browser submission; terminal roles are never resubmitted.

## Preview first

Keep live mode disabled:

```dotenv
AUTO_APPLY_LIVE=false
AUTO_APPLY_BROWSER=false
AUTO_APPLY_APPROVALS_FILE=data/application_approvals.json
```

Run `python -m runner`. Tier-A applications are prepared as dry runs without opening a browser
or submitting anything.

## Approved browser submission

Only after reviewing the exact job and profile:

```dotenv
AUTO_APPLY_LIVE=true
AUTO_APPLY_BROWSER=true
AUTO_APPLY_APPROVALS_FILE=data/application_approvals.json
AUTO_APPLY_HEADLESS=false
AUTO_APPLY_BROWSER_PROFILE=data/browser_profile
```

Then run `python -m runner` interactively. Start with a visible browser (`HEADLESS=false`).
The browser fills standard fields, custom label-based answers, and the local resume. It clicks
Submit only for an approved job and marks it applied only when a confirmation message is found.

## Platform expectations

- Greenhouse and Lever hosted forms: standard fields and resume upload are supported; custom
  questions may require review.
- Workday: multi-step and account-dependent forms commonly require review.
- LinkedIn Easy Apply: login, multi-step questions, and anti-automation controls commonly require
  review. Respect LinkedIn's terms.
- MyCareersFuture: Singpass/account steps and declarations require the applicant's participation.
- Any CAPTCHA stops automation.

Always inspect the application confirmation and tracker status after a live run.

Every prepared application also creates a tailored cover-letter package in the local
`data/application_drafts.jsonl` review queue. When Google Sheets is configured, the same package
is upserted into the `Applications` tab with its job key, application link, resume filename,
matched keywords, cover letter, status, and update time. Browser-assisted forms attempt to fill
a visible cover-letter text area; unsupported file-only or custom fields remain for review.

When a structured achievement bank is available, the local application draft also records the
resume fit brief, required/preferred keyword-to-evidence map, selected evidence with rubric scores,
evidence gaps, wording change log, and pagination status. Generated content remains
`two-page-targeted` until the approved Word template is rendered and visually verified; the
generator never treats keyword overlap as permission to invent evidence.

Each draft includes a stable `resume_version_id` and the selected `resume_evidence_ids`, allowing
the JSONL queue to record which evidence-backed version was prepared for each vacancy.

## ATS document audit

Audit the rendered Word resume before submission:

```powershell
python -m resume_audit_cli "resume\Evan Goh - CV 051226.docx" `
  --keyword "data governance" --keyword "generative ai"
```

The audit checks whether text can be extracted, standard section headings are recognized, and
tables, text boxes, multi-column layout, or header/footer content may create parsing risk. Keyword
coverage is reported as a transparent matched/required fraction; it is not presented as an
interview probability or an assurance that a specific ATS will accept the document.
# Automated applications and daily networking

Application submission is deliberately split into two paths:

- The daily job workflow fetches, deduplicates, scores, and writes roles and salary fields to
  Google Sheets. It always forces application dry-run mode.
- `.github/workflows/application.yml` previews one exact job key or, on the protected
  self-hosted runner, opens Playwright for a separately approved live submission.

Live applications require `mode=live`, confirmation `APPLY`, the `job-applications`
environment, the `main` branch, and an exact dedupe key. CAPTCHA or an unfilled required
question returns the application for manual review.

## Daily networking review

`.github/workflows/daily-networking.yml` creates a weekday Markdown artifact. It never sends
LinkedIn messages or coffee-chat requests. Store a private JSON value based on
`config/networking_targets.example.json` in the `NETWORKING_TARGETS_JSON` Actions secret.
Each target must include a real company signal, a narrow question, and a measurable applicant
proof point; missing context fails generation instead of producing a generic message.

Generate the packet locally with:

```powershell
python -m networking_cli --targets config/networking_targets.example.json
```

Replace the example placeholders first, then review every draft in
`data/daily_networking_drafts.md` before sending it manually.
