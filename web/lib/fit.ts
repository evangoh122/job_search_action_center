/**
 * Fit scoring — the "drop in a JD, get a match %" tool.
 *
 * The rule the campaign runs on: only apply to roles that clear a fixed fit
 * threshold. We do NOT tailor the resume per role to inflate the number — we
 * score the master resume as-is and skip anything under the bar.
 */
export const FIT_THRESHOLD = 75;

export type FitVerdict = "apply" | "skip";

/** Above the threshold it's worth an application; below it, skip and save the effort. */
export function verdictFor(fit: number): FitVerdict {
  return fit >= FIT_THRESHOLD ? "apply" : "skip";
}

/**
 * Extracts the master resume as a single block of text from a bootstrap payload's
 * "Master Resume Blocks" tab. Only rows flagged Active are included, so retired
 * blocks never leak into scoring.
 *
 * @param payload - The bootstrap payload (tab name → row objects).
 * @returns The joined block text, or an empty string if none are available.
 */
export function resumeFromPayload(payload: unknown): string {
  if (typeof payload !== "object" || payload === null) return "";
  const rows = (payload as Record<string, unknown>)["Master Resume Blocks"];
  if (!Array.isArray(rows)) return "";
  return rows
    .filter((row): row is Record<string, unknown> => typeof row === "object" && row !== null)
    .filter((row) => {
      // Coerce defensively — a Sheets cell can arrive as a number/boolean, not a string.
      const active = String(row.Active ?? "").trim().toLowerCase();
      // Treat blank Active as active — an unset flag shouldn't silently drop a block.
      return active === "" || active === "true" || active === "yes" || active === "1";
    })
    .map((row) => String(row["Block Text"] ?? "").trim())
    .filter(Boolean)
    .join("\n\n");
}

/**
 * Builds a prompt asking a model to score how well a master resume fits a role,
 * on a 0–100 scale, and to name the concrete requirements matched and missing.
 */
export function fitPrompt(resume: string, jobDescription: string): string {
  return `You are a pragmatic hiring screener deciding whether a candidate is worth an application.

CANDIDATE MASTER RESUME:
${resume}

JOB DESCRIPTION:
${jobDescription}

Score how well THIS resume fits THIS role from 0 to 100, where:
- 75+ means the candidate clears the bar and should apply as-is (do not assume they will tailor the resume).
- Below 75 means the gap is too large to be worth an application.

Judge on real evidence in the resume, not keyword overlap. Reward demonstrated scope, domain and seniority; penalise missing must-have requirements.

Return:
- "fit": integer 0–100.
- "matched": up to 4 specific role requirements the resume clearly satisfies (short phrases).
- "missing": up to 4 key role requirements the resume does not evidence (short phrases).
- "summary": one sentence recommending apply or skip and why.

Reply with ONLY strict, minified JSON of exactly this shape and nothing else:

{"fit":n,"matched":["..."],"missing":["..."],"summary":"..."}

Do not include markdown fences, explanations, or prose.`;
}
