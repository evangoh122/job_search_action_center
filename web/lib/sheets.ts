import { readFileSync } from "node:fs";

export interface SheetsEnv {
  SPREADSHEET_ID?: string;
  GOOGLE_SERVICE_ACCOUNT_JSON?: string;
  GOOGLE_DRIVE_GAPS_DOCUMENT_ID?: string;
}

/**
 * Reads the Google Sheets / Drive configuration from environment variables.
 *
 * @returns The environment values needed to authenticate and reach the configured spreadsheet and gaps document.
 */
export function getSheetsEnv(): SheetsEnv {
  return {
    SPREADSHEET_ID: process.env.SPREADSHEET_ID,
    GOOGLE_SERVICE_ACCOUNT_JSON: process.env.GOOGLE_SERVICE_ACCOUNT_JSON,
    GOOGLE_DRIVE_GAPS_DOCUMENT_ID: process.env.GOOGLE_DRIVE_GAPS_DOCUMENT_ID,
  };
}

type ServiceAccount = {
  client_email: string;
  private_key: string;
  token_uri?: string;
};

type TokenCache = { token: string; expiresAt: number } | null;
let tokenCache: TokenCache = null;

const SHEETS_BASE = "https://sheets.googleapis.com/v4/spreadsheets";
const TAB_HEADERS = {
  Jobs: ["DedupeKey", "Title", "Company", "URL", "Score", "Tier", "Status", "Source", "Posted", "Description", "Aging", "Applied"],
  Applications: ["Key", "Job", "Company", "Title", "Application Link", "Resume File", "Cover Letter", "Matched Keywords", "Status", "Updated", "Resume Block IDs"],
  "Networking Tracker": ["Key", "Name", "Email", "Company", "Role", "LinkedIn", "Source", "Last Contacted", "Status", "Notes", "Follow Up Due"],
  "OKR Events": ["Key", "Date", "Kind", "Count", "Minutes", "Job", "Contact", "Notes", "Created"],
  "Learning Gaps": ["Key", "Found", "Source", "Gap", "Priority", "Review Plan", "Drive State", "Drive Reference", "Resolved"],
  "Weekly Reviews": ["Key", "Week Start", "KR Actuals", "Pipeline", "Follow Ups", "Gaps", "Chats Sourced", "Decision", "Completed"],
  "Master Resume Blocks": ["Key", "Block Text", "Tags", "Source", "Hash", "Active"],
} as const;

/** Milliseconds to wait for a single outbound fetch before aborting, so a Cloud Run request never hangs indefinitely. */
const FETCH_TIMEOUT_MS = 10_000;

/**
 * Runs `fetch` with a hard timeout, aborting the request if it doesn't settle in time.
 *
 * @param url - The request URL.
 * @param init - Standard `fetch` options.
 * @returns The `fetch` response.
 * @throws {Error} If the request does not complete within {@link FETCH_TIMEOUT_MS}, or on any underlying network failure.
 */
async function fetchWithTimeout(url: string, init: RequestInit = {}): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(`Request to ${url} timed out after ${FETCH_TIMEOUT_MS}ms`);
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * Base64url-encodes a string or byte buffer (no padding), as required for JWT segments.
 *
 * @param value - The UTF-8 string or raw bytes to encode.
 * @returns The base64url-encoded representation.
 */
