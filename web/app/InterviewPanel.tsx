"use client";

import { useEffect, useRef, useState } from "react";
import { getFirebaseAuth } from "@/lib/firebase-client";
import { RUBRIC } from "@/lib/interview";

type SpeechRecognitionCtor = new () => MinimalSpeechRecognition;

interface MinimalRecognitionAlternative {
  readonly transcript: string;
}

interface MinimalRecognitionResult {
  readonly isFinal: boolean;
  readonly length: number;
  readonly [index: number]: MinimalRecognitionAlternative;
}

interface MinimalRecognitionResultList {
  readonly length: number;
  readonly [index: number]: MinimalRecognitionResult;
}

interface MinimalRecognitionEvent {
  readonly resultIndex: number;
  readonly results: MinimalRecognitionResultList;
}

interface MinimalSpeechRecognition {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: MinimalRecognitionEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  start(): void;
  stop(): void;
}

type ModelKey = "kimi" | "deepseek" | "mimo";

interface RatingSuccess {
  model: ModelKey;
  scores: Record<string, number>;
  overall: number;
  feedback: string;
  improvements: string[];
}

interface RatingError {
  model: ModelKey;
  error: string;
}

type RatingEntry = RatingSuccess | RatingError;

interface RateResponse {
  ok: true;
  ratings: RatingEntry[];
  consolidated: {
    scores: Record<string, number>;
    overall: number;
    topFixes: string[];
  };
}

const MODEL_NAMES: Record<ModelKey, string> = {
  kimi: "Kimi",
  deepseek: "DeepSeek",
  mimo: "MiMo",
};

const FALLBACK_QUESTIONS = [
  "Tell me about a time you built or scaled a data platform. What decisions mattered most?",
  "Describe a conflict with a senior stakeholder over data strategy. How did you resolve it?",
  "Walk me through how you evaluate and productionize a machine-learning model.",
  "Tell me about a data or AI project that failed and what you learned.",
];

function toneClass(score: number): string {
  if (score >= 4) return "tone-green";
  if (score >= 3) return "tone-yellow";
  return "tone-red";
}

