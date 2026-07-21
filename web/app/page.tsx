"use client";

import { onAuthStateChanged } from "firebase/auth";
import { useEffect, useRef, useState } from "react";
import { commandDeckCss } from "./commandDeckCss";
import { getFirebaseAuth } from "@/lib/firebase-client";

type Job = {
  key: string;
  company: string;
  title: string;
  score: number | null;
  tier: string;
  status: string;
  reason: string;
  brief: string;
  url: string;
};

type SheetJob = Record<string, string>;

const previewJobs: Job[] = [
  { key: "preview-northstar", company: "Northstar Bank", title: "Senior Data Scientist, GenAI", score: 92, tier: "A", status: "New", reason: "GenAI evaluation · Banking domain · 2 warm contacts", brief: "Lead applied AI use cases, model evaluation and regional stakeholder delivery across a complex banking environment.", url: "" },
  { key: "preview-meridian", company: "Meridian Financial", title: "VP, Data Science & Analytics", score: 87, tier: "B", status: "Drafting", reason: "Analytics leadership · Regional scope", brief: "Own the analytics roadmap and build high-impact data products with senior business partners.", url: "" },
  { key: "preview-civic", company: "Civic Digital", title: "AI Product Lead", score: 84, tier: "B", status: "New", reason: "Responsible AI · Product strategy", brief: "Shape responsible AI products from discovery through scaled adoption.", url: "" },
];

type StatusTone = "grey" | "blue" | "green" | "red" | "yellow";

const statusTones: Record<string, StatusTone> = {
  new: "grey",
  drafting: "grey",
  applied: "yellow",
  interview: "blue",
  offer: "green",
  rejected: "red",
};

function statusTone(status: string): StatusTone {
  return statusTones[status.trim().toLowerCase()] ?? "grey";
}

function statusLabel(status: string): string {
  return status.trim() || "No status";
}

function fromSheet(row: SheetJob): Job | null {
  const company = row.Company?.trim();
  const title = row.Title?.trim();
  if (!company || !title) return null;
  const rawScore = row.Score?.trim() || "";
  const hasNumericScore = /^\d+(?:\.\d+)?$/.test(rawScore);
  const score = hasNumericScore ? Math.max(0, Math.min(100, Math.round(Number(rawScore)))) : null;
  const tier = row.Tier?.trim() || (score === null ? "Pending" : score >= 90 ? "A" : score >= 75 ? "B" : "C");
  const status = row.Status?.trim() || "New";
  const source = row.Source?.trim() || "Google Sheets";
  return {
    key: row.DedupeKey?.trim() || `${company}:${title}`,
    company,
    title,
    score,
    tier,
    status,
    reason: `${score === null ? "Fit score pending" : `${score}% backend fit`} · Tier ${tier} · ${source}`,
    brief: row.Description?.trim() || "No role description has been stored in the Jobs sheet yet.",
    url: row.URL?.trim() || "",
  };
}

type BootstrapPayload = {
  Jobs?: SheetJob[];
  Applications?: SheetJob[];
  "Networking Tracker"?: SheetJob[];
  "OKR Events"?: SheetJob[];
  "Learning Gaps"?: SheetJob[];
  "Weekly Reviews"?: SheetJob[];
};

interface Application {
  key: string;
  job?: string;
  company: string;
  title: string;
  appLink: string;
  resumeFile: string;
  coverLetter: string;
  matchedKeywords: string;
  status: string;
  updated: string;
  resumeBlockIds: string;
}

interface Contact {
  key: string;
  name: string;
  email: string;
  company: string;
  role: string;
  linkedIn: string;
  source: string;
  lastContacted: string;
  status: string;
  notes: string;
  followUpDue: string;
}

interface OkrEvent {
  key: string;
  date: string;
  kind: string;
  count: number;
  minutes: number;
  job: string;
  contact: string;
  notes: string;
  created: string;
}

interface LearningGap {
  key: string;
  found: string;
  source: string;
  gap: string;
  priority: string;
  reviewPlan: string;
  driveState: string;
  driveReference: string;
  resolved: string;
}

interface WeeklyReview {
  key: string;
  weekStart: string;
  krActuals: string;
  pipeline: string;
  followUps: string;
  gaps: string;
  chatsSourced: string;
  decision: string;
  completed: string;
}