function b64url(value: string | ArrayBuffer): string {
  const bytes = typeof value === "string" ? new TextEncoder().encode(value) : new Uint8Array(value);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  // Standard base64 uses `+`/`/`/`=`, which aren't URL/JWT-safe — swap them for the url-safe variant and drop padding.
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

/**
 * Obtains (and caches) a Google OAuth2 access token for the configured service account, using the
 * JWT bearer grant flow (RFC 7523) so no interactive consent is required.
 *
 * @param env - Sheets/Drive environment configuration, including the service account JSON.
 * @returns A bearer access token valid for the Sheets and Docs APIs.
 * @throws {Error} If the service account is not configured, or if the token exchange request fails.
 */
/**
 * Loads the service account from either raw JSON (the deployed Secret Manager value) or a path to a
 * key file (local dev / parity with the root `.env`, which stores `secrets/service-account.json`).
 *
 * A malformed value here would otherwise surface as a cryptic `JSON.parse` SyntaxError
 * ("Expected property name…") on every Sheets call, so both failure modes are wrapped in a clear,
 * "not configured" message that the API routes translate to a 503.
 *
 * @param raw - The `GOOGLE_SERVICE_ACCOUNT_JSON` value: inline JSON or a filesystem path.
 * @returns The parsed service account credentials.
 * @throws {Error} If a path can't be read, or the resolved content isn't valid service-account JSON.
 */
function loadServiceAccount(raw: string): ServiceAccount {
  const trimmed = raw.trim();
  let source = trimmed;
  if (!trimmed.startsWith("{")) {
    try {
      source = readFileSync(trimmed, "utf8");
    } catch {
      throw new Error("Google Sheets service account is not configured: GOOGLE_SERVICE_ACCOUNT_JSON looks like a path but the key file could not be read");
    }
  }
  try {
    return JSON.parse(source) as ServiceAccount;
  } catch {
    throw new Error("Google Sheets service account is not configured: GOOGLE_SERVICE_ACCOUNT_JSON is not valid service-account JSON (or a readable key-file path)");
  }
}

async function accessToken(env: SheetsEnv): Promise<string> {
  // Reuse the cached token until it's within 60s of expiry, to avoid signing a fresh JWT on every call.
  if (tokenCache && tokenCache.expiresAt > Date.now() + 60_000) return tokenCache.token;
  if (!env.GOOGLE_SERVICE_ACCOUNT_JSON) throw new Error("Google Sheets service account is not configured");
  const account = loadServiceAccount(env.GOOGLE_SERVICE_ACCOUNT_JSON);
  const now = Math.floor(Date.now() / 1000);
  // Build and sign a JWT assertion by hand (header.claim.signature) since the service account
  // flow only needs a single RS256-signed token, not a full OAuth client library.
  const header = b64url(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const claim = b64url(JSON.stringify({
    iss: account.client_email,
    scope: "https://www.googleapis.com/auth/spreadsheets https://www.googleapis.com/auth/documents",
    aud: account.token_uri || "https://oauth2.googleapis.com/token",
    iat: now,
    exp: now + 3600,
  }));
  // Strip PEM armor/whitespace and decode to raw DER bytes so WebCrypto can import the key.
  const pem = account.private_key.replace(/-----BEGIN PRIVATE KEY-----|-----END PRIVATE KEY-----|\s/g, "");
  const der = Uint8Array.from(atob(pem), (char) => char.charCodeAt(0));
  const key = await crypto.subtle.importKey("pkcs8", der, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["sign"]);
  const signature = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, new TextEncoder().encode(`${header}.${claim}`));
  const assertion = `${header}.${claim}.${b64url(signature)}`;
  const response = await fetchWithTimeout(account.token_uri || "https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer", assertion }),
  });
  if (!response.ok) throw new Error(`Google authentication failed (${response.status})`);
  const data = await response.json() as { access_token: string; expires_in?: number };
  tokenCache = { token: data.access_token, expiresAt: Date.now() + (data.expires_in || 3600) * 1000 };
  return data.access_token;
}

/**
 * Issues an authenticated request against a Google API (Sheets or Docs) and parses the JSON response.
 *
 * @param env - Sheets/Drive environment configuration used to obtain the access token.
 * @param url - The full request URL.
 * @param init - Standard `fetch` options; an `authorization` header is added automatically.
 * @returns The parsed JSON body, or `{}` for a 204 No Content response.
 * @throws {Error} If the response status is not OK.
 */
async function googleFetch(env: SheetsEnv, url: string, init: RequestInit = {}): Promise<any> {
  const token = await accessToken(env);
  const response = await fetchWithTimeout(url, {
    ...init,
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json", ...(init.headers || {}) },
  });
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 300);
    throw new Error(`Google API failed (${response.status}): ${detail}`);
  }
  return response.status === 204 ? {} : response.json();
}

/**
 * Builds a URL-encoded A1 notation range reference for a sheet tab.
 *
 * @param tab - The sheet tab name.
 * @param range - The A1 range within the tab (defaults to the full usable grid).
 * @returns The encoded `'tab'!range` string suitable for use in a Sheets API URL path segment.
 */
function a1(tab: string, range = "A1:ZZ"): string {
  return encodeURIComponent(`'${tab}'!${range}`);
}

/**
 * Ensures every tab in {@link TAB_HEADERS} exists in the spreadsheet and has an up-to-date header row.
 * Creates any missing tabs and writes/repairs header rows as needed.
 *
 * @param env - Sheets environment configuration, including the target spreadsheet ID.
 * @throws {Error} If `SPREADSHEET_ID` is not configured.
 */
