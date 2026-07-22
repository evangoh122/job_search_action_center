"use client";

import { useState } from "react";
import { getFirebaseAuth } from "@/lib/firebase-client";
import { FIT_THRESHOLD } from "@/lib/fit";

type ModelKey = "kimi" | "deepseek" | "mimo";

interface FitSuccess {
  model: ModelKey;
  fit: number;
  matched: string[];
  missing: string[];
  summary: string;
}

interface FitError {
  model: ModelKey;
  error: string;
}

type FitEntry = FitSuccess | FitError;

interface FitResponse {
  ok: true;
  entries: FitEntry[];
  consolidated: {
    fit: number;
    verdict: "apply" | "skip";
    threshold: number;
    matched: string[];
    missing: string[];
    summary: string;
  };
}

const MODEL_NAMES: Record<ModelKey, string> = {
  kimi: "Kimi",
  deepseek: "DeepSeek",
  mimo: "MiMo",
};

function fitTone(fit: number): string {
  if (fit >= FIT_THRESHOLD) return "tone-green";
  if (fit >= FIT_THRESHOLD - 15) return "tone-yellow";
  return "tone-red";
}

export default function FitPanel({ resume }: { resume: string }) {
  const [jobDescription, setJobDescription] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<FitResponse | null>(null);

  async function scoreFit() {
    if (!jobDescription.trim()) return;
    setIsSubmitting(true);
    setError(null);
    setResult(null);

    try {
      const token = await getFirebaseAuth().currentUser?.getIdToken();
      const res = await fetch("/api/fit", {
        method: "POST",
        headers: {
          authorization: token ? `Bearer ${token}` : "",
          accept: "application/json",
          "content-type": "application/json",
        },
        body: JSON.stringify({ jobDescription, resume }),
      });

      const data = (await res.json()) as {
        ok?: boolean;
        error?: string;
        entries?: FitEntry[];
        consolidated?: FitResponse["consolidated"];
      };

      if (!res.ok || data.ok !== true) {
        setError(data.error ?? `Request failed (${res.status})`);
      } else {
        setResult(data as FitResponse);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fit request failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  const consolidated = result?.consolidated;

  return (
    <section className="paper interview-pane">
      <div className="section-head">
        <div><p>SCREEN BEFORE YOU APPLY</p><h2>Fit score</h2></div>
        <span className="status-pill tone-grey">Apply only at {FIT_THRESHOLD}%+</span>
      </div>

      <p className="today-empty">
        Paste a job description. Kimi, DeepSeek and MiMo score it against your master resume as-is —
        no per-role tailoring. Under {FIT_THRESHOLD}%, skip it and save the effort.
      </p>

      <textarea
        className="transcript-area"
        aria-label="Job description"
        placeholder="Paste the full job description here…"
        value={jobDescription}
        onChange={(e) => setJobDescription(e.target.value)}
      />

      <button
        className="go"
        type="button"
        disabled={isSubmitting || !jobDescription.trim()}
        onClick={scoreFit}
      >
        {isSubmitting ? "3 screeners scoring…" : "Score fit"}
      </button>

      {error && (
        <div className="interview-error" role="alert">
          {error}
        </div>
      )}

      {consolidated && (
        <div className="rating-results">
          <div className="briefing fit-verdict">
            <div className="dial-area">
              <div
                className="dial"
                style={{ background: `conic-gradient(var(--brass) 0 ${consolidated.fit}%, #4a4438 ${consolidated.fit}%)` }}
              >
                <div><strong>{consolidated.fit}</strong><small>FIT</small></div>
              </div>
            </div>
            <div className="brief-main">
              <p className="gold-label">CONSENSUS VERDICT</p>
              <h1>
                {consolidated.verdict === "apply" ? "Apply — clears the bar" : "Skip — under the bar"}
              </h1>
              <div className="meta">
                <span className={`status-pill ${fitTone(consolidated.fit)}`}>
                  {consolidated.fit}% fit
                </span>
                <span>Threshold {consolidated.threshold}%</span>
                <span>{result.entries.filter((e) => !("error" in e)).length} of 3 raters</span>
              </div>
              {consolidated.summary && <p className="fit-summary">{consolidated.summary}</p>}
            </div>
          </div>

          <div className="fit-lists">
            <div className="top-fixes">
              <h4>Matched</h4>
              {consolidated.matched.length === 0 ? (
                <p className="today-empty">No clear matches surfaced.</p>
              ) : (
                <ul>
                  {consolidated.matched.map((item, i) => (
                    <li key={i}><span className="status-pill tone-green">✓</span> {item}</li>
                  ))}
                </ul>
              )}
            </div>
            <div className="top-fixes">
              <h4>Missing</h4>
              {consolidated.missing.length === 0 ? (
                <p className="today-empty">No blocking gaps surfaced.</p>
              ) : (
                <ul>
                  {consolidated.missing.map((item, i) => (
                    <li key={i}><span className="status-pill tone-yellow">!</span> {item}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <h3>Per-model scores</h3>
          <div className="rating-grid">
            {result.entries.map((entry, idx) => {
              if ("error" in entry) {
                return (
                  <p key={idx} className="today-empty">
                    {MODEL_NAMES[entry.model]} couldn&apos;t score this ({entry.error})
                  </p>
                );
              }
              return (
                <div className="paper rating-card" key={idx}>
                  <div className="section-head">
                    <h4>{MODEL_NAMES[entry.model]}</h4>
                    <span className={`status-pill ${fitTone(entry.fit)}`}>{entry.fit}%</span>
                  </div>
                  {entry.summary && <p className="feedback">{entry.summary}</p>}
                  {entry.missing.length > 0 && (
                    <ul className="improvements">
                      {entry.missing.map((item, i) => (
                        <li key={i}>{item}</li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
