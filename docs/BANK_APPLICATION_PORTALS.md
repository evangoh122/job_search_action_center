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

Candidate accounts are not shared between employers, even when both employers use Workday.
Passwords, MFA codes, recovery codes, CAPTCHA responses, and legal consent decisions must not
be stored in this repository or in `.env`.

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

CITI_LOGIN_EMAIL=
JPMC_LOGIN_EMAIL=
DBS_LOGIN_EMAIL=
UOB_LOGIN_EMAIL=
OCBC_LOGIN_EMAIL=

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

## Form-capture workflow

1. Select one exact, active vacancy at the bank.
2. Confirm that the role satisfies the S$12,000 monthly salary floor when a conclusive SGD range
   is published. Unknown salaries remain visible for review.
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
- a visible authenticated browser session.

GitHub-hosted runners must not receive reusable portal passwords or browser profiles. CAPTCHA,
MFA, missing required questions, or an unconfirmed success page must stop the workflow for human
review and must not mark the vacancy as applied.