async function ensureTabs(env: SheetsEnv): Promise<void> {
  const id = env.SPREADSHEET_ID;
  if (!id) throw new Error("SPREADSHEET_ID is not configured");
  const meta = await googleFetch(env, `${SHEETS_BASE}/${id}?fields=sheets.properties`);
  const existing = new Set<string>((meta.sheets || []).map((sheet: any) => sheet.properties.title));
  const missing = Object.keys(TAB_HEADERS).filter((tab) => !existing.has(tab));
  if (missing.length) {
    await googleFetch(env, `${SHEETS_BASE}/${id}:batchUpdate`, {
      method: "POST",
      body: JSON.stringify({ requests: missing.map((title) => ({ addSheet: { properties: { title } } })) }),
    });
  }
  for (const [tab, headers] of Object.entries(TAB_HEADERS)) {
    const rows = await values(env, tab, "1:1");
    if (!rows.length || rows[0].length < headers.length) await updateValues(env, tab, "A1", [headers as unknown as string[]]);
  }
}

/**
 * Reads raw row values from a sheet tab.
 *
 * @param env - Sheets environment configuration.
 * @param tab - The sheet tab name.
 * @param range - The A1 range to read (defaults to the full usable grid).
 * @returns The rows as arrays of cell strings; empty if the range has no data.
 */
async function values(env: SheetsEnv, tab: string, range = "A1:ZZ"): Promise<string[][]> {
  const data = await googleFetch(env, `${SHEETS_BASE}/${env.SPREADSHEET_ID}/values/${a1(tab, range)}`);
  return data.values || [];
}

/**
 * Overwrites the cells in a given range with the supplied rows.
 *
 * @param env - Sheets environment configuration.
 * @param tab - The sheet tab name.
 * @param range - The starting A1 range to write into (e.g. `"A5"` or `"A5:C5"`).
 * @param rows - The row values to write, in order.
 */
async function updateValues(env: SheetsEnv, tab: string, range: string, rows: unknown[][]): Promise<void> {
  await googleFetch(env, `${SHEETS_BASE}/${env.SPREADSHEET_ID}/values/${a1(tab, range)}?valueInputOption=RAW`, {
    method: "PUT",
    body: JSON.stringify({ values: rows }),
  });
}

/**
 * Appends a single row to the end of a sheet tab.
 *
 * @param env - Sheets environment configuration.
 * @param tab - The sheet tab name.
 * @param row - The cell values for the new row.
 */
async function appendValues(env: SheetsEnv, tab: string, row: unknown[]): Promise<void> {
  await googleFetch(env, `${SHEETS_BASE}/${env.SPREADSHEET_ID}/values/${a1(tab, "A1")}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS`, {
    method: "POST",
    body: JSON.stringify({ values: [row] }),
  });
}

/**
 * Tracks in-flight {@link upsertByKey} calls by `tab:key`, so concurrent callers targeting the same
 * row are serialized instead of racing each other's read-then-write.
 */
const upsertInFlight = new Map<string, Promise<void>>();

/**
 * Inserts or updates the row identified by `key` in the first column of a sheet tab.
 *
 * NOTE: Google Sheets has no compare-and-swap primitive, so this is inherently a read-then-write
 * (TOCTOU) operation — two concurrent upserts for the *same* key can both read "not found" and both
 * append, producing a duplicate row, or one can overwrite the other's write based on a stale row
 * index. There is no perfect fix for this against the Sheets API. As a mitigation, calls sharing the
 * same `tab:key` are serialized via {@link upsertInFlight} so they can't race each other within this
 * process; it does not protect against concurrent writers from other processes/instances.
 *
 * @param env - Sheets environment configuration.
 * @param tab - The sheet tab name (must be a key of {@link TAB_HEADERS}).
 * @param key - The value to match against column A.
 * @param row - The full row to write (or append, if no existing row matches).
 */
async function upsertByKey(env: SheetsEnv, tab: keyof typeof TAB_HEADERS, key: string, row: unknown[]): Promise<void> {
  const dedupeKey = `${tab}:${key}`;
  const previous = upsertInFlight.get(dedupeKey) || Promise.resolve();
  const run = previous
    .catch(() => {})
    .then(() => upsertByKeyInternal(env, tab, key, row))
    .finally(() => {
      if (upsertInFlight.get(dedupeKey) === run) upsertInFlight.delete(dedupeKey);
    });
  upsertInFlight.set(dedupeKey, run);
  return run;
}

/**
 * Performs the actual read-then-write for {@link upsertByKey}, without any concurrency guard.
 *
 * @param env - Sheets environment configuration.
 * @param tab - The sheet tab name.
 * @param key - The value to match against column A.
 * @param row - The full row to write (or append, if no existing row matches).
 */
