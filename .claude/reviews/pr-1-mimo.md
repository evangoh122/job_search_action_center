# mimo review of PR #1 (model: mimo-v2-pro)

## Critical

1. **`store/google_sheets_repo.py`** — `from_service_account_file` / `from_service_account_info` refresh the token once at construction time and cache it forever. Google service-account access tokens expire after **1 hour**; any run lasting longer (or a long batch of `upsert_job` calls) will start getting `401 Unauthorized` mid-run.
   **Fix:** Refresh the token on each request (or when a 401 is received), e.g. store the `Credentials` object and call `creds.refresh(Request())` inside `_default_http` or on demand.

2. **`network/gmail_drafter.py` / `network/gmail_network.py`** — Same one-shot token problem: the OAuth2 access token obtained via `refresh_gmail_access_token` is cached indefinitely. Gmail access tokens expire in ~1 hour; a long outreach run or large network scrape will silently start failing with 401s.
   **Fix:** Reuse the pattern from #1 — store the OAuth credentials object, or re-call the token provider on `401`.

## High

3. **`store/airtable_repo.py`, `_eq` method** — The formula builder escapes only `"` → `" "` to prevent Airtable formula injection. Backslashes, newlines, or curly braces in user-controlled values (contact names, emails) can still break or inject into the `filterByFormula`. This is user-supplied data flowing through a public API.
   **Fix:** Use Airtable's `SEARCH()` function or percent-encode the value properly. At minimum, also escape `\` and newlines:
   ```python
   safe = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
   ```

4. **`network/gmail_network.py`, `_company_from_email`** — Extracts only `domain.split(".")[-2]`, which yields wrong results for multi-part TLDs or subdomains: `a@corp.hsbc.com` → `"Hsbc"`, but `a@uk.hsbc.co.uk` → `"Co"` (should be `"Hsbc"`). This corrupts the `Company` column in the Networking Tracker.
   **Fix:** Use a proper public-suffix list library (`tldextract`) or a heuristic that skips known suffixes (`.co.uk`, `.com.sg`, etc.):
   ```python
   import tldextract
   ext = tldextract.extract(domain)
   return ext.domain.replace("-", " ").title()
   ```

5. **`store/google_sheets_repo.py`, `_upsert_row`** — Reads **all** rows of column A (`A2:A`) on every single upsert to find the matching key. For a tracker with thousands of jobs/contacts, this is O(n) API calls per upsert — extremely slow and will hit Sheets API rate limits (300 requests/minute).
   **Fix:** Fetch column A once at the start of each batch run, cache the mapping `{key: row_number}`, and update it as rows are written.

6. **`scoring.py`, `_profile_doc`** — Decorated with `@lru_cache(maxsize=1)`. `RESUME_SUMMARY` is loaded from `os.environ` inside the cached function. If the environment variable isn't set at import time (common in testing / lazy import), it caches the empty string and all subsequent calls return `""`, making every TF-IDF score zero. Re-running with a populated env var won't fix it without restarting the process.
   **Fix:** Either remove the cache, or key it on the actual value of `RESUME_SUMMARY`.

## Medium

7. **`.github/workflows/daily-jobs.yml`** — `continue-on-error: true` on the "Refresh networking contacts" step masks **all** failures, including real bugs (schema changes, data corruption). Only authentication-not-configured should be a silent skip.
   **Fix:** Wrap the step in a conditional: `if: env.GMAIL_CLIENT_ID != ''` so it's skipped entirely when creds are absent, and let real errors fail the job.

8. **`scoring.py`, `tfidf_similarity`** — A new `TfidfVectorizer` is instantiated and fitted **per job**. With hundreds of jobs per run, this is needlessly slow and produces non-comparable TF-IDF spaces (IDF weights differ per pair).
   **Fix:** Fit the vectorizer once on the profile doc's vocabulary, then `transform` each job text individually.

9. **`tests/test_scoring.py`** — The diff is truncated at `def test_matc` — this test function is incomplete and will cause a `SyntaxError` when the test suite runs.
   **Fix:** Complete the truncated test method.

10. **`migrate_airtable_to_sheets.py`** — Each Airtable table is fetched twice: once here via `_fetch_all`, and the same function is exported and used by `extract_airtable.py`. If `_fetch_all` is called from both scripts on the same run, it's redundant, but more importantly there's no pagination timeout or max-records guard — a very large Airtable base could OOM or exceed the 30-minute job timeout.
    **Fix:** Add a `max_records` parameter to `_fetch_all` as a safety cap.

11. **`store/google_sheets_repo.py`, `_upsert_row` update path** — When updating an existing row, the range is built as `A{match}:{last}{match}` where `last = _col_letter(len(row))`. If the new row has **fewer** columns than the existing row, trailing old columns remain, causing stale data to persist.
    **Fix:** Also clear columns beyond the new row width, or always write the full header-width range.

12. **`config/exclusions.json`** — `"Ernst Young"` is missing the ampersand; the canonical name is `"Ernst & Young"`. Any job listing with the correct company name won't match.
    **Fix:** `"canonical": "Ernst & Young", "aliases": ["EY"]`.

## Low

13. **`network/gmail_network.py`, `_merge`** — When `date == existing.last_contacted`, the source is never updated. If a more informative source (e.g., `gmail:sent`) has the same date as a prior `gmail:received`, the less-informative one wins based on encounter order.
    **Fix:** Add a tiebreaker: `if date >= existing.last_contacted:`.

14. **`sources/linkedin.py`, `_items` static method** — Duplicates the inline `isinstance(resp, dict)` logic already in `_default_post`. Dead/confusing code.
    **Fix:** Remove the static method and use `_default_post`'s return directly.

15. **`store/hubspot_repo.py`** — `upsert_contact` now filters on `email` instead of `contact_id`. If two different `Contact` objects share the same email (e.g., a recruiter who changed roles), the second upsert silently overwrites the first's `jobtitle`/`company`.
    **Fix:** Accept this as the intended dedupe strategy, but document the behavior.

16. **`.github/workflows/backup-sheet.yml`** — Comment says "Runs roughly every 15 days" but the cron `0 2 1,16 * *` runs on the 1st and 16th, which is every ~15 days only in non-February months. Minor, but the comment is misleading in months with 28/31 days.

---

**Overall verdict:** The PR introduces solid automation but has two critical token-expiry bugs (Sheets + Gmail) that will cause silent failures in production after ~1 hour, plus a formula-injection vector in Airtable and a TF-IDF caching trap — all should be fixed before merge.
