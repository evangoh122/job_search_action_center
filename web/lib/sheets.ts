export interface SheetsEnv {
  SPREADSHEET_ID?: string;
  GOOGLE_SERVICE_ACCOUNT_JSON?: string;
  GOOGLE_DRIVE_GAPS_DOCUMENT_ID?: string;
}

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
  Jobs: ["DedupeKey", "Title", "Company", "URL", "ApplicationLink", "Score", "Tier", "Status", "Source", "Posted", "Description", "Aging", "Applied", "Salary Min", "Salary Max", "Salary Average", "Salary Currency", "Salary Period"],
  Applications: ["Key", "Job", "Company", "Title", "Application Link", "Resume File", "Cover Letter", "Matched Keywords", "Status", "Updated", "Resume Block IDs"],
  "Networking Tracker": ["Key", "Name", "Email", "Company", "Role", "LinkedIn", "Source", "Last Contacted", "Status", "Notes", "Follow Up Due"],
  "OKR Events": ["Key", "Date", "Kind", "Count", "Minutes", "Job", "Contact", "Notes", "Created"],
  "Learning Gaps": ["Key", "Found", "Source", "Gap", "Priority", "Review Plan", "Drive State", "Drive Reference", "Resolved"],
  "Weekly Reviews": ["Key", "Week Start", "KR Actuals", "Pipeline", "Follow Ups", "Gaps", "Chats Sourced", "Decision", "Completed"],
  "Master Resume Blocks": ["Key", "Block Text", "Tags", "Source", "Hash", "Active"],
} as const;

function b64url(value: string | ArrayBuffer): string {
  const bytes = typeof value === "string" ? new TextEncoder().encode(value) : new Uint8Array(value);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

async function accessToken(env: SheetsEnv): Promise<string> {
  if (tokenCache && tokenCache.expiresAt > Date.now() + 60_000) return tokenCache.token;
  if (!env.GOOGLE_SERVICE_ACCOUNT_JSON) throw new Error("Google Sheets service account is not configured");
  const account = JSON.parse(env.GOOGLE_SERVICE_ACCOUNT_JSON) as ServiceAccount;
  const now = Math.floor(Date.now() / 1000);
  const header = b64url(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const claim = b64url(JSON.stringify({
    iss: account.client_email,
    scope: "https://www.googleapis.com/auth/spreadsheets https://www.googleapis.com/auth/documents",
    aud: account.token_uri || "https://oauth2.googleapis.com/token",
    iat: now,
    exp: now + 3600,
  }));
  const pem = account.private_key.replace(/-----BEGIN PRIVATE KEY-----|-----END PRIVATE KEY-----|\s/g, "");
  const der = Uint8Array.from(atob(pem), (char) => char.charCodeAt(0));
  const key = await crypto.subtle.importKey("pkcs8", der, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["sign"]);
  const signature = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, new TextEncoder().encode(`${header}.${claim}`));
  const assertion = `${header}.${claim}.${b64url(signature)}`;
  const response = await fetch(account.token_uri || "https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer", assertion }),
  });
  if (!response.ok) throw new Error(`Google authentication failed (${response.status})`);
  const data = await response.json() as { access_token: string; expires_in?: number };
  tokenCache = { token: data.access_token, expiresAt: Date.now() + (data.expires_in || 3600) * 1000 };
  return data.access_token;
}

async function googleFetch(env: SheetsEnv, url: string, init: RequestInit = {}): Promise<any> {
  const token = await accessToken(env);
  const response = await fetch(url, {
    ...init,
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json", ...(init.headers || {}) },
  });
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 300);
    throw new Error(`Google API failed (${response.status}): ${detail}`);
  }
  return response.status === 204 ? {} : response.json();
}

function a1(tab: string, range = "A1:ZZ"): string {
  return encodeURIComponent(`'${tab}'!${range}`);
}

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

async function values(env: SheetsEnv, tab: string, range = "A1:ZZ"): Promise<string[][]> {
  const data = await googleFetch(env, `${SHEETS_BASE}/${env.SPREADSHEET_ID}/values/${a1(tab, range)}`);
  return data.values || [];
}

async function updateValues(env: SheetsEnv, tab: string, range: string, rows: unknown[][]): Promise<void> {
  await googleFetch(env, `${SHEETS_BASE}/${env.SPREADSHEET_ID}/values/${a1(tab, range)}?valueInputOption=RAW`, {
    method: "PUT",
    body: JSON.stringify({ values: rows }),
  });
}

