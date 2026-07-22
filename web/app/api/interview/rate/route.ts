import { NextRequest, NextResponse } from "next/server";
import { AuthError, verifyRequestUser } from "@/lib/firebase-admin";
import {
  askModel,
  extractJson,
  type ModelProvider,
} from "@/lib/models";
import { RUBRIC, ratingPrompt } from "@/lib/interview";

interface ParsedRating {
  model: ModelProvider;
  scores: Record<string, number>;
  overall: number;
  feedback: string;
  improvements: string[];
}

type RatingEntry = ParsedRating | { model: ModelProvider; error: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function clampScore(value: unknown): number {
  const n = Number(value);
  if (!Number.isFinite(n)) return 1;
  return Math.min(5, Math.max(1, n));
}

function normalizeRating(
  model: ModelProvider,
  raw: unknown,
): ParsedRating | null {
  if (!isRecord(raw)) return null;

  const rawScores = isRecord(raw.scores) ? raw.scores : {};
  const scores: Record<string, number> = {};

  for (const dim of RUBRIC) {
    scores[dim.key] = clampScore(rawScores[dim.key]);
  }

  const overall = clampScore(raw.overall);
  const feedback =
    typeof raw.feedback === "string" ? raw.feedback.trim() : "";

  const improvements = Array.isArray(raw.improvements)
    ? raw.improvements
        .filter((item): item is string => typeof item === "string")
        .map((item) => item.trim())
        .filter(Boolean)
    : [];

  if (feedback.length === 0 && improvements.length === 0) {
    // Likely hallucinated or empty payload; reject it.
    return null;
  }

  return { model, scores, overall, feedback, improvements };
}

export async function POST(request: NextRequest) {
  try {
    await verifyRequestUser(request);
  } catch (error) {
    if (error instanceof AuthError) {
      return NextResponse.json(
        { error: error.message },
        { status: error.status },
      );
    }
    throw error;
  }

  let body: { question?: unknown; transcript?: unknown; roleContext?: unknown };
  try {
    body = (await request.json()) as {
      question?: unknown;
      transcript?: unknown;
      roleContext?: unknown;
    };
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  try {

    const question =
      typeof body.question === "string" ? body.question.trim() : "";
    const transcript =
      typeof body.transcript === "string" ? body.transcript.trim() : "";
    const roleContext =
      typeof body.roleContext === "string" ? body.roleContext.trim() : "";

    if (!transcript) {
      return NextResponse.json(
        { error: "Transcript is required" },
        { status: 400 },
      );
    }

    const prompt = ratingPrompt(question, transcript, roleContext);

    const models: ModelProvider[] = ["kimi", "deepseek", "mimo"];
    const results = await Promise.allSettled([
      askModel("kimi", prompt, { maxTokens: 1200 }),
      askModel("deepseek", prompt, { maxTokens: 1200 }),
      askModel("mimo", prompt, { maxTokens: 1200 }),
    ]);

    const ratings: RatingEntry[] = [];
    const validRatings: ParsedRating[] = [];

    for (let i = 0; i < models.length; i++) {
      const model = models[i];
      const result = results[i];

      if (result.status === "rejected") {
        const message =
          result.reason instanceof Error
            ? result.reason.message
            : String(result.reason);
        ratings.push({ model, error: message });
        continue;
      }

      const parsed = extractJson(result.value);
      const normalized = normalizeRating(model, parsed);

      if (normalized) {
        ratings.push(normalized);
        validRatings.push(normalized);
      } else {
        ratings.push({ model, error: "Failed to parse model response as rating JSON" });
      }
    }

    if (validRatings.length === 0) {
      return NextResponse.json(
        { error: "All raters failed" },
        { status: 502 },
      );
    }

    const scores: Record<string, number> = {};
    for (const dim of RUBRIC) {
      const values = validRatings.map((r) => r.scores[dim.key]);
      const avg = values.reduce((a, b) => a + b, 0) / values.length;
      scores[dim.key] = Math.round(avg * 100) / 100;
    }

    const overallValues = validRatings.map((r) => r.overall);
    const overallAvg =
      overallValues.reduce((a, b) => a + b, 0) / overallValues.length;

    const seenFixes = new Set<string>();
    const topFixes: string[] = [];

    for (const rating of validRatings) {
      for (const improvement of rating.improvements) {
        const key = improvement.toLowerCase().replace(/\s+/g, " ").trim();
        if (!seenFixes.has(key)) {
          seenFixes.add(key);
          topFixes.push(improvement);
          if (topFixes.length >= 5) break;
        }
      }
      if (topFixes.length >= 5) break;
    }

    const consolidated = {
      scores,
      overall: Math.round(overallAvg * 100) / 100,
      topFixes,
    };

    return NextResponse.json({ ok: true, ratings, consolidated });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Request failed";
    return NextResponse.json(
      { error: message },
      { status: /not configured/i.test(message) ? 503 : 400 },
    );
  }
}
