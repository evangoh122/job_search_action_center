import { NextRequest, NextResponse } from "next/server";
import { AuthError, verifyRequestUser } from "@/lib/firebase-admin";
import { getSheetsEnv, logEvent, logGap, saveApplication, saveWeeklyReview, updateJobStatus, type SheetsEnv } from "@/lib/sheets";

/** Maps a client-supplied action name to the Sheets-writing function that performs it. */
const actions: Record<string, (env: SheetsEnv, payload: unknown) => Promise<unknown>> = {
  logEvent,
  logGap,
  saveApplication,
  saveWeeklyReview,
  updateJobStatus,
};

/**
 * Authenticated write endpoint that dispatches a named action against Google Sheets.
 *
 * Request body: `{ action: keyof typeof actions, payload: unknown }`. The `payload` shape is
 * validated by the target action function itself, not by this handler.
 *
 * @param request - The incoming Next.js request; must carry a valid bearer token for the allowed user.
 * @returns 200 with `{ ok: true, result }` on success; 401/403 if unauthenticated/unauthorized;
 *   400 for an unsupported action or a validation error from the action function; 503 if the
 *   Sheets backend is not configured.
 */
export async function POST(request: NextRequest) {
  try {
    await verifyRequestUser(request);
  } catch (error) {
    if (error instanceof AuthError) return NextResponse.json({ error: error.message }, { status: error.status });
    throw error;
  }

  try {
    const body = (await request.json()) as { action?: string; payload?: unknown };
    if (!body.action || !Object.hasOwn(actions, body.action)) {
      return NextResponse.json({ error: "Unsupported action" }, { status: 400 });
    }
    const action = actions[body.action as keyof typeof actions];
    return NextResponse.json({ ok: true, result: await action(getSheetsEnv(), body.payload) });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Request failed";
    return NextResponse.json({ error: message }, { status: /not configured/i.test(message) ? 503 : 400 });
  }
}
