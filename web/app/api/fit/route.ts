import { NextRequest, NextResponse } from "next/server";
import { AuthError, verifyRequestUser } from "@/lib/firebase-admin";
import { askModel, extractJson, type ModelProvider } from "@/lib/models";
import { FIT_THRESHOLD, fitPrompt, resumeFromPayload, verdictFor } from "@/lib/fit";
import { bootstrap, getSheetsEnv } from "@/lib/sheets";

interface ParsedFit {
  model: ModelProvider;
  fit: number;
  matched: string[];
  missing: string[];
  summary: string;
}

type FitEntry = ParsedFit | { model: ModelProvider; error: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function clampFit(value: unknown): number {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.min(100, Math.max(0, Math.round(n)));
}

function stringList(value: unknown, cap: number): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, cap);
}

function normalizeFit(model: ModelProvider, raw: unknown): ParsedFit | null {
  if (!isRecord(raw)) return null;
  const hasFit = Number.isFinite(Number(raw.fit));
  const summary = typeof raw.summary === "string" ? raw.summary.trim() : "";
  const matched = stringList(raw.matched, 4);
  const missing = stringList(raw.missing, 4);
  // The fit number is the whole point — a payload without one is useless for the
  // consensus average (defaulting it to 0 would silently drag the mean down), so
  // reject it rather than admit it.
  if (!hasFit) return null;
  return { model, fit: clampFit(raw.fit), matched, missing, summary };
}

/** Merges string lists across models, de-duplicating case-insensitively, preserving order. */
function mergeUnique(lists: string[][], cap: number): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const list of lists) {
    for (const item of list) {
      const key = item.toLowerCase().replace(/\s+/g, " ").trim();
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(item);
      if (out.length >= cap) return out;
    }
  }
  return out;
}

export async function POST(request: NextRequest) {
  try {
    await verifyRequestUser(request);
  } catch (error) {
    if (error instanceof AuthError) {
      return NextResponse.json({ error: error.message }, { status: error.status });
    }
    throw error;
  }

  let body: { jobDescription?: unknown; resume?: unknown };
  try {
    body = (await request.json()) as { jobDescription?: unknown; resume?: unknown };
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const jobDescription =
    typeof body.jobDescription === "string" ? body.jobDescription.trim() : "";
  if (!jobDescription) {
    return NextResponse.json({ error: "Job description is required" }, { status: 400 });
  }

  try {
    // Prefer a resume the client supplied (the master blocks it already loaded);
    // fall back to reading the "Master Resume Blocks" tab straight from Sheets.
    let resume = typeof body.resume === "string" ? body.resume.trim() : "";
    if (!resume) {
      const payload = await bootstrap(getSheetsEnv());
      resume = resumeFromPayload(payload);
    }
    if (!resume) {
      // A missing resume is a server-side configuration gap, not a malformed request.
      return NextResponse.json(
        { error: "No master resume is configured. Add rows to the Master Resume Blocks sheet." },
        { status: 503 },
      );
    }

    const prompt = fitPrompt(resume, jobDescription);
    // Derive the fan-out from `models` so order and attribution can't drift apart.
    const models: ModelProvider[] = ["kimi", "deepseek", "mimo"];
    const results = await Promise.allSettled(
      models.map((model) => askModel(model, prompt, { maxTokens: 900 })),
    );

    const entries: FitEntry[] = [];
    const valid: ParsedFit[] = [];

    for (let i = 0; i < models.length; i++) {
      const model = models[i];
      const result = results[i];
      if (result.status === "rejected") {
        const message =
          result.reason instanceof Error ? result.reason.message : String(result.reason);
        entries.push({ model, error: message });
        continue;
      }
      const normalized = normalizeFit(model, extractJson(result.value));
      if (normalized) {
        entries.push(normalized);
        valid.push(normalized);
      } else {
        entries.push({ model, error: "Failed to parse model response as fit JSON" });
      }
    }

    if (valid.length === 0) {
      return NextResponse.json({ error: "All raters failed" }, { status: 502 });
    }

    const fit = Math.round(valid.reduce((sum, r) => sum + r.fit, 0) / valid.length);
    // Pick the summary from the model whose score is closest to the consensus.
    const anchor = valid.reduce((best, r) =>
      Math.abs(r.fit - fit) < Math.abs(best.fit - fit) ? r : best,
    );

    const consolidated = {
      fit,
      verdict: verdictFor(fit),
      threshold: FIT_THRESHOLD,
      matched: mergeUnique(valid.map((r) => r.matched), 6),
      missing: mergeUnique(valid.map((r) => r.missing), 6),
      summary: anchor.summary,
    };

    return NextResponse.json({ ok: true, entries, consolidated });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Request failed";
    // Reaching here means an unexpected upstream/server failure (Sheets, network,
    // model transport) — surface it as 5xx, keeping 503 for configuration gaps.
    return NextResponse.json(
      { error: message },
      { status: /not configured/i.test(message) ? 503 : 500 },
    );
  }
}