export default function InterviewPanel({
  roleContext,
}: {
  roleContext: string;
}) {
  const [questions, setQuestions] = useState<string[]>([]);
  const [loadingQuestions, setLoadingQuestions] = useState(true);
  const [qIndex, setQIndex] = useState(0);
  const [isRecording, setIsRecording] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [audioUrl, setAudioUrlState] = useState<string | null>(null);
  const [transcribeUnsupported, setTranscribeUnsupported] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RateResponse | null>(null);

  const mountedRef = useRef(true);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recognitionRef = useRef<MinimalSpeechRecognition | null>(null);
  const audioUrlRef = useRef<string | null>(null);

  const currentQuestion = questions[qIndex] ?? "";

  const setAudioUrl = (url: string | null) => {
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
    }
    audioUrlRef.current = url;
    setAudioUrlState(url);
  };

  const stopTracks = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  };

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      try {
        mediaRecorderRef.current?.stop();
      } catch {
        /* ignore */
      }
      recognitionRef.current?.stop();
      stopTracks();
      if (audioUrlRef.current) {
        URL.revokeObjectURL(audioUrlRef.current);
      }
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadQuestions() {
      try {
        const token = await getFirebaseAuth().currentUser?.getIdToken();
        const res = await fetch("/api/interview/questions", {
          headers: {
            authorization: token ? `Bearer ${token}` : "",
            accept: "application/json",
          },
        });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const data = (await res.json()) as { questions: string[] };
        if (!cancelled) {
          setQuestions(data.questions?.length ? data.questions : FALLBACK_QUESTIONS);
        }
      } catch {
        if (!cancelled) {
          setQuestions(FALLBACK_QUESTIONS);
        }
      } finally {
        if (!cancelled) {
          setLoadingQuestions(false);
        }
      }
    }

    void loadQuestions();
    return () => {
      cancelled = true;
    };
  }, []);

  async function startRecording() {
    setError(null);
    setTranscribeUnsupported(false);
    setTranscript("");
    setAudioUrl(null);

    try {
      if (
        !navigator.mediaDevices ||
        typeof navigator.mediaDevices.getUserMedia !== "function"
      ) {
        throw new Error("Microphone access is not supported in this browser.");
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      if (typeof MediaRecorder === "undefined") {
        throw new Error("MediaRecorder is not supported in this browser.");
      }

      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      recorder.onerror = () => {
        recognitionRef.current?.stop();
        recognitionRef.current = null;
        stopTracks();
        setIsRecording(false);
        setError("Recording error — please try again.");
      };

      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunks.push(event.data);
        }
      };

      recorder.onstop = () => {
        const blob = new Blob(chunks, {
          type: recorder.mimeType || "audio/webm",
        });
        if (blob.size > 0 && mountedRef.current) {
          setAudioUrl(URL.createObjectURL(blob));
        }
        stream.getTracks().forEach((track) => track.stop());
      };

      recorder.start();

      const win = window as unknown as {
        SpeechRecognition?: SpeechRecognitionCtor;
        webkitSpeechRecognition?: SpeechRecognitionCtor;
      };
      const RecognitionCtor = win.SpeechRecognition ?? win.webkitSpeechRecognition;

      if (RecognitionCtor) {
        const recognition = new RecognitionCtor();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = "en-US";
        recognition.onresult = (event) => {
          let final = "";
          // `results` is cumulative; start at `resultIndex` (the first changed
          // result) so we never re-append phrases finalized in earlier events.
          for (let i = event.resultIndex; i < event.results.length; i++) {
            const res = event.results[i];
            // A SpeechRecognitionResult is array-like; the best alternative's
            // text lives at index 0. `isFinal` marks a settled phrase.
            if (res.isFinal && res.length > 0) {
              final += res[0].transcript;
            }
          }
          if (final.trim()) {
            setTranscript((prev) => (prev ? `${prev} ` : "") + final.trim());
          }
        };
        recognition.onerror = (event) => {
          if (event.error !== "no-speech" && event.error !== "aborted") {
            setError(`Transcription error: ${event.error}`);
          }
        };
        recognition.start();
        recognitionRef.current = recognition;
      } else {
        setTranscribeUnsupported(true);
      }

      setIsRecording(true);
    } catch (err) {
      try {
        mediaRecorderRef.current?.stop();
      } catch {
        /* ignore */
      }
      mediaRecorderRef.current = null;
      recognitionRef.current?.stop();
      recognitionRef.current = null;
      stopTracks();
      setIsRecording(false);
      setError(err instanceof Error ? err.message : "Could not start recording");
    }
  }

  function stopRecording() {
    try {
      mediaRecorderRef.current?.stop();
    } catch {
      /* ignore */
    }
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    stopTracks();
    setIsRecording(false);
  }

  async function submitForRating() {
    if (!transcript.trim()) return;

    setIsSubmitting(true);
    setError(null);
    setResult(null);

    try {
      const token = await getFirebaseAuth().currentUser?.getIdToken();
      const res = await fetch("/api/interview/rate", {
        method: "POST",
        headers: {
          authorization: token ? `Bearer ${token}` : "",
          accept: "application/json",
          "content-type": "application/json",
        },
        body: JSON.stringify({
          question: currentQuestion,
          transcript,
          roleContext,
        }),
      });

      const data = (await res.json()) as {
        ok?: boolean;
        error?: string;
        ratings?: RatingEntry[];
        consolidated?: RateResponse["consolidated"];
      };

      if (!res.ok || data.ok !== true) {
        setError(data.error ?? `Request failed (${res.status})`);
      } else {
        setResult(data as RateResponse);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Rating request failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="paper interview-pane">
      <div className="section-head">
        <div><p>PRACTICE</p><h2>Mock interviewer</h2></div>
        {roleContext && <span className="status-pill tone-grey">{roleContext}</span>}
      </div>

      {loadingQuestions ? (
        <div className="today-empty">
          <span className="interview-spinner" aria-hidden />
          Loading tailored questions…
        </div>
      ) : (
        <div className="interview-controls">
          <select
            aria-label="Select a question"
            value={qIndex}
            onChange={(e) => setQIndex(Number(e.target.value))}
          >
            {questions.map((q, i) => (
              <option key={i} value={i}>
                {q}
              </option>
            ))}
          </select>

          <button
            className="ghost"
            type="button"
            disabled={questions.length === 0}
            onClick={() =>
              setQIndex((prev) => (prev + 1) % Math.max(questions.length, 1))
            }
          >
            New question
          </button>
        </div>
      )}

      <div className="recorder-row">
        <button
          className={`go ${isRecording ? "recording" : ""}`}
          type="button"
          disabled={loadingQuestions}
          onClick={isRecording ? stopRecording : startRecording}
        >
          {isRecording ? "Stop" : "Record answer"}
        </button>

        {isRecording && <span className="record-pulse" aria-hidden />}
        {isRecording && (
          <span className="today-empty">Recording… speak clearly</span>
        )}
      </div>

      {transcribeUnsupported && (
        <p className="today-empty">
          Live transcription is unavailable in this browser. Your audio is still
          being recorded — please type or paste your answer below.
        </p>
      )}

      <textarea
        className="transcript-area"
        aria-label="Your interview answer transcript"
        placeholder="Your answer will appear here. Edit it directly or type your own."
        value={transcript}
        onChange={(e) => setTranscript(e.target.value)}
      />

      {audioUrl && <audio controls src={audioUrl} />}

      <button
        className="go"
        type="button"
        disabled={isSubmitting || !transcript.trim()}
        onClick={submitForRating}
      >
        {isSubmitting ? "3 interviewers scoring…" : "Submit for rating"}
      </button>

      <p className="today-empty">
        Your transcript (not your audio) is sent to Kimi, DeepSeek and MiMo for scoring.
      </p>

      {error && (
        <div className="interview-error" role="alert">
          {error}
        </div>
      )}

      {result && (
        <div className="rating-results">
          <h3>Consolidated scorecard</h3>
          <div className="evidence-summary">
            <div className="consolidated-overall">
              <span
                className={`status-pill ${toneClass(
                  result.consolidated.overall
                )}`}
              >
                {result.consolidated.overall.toFixed(1)}
              </span>
              <span>Overall</span>
            </div>
            {RUBRIC.map((rubric) => {
              const score = result.consolidated.scores[rubric.key] ?? 0;
              return (
                <div className="kr" key={rubric.key}>
                  <span>{rubric.label}</span>
                  <span className={`status-pill ${toneClass(score)}`}>
                    {score.toFixed(1)}
                  </span>
                </div>
              );
            })}
          </div>

          {result.consolidated.topFixes.length > 0 && (
            <div className="top-fixes">
              <h4>Top fixes</h4>
              <ul>
                {result.consolidated.topFixes.map((fix, i) => (
                  <li key={i}>{fix}</li>
                ))}
              </ul>
            </div>
          )}

          <h3>Per-model ratings</h3>
          <div className="rating-grid">
            {result.ratings.map((entry, idx) => {
              if ("error" in entry) {
                return (
                  <p key={idx} className="today-empty">
                    {MODEL_NAMES[entry.model]} couldn&apos;t score this (
                    {entry.error})
                  </p>
                );
              }

              return (
                <div className="paper rating-card" key={idx}>
                  <div className="section-head">
                    <h4>{MODEL_NAMES[entry.model]}</h4>
                    <span
                      className={`status-pill ${toneClass(entry.overall)}`}
                    >
                      {entry.overall.toFixed(1)}
                    </span>
                  </div>

                  <div className="evidence-summary">
                    {RUBRIC.map((rubric) => {
                      const score = entry.scores[rubric.key] ?? 0;
                      return (
                        <div className="kr" key={rubric.key}>
                          <span>{rubric.label}</span>
                          <span className={`status-pill ${toneClass(score)}`}>
                            {score.toFixed(1)}
                          </span>
                        </div>
                      );
                    })}
                  </div>

                  <p className="feedback">{entry.feedback}</p>

                  {entry.improvements.length > 0 && (
                    <ul className="improvements">
                      {entry.improvements.map((improvement, i) => (
                        <li key={i}>{improvement}</li>
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
