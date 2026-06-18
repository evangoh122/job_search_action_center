Yes, there are several ways to build the keyword and ATS (Applicant Tracking System) search with a 90% match threshold that you're looking for. Here's how you can implement it.

### 🔍 How to Implement a "90% Match" Filter

The key challenge is building the match scoring logic and applying the 90% filter. Different tools and platforms handle this in slightly different ways.

**1. Using the Bullhorn ATS (if your target companies use it)**

The Bullhorn Automation platform has a built-in **Match Candidates** step that handles this exactly. Within its configuration, you can set a threshold to **"Only Match Candidates with a Score Over __%"**, and the default is 90%. This would automatically filter for jobs that are a 90%+ match with your profile. In this context, a score over 85% is considered "Excellent".

**2. Using an AI-Powered Matching Service**

There are AI-powered services built for this exact purpose. For example, Talent Genie's AI candidate matching software instantly analyzes your CV against a job description and generates a percentage match score for every job. You can then filter your search to only show jobs with a 90%+ match. This type of service goes beyond simple keyword matching to understand the context of your experience.

**3. Building Your Own Matching Logic with Scrapers**

You can also build this yourself. Here's the general approach:

*   **Step 1: Scrape Job Descriptions and Metadata.** Use an API or scraper to get job data, including the full description and requirements.
*   **Step 2: Extract Keywords from Job Descriptions.** Identify the key skills, experience, and qualifications in the job posting.
*   **Step 3: Build a Scoring Algorithm.** Write a function that compares the job's requirements against your profile and resume.
*   **Step 4: Implement the 90% Threshold.** In your main script, add an `if` condition that only proceeds to the application step if the `match_score` is >= 90.

### 🎯 How to Filter for Jobs Posted in the Last 24 Hours

This is the easiest part to implement. Several APIs and scrapers have a built-in filter for this.

*   **Apify's Advanced LinkedIn Job Search API** has a `timeRange` parameter where you can select `24h` to only fetch jobs posted in the last 24 hours.
*   The `linkedin-jobs-api` npm package has a `dateSincePosted` parameter that you can set to `24hr`.
*   Workday Jobs Scrapers also support filtering by a `posted_after` date, such as `1 day ago`.

### 💡 My Recommendation for Your Automation

Based on your requirements, here's a practical way to structure this in your existing plan:

1.  **Start with the 24-Hour Filter:** Set your scraping tool of choice to filter for jobs posted in the last 24 hours. This creates your "HOT" list of new jobs.
2.  **Apply the "90% Match" Filter:** For each job in your "HOT" list, run your match scoring logic. This could be:
    *   A simple keyword-matching script if you want a fast and free solution.
    *   A call to an AI-powered matching API (like Talent Genie) for a more sophisticated analysis.
    *   A connection to an ATS (like Bullhorn) that natively supports this feature.
3.  **Auto-Apply:** The script should then only apply to the jobs that meet **both** the 24-hour freshness and the 90% match threshold.

If you want to keep it simple and cost-effective, I'd recommend starting with the `Apify Advanced LinkedIn Job Search API` (for the 24-hour filter) and writing a simple keyword-scoring script in Python to evaluate the match percentage. Once that's working reliably, you could swap out your simple scoring script for a more advanced AI-based matcher.