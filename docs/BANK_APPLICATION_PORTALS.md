# Bank application portal setup

This guide records the application platforms and safe browser-assisted workflow for the
priority banks. It supports preparing and filling an application; it does not authorize a
submission. Every live submission still requires an exact vacancy approval and final review.

## Portal map

| Bank | Platform | Public portal | Automation expectation |
|---|---|---|---|
| Citi | Workday | `citi.wd5.myworkdayjobs.com` | Multi-step Workday flow; login, MFA, CAPTCHA, and declarations require handoff. |
| J.P. Morgan | Oracle Cloud Candidate Experience | `jpmc.fa.oraclecloud.com` | Oracle flow, not Workday; common profile plus requisition-specific questions. |
| DBS | Workday | `dbs.wd3.myworkdayjobs.com` | Multi-step Workday flow with a separate DBS candidate account. |
| UOB | Workday | `uobgroup.wd3.myworkdayjobs.com` | Multi-step Workday flow with a separate UOB candidate account. |
| OCBC | Oracle Taleo | `ocbc.taleo.net` | Separate Taleo adapter and candidate account are required. |
| Deutsche Bank | Workday | `db.wd3.myworkdayjobs.com` | Workday account and job-specific questions. |
| Morgan Stanley | Workday | `ms.wd5.myworkdayjobs.com` | Workday account and job-specific questions. |
| MUFG | Workday | `mufgub.wd3.myworkdayjobs.com` | Workday account; professional and early-career sites are separate. |
| Mizuho | Workday | `mizuhogroup.wd102.myworkdayjobs.com` | Workday account for the Mizuho Group external site. |
| Wells Fargo | Workday | `wf.wd1.myworkdayjobs.com` | Workday account and job-specific questions. |
| State Street | Workday | `statestreet.wd1.myworkdayjobs.com` | Workday account and job-specific questions. |
| Northern Trust | Workday | `ntrs.wd1.myworkdayjobs.com` | Workday account and job-specific questions. |
| BlackRock | Workday | `blackrock.wd1.myworkdayjobs.com` | Financial-services target using a Workday professional-careers site. |

Candidate accounts are not shared between employers, even when both employers use Workday.
Passwords, MFA codes, recovery codes, CAPTCHA responses, and legal consent decisions must not
be stored in this repository or in `.env`.

Automated Workday discovery is restricted to listings whose Workday `locationsText` contains
`Singapore`. A missing, blank, or non-Singapore `WORKDAY_LOCATION` value cannot disable or
broaden this production constraint.

## Information to prepare

Store reusable, non-password application data in the ignored local `.env`:

- legal name, email, phone, and location;
- LinkedIn and GitHub URLs;
- current employer;
- work authorization and sponsorship requirement;
- notice period and salary expectation;
- local path to the approved ATS-safe resume;
- path to reviewed answers for recurring application questions;
- persistent local browser-profile path.

Employment history, education, certifications, languages, referrals, conflicts of interest,
criminal/regulatory declarations, disability/accommodation information, demographic questions,
and consent answers must be verified by the applicant. Never infer or invent an answer.

## Local environment settings

The local `.env` should contain the following settings. Leave a value blank until it has been
verified by the applicant.

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
RESUME_PATH=
APPLICATION_ANSWERS_JSON=data/application_answers.json
WORKDAY_LOCATION=Singapore

CITI_LOGIN_EMAIL=
JPMC_LOGIN_EMAIL=
DBS_LOGIN_EMAIL=
UOB_LOGIN_EMAIL=
OCBC_LOGIN_EMAIL=
DEUTSCHE_BANK_LOGIN_EMAIL=
MORGAN_STANLEY_LOGIN_EMAIL=
MUFG_LOGIN_EMAIL=
MIZUHO_LOGIN_EMAIL=
WELLS_FARGO_LOGIN_EMAIL=
STATE_STREET_LOGIN_EMAIL=
NORTHERN_TRUST_LOGIN_EMAIL=
BLACKROCK_LOGIN_EMAIL=

AUTO_APPLY_LIVE=false
AUTO_APPLY_BROWSER=false
AUTO_APPLY_HEADLESS=false
AUTO_APPLY_BROWSER_PROFILE=data/browser_profile
AUTO_APPLY_APPROVALS_FILE=data/application_approvals.json
```

The portal-specific email variables are identifiers only. Authentication passwords remain in
the user's password manager, and the user completes initial sign-in, MFA, and acceptance of each
portal's terms in the visible browser. The ignored persistent browser profile can retain the
resulting authenticated sessions.

Treat `AUTO_APPLY_BROWSER_PROFILE` as a credential. Restrict its filesystem permissions to the
runner account, store it only on an encrypted local volume, and never upload it as an artifact,
include it in backups, or use it on a shared runner. If the runner is lost or another user may
have accessed the directory, revoke the saved portal sessions and delete the profile before
creating a new one.

## Form-capture workflow

1. Select one exact, active vacancy at the bank.
2. Confirm that a conclusive normalized SGD range reaches the S$12,000 monthly floor. Unknown or
   unparseable salaries remain visible for review but cannot proceed to live execution unless the
   applicant records an explicit override for that exact vacancy with
   `python -m application_cli salary-override "<job-key>"`.
3. Open the employer's official application portal in a visible browser.
4. The applicant completes account creation, password entry, MFA, CAPTCHA, and legal consent.
5. Capture the common profile sections and all visible requisition-specific question labels.
6. Add only applicant-verified reusable answers to the ignored
   `data/application_answers.json` file.
7. Fill the form and stop at its final review page. Record missing or ambiguous fields.
8. Submit only after the applicant explicitly approves that exact vacancy and confirms the final
   rendered form.

## CI/CD boundary

Scheduled discovery is always dry-run. A live browser application must run on the protected
self-hosted Windows runner and requires all of the following:

- the `job-applications` protected environment;
- `mode=live`;
- confirmation value `APPLY`;
- the exact job dedupe key;
- an approval entry for that exact vacancy;
- a conclusive normalized salary meeting the S$12,000 monthly floor, or a separately recorded
  salary-review override for that exact vacancy;
- a visible authenticated browser session.

GitHub-hosted runners must not receive reusable portal passwords or browser profiles. CAPTCHA,
MFA or missing required questions must stop the workflow for human review. An unconfirmed
post-submit page must be stored as `submission_unknown`, must not be marked applied, and must
never be retried automatically.
