import { NextRequest, NextResponse } from "next/server";
import { AuthError, verifyRequestUser } from "@/lib/firebase-admin";
import { bootstrap, getSheetsEnv } from "@/lib/sheets";

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
