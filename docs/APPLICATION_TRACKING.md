# Application tracking and duplicate prevention

## The rule

Exact matches are identified by normalized company and title, not by job-board URL. The report
also compares the actual responsibilities and requirements across different boards. It uses
character-level TF-IDF similarity plus shared multi-word phrase containment. This catches both
small wording changes and copied requirement blocks embedded inside longer recruiter adverts.

Exact company/title identities are merged and retain every source link. Description matches
are shown in a separate **Likely duplicates from write-up similarity** section. They are not
automatically merged: review the paired listings and apply only once when they describe the
same vacancy.

The report also lists the ten **Closest cross-board write-ups**, including pairs below the
duplicate threshold. This makes the comparison auditable: low similarity indicates materially
different responsibilities even when titles look alike.

Statuses `queued`, `drafted`, `approved`, `submitted`, `applied`, `interviewing`, `offer`, `rejected`,
and `closed` block another application action. Keep statuses accurate; the software cannot
infer every application made outside this repository.

## Safe daily comparison

```powershell
python -m job_compare scan --max-age-days 7
```

This command only fetches listings, updates the local SQLite tracker, and writes
`data/job_comparison.md`. It does not apply, create outreach, or notify anyone.

The report labels handled roles `DO NOT APPLY` and shows every source link beside the one
canonical vacancy.

To rebuild the report without accessing any job board:

```powershell
python -m job_compare report
```

## Import applications made elsewhere

Export or create a CSV with these headers:

```csv
company,title,status,url,source,notes
DBS Bank,VP Data Analytics,applied,https://example.invalid,linkedin,Applied 2026-07-15
```

Then run:

```powershell
python -m job_compare import-history .\path\applications.csv
```

Matching is deliberately conservative. Unmatched rows are counted and left unchanged so
an uncertain match cannot suppress a different vacancy.

## Important limitations

- Public/search feeds show current listings, not a guaranteed complete account history.
- LinkedIn collection requires `APIFY_TOKEN`; without it, the scan still compares
  MyCareersFuture and eFinancialCareers.
- LinkedIn scraping can be subject to LinkedIn's terms and Apify usage charges. Review both
  before enabling it.
- eFinancialCareers may return a human-verification page to automated clients. The connector
  uses its current `/jobs/<term>/in-<location>` route and stops after repeated blocks; when
  blocked, review that board manually and import any resulting application history.
- Reposted vacancies with exactly the same normalized company and title are treated as the
  same role. Review a `closed` record manually if a genuinely new requisition reuses a title.
