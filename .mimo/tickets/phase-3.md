# MiMo Ticket — Phase 3: HubSpot tracking backbone

Implements `PLAN.md §6`. HubSpot becomes the CRM view of the pipeline, behind the existing
`Repository` interface so it's swappable with SQLite. HTTP is injectable (tested against mocks;
live when `HUBSPOT_TOKEN` is set).

## Build
- `store/hubspot_repo.py`: `HubSpotRepository(Repository)` — jobs as Deals (full job JSON stored
  in a `job_data` property; searched/deduped by `dedupe_key` and `job_id`), contacts as Contacts.
  Daily-cap counters delegate to an internal SqliteRepository (HubSpot isn't a counter store).
- `tests/test_hubspot_repo.py`: fake HTTP, no network.

## Exit
- upsert creates a Deal when none matches dedupe_key, PATCHes when one does.
- get_job/list_jobs reconstruct Job from stored JSON.
- action counters delegate correctly. Tests green.