async function upsertByKeyInternal(env: SheetsEnv, tab: keyof typeof TAB_HEADERS, key: string, row: unknown[]): Promise<void> {
  const keys = await values(env, tab, "A2:A");
  const index = keys.findIndex((item) => item[0] === key);
  if (index < 0) return appendValues(env, tab, row);
  const rowNumber = index + 2;
  const lastColumn = String.fromCharCode(64 + Math.min(row.length, 26));
  await updateValues(env, tab, `A${rowNumber}:${lastColumn}${rowNumber}`, [row]);
}

/**
 * Converts raw sheet rows (with a header row) into an array of plain objects keyed by header name.
 *
 * @param rows - Raw rows as returned by {@link values}, where `rows[0]` is the header row.
 * @returns One object per non-empty data row, mapping header name to cell string.
 */
function objects(rows: string[][]): Record<string, string>[] {
  if (!rows.length) return [];
  const headers = rows[0];
  return rows.slice(1).filter((row) => row.some(Boolean)).map((row) => Object.fromEntries(headers.map((header, index) => [header, row[index] || ""])));
}

/**
 * Ensures all tabs exist and loads the full contents of every tracked tab.
 *
 * @param env - Sheets environment configuration.
 * @returns A map of tab name to that tab's rows, each row converted to a header-keyed object.
 */
export async function bootstrap(env: SheetsEnv): Promise<Record<string, unknown>> {
  await ensureTabs(env);
  const tabs = await Promise.all(Object.keys(TAB_HEADERS).map((tab) => values(env, tab)));
  return Object.fromEntries(Object.keys(TAB_HEADERS).map((tab, index) => [tab, objects(tabs[index])]));
}

const EVENT_KINDS = new Set(["coffee_chat", "targeted_application", "linkedin_post", "coding", "stats_deep", "commute_review", "portfolio", "mock_interview", "sourcing", "referral", "follow_up", "offer_accepted"]);

/**
 * Appends a new OKR activity event (e.g. a coffee chat or an application) to the "OKR Events" tab.
 *
 * @param env - Sheets environment configuration.
 * @param input - The event payload; `kind` must be one of {@link EVENT_KINDS}.
 * @returns The generated key for the new event row.
 * @throws {Error} If `input.kind` is not a supported event kind.
 */
export async function logEvent(env: SheetsEnv, input: any): Promise<{ key: string }> {
  if (!EVENT_KINDS.has(input.kind)) throw new Error("Unsupported OKR event kind");
  const key = crypto.randomUUID();
  const now = new Date().toISOString();
  await appendValues(env, "OKR Events", [key, input.date || now.slice(0, 10), input.kind, Number(input.count || 0), Number(input.minutes || 0), input.job || "", input.contact || "", input.notes || "", now]);
  return { key };
}

/**
 * Updates the status (and, if applying, the applied date) of a job row in the "Jobs" tab.
 *
 * @param env - Sheets environment configuration.
 * @param input - Must include `key` (matching `DedupeKey`) and `status`; may include `date`.
 * @throws {Error} If no job row matches `input.key`.
 */
export async function updateJobStatus(env: SheetsEnv, input: any): Promise<void> {
  const rows = await values(env, "Jobs");
  const headers = rows[0] || [];
  const keyIndex = headers.indexOf("DedupeKey");
  const statusIndex = headers.indexOf("Status");
  const appliedIndex = headers.indexOf("Applied");
  const found = rows.findIndex((row, index) => index > 0 && row[keyIndex] === input.key);
  if (found < 1) throw new Error("Job was not found in Google Sheets");
  const row = [...rows[found]];
  while (row.length < headers.length) row.push("");
  row[statusIndex] = input.status;
  if (input.status === "applied" && appliedIndex >= 0) row[appliedIndex] = input.date || new Date().toISOString().slice(0, 10);
  const lastColumn = String.fromCharCode(64 + Math.min(headers.length, 26));
  await updateValues(env, "Jobs", `A${found + 1}:${lastColumn}${found + 1}`, [row.slice(0, headers.length)]);
}

/**
 * Appends a formatted learning-gap entry to the end of the configured Google Doc.
 *
 * @param env - Sheets/Drive environment configuration, including the target document ID.
 * @param input - The gap details (`found`, `source`, `priority`, `gap`, `reviewPlan`).
 * @param key - The Sheets row key to embed as a cross-reference in the doc text.
 * @returns A `google-doc:<id>` reference string identifying the synced document.
 * @throws {Error} If `GOOGLE_DRIVE_GAPS_DOCUMENT_ID` is not configured.
 */
