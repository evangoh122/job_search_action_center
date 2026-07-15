# LinkedIn vacancy-post matching

The daily job workflow searches recent LinkedIn posts for up to five active Tier-A/B vacancies.
It uses the HarvestAPI `linkedin-post-search` Apify actor with bounded query forms for the exact
job title, referral language plus title, and any numeric LinkedIn job ID found in the tracked
source URLs. Comments and reactions are disabled to limit cost and data collection.

## Confidence rules

- An exact tracked vacancy URL or LinkedIn job ID anywhere in the returned post payload: `100%`.
- A linkless result must have hiring language, at least 55% job-title token coverage, and company
  evidence in either the post text or the author's headline.
- Results below `72%` are discarded. All retained results remain `review_required`.
- Explicit phrases such as “happy to refer,” “can refer,” and “DM me for a referral” classify
  the post as `referral_offer` or `both`; ordinary hiring posts remain `hiring`.

The matcher stores the post URL/text, author name/headline/profile, job key, confidence, and the
specific evidence used. It writes locally to SQLite and, when configured, to the Google Sheets
`LinkedIn Post Matches` tab.

## Post-grounded outreach

The review artifact cites an excerpt from the actual matched post. It generates a message only
when both `NETWORKING_APPLICANT_PROOF` and `NETWORKING_RELEVANCE` are configured. Otherwise the
draft is deliberately blocked so the system cannot emit generic outreach. Nothing is sent.
When the author explicitly offered referrals, the draft politely asks whether that offer is still
current and what evidence they would need before considering one; it never presumes a referral.

Run locally after the job tracker has been populated:

```powershell
$env:APIFY_TOKEN = "..."
$env:NETWORKING_APPLICANT_PROOF = "A specific result, metric/scale, and method"
$env:NETWORKING_RELEVANCE = "Why the post's stated need connects to that experience"
python -m linkedin_post_cli --max-jobs 5 --max-posts 5
```

Review `data/linkedin_post_matches.md` and verify the post really refers to the tracked vacancy
before contacting its author. The actor is a third-party community integration, not an official
LinkedIn API, and usage should comply with LinkedIn's terms and applicable law.
