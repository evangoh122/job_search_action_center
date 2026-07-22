import { NextRequest, NextResponse } from "next/server";
import { AuthError, verifyRequestUser } from "@/lib/firebase-admin";
import { askModel, extractJson } from "@/lib/models";
import { FALLBACK_QUESTIONS, questionsPrompt } from "@/lib/interview";
import { bootstrap, getSheetsEnv } from "@/lib/sheets";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function extractTitles(payload: Record<string, unknown>): string[] {
  const jobs = payload.Jobs;
  if (!Array.isArray(jobs)) return [];

  const titles: string[] = [];
  for (const row of jobs) {
    if (titles.length >= 8) break;
    if (!isRecord(row)) continue;

    const title = row.Title;
    if (typeof title !== "string") continue;

    const trimmed = title.trim();
    if (trimmed.length > 0 && !titles.includes(trimmed)) {
      titles.push(trimmed);
    }
  }

  return titles;
}

function parseQuestions(raw: unknown): string[] | null {
  if (!isRecord(raw)) return null;
  const questions = raw.questions;
  if (!Array.isArray(questions)) return null;

  const parsed = questions
    .filter((q): q is string => typeof q === "string")
    .map((q) => q.trim())
    .filter(Boolean);

  return parsed.length >= 3 ? parsed : null;
}

export async function GET(request: NextRequest) {
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

  try {
    const payload = await bootstrap(getSheetsEnv());
    const titles = extractTitles(payload);

    let questions: string[] | null = null;

    if (titles.length > 0) {
      try {
        const rawText = await askModel("kimi", questionsPrompt(titles), {
          maxTokens: 1200,
        });
        const parsed = extractJson(rawText);
        questions = parseQuestions(parsed);
      } catch {
        questions = null;
      }
    }

    const finalQuestions =
      questions && questions.length >= 3 ? questions : FALLBACK_QUESTIONS;

    return NextResponse.json({ questions: finalQuestions });
  } catch {
    // Never fail the interview prep flow: always return a usable list.
    return NextResponse.json({ questions: FALLBACK_QUESTIONS });
  }
}
