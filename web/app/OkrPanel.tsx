"use client";

import { useState } from "react";
import { getFirebaseAuth } from "@/lib/firebase-client";

// One OKR activity event as loaded from the "OKR Events" sheet.
export type OkrEvent = { date: string; kind: string; count: number };
// One week's learning-progress percentage from the "Learning" sheet.
export type LearningWeek = { weekStart: string; percent: number };

// The user's primary calendar; embedded so the recurring OKR cadence shows in-site.
const CAL_SRC = "evangohsg@gmail.com";
const CAL_EMBED =
  `https://calendar.google.com/calendar/embed?src=${encodeURIComponent(CAL_SRC)}` +
  `&ctz=Asia%2FSingapore&mode=WEEK&wkst=1&showPrint=0&showTabs=1&showCalendars=0`;

const OBJECTIVES: { id: string; title: string; krs: string[] }[] = [
  {
    id: "O1",
    title: "Referral-first pipeline",
    krs: [
      "Lock a 30-company target list (Wk 2)",
      "Contact 5–10 insiders/wk → 60+",
      "≥10% outreach → 6 advocates",
      "Secure 8 referrals",
    ],
  },
  {
    id: "O2",
    title: "Apply with precision · 75% Fit bar",
    krs: [
      "100% of apps score ≥75% on the Fit tab",
      "8 targeted apps/wk, within 48h of posting",
      "Hiring-manager note on 80% of apps",
      "Reply rate 15% (vs ~1% baseline)",
    ],
  },
  {
    id: "O3",
    title: "Convert interviews",
    krs: [
      "2 mocks/wk, avg ≥4.0/5 by Wk 6",
      "Close 1 learning gap/wk",
      "40% first-round → next · 3 finals",
    ],
  },
  {
    id: "O4",
    title: "Compound visibility & craft",
    krs: [
      "1 LinkedIn post/wk (real work-product)",
      "Portfolio #1 by Wk 4, #2 by Wk 10",
      "3h coding + 2h deep work/wk",
    ],
  },
  {
    id: "O5",
    title: "Learning · Claude & AI",
    krs: [
      "Hit ≥80% of the week's learning plan",
      "1 hands-on Claude/AI build per week",
      "Turn 1 learning into a work-product",
    ],
  },
];

// The weekly scorecard — each row maps to an EVENT_KINDS activity and a weekly target.
const WEEKLY: { kind: string; label: string; target: number; timed?: boolean }[] = [
  { kind: "coffee_chat", label: "Coffee chat / insider outreach", target: 5 },
  { kind: "targeted_application", label: "Targeted application · ≥75% Fit", target: 8 },
  { kind: "referral", label: "Referral ask", target: 2 },
  { kind: "linkedin_post", label: "LinkedIn post", target: 1 },
  { kind: "mock_interview", label: "Mock interview", target: 2 },
  { kind: "coding", label: "Coding (hours)", target: 3, timed: true },
  { kind: "stats_deep", label: "Deep work (hours)", target: 2, timed: true },
  { kind: "follow_up", label: "Follow-up by hand", target: 5 },
];