function fromApplication(row: SheetJob): Application | null {
  const company = row.Company?.trim();
  const title = row.Title?.trim();
  if (!company || !title) return null;
  return {
    key: row.Key?.trim() || `${company}:${title}`,
    job: row.Job?.trim(),
    company,
    title,
    appLink: row["Application Link"]?.trim() || "",
    resumeFile: row["Resume File"]?.trim() || "",
    coverLetter: row["Cover Letter"]?.trim() || "",
    matchedKeywords: row["Matched Keywords"]?.trim() || "",
    status: row.Status?.trim() || "New",
    updated: row.Updated?.trim() || "",
    resumeBlockIds: row["Resume Block IDs"]?.trim() || "",
  };
}

function fromContact(row: SheetJob): Contact | null {
  const name = row.Name?.trim();
  if (!name) return null;
  return {
    key: row.Key?.trim() || name,
    name,
    email: row.Email?.trim() || "",
    company: row.Company?.trim() || "",
    role: row.Role?.trim() || "",
    linkedIn: row.LinkedIn?.trim() || "",
    source: row.Source?.trim() || "",
    lastContacted: row["Last Contacted"]?.trim() || "",
    status: row.Status?.trim() || "",
    notes: row.Notes?.trim() || "",
    followUpDue: row["Follow Up Due"]?.trim() || "",
  };
}

function parseNumberBlank(value: string | undefined): number {
  const trimmed = value?.trim() || "";
  if (!trimmed) return 0;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : 0;
}

function fromOkrEvent(row: SheetJob): OkrEvent | null {
  const key = row.Key?.trim();
  if (!key) return null;
  return {
    key,
    date: row.Date?.trim() || "",
    kind: row.Kind?.trim() || "",
    count: parseNumberBlank(row.Count),
    minutes: parseNumberBlank(row.Minutes),
    job: row.Job?.trim() || "",
    contact: row.Contact?.trim() || "",
    notes: row.Notes?.trim() || "",
    created: row.Created?.trim() || "",
  };
}

function fromLearningGap(row: SheetJob): LearningGap | null {
  const gap = row.Gap?.trim();
  if (!gap) return null;
  return {
    key: row.Key?.trim() || gap,
    found: row.Found?.trim() || "",
    source: row.Source?.trim() || "",
    gap,
    priority: row.Priority?.trim() || "",
    reviewPlan: row["Review Plan"]?.trim() || "",
    driveState: row["Drive State"]?.trim() || "",
    driveReference: row["Drive Reference"]?.trim() || "",
    resolved: row.Resolved?.trim() || "",
  };
}

function fromWeeklyReview(row: SheetJob): WeeklyReview | null {
  const weekStart = row["Week Start"]?.trim();
  if (!weekStart) return null;
  return {
    key: row.Key?.trim() || weekStart,
    weekStart,
    krActuals: row["KR Actuals"]?.trim() || "",
    pipeline: row.Pipeline?.trim() || "",
    followUps: row["Follow Ups"]?.trim() || "",
    gaps: row.Gaps?.trim() || "",
    chatsSourced: row["Chats Sourced"]?.trim() || "",
    decision: row.Decision?.trim() || "",
    completed: row.Completed?.trim() || "",
  };
}

