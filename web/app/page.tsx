"use client";

import { onAuthStateChanged } from "firebase/auth";
import { useEffect, useState } from "react";
import { commandDeckCss } from "./commandDeckCss";
import InterviewPanel from "./InterviewPanel";
import FitPanel from "./FitPanel";
import OkrPanel, { type OkrEvent, type LearningWeek } from "./OkrPanel";
import { resumeFromPayload } from "@/lib/fit";
import { getFirebaseAuth } from "@/lib/firebase-client";

type SheetJob = Record<string, string>;
type BootstrapPayload = { Jobs?: SheetJob[]; "OKR Events"?: SheetJob[]; Learning?: SheetJob[] } & Record<string, unknown>;

// The tracker lives in Google Sheets; all job/application/networking prep happens
// directly in the embedded sheet (each section is its own worksheet tab).
const SHEET_URL =
  "https://docs.google.com/spreadsheets/d/14-8e2qfmDfyFkNJqiErgGyq1LujUw1eWoyvKw9Ap8T4/edit";

const TABS = ["Sheet", "OKRs", "Interview", "Fit"] as const;
const TAB_ICONS = ["▦", "✓", "🎙", "◎"];

export default function Home() {
  // Default to the Sheet — it's where the campaign is actually run.
  const [activeTab, setActiveTab] = useState(0);
  const [sheetLoaded, setSheetLoaded] = useState(false);
  const [sheetState, setSheetState] = useState<"loading" | "live" | "preview">("loading");
  const [jobTitles, setJobTitles] = useState<string[]>([]);
  const [resumeText, setResumeText] = useState<string>("");
  const [okrEvents, setOkrEvents] = useState<OkrEvent[]>([]);
  const [learning, setLearning] = useState<LearningWeek[]>([]);

  useEffect(() => {
    // Guards against a stale bootstrap response calling setState after the component has
    // unmounted (or this effect has re-run) — abort() rejects any in-flight fetch on cleanup.
    const controller = new AbortController();
    const unsubscribe = onAuthStateChanged(getFirebaseAuth(), (user) => {
      (user ? user.getIdToken() : Promise.resolve(null))
        .then((token) =>
          fetch("/api/bootstrap", {
            signal: controller.signal,
            headers: { accept: "application/json", ...(token ? { authorization: `Bearer ${token}` } : {}) },
          }),
        )
        .then(async (response) => {
          if (!response.ok) throw new Error("Sheets backend unavailable");
          return response.json() as Promise<BootstrapPayload>;
        })
        .then((payload) => {
          // Job titles feed the mock interviewer's role context.
          const titles = (payload.Jobs || [])
            .map((row) => (row.Title || "").trim())
            .filter(Boolean)
            .slice(0, 5);
          setJobTitles(titles);
          // Master resume feeds the Fit scorer; empty when the sheet has none.
          const liveResume = resumeFromPayload(payload);
          if (liveResume) setResumeText(liveResume);
          // OKR activity events seed the weekly scorecard's week-to-date counts.
          setOkrEvents(
            (payload["OKR Events"] || [])
              .map((row) => ({ date: (row.Date || "").trim(), kind: (row.Kind || "").trim(), count: Number(row.Count) || 0 }))
              .filter((e) => e.date && e.kind),
          );
          // Weekly learning-progress percentages seed the Learning slider.
          setLearning(
            (payload.Learning || [])
              .map((row) => ({ weekStart: (row["Week Start"] || "").trim(), percent: Number(row.Percent) || 0 }))
              .filter((l) => l.weekStart),
          );
          setSheetState("live");
        })
        .catch((error: unknown) => {
          if (error instanceof DOMException && error.name === "AbortError") return;
          setSheetState("preview");
        });
    });
    return () => {
      controller.abort();
      unsubscribe();
    };
  }, []);

  const sheetLabel =
    sheetState === "live" ? "Sheets live" : sheetState === "loading" ? "Connecting to Sheets…" : "Sheets preview";
  const roleContext = jobTitles.join(", ");

  return <>
    <style>{commandDeckCss}</style>
    <div className="deck">
      <aside className="rail">
        <div className="wordmark"><span>J</span><div><b>Job Action Center</b><small>PRIVATE · SHEETS-BACKED</small></div></div>
        <p className="rail-label">CAMPAIGN</p>
        <nav>{TABS.map((item, index) => (
          <button className={activeTab === index ? "active" : ""} onClick={() => setActiveTab(index)} key={item}>
            <i>{TAB_ICONS[index]}</i>{item}
          </button>
        ))}</nav>
        <div className="week-card"><div><span>Week 1 of 15</span><b>Offer by Nov 1</b></div><div className="segments" aria-label="Week 1 of 15">{Array.from({length:15},(_,i)=><i className={i===0?"filled":""} key={i}/>)}</div><small>Singapore · 15-week campaign</small><p><i/> {sheetLabel}</p></div>
      </aside>

      <main className={activeTab === 0 ? "canvas canvas-sheet" : "canvas"}>
        <iframe
          className="sheet-frame"
          src={SHEET_URL}
          allow="fullscreen"
          allowFullScreen
          title="Job tracker Google Sheet"
          style={{ display: activeTab === 0 ? "block" : "none" }}
          onLoad={() => setSheetLoaded(true)}
        />
        {activeTab === 0 && !sheetLoaded && <div className="sheet-loading">Loading…</div>}
        {activeTab === 1 && <OkrPanel events={okrEvents} learning={learning} />}
        {activeTab === 2 && <InterviewPanel roleContext={roleContext} />}
        {activeTab === 3 && <FitPanel resume={resumeText} />}
      </main>

      <nav className="bottom-nav">{TABS.map((item, index) => (
        <button className={activeTab === index ? "active" : ""} onClick={() => setActiveTab(index)} key={item}>
          <span>{String(index + 1).padStart(2, "0")}</span>{item}
        </button>
      ))}</nav>
    </div>
  </>;
}
