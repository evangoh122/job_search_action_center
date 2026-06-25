# deepseek review of PR #1 (model: deepseek-chat)

## CRITICAL

1. **`backup_sheet.py` line 15-17** - Secrets leaked to stdout: `print(f"backed_up_tabs={len(written)}")` could expose backup metadata in logs.  
   **Fix:** Remove the print statement or redirect to logging only.

2. **`network/gmail_network.py` line 172-175** - Hardcoded URL construction with `sep = "&" if "?" in _LIST_URL else "?"` is fragile and incorrect - `_LIST_URL` never has a `?`.  
   **Fix:** Use proper URL construction with `urllib.parse.urlencode` for the full URL.

3. **`store/google_sheets_repo.py` line 135-140** - `_ensure_ready` is called inside `_upsert_row` but never sets `_ready = True`. This creates a race condition where every upsert re-checks tabs.  
   **Fix:** Set `self._ready = True` at end of `_ensure_ready()`, or remove the flag and call once in constructor.

## HIGH

4. **`runner.py` line 100-101** - `_track_contact` returns `None` when both `crm` and `tracker` are None. Creates silent failures in `contact_rec_by_email` mapping.  
   **Fix:** Add explicit `if crm or tracker` guard before calling.

5. **`network/gmail_drafter.py` line 89-92** - `_access_token()` returns empty string if both `_cached_token` and `_token_provider` are None. Causes Gmail API calls to fail without auth.  
   **Fix:** Raise `ValueError("No authentication method configured")` instead.

6. **`migrate_airtable_to_sheets.py` line 133-136** - Airtable record ID format assumed to be `[0]` for linked records. If Airtable returns empty list or different format, `IndexError` occurs.  
   **Fix:** Use `(f.get("Job") or [None])[0]` and handle None case.

7. **`scoring.py` line 47-49** - `_match_text` calls `_relevant_section` on every job, which uses regex with Unicode smart quotes (`â€™`). If HTML/markup descriptions are passed, regex won't match properly.  
   **Fix:** Add HTML unescaping or strip tags before applying regex.

## MEDIUM

8. **`network/gmail_network.py` line 65** - `parsedate_to_datetime` returns `None` for invalid dates, causing `AttributeError` on `.date()`.  
   **Fix:** Check for `None` before calling `.date()`.

9. **`store/google_sheets_repo.py` line 285-288** - `_titles` makes a GET request that could fail if backup spreadsheet is not shared with service account. No error handling.  
   **Fix:** Wrap in try/except and return empty set on failure.

10. **`migrate_airtable_to_sheets.py` line 110** - `sheets.upsert_contact(contact)` called with potentially missing required fields (empty `email`, `linkedin_url`, `name`).  
    **Fix:** Validate at least one identifier exists before upserting.

11. **`backup_sheet.py` line 27** - `print(f"backed_up_tabs=...")` uses stdout, which is captured by GitHub Actions and could interfere with subsequent steps.  
    **Fix:** Use `logging.info()` and GitHub Action `$GITHUB_OUTPUT` if needed.

## LOW

12. **`config/exclusions.json`** - `Ernst Young` should be `Ernst & Young` or `Ernst & Young Global Limited`.  
    **Fix:** Correct the canonical name to include the ampersand.

13. **`sources/linkedin.py` line 62** - Comment says `HttpPost = Callable[..., list]` but response could be `dict` for some Apify actors.  
    **Fix:** Type hint should be `Union[Callable[..., list], Callable[..., dict]]`.

14. **`.github/workflows/daily-jobs.yml` line 38-45** - Airtable secrets (`AIRTABLE_TOKEN`, `AIRTABLE_BASE_ID`) are not listed in env, but `AUTO_APPLY_LIVE` is. If migrating to Google Sheets, these should be present for backward compatibility.  
    **Fix:** Add `AIRTABLE_TOKEN` and `AIRTABLE_BASE_ID` to env vars or document removal.

15. **`tests/test_scoring.py`** - Test file appears to be truncated (ends with `...`). Missing closing brackets and assertions.  
    **Fix:** Complete the test file with proper test functions.

## OVERALL VERDICT

Major security and stability issues in critical paths (secret exposure, auth failures, race condition in Sheet bootstrapping); moderate concerns in backup and migration scripts.
