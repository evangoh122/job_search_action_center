import { NextRequest, NextResponse } from "next/server";
import { AuthError, verifyRequestUser } from "@/lib/firebase-admin";
import { bootstrap, getSheetsEnv } from "@/lib/sheets";

/**
 * Authenticated read endpoint that loads the full contents of every tracked Google Sheets tab,
 * used by the client to hydrate the dashboard on load.
 *
 * @param request - The incoming Next.js request; must carry a valid bearer token for the allowed user.
 * @returns 200 with the bootstrap payload (tab name → row objects) on success; 401/403 if
 *   unauthenticated/unauthorized; 503 if the Sheets backend is not configured; 400 for any other failure.
 */
export async function GET(request: NextRequest) {
  try {
    await verifyRequestUser(request);
  } catch (error) {
    if (error instanceof AuthError) return NextResponse.json({ error: error.message }, { status: error.status });
    throw error;
  }

  try {
    return NextResponse.json(await bootstrap(getSheetsEnv()));
  } catch (error) {
    const message = error instanceof Error ? error.message : "Request failed";
    return NextResponse.json({ error: message }, { status: /not configured/i.test(message) ? 503 : 400 });
  }
}