async function appendValues(env: SheetsEnv, tab: string, row: unknown[]): Promise<void> {
  await googleFetch(env, `${SHEETS_BASE}/${env.SPREADSHEET_ID}/values/${a1(tab, "A1")}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS`, {
    method: "POST",
    body: JSON.stringify({ values: [row] }),
  });
}

async function upsertByKey(env: SheetsEnv, tab: keyof typeof TAB_HEADERS, key: string, row: unknown[]): Promise<void> {
  const keys = await values(env, tab, "A2:A");
  const index = keys.findIndex((item) => item[0] === key);
  if (index < 0) return appendValues(env, tab, row);
  const rowNumber = index + 2;
  const lastColumn = String.fromCharCode(64 + Math.min(row.length, 26));
  await updateValues(env, tab, `A${rowNumber}:${lastColumn}${rowNumber}`, [row]);
}

function objects(rows: string[][]): Record<string, string>[] {
  if (!rows.length) return [];
  const headers = rows[0];
  return rows.slice(1).filter((row) => row.some(Boolean)).map((row) => Object.fromEntries(headers.map((header, index) => [header, row[index] || ""])));
}

export async function bootstrap(env: SheetsEnv): Promise<Record<string, unknown>> {
  await ensureTabs(env);
  const tabs = await Promise.all(Object.keys(TAB_HEADERS).map((tab) => values(env, tab)));
  return Object.fromEntries(Object.keys(TAB_HEADERS).map((tab, index) => [tab, objects(tabs[index])]));
}

const EVENT_KINDS = new Set(["coffee_chat", "targeted_application", "linkedin_post", "coding", "stats_deep", "commute_review", "portfolio", "mock_interview", "sourcing", "referral", "follow_up", "offer_accepted"]);

export async function logEvent(env: SheetsEnv, input: any): Promise<{ key: string }> {
  if (!EVENT_KINDS.has(input.kind)) throw new Error("Unsupported OKR event kind");
  const key = crypto.randomUUID();
  const now = new Date().toISOString();
  await appendValues(env, "OKR Events", [key, input.date || now.slice(0, 10), input.kind, Number(input.count || 0), Number(input.minutes || 0), input.job || "", input.contact || "", input.notes || "", now]);
  return { key };
}

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
  await updateValues(env, "Jobs", `A${found + 1}:R${found + 1}`, [row.slice(0, 18)]);
}

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

export async function logGap(env: SheetsEnv, input: any): Promise<{ key: string; driveState: string; driveReference: string }> {
  if (!input.gap?.trim() || !["interview", "challenge"].includes(input.source)) throw new Error("Interview/challenge gap text is required");
  const key = crypto.randomUUID();
  const found = input.found || new Date().toISOString().slice(0, 10);
  const base = [key, found, input.source, input.gap.trim(), input.priority || "medium", input.reviewPlan || "", "pending", "", ""];
  await appendValues(env, "Learning Gaps", base);
  try {
    const reference = await appendGapToDrive(env, { ...input, found }, key);
    await upsertByKey(env, "Learning Gaps", key, [...base.slice(0, 6), "synced", reference, ""]);
    return { key, driveState: "synced", driveReference: reference };
  } catch {
    return { key, driveState: "pending", driveReference: "" };
  }
}

export async function saveApplication(env: SheetsEnv, input: any): Promise<void> {
  if (!input.key || !Array.isArray(input.blockIds) || !input.blockIds.length) throw new Error("At least one verified master-resume block is required");
  const now = new Date().toISOString();
  await upsertByKey(env, "Applications", input.key, [input.key, input.key, input.company, input.title, input.applicationLink, input.resumeFile, input.coverLetter || "", (input.keywords || []).join(", "), input.status || "drafted", now, input.blockIds.join(", ")]);
}

export async function saveWeeklyReview(env: SheetsEnv, input: any): Promise<void> {
  if (!input.weekStart) throw new Error("Week start is required");
  await upsertByKey(env, "Weekly Reviews", input.weekStart, [input.weekStart, input.weekStart, input.krActuals || "", input.pipeline || "", input.followUps || "", input.gaps || "", input.chatsSourced || "", input.decision || "", new Date().toISOString()]);
}