function todayIso(): string {
  // Local calendar date (not UTC) so date filters match the user's timezone, e.g. SGT.
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function isOpenApp(status: string): boolean {
  // "To send" = not yet submitted; interview/applied/offer/rejected are already out the door.
  return ["", "new", "drafting", "drafted"].includes(status.trim().toLowerCase());
}

function followUpSort(a: Contact, b: Contact): number {
  if (!a.followUpDue && !b.followUpDue) return 0;
  if (!a.followUpDue) return 1;
  if (!b.followUpDue) return -1;
  return a.followUpDue.localeCompare(b.followUpDue);
}

function pipelineGroups(apps: Application[]): { label: string; tone: StatusTone; items: Application[] }[] {
  const order = ["drafted", "applied", "interview", "offer", "rejected"];
  const labels: Record<string, string> = {
    drafted: "Drafting / New",
    applied: "Applied",
    interview: "Interview",
    offer: "Offer",
    rejected: "Rejected",
  };
  const toneSource: Record<string, string> = {
    drafted: "drafting",
    applied: "applied",
    interview: "interview",
    offer: "offer",
    rejected: "rejected",
  };
  const buckets: Record<string, Application[]> = {
    drafted: [],
    applied: [],
    interview: [],
    offer: [],
    rejected: [],
    other: [],
  };
  for (const app of apps) {
    const s = app.status.trim().toLowerCase();
    let key = "other";
    if (s === "new" || s === "drafting" || s === "drafted") key = "drafted";
    else if (order.includes(s)) key = s;
    buckets[key].push(app);
  }
  const groups = order.map((key) => ({
    label: labels[key],
    tone: statusTone(toneSource[key]),
    items: buckets[key],
  }));
  if (buckets.other.length) {
    groups.push({ label: "Other", tone: statusTone(""), items: buckets.other });
  }
  return groups;
}

function gapOpen(resolved: string): boolean {
  const r = resolved.trim().toLowerCase();
  return !r || r === "false" || r === "no" || r === "0";
}

function openGapsByPriority(gaps: LearningGap[]): { priority: string; items: LearningGap[] }[] {
  const order = ["high", "medium", "low"];
  const buckets: Record<string, LearningGap[]> = { high: [], medium: [], low: [], other: [] };
  for (const g of gaps) {
    const p = g.priority.trim().toLowerCase();
    if (order.includes(p)) buckets[p].push(g);
    else buckets.other.push(g);
  }
  const result = order.filter((k) => buckets[k].length).map((k) => ({ priority: k, items: buckets[k] }));
  if (buckets.other.length) result.push({ priority: "Other", items: buckets.other });
  return result;
}

function latestWeeklyReview(reviews: WeeklyReview[]): WeeklyReview | null {
  if (!reviews.length) return null;
  return reviews.reduce((latest, r) => (r.weekStart > latest.weekStart ? r : latest));
}

const previewApplications: Application[] = [
  { key: "preview-app-northstar", job: "preview-northstar", company: "Northstar Bank", title: "Senior Data Scientist, GenAI", appLink: "", resumeFile: "", coverLetter: "", matchedKeywords: "Python, MLOps, Banking", status: "Drafting", updated: "", resumeBlockIds: "1,2" },
  { key: "preview-app-meridian", job: "preview-meridian", company: "Meridian Financial", title: "VP, Data Science & Analytics", appLink: "", resumeFile: "", coverLetter: "", matchedKeywords: "Leadership, Analytics", status: "Applied", updated: "", resumeBlockIds: "1,3" },
  { key: "preview-app-civic", job: "preview-civic", company: "Civic Digital", title: "AI Product Lead", appLink: "", resumeFile: "", coverLetter: "", matchedKeywords: "Product, Responsible AI", status: "Interview", updated: "", resumeBlockIds: "2,3" },
];

const previewContacts: Contact[] = [
  { key: "preview-contact-sarah", name: "Sarah Chen", email: "sarah.chen@meridian.financial", company: "Meridian Financial", role: "VP Analytics", linkedIn: "https://linkedin.com/in/sarahchen", source: "LinkedIn outbound", lastContacted: "2025-08-10", status: "Warm intro", notes: "Introduced me to the hiring manager", followUpDue: "2025-08-13" },
  { key: "preview-contact-daniel", name: "Daniel Park", email: "daniel.park@civic.digital", company: "Civic Digital", role: "AI Product Lead", linkedIn: "", source: "Referral", lastContacted: "2025-08-08", status: "Need reply", notes: "Asked for portfolio link", followUpDue: "2025-08-12" },
];

const previewEvents: OkrEvent[] = [
  { key: "preview-event-chat", date: "2025-08-13", kind: "Coffee chat", count: 1, minutes: 30, job: "", contact: "Sarah Chen", notes: "Warm intro call, shared team context", created: "" },
  { key: "preview-event-app", date: "2025-08-13", kind: "Application", count: 1, minutes: 90, job: "Senior Data Scientist, GenAI", contact: "", notes: "Submitted tailored package to Northstar", created: "" },
  { key: "preview-event-post", date: "2025-08-12", kind: "LinkedIn post", count: 1, minutes: 20, job: "", contact: "", notes: "Shared learnings on GenAI evaluation", created: "" },
];

const previewGaps: LearningGap[] = [
  { key: "preview-gap-mlops", found: "2025-08-11", source: "JD review — Northstar", gap: "MLOps on AWS SageMaker", priority: "High", reviewPlan: "Complete AWS ML Engineer course + lab", driveState: "Planned", driveReference: "", resolved: "No" },
  { key: "preview-gap-system", found: "2025-08-10", source: "Mock interview", gap: "System design for GenAI products", priority: "Medium", reviewPlan: "Practice 2 case studies this week", driveState: "Planned", driveReference: "", resolved: "No" },
  { key: "preview-gap-finance", found: "2025-08-09", source: "Coffee chat", gap: "Banking risk framework basics", priority: "Low", reviewPlan: "Read MAS TRM guidelines summary", driveState: "Planned", driveReference: "", resolved: "No" },
];

const previewReviews: WeeklyReview[] = [
  { key: "preview-review-w2", weekStart: "2025-08-11", krActuals: "2/5 chats · 1/10 apps · 1/1 posts", pipeline: "3 drafting · 1 applied · 1 interview", followUps: "2 due", gaps: "2 open", chatsSourced: "3", decision: "Focus on Tier A banks this week", completed: "No" },
  { key: "preview-review-w1", weekStart: "2025-08-04", krActuals: "1/5 chats · 0/10 apps · 0/1 posts", pipeline: "2 drafting", followUps: "1 due", gaps: "1 open", chatsSourced: "1", decision: "Build portfolio piece before applying", completed: "Yes" },
];
const resumeBlocks = [
  "Led regional analytics strategy across business and technology teams, translating complex data into executive decisions and measurable delivery outcomes.",
  "Built and evaluated machine-learning solutions using Python, SQL and large-scale customer datasets, partnering with risk and product stakeholders.",
  "Drove adoption of responsible generative-AI workflows through structured enablement, governance and cross-regional stakeholder engagement.",
];

export default function Home() {
  const [selected, setSelected] = useState(0);
  const [activeTab, setActiveTab] = useState(0);
  const [modal, setModal] = useState(false);
  const [blocks, setBlocks] = useState([0, 1]);
  const [jobs, setJobs] = useState<Job[]>(previewJobs);
  const [sheetState, setSheetState] = useState<"loading" | "live" | "preview">("loading");
  const [sheetLoaded, setSheetLoaded] = useState(false);
  const [query, setQuery] = useState("");
  const [dailyChecklist, setDailyChecklist] = useState([false, false]);
  const [applications, setApplications] = useState<Application[]>(previewApplications);
  const [contacts, setContacts] = useState<Contact[]>(previewContacts);
  const [events, setEvents] = useState<OkrEvent[]>(previewEvents);
  const [gaps, setGaps] = useState<LearningGap[]>(previewGaps);
  const [reviews, setReviews] = useState<WeeklyReview[]>(previewReviews);
  const [tierFilter, setTierFilter] = useState<"all" | "A" | "B">("all");
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const [modalStep, setModalStep] = useState<2 | 3>(2);
  const dailyChecklistDone = dailyChecklist.every(Boolean);
  const job = jobs[selected] ?? jobs[0];
  const normalizedQuery = query.trim().toLowerCase();
  const jobMatchesFilters = (item: Job, skipSet: Set<string>) =>
    !skipSet.has(item.key)
    && (tierFilter === "all" || item.tier.trim().toUpperCase() === tierFilter)
    && (!normalizedQuery || `${item.company} ${item.title} ${item.status} ${item.tier}`.toLowerCase().includes(normalizedQuery));
  const visibleJobs = jobs.filter((item) => jobMatchesFilters(item, skipped));
  const modalRef = useRef<HTMLElement>(null);
  const continueButtonRef = useRef<HTMLButtonElement>(null);
  const modalTriggerRef = useRef<HTMLElement>(null);

  function openModal(event: React.MouseEvent<HTMLButtonElement>) {
    modalTriggerRef.current = event.currentTarget;
    setModalStep(2);
    setModal(true);
  }

  function closeModal() {
    setModal(false);
    setModalStep(2);
    modalTriggerRef.current?.focus();
  }

  function toggleDailyRole(index: number) {
    setDailyChecklist((current) => current.map((value, i) => (i === index ? !value : value)));
  }

  function handleSkip() {
    if (!job) return;
    const nextSkipped = new Set(skipped);
    nextSkipped.add(job.key);
    setSkipped(nextSkipped);
    const nextVisible = jobs.filter((item) => jobMatchesFilters(item, nextSkipped));
    if (nextVisible.length > 0) {
      const nextIndex = jobs.findIndex((candidate) => candidate.key === nextVisible[0].key);
      setSelected(nextIndex >= 0 ? nextIndex : 0);
    }
  }

  useEffect(() => {
    if (!modal) return;
    const container = modalRef.current;
    const focusable = () =>
      Array.from(container?.querySelectorAll<HTMLElement>('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])') || []);

    // Auto-focus: prefer the primary "Continue to review" action, falling back to the first
    // focusable element when it is disabled (e.g. no resume blocks selected yet).
    const initialTarget = continueButtonRef.current && !continueButtonRef.current.disabled ? continueButtonRef.current : focusable()[0];
    initialTarget?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeModal();
        return;
      }
      if (event.key !== "Tab") return;
      const elements = focusable();
      if (!elements.length) return;
      const first = elements[0];
      const last = elements[elements.length - 1];
      // Focus trap: wrap Tab/Shift+Tab around the modal's boundary elements instead of
      // letting focus escape to the page behind it.
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [modal, modalStep]);

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
          const liveJobs = (payload.Jobs || [])
            .map(fromSheet)
            .filter((item): item is Job => Boolean(item))
            .sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
          if (!liveJobs.length) throw new Error("No jobs in Sheets");
          setJobs(liveJobs);
          setSelected(0);
          setSheetState("live");
          setApplications((payload.Applications || []).map(fromApplication).filter((item): item is Application => Boolean(item)));
          setContacts(
            (payload["Networking Tracker"] || [])
              .map(fromContact)
              .filter((item): item is Contact => Boolean(item))
              .sort(followUpSort),
          );
          setEvents((payload["OKR Events"] || []).map(fromOkrEvent).filter((item): item is OkrEvent => Boolean(item)));
          setGaps((payload["Learning Gaps"] || []).map(fromLearningGap).filter((item): item is LearningGap => Boolean(item)));
          setReviews((payload["Weekly Reviews"] || []).map(fromWeeklyReview).filter((item): item is WeeklyReview => Boolean(item)));
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

  const sheetLabel = sheetState === "live" ? "Sheets live · backend fit" : sheetState === "loading" ? "Connecting to Sheets…" : "Sheets preview · sample fit";
  return <>
    <style>{commandDeckCss}</style>
    {activeTab !== 5 && <a className="skip" href="#next-action">Skip to next action</a>}
    <div className="deck">
      <aside className="rail">
        <div className="wordmark"><span>J</span><div><b>Job Action Center</b><small>PRIVATE · SHEETS-BACKED</small></div></div>
        <p className="rail-label">CAMPAIGN</p>
        <nav>{["Apply","Today","Pipeline","Network","Review","Sheet"].map((item,index)=>{const enabled=index>=0&&index<=5;return <button className={activeTab===index?"active":""} disabled={!enabled} title={!enabled?"Coming soon":undefined} onClick={enabled?()=>setActiveTab(index):undefined} key={item}><i>{index===5?"▦":String(index+1).padStart(2,"0")}</i>{item}</button>})}</nav>
        <div className="week-card"><div><span>Week 1 of 15</span><b>Offer by Nov 1</b></div><div className="segments" aria-label="Week 1 of 15">{Array.from({length:15},(_,i)=><i className={i===0?"filled":""} key={i}/>)}</div><small>Singapore · 15-week campaign</small><p><i/> {sheetLabel}</p></div>
      </aside>

      <main className={activeTab === 5 ? "canvas canvas-sheet" : "canvas"}>
        <iframe
          className="sheet-frame"
          src="https://docs.google.com/spreadsheets/d/14-8e2qfmDfyFkNJqiErgGyq1LujUw1eWoyvKw9Ap8T4/edit"
          allow="fullscreen"
          allowFullScreen
          title="Job tracker Google Sheet"
          style={{ display: activeTab === 5 ? "block" : "none" }}
          onLoad={() => setSheetLoaded(true)}
        />
        {activeTab === 5 && !sheetLoaded && <div className="sheet-loading">Loading…</div>}
        {activeTab === 0 && <>
        <header className="top"><div><p>APPLY</p><h2>Week 1 · Build momentum deliberately</h2></div><div className="top-actions">
          <div className="daily-checklist">
            <span className="daily-checklist-done" role="status" aria-live="polite" aria-atomic="true">{dailyChecklistDone && "Done for today! 🎯"}</span>
            <span className="daily-checklist-label">Apply to 2 roles today</span>
            <div className="daily-checklist-items">{dailyChecklist.map((checked,index)=><label key={index}><input type="checkbox" checked={checked} onChange={()=>toggleDailyRole(index)} />Role {index+1}</label>)}</div>
          </div>
          <button className="quiet" disabled title="Review-first — gaps are logged from the CLI and shown in the Review tab">Log learning gap</button><span className="sync"><i/> {sheetLabel}</span></div></header>

        <section className="briefing" id="next-action">
          <div className="brief-main"><p className="gold-label">YOUR #1 NEXT ACTION — RANKED BY FIT</p><div className="company"><span>{job.company.slice(0,1).toUpperCase()}</span>{job.company}</div><h1>{job.title}</h1><div className="meta"><span>Singapore</span><span>Hybrid</span><span>Backend ranked</span><span>{sheetState === "live" ? "Live sheet record" : "Preview record"}</span></div><div className="why">{job.reason.split(" · ").map(reason=><span key={reason}>{reason}</span>)}</div></div>
          <div className="dial-area"><div className="dial" style={{background:`conic-gradient(var(--brass) 0 ${job.score ?? 0}%, #4a4438 ${job.score ?? 0}%)`}}><div><strong>{job.score ?? "—"}</strong><small>{job.score === null ? "PENDING" : "FIT"}</small></div></div><div className="badges"><span>Tier {job.tier}</span></div></div>
          <div className="brief-actions"><button className="go" onClick={openModal}>Start application package</button><span className={`status-pill lg tone-${statusTone(job.status)}`}>{statusLabel(job.status)}</span><button className="ghost" disabled={!job.url} onClick={()=>job.url&&window.open(job.url,"_blank","noopener,noreferrer")}>Open role posting ↗</button><button className="text-action" onClick={handleSkip}>Skip for today</button><p>You always submit on the employer&apos;s own form. Nothing here auto-submits.</p></div>
          <blockquote>One strong application beats ten rushed ones.</blockquote>
        </section>

        <div className="workspace">
          <section className="paper queue">
            <div className="section-head"><div><p>RANKED BY BACKEND FIT</p><h2>Application queue</h2></div><span>{visibleJobs.length}{normalizedQuery ? ` / ${jobs.length}` : ""} ROLES</span></div>
            <label className="search"><span>Search roles</span><input placeholder="Company or title" value={query} onChange={(event)=>setQuery(event.target.value)} /></label>
            <div className="filters">
              <button className={tierFilter === "all" ? "on" : ""} onClick={() => setTierFilter("all")}>All</button>
              <button className={tierFilter === "A" ? "on" : ""} onClick={() => setTierFilter("A")}>Tier A</button>
              <button className={tierFilter === "B" ? "on" : ""} onClick={() => setTierFilter("B")}>Tier B</button>
            </div>
            <div className="job-stack" aria-label="Google Sheets job list">{visibleJobs.map((item)=>{const index=jobs.findIndex(candidate=>candidate.key===item.key);return <button className={selected===index?"job selected":"job"} onClick={()=>setSelected(index)} key={item.key}><span className="ordinal">{String(index+1).padStart(2,"0")}</span><span className="job-copy"><strong>{item.title}</strong><small>{item.company}</small><span className={`status-pill tone-${statusTone(item.status)}`}>{statusLabel(item.status)}</span></span><span className="job-score"><b>{item.score ?? "—"}</b><small>{item.score === null ? "PENDING" : "FIT"}</small></span></button>})}</div>
          </section>

          <section className="paper evidence">
            <div className="section-head"><div><p>SELECTED ROLE</p><h2>{job.title}</h2><span>{job.company}</span></div><button className="mini-go" onClick={openModal}>Start package</button></div>
            <div className="evidence-summary"><div><span>WHY THIS ROLE</span><strong>{job.reason}</strong></div><div><span>APPLICATION STATE</span><strong>{job.status}</strong></div></div>
            <article><h3>Role brief</h3><p>{job.brief}</p></article>
            <div className="block-preview"><div><h3>Evidence from master resume</h3><span>2 MATCHED BLOCKS</span></div>{resumeBlocks.slice(0,2).map((text,index)=><div className="locked" key={text}><span>LOCKED</span><p>{text}</p><small>Verbatim master block {index+1} · not editable here</small></div>)}</div>
          </section>

          <aside className="side-stack">
            <section className="paper okrs"><div className="section-head"><div><p>THIS WEEK</p><h2>Week 1 targets</h2></div><span>DAY 0 / 7</span></div>{[["Coffee chats",0,5],["Applications",0,10],["LinkedIn posts",0,1],["Coding",0,3],["Deep work",0,2]].map(([label,value,target])=><div className="kr" key={String(label)}><div><span>{label}</span><b>{value} / {target}{label==="Coding"||label==="Deep work"?"h":""}</b></div><i><span/></i></div>)}<small>Resets Sunday · review at 16:00</small></section>
            <section className="paper agenda"><div className="section-head"><div><p>TODAY</p><h2>Prepare week 1</h2></div></div>{[["08:00","Portfolio project","3 hours"],["11:00","Weekly review","Source next week's chats"],["17:00","LinkedIn post","30 minutes"]].map(row=><div className="event" key={row[0]}><time>{row[0]}</time><p><b>{row[1]}</b><span>{row[2]}</span></p></div>)}</section>
            <section className="paper follow"><p>BEFORE MONDAY</p><h3>Source 5 coffee chats</h3><span>0 of 5 ready</span><button onClick={() => setActiveTab(3)}>Open networking</button></section>
          </aside>
        </div>
        </>}

        {activeTab === 1 ? (() => {
          const today = todayIso();
          const toApply = applications.filter((a) => isOpenApp(a.status));
          const toFollow = contacts.filter((c) => c.followUpDue && c.followUpDue <= today).sort(followUpSort);
          const todayEvents = events.filter((e) => e.date === today);
          const totalActions = toApply.length + toFollow.length + todayEvents.length;
          return (
            <section className="paper today-pane">
              <div className="section-head"><div><p>DAILY ACTIONS</p><h2>Today · {today}</h2></div><span>{totalActions} ACTIONS</span></div>
              <div className="today-group">
                <h3>Applications to send · {toApply.length}</h3>
                {toApply.length === 0 ? <p className="today-empty">No open applications on your plate.</p> : (
                  <div className="agenda">
                    {toApply.map((app, i) => (
                      <div className="event" key={`${app.key}-${i}`}>
                        <time>{statusLabel(app.status)}</time>
                        <p>
                          <b>{app.title}</b>
                          <span>{app.company}</span>
                          <span className={`status-pill tone-${statusTone(app.status)}`}>{statusLabel(app.status)}</span>
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="today-group">
                <h3>Networking follow-ups due · {toFollow.length}</h3>
                {toFollow.length === 0 ? <p className="today-empty">No follow-ups due today.</p> : (
                  <div className="agenda">
                    {toFollow.map((c) => (
                      <div className="event" key={c.key}>
                        <time>{c.followUpDue}</time>
                        <p><b>{c.name}</b><span>{c.company} · {c.role}</span></p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="today-group">
                <h3>OKR events today · {todayEvents.length}</h3>
                {todayEvents.length === 0 ? <p className="today-empty">Nothing logged for today yet.</p> : (
                  <div className="agenda">
                    {todayEvents.map((e) => (
                      <div className="event" key={e.key}>
                        <time>{e.kind || "Event"}</time>
                        <p><b>{e.job || e.contact || "Untitled"}</b><span>{e.notes}</span></p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>
          );
        })() : null}

        {activeTab === 2 ? (
          <section className="paper pipeline">
            <div className="section-head"><div><p>FUNNEL</p><h2>Application pipeline</h2></div><span>{applications.length} ROLES</span></div>
            <div className="pipeline-stages">
              {pipelineGroups(applications).map((group) => (
                <div className="pipeline-stage" key={group.label}>
                  <div className="section-head">
                    <div><span className={`status-pill tone-${group.tone}`}>{group.label}</span></div>
                    <span>{group.items.length}</span>
                  </div>
                  {group.items.length === 0 ? <p className="today-empty">No roles in this stage.</p> : (
                    <ul className="pipeline-list">
                      {group.items.map((app, i) => (
                        <li className="pipeline-item" key={`${app.key}-${i}`}>
                          <strong>{app.title}</strong>
                          <span>{app.company}</span>
                          <span className={`status-pill tone-${statusTone(app.status)}`}>{statusLabel(app.status)}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {activeTab === 3 ? (
          <section className="paper network">
            <div className="section-head"><div><p>NETWORK</p><h2>Contacts</h2></div><span>{contacts.length} CONTACTS</span></div>
            {contacts.length === 0 ? <p className="today-empty">No contacts loaded.</p> : (
              <div className="contact-list">
                {[...contacts].sort(followUpSort).map((c, i) => (
                  <div className="contact-row" key={`${c.key}-${i}`}>
                    <div className="contact-main">
                      <b>{c.name}</b>
                      <span>{c.role}{c.company ? ` · ${c.company}` : ""}</span>
                    </div>
                    <div className="contact-meta">
                      <span>Last contacted: {c.lastContacted || "—"}</span>
                      <span>Follow up: {c.followUpDue || "—"}</span>
                      <span className={`status-pill tone-${statusTone(c.status)}`}>{statusLabel(c.status)}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        ) : null}

        {activeTab === 4 ? (() => {
          const latest = latestWeeklyReview(reviews);
          const openGaps = gaps.filter((g) => gapOpen(g.resolved));
          const grouped = openGapsByPriority(openGaps);
          return (
            <div className="review-panes">
              <section className="paper">
                <div className="section-head"><div><p>WEEKLY REVIEW</p><h2>{latest ? `Week of ${latest.weekStart}` : "No weekly review loaded"}</h2></div><span>{latest ? "LATEST" : "0 REVIEWS"}</span></div>
                {latest ? (
                  <div className="evidence-summary review-grid">
                    <div><span>PIPELINE</span><strong>{latest.pipeline || "—"}</strong></div>
                    <div><span>FOLLOW UPS</span><strong>{latest.followUps || "—"}</strong></div>
                    <div><span>GAPS</span><strong>{latest.gaps || "—"}</strong></div>
                    <div><span>CHATS SOURCED</span><strong>{latest.chatsSourced || "—"}</strong></div>
                    <div><span>KR ACTUALS</span><strong>{latest.krActuals || "—"}</strong></div>
                    <div><span>DECISION</span><strong>{latest.decision || "—"}</strong></div>
                  </div>
                ) : <p className="today-empty">No weekly reviews available.</p>}
              </section>

              <section className="paper">
                <div className="section-head"><div><p>OPEN GAPS</p><h2>Learning gaps</h2></div><span>{openGaps.length} OPEN</span></div>
                {grouped.length === 0 ? <p className="today-empty">No open learning gaps.</p> : (
                  <div className="gap-groups">
                    {grouped.map(({ priority, items }) => (
                      <div className="gap-group" key={priority}>
                        <h3 className={`status-pill tone-${priority === "high" ? "red" : priority === "medium" ? "yellow" : "grey"}`}>{priority}</h3>
                        <div className="agenda">
                          {items.map((g) => (
                            <div className="event" key={g.key}>
                              <time>{g.found || "Gap"}</time>
                              <p><b>{g.gap}</b><span>{g.source}{g.reviewPlan ? ` · ${g.reviewPlan}` : ""}</span></p>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </div>
          );
        })() : null}
      </main>
      <nav className="bottom-nav">{["Apply","Today","Pipeline","Network","Review","Sheet"].map((item,index)=>{const enabled=index>=0&&index<=5;return <button className={activeTab===index?"active":""} disabled={!enabled} title={!enabled?"Coming soon":undefined} onClick={enabled?()=>setActiveTab(index):undefined} key={item}><span>{String(index+1).padStart(2,"0")}</span>{item}</button>})}</nav>
    </div>

    {modal && (
      <div className="scrim">
        <section className="package" role="dialog" aria-modal="true" aria-labelledby="package-title" ref={modalRef} tabIndex={-1}>
          <header>
            <div>
              <p>APPLICATION PACKAGE · STEP {modalStep} OF 4</p>
              <h2 id="package-title">{job.company} — {job.title}</h2>
            </div>
            <button onClick={closeModal}>Close</button>
          </header>
          <ol>
            <li className="done">1 Evidence</li>
            <li className={modalStep === 2 ? "current" : "done"}>2 Master blocks</li>
            <li className={modalStep === 3 ? "current" : ""}>3 Open &amp; submit</li>
            <li>4 Log result</li>
          </ol>
          <div className="package-body">
            {modalStep === 2 ? (
              <>
                <h3>Select immutable master-resume blocks</h3>
                <p>Content is locked and copied byte-for-byte. Edit the master resume at its source, never here.</p>
                {resumeBlocks.map((text, index) => (
                  <label className={blocks.includes(index) ? "resume-block checked" : "resume-block"} key={text}>
                    <input type="checkbox" checked={blocks.includes(index)} onChange={() => setBlocks((current) => (current.includes(index) ? current.filter((i) => i !== index) : [...current, index]))} />
                    <span><b>VERBATIM MASTER BLOCK {index + 1}</b><small>{text}</small></span>
                  </label>
                ))}
                <div className="manual-note"><b>Manual submission only</b><p>When the package is ready, you will open the employer form in a separate tab and submit it yourself.</p></div>
              </>
            ) : (
              <>
                <h3>Open the employer form</h3>
                <p>Click the button below to open the role posting in a new tab. Submit your application there.</p>
                <div className="manual-note"><b>{job.company} — {job.title}</b><p>{job.url || "No application URL is stored for this role yet."}</p></div>
              </>
            )}
          </div>
          <footer>
            <span>Review-first · you submit on the employer&apos;s own form.</span>
            <div>
              <button className="ghost-paper" onClick={closeModal}>Cancel</button>
              {modalStep === 2 ? (
                <button className="go" disabled={!blocks.length} ref={continueButtonRef} title={!blocks.length ? "Select at least one block to continue" : undefined} onClick={() => setModalStep(3)}>
                  Continue to review
                </button>
              ) : (
                <>
                  <button className="ghost-paper" onClick={() => setModalStep(2)}>Back</button>
                  <button className="go" disabled={!job.url} ref={continueButtonRef} onClick={() => job.url && window.open(job.url, "_blank", "noopener,noreferrer")}>
                    Open employer form ↗
                  </button>
                </>
              )}
            </div>
          </footer>
        </section>
      </div>
    )}
  </>;
}