async function appendGapToDrive(env: SheetsEnv, input: any, key: string): Promise<string> {
  if (!env.GOOGLE_DRIVE_GAPS_DOCUMENT_ID) throw new Error("GOOGLE_DRIVE_GAPS_DOCUMENT_ID is not configured");
  const id = env.GOOGLE_DRIVE_GAPS_DOCUMENT_ID;
  const document = await googleFetch(env, `https://docs.googleapis.com/v1/documents/${id}`);
  const content = document.body?.content || [];
  const endIndex = Math.max(1, (content.at(-1)?.endIndex || 1) - 1);
  const text = `\n${input.found} — ${input.source} [${input.priority}]\n${input.gap}\nReview plan: ${input.reviewPlan || "Unassigned"}\nReference: ${key}\n`;
  await googleFetch(env, `https://docs.googleapis.com/v1/documents/${id}:batchUpdate`, {
    method: "POST",
    body: JSON.stringify({ requests: [{ insertText: { location: { index: endIndex }, text } }] }),
  });
  return `google-doc:${id}`;
}

/**
 * Records a learning gap in the "Learning Gaps" tab and best-effort mirrors it to the gaps Google Doc.
 *
 * @param env - Sheets/Drive environment configuration.
 * @param input - Must include non-empty `gap` text and `source` of `"interview"` or `"challenge"`; may include `found`, `priority`, `reviewPlan`.
 * @returns The new row's key, and the Drive sync outcome (`driveState` is `"synced"` on success or `"pending"` if the Drive sync failed).
 * @throws {Error} If `input.gap` is blank or `input.source` is not `"interview"`/`"challenge"`.
 */
export async function logGap(env: SheetsEnv, input: any): Promise<{ key: string; driveState: string; driveReference: string }> {
  if (!input.gap?.trim() || !["interview", "challenge"].includes(input.source)) throw new Error("Interview/challenge gap text is required");
  const key = crypto.randomUUID();
  const found = input.found || new Date().toISOString().slice(0, 10);
  const base = [key, found, input.source, input.gap.trim(), input.priority || "medium", input.reviewPlan || "", "pending", "", ""];
  await appendValues(env, "Learning Gaps", base);
  try {
    // The Sheets row is the source of truth; the Drive doc is a best-effort mirror, so a Drive
    // failure here is swallowed and reported back as "pending" rather than failing the whole call.
    const reference = await appendGapToDrive(env, { ...input, found }, key);
    await upsertByKey(env, "Learning Gaps", key, [...base.slice(0, 6), "synced", reference, ""]);
    return { key, driveState: "synced", driveReference: reference };
  } catch {
    return { key, driveState: "pending", driveReference: "" };
  }
}

/**
 * Inserts or updates an application record in the "Applications" tab.
 *
 * @param env - Sheets environment configuration.
 * @param input - Must include `key` and at least one entry in `blockIds` (verified master-resume blocks); may include `company`, `title`, `applicationLink`, `resumeFile`, `coverLetter`, `keywords`, `status`.
 * @throws {Error} If `input.key` is missing or `input.blockIds` is empty/not an array.
 */
export async function saveApplication(env: SheetsEnv, input: any): Promise<void> {
  if (!input.key || !Array.isArray(input.blockIds) || !input.blockIds.length) throw new Error("At least one verified master-resume block is required");
  const now = new Date().toISOString();
  await upsertByKey(env, "Applications", input.key, [input.key, input.key, input.company, input.title, input.applicationLink, input.resumeFile, input.coverLetter || "", (input.keywords || []).join(", "), input.status || "drafted", now, input.blockIds.join(", ")]);
}

/**
 * Inserts or updates a weekly review record in the "Weekly Reviews" tab, keyed by week start date.
 *
 * @param env - Sheets environment configuration.
 * @param input - Must include `weekStart`; may include `krActuals`, `pipeline`, `followUps`, `gaps`, `chatsSourced`, `decision`.
 * @throws {Error} If `input.weekStart` is missing.
 */
export async function saveWeeklyReview(env: SheetsEnv, input: any): Promise<void> {
  if (!input.weekStart) throw new Error("Week start is required");
  await upsertByKey(env, "Weekly Reviews", input.weekStart, [input.weekStart, input.weekStart, input.krActuals || "", input.pipeline || "", input.followUps || "", input.gaps || "", input.chatsSourced || "", input.decision || "", new Date().toISOString()]);
}