// Most recent Sunday (local date) — the scorecard resets each Sunday, so the week's
// counts naturally start fresh every week ("it repeats").
function weekStartSunday(d = new Date()): string {
  const x = new Date(d);
  x.setDate(x.getDate() - x.getDay());
  return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`;
}

export default function OkrPanel({ events, learning }: { events: OkrEvent[]; learning: LearningWeek[] }) {
  // Local increments logged this session, layered on top of the sheet's week-to-date counts,
  // so a tick shows instantly and survives a late-arriving events prop.
  const [logged, setLogged] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const weekStart = weekStartSunday();
  const base: Record<string, number> = {};
  for (const e of events) {
    if (e.date >= weekStart) base[e.kind] = (base[e.kind] || 0) + (e.count || 0);
  }
  const current = (kind: string) => (base[kind] || 0) + (logged[kind] || 0);

  // Learning progress for this week: the slider value overrides the saved value once touched,
  // so a late-arriving `learning` prop still seeds the initial position.
  const savedLearning = learning.find((l) => l.weekStart === weekStart)?.percent ?? null;
  const [learnOverride, setLearnOverride] = useState<number | null>(null);
  const [learnBusy, setLearnBusy] = useState(false);
  const [learnSaved, setLearnSaved] = useState(false);
  const learnPct = learnOverride ?? savedLearning ?? 0;

  async function saveLearn() {
    setLearnBusy(true);
    setError(null);
    setLearnSaved(false);
    try {
      const token = await getFirebaseAuth().currentUser?.getIdToken();
      const res = await fetch("/api/action", {
        method: "POST",
        headers: {
          authorization: token ? `Bearer ${token}` : "",
          accept: "application/json",
          "content-type": "application/json",
        },
        body: JSON.stringify({
          action: "saveLearning",
          payload: { weekStart, percent: learnPct, focus: "Claude & AI engineering" },
        }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(data.error || `HTTP ${res.status}`);
      }
      setLearnSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save learning progress");
    } finally {
      setLearnBusy(false);
    }
  }

  async function logOne(kind: string, timed?: boolean) {
    setBusy(kind);
    setError(null);
    setLogged((c) => ({ ...c, [kind]: (c[kind] || 0) + 1 })); // optimistic
    try {
      const token = await getFirebaseAuth().currentUser?.getIdToken();
      const res = await fetch("/api/action", {
        method: "POST",
        headers: {
          authorization: token ? `Bearer ${token}` : "",
          accept: "application/json",
          "content-type": "application/json",
        },
        body: JSON.stringify({
          action: "logEvent",
          payload: { kind, count: 1, minutes: timed ? 60 : 0, notes: "Logged from OKRs tab" },
        }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(data.error || `HTTP ${res.status}`);
      }
    } catch (e) {
      setLogged((c) => ({ ...c, [kind]: Math.max(0, (c[kind] || 1) - 1) })); // rollback
      setError(e instanceof Error ? e.message : "Could not log — try again");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="okr-pane">
      <section className="paper">
        <div className="section-head">
          <div><p>THIS WEEK · RESETS SUNDAY</p><h2>Weekly scorecard</h2></div>
          <span>WK OF {weekStart}</span>
        </div>
        <p className="today-empty">
          Tick an activity as you do it — each one logs to your OKR Events sheet and counts toward
          the week&apos;s target. Counts reset every Sunday.
        </p>
        <div className="okr-scorecard">
          {WEEKLY.map((item) => {
            const done = current(item.kind);
            const complete = done >= item.target;
            const pct = Math.min(100, Math.round((done / item.target) * 100));
            return (
              <div className={`okr-kr${complete ? " complete" : ""}`} key={item.kind}>
                <div className="okr-kr-head">
                  <span>{item.label}</span>
                  <b>{done} / {item.target}{item.timed ? "h" : ""}</b>
                </div>
                <div className="okr-bar"><span style={{ width: `${pct}%` }} /></div>
                <button
                  className="okr-tick"
                  type="button"
                  disabled={busy === item.kind}
                  onClick={() => logOne(item.kind, item.timed)}
                  aria-label={`Log one ${item.label}`}
                >
                  {complete ? "✓ done · log more" : busy === item.kind ? "Logging…" : `+ Log ${item.timed ? "1h" : "1"}`}
                </button>
              </div>
            );
          })}
        </div>
        {error && <div className="interview-error" role="alert">{error}</div>}
      </section>

      <section className="paper">
        <div className="section-head">
          <div><p>LEARNING · CLAUDE &amp; AI</p><h2>Weekly learning progress</h2></div>
          <span>WK OF {weekStart}</span>
        </div>
        <p className="today-empty">
          Set how far through this week&apos;s learning plan you are. Saved per week, resets Sunday.
        </p>
        <div className="okr-learning">
          <div className="okr-learning-head">
            <span>Claude &amp; AI engineering</span>
            <b>{learnPct}% <small>this week</small></b>
          </div>
          <div className={`okr-bar${learnPct >= 80 ? " complete" : ""}`}><span style={{ width: `${learnPct}%` }} /></div>
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={learnPct}
            aria-label="Weekly learning completion percent"
            onChange={(e) => { setLearnOverride(Number(e.target.value)); setLearnSaved(false); }}
          />
          <div className="okr-learning-actions">
            <button className="okr-tick" type="button" disabled={learnBusy} onClick={saveLearn}>
              {learnBusy ? "Saving…" : learnSaved ? "✓ saved" : "Save this week"}
            </button>
          </div>
        </div>
      </section>

      <section className="paper">
        <div className="section-head">
          <div><p>OBJECTIVES · OFFER BY 1 NOV</p><h2>Campaign OKRs</h2></div>
          <span>15-WEEK</span>
        </div>
        <div className="okr-objectives">
          {OBJECTIVES.map((o) => (
            <div className="okr-obj" key={o.id}>
              <h3>{o.id} · {o.title}</h3>
              <ul>{o.krs.map((kr) => <li key={kr}>{kr}</li>)}</ul>
            </div>
          ))}
        </div>
      </section>

      <section className="paper okr-calendar">
        <div className="section-head">
          <div><p>CADENCE</p><h2>Calendar</h2></div>
          <span>ASIA/SINGAPORE</span>
        </div>
        <iframe
          className="okr-cal-frame"
          src={CAL_EMBED}
          title="OKR cadence calendar"
          loading="lazy"
        />
        <p className="today-empty">
          Recurring OKR blocks live on your Google Calendar. If the calendar looks empty, make sure
          this browser is signed in to {CAL_SRC}.
        </p>
      </section>
    </div>
  );
}
