# Browser-assisted applications

## Safety model

The application system uses an exact-package gate. A role may be discovered or drafted without
authority to apply. Browser autofill requires an immutable package containing the exact vacancy,
answers, cover letter, structurally valid two-page PDF, visual-QA receipt, Drive archive, and
authoritative Sheets row. Approval is short-lived, single-use, and bound to that package hash.
CAPTCHA, missing required questions, changed remote evidence, or a changed PDF blocks progress.
Only the applicant clicks the employer's final Submit control and records the result afterward.

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

`RESUME_PATH` must reference the exact final PDF. The deterministic application harness rejects
DOCX, missing files, and files merely renamed to `.pdf`; there is no fallback résumé upload.

Copy `config/application_answers.example.json` to ignored `data/application_answers.json` and
use each form's visible question label as the JSON key. Never invent an answer; ambiguous or
unmatched questions remain for review.

## Review and approve jobs

```powershell
python application_cli.py eligible
python resume_page_gate.py "<final-resume.pdf>" --record-visual-qa --reviewer "Evan Goh"
python application_cli.py prepare "<job-id-or-dedupe-key>" --resume "<final-resume.pdf>" --salary-reviewed
python application_cli.py show "<package-id>"
python application_cli.py approve "<package-id>"
python application_cli.py open "<package-id>"
python application_cli.py record-submitted "<package-id>"
```

Use `--salary-reviewed` only after personally reviewing an unknown or unparseable salary. The
approval is bound to the immutable package ID, exact PDF SHA-256, exact answers, cover letter,
vacancy, Drive archive, and authoritative Google Sheets row. It expires and is single-use.

## Preview first

Background discovery and `runner.py` are draft-only. Drafts stay in the local review queue and
never enter the authoritative Google Sheets `Applications` tab. Only `application_cli.py prepare`
can create the exact reviewed package and sync its Drive/Sheets evidence.

## Approved browser submission

`open` launches a visible browser, revalidates remote Drive and Sheets authority, stages the exact
approved PDF bytes, recomputes their SHA-256, structurally parses the staged PDF, and only then
passes that staged file to the employer file input. It fills supported fields and pauses. It never
clicks the employer's final Submit control. The applicant reviews the form and clicks Submit.
Afterward, record `record-submitted`; use `record-unknown` if the outcome is uncertain.

## Platform expectations

- Greenhouse and Lever hosted forms: standard fields and resume upload are supported; custom
  questions may require review.
- Workday: multi-step and account-dependent forms commonly require review.
- LinkedIn Easy Apply: login, multi-step questions, and anti-automation controls commonly require
  review. Respect LinkedIn's terms.
- MyCareersFuture: Singpass/account steps and declarations require the applicant's participation.
- Any CAPTCHA stops automation.

Always inspect the application confirmation and tracker status after manual submission.

Discovery may create a tailored cover-letter draft in the local `data/application_drafts.jsonl`
review queue. It is not an authoritative application. The `Applications` Sheet accepts only a
passing immutable package with complete package/resume/answer hashes, two-page proof, and verified
Drive file ID, link, and PDF archive name. Unsupported form fields remain for human review.

When a structured achievement bank is available, the local application draft also records the
resume fit brief, required/preferred keyword-to-evidence map, selected evidence with rubric scores,
evidence gaps, wording change log, and pagination status. Generated content remains
blocked until the exact final PDF renders to two pages and has a hash-bound visual-QA receipt; a
`two-page-targeted` label is never sufficient. The generator never treats keyword overlap as
permission to invent evidence.

Each draft includes a stable `resume_version_id` and the selected `resume_evidence_ids`, allowing
the JSONL queue to record which evidence-backed version was prepared for each vacancy.

## ATS document audit

Audit the rendered Word resume before submission:

```powershell
python -m resume_audit_cli "<updated-master-resume-path>" `
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
- `.github/workflows/application.yml` runs on the protected self-hosted runner and only
  builds and deterministically reviews one exact package (`application_cli prepare`),
  archives the résumé to Drive, and syncs it to Sheets. It stops there.

Approving a prepared package, autofilling the browser, and clicking the employer's final
Submit button are manual, local-only steps (`application_cli show|approve|open|record-submitted`)
that the applicant runs themselves; no workflow automates them. CAPTCHA or an unfilled required
question returns the application for manual review.

## Daily networking review

`.github/workflows/daily-networking.yml` creates a weekday Markdown artifact. It never sends
LinkedIn messages or coffee-chat requests. Store a private JSON value based on
`config/networking_targets.example.json` in the `NETWORKING_TARGETS_JSON` Actions secret.
Each target must include a real company signal, a narrow question, and a measurable applicant
proof point; missing context fails generation instead of producing a generic message.

Create an ignored working copy, replace its placeholders, and generate the packet locally:

```powershell
Copy-Item config\networking_targets.example.json data\networking_targets.json
python -m networking_cli --targets data/networking_targets.json
```

Never place personal proof or contact details in the committed example file. Review every draft in
`data/daily_networking_drafts.md` before sending it manually.
