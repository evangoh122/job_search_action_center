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

function fromSheet(row: SheetJob): Job | null {
  const company = row.Company?.trim();
  const title = row.Title?.trim();
  if (!company || !title) return null;
  const rawScore = row.Score?.trim() || "";
  const hasNumericScore = /^\d+(?:\.\d+)?$/.test(rawScore);
  const boundedScore = hasNumericScore ? Math.max(0, Math.min(100, Math.round(Number(rawScore)))) : null;
  const rawAppLink = (row.ApplicationLink ?? "").trim();
  const legacyShifted = rawAppLink !== "" && /^\d+(\.\d+)?$/.test(rawAppLink);
  const score = legacyShifted ? Math.max(0, Math.min(100, Math.round(Number(rawAppLink)))) : boundedScore;
  const tier = (legacyShifted ? rawScore : row.Tier)?.trim() || (score === null ? "Pending" : score >= 90 ? "A" : score >= 75 ? "B" : "C");
  const status = (legacyShifted ? row.Tier : row.Status)?.trim() || "New";
  const source = (legacyShifted ? row.Status : row.Source)?.trim() || "Google Sheets";
  return {
    key: row.DedupeKey?.trim() || `${company}:${title}`,
    company,
    title,
    score,
    tier,
    status,
    reason: `${score === null ? "Fit score pending" : `${score}% backend fit`} · Tier ${tier} · ${source}`,
    brief: (legacyShifted ? row.Posted : row.Description)?.trim() || "No role description has been stored in the Jobs sheet yet.",
    url: legacyShifted ? (row.URL?.trim() || "") : (row.ApplicationLink?.trim() || row.URL?.trim() || ""),
  };
}
const resumeBlocks = [
  "Led regional analytics strategy across business and technology teams, translating complex data into executive decisions and measurable delivery outcomes.",
  "Built and evaluated machine-learning solutions using Python, SQL and large-scale customer datasets, partnering with risk and product stakeholders.",
  "Drove adoption of responsible generative-AI workflows through structured enablement, governance and cross-regional stakeholder engagement.",
];

export default function Home() {
  const [selected, setSelected] = useState(0);
  const [modal, setModal] = useState(false);
  const [blocks, setBlocks] = useState([0, 1]);
  const [jobs, setJobs] = useState<Job[]>(previewJobs);
  const [sheetState, setSheetState] = useState<"loading" | "live" | "preview">("loading");
  const [query, setQuery] = useState("");
  const job = jobs[selected];
  const normalizedQuery = query.trim().toLowerCase();
  const visibleJobs = normalizedQuery ? jobs.filter((item) => `${item.company} ${item.title} ${item.status} ${item.tier}`.toLowerCase().includes(normalizedQuery)) : jobs;
  const modalRef = useRef<HTMLElement>(null);
  const continueButtonRef = useRef<HTMLButtonElement>(null);
  const modalTriggerRef = useRef<HTMLElement>(null);

  function openModal(event: React.MouseEvent<HTMLButtonElement>) {
    modalTriggerRef.current = event.currentTarget;
    setModal(true);
  }

  function closeModal() {
    setModal(false);
    modalTriggerRef.current?.focus();
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
  }, [modal]);

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
          return response.json() as Promise<{ Jobs?: SheetJob[] }>;
        })
        .then((payload) => {
          const liveJobs = (payload.Jobs || []).map(fromSheet).filter((item): item is Job => Boolean(item)).sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
          if (!liveJobs.length) throw new Error("No jobs in Sheets");
          setJobs(liveJobs);
          setSelected(0);
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

  const sheetLabel = sheetState === "live" ? "Sheets live · backend fit" : sheetState === "loading" ? "Connecting to Sheets…" : "Sheets preview · sample fit";
  return <>
    <style>{commandDeckCss}</style>
    <a className="skip" href="#next-action">Skip to next action</a>
    <div className="deck">
      <aside className="rail">
        <div className="wordmark"><span>J</span><div><b>Job Action Center</b><small>PRIVATE · SHEETS-BACKED</small></div></div>
        <p className="rail-label">CAMPAIGN</p>
        <nav>{["Apply","Today","Pipeline","Network","Review"].map((item,index)=><button className={index===0?"active":""} key={item}><i>{String(index+1).padStart(2,"0")}</i>{item}</button>)}</nav>
        <div className="week-card"><div><span>Week 1 of 15</span><b>Offer by Nov 1</b></div><div className="segments" aria-label="Week 1 of 15">{Array.from({length:15},(_,i)=><i className={i===0?"filled":""} key={i}/>)}</div><small>Singapore · 15-week campaign</small><p><i/> {sheetLabel}</p></div>
      </aside>

      <main className="canvas">
        <header className="top"><div><p>APPLY</p><h2>Week 1 · Build momentum deliberately</h2></div><div className="top-actions"><button className="quiet" disabled title="Coming soon">Log learning gap</button><span className="sync"><i/> {sheetLabel}</span></div></header>

        <section className="briefing" id="next-action">
          <div className="brief-main"><p className="gold-label">YOUR #1 NEXT ACTION — RANKED BY FIT</p><div className="company"><span>{job.company.slice(0,1).toUpperCase()}</span>{job.company}</div><h1>{job.title}</h1><div className="meta"><span>Singapore</span><span>Hybrid</span><span>Backend ranked</span><span>{sheetState === "live" ? "Live sheet record" : "Preview record"}</span></div><div className="why">{job.reason.split(" · ").map(reason=><span key={reason}>{reason}</span>)}</div></div>
          <div className="dial-area"><div className="dial" style={{background:`conic-gradient(var(--brass) 0 ${job.score ?? 0}%, #4a4438 ${job.score ?? 0}%)`}}><div><strong>{job.score ?? "—"}</strong><small>{job.score === null ? "PENDING" : "FIT"}</small></div></div><div className="badges"><span>Tier {job.tier}</span><span>{job.status}</span></div></div>
          <div className="brief-actions"><button className="go" onClick={openModal}>Start application package</button><button className="ghost" disabled={!job.url} onClick={()=>job.url&&window.open(job.url,"_blank","noopener,noreferrer")}>Open role posting ↗</button><button className="text-action" disabled title="Coming soon">Skip for today</button><p>You always submit on the employer&apos;s own form. Nothing here auto-submits.</p></div>
          <blockquote>One strong application beats ten rushed ones.</blockquote>
        </section>

        <div className="workspace">
          <section className="paper queue">
            <div className="section-head"><div><p>RANKED BY BACKEND FIT</p><h2>Application queue</h2></div><span>{visibleJobs.length}{normalizedQuery ? ` / ${jobs.length}` : ""} ROLES</span></div>
            <label className="search"><span>Search roles</span><input placeholder="Company or title" value={query} onChange={(event)=>setQuery(event.target.value)} /></label>
            <div className="filters"><button className="on">All</button><button>Tier A</button><button>Tier B</button></div>
            <div className="job-stack" aria-label="Google Sheets job list">{visibleJobs.map((item)=>{const index=jobs.findIndex(candidate=>candidate.key===item.key);return <button className={selected===index?"job selected":"job"} onClick={()=>setSelected(index)} key={item.key}><span className="ordinal">{String(index+1).padStart(2,"0")}</span><span className="job-copy"><strong>{item.title}</strong><small>{item.company}</small><em>{item.status}</em></span><span className="job-score"><b>{item.score ?? "—"}</b><small>{item.score === null ? "PENDING" : "FIT"}</small></span></button>})}</div>
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
            <section className="paper follow"><p>BEFORE MONDAY</p><h3>Source 5 coffee chats</h3><span>0 of 5 ready</span><button disabled title="Coming soon">Open networking</button></section>
          </aside>
        </div>
      </main>
      <nav className="bottom-nav">{["Apply","Today","Pipeline","Network","Review"].map((item,index)=><button className={index===0?"active":""} disabled={index>0} title={index>0?"Coming soon":undefined} key={item}><span>{String(index+1).padStart(2,"0")}</span>{item}</button>)}</nav>
    </div>

    {modal&&<div className="scrim"><section className="package" role="dialog" aria-modal="true" aria-labelledby="package-title" ref={modalRef} tabIndex={-1}><header><div><p>APPLICATION PACKAGE · STEP 2 OF 4</p><h2 id="package-title">{job.company} — {job.title}</h2></div><button onClick={closeModal}>Close</button></header><ol><li className="done">1 Evidence</li><li className="current">2 Master blocks</li><li>3 Open & submit</li><li>4 Log result</li></ol><div className="package-body"><h3>Select immutable master-resume blocks</h3><p>Content is locked and copied byte-for-byte. Edit the master resume at its source, never here.</p>{resumeBlocks.map((text,index)=><label className={blocks.includes(index)?"resume-block checked":"resume-block"} key={text}><input type="checkbox" checked={blocks.includes(index)} onChange={()=>setBlocks(current=>current.includes(index)?current.filter(i=>i!==index):[...current,index])}/><span><b>VERBATIM MASTER BLOCK {index+1}</b><small>{text}</small></span></label>)}<div className="manual-note"><b>Manual submission only</b><p>When the package is ready, you will open the employer form in a separate tab and submit it yourself.</p></div></div><footer><span>Local preview draft · Sheets writes disabled</span><div><button className="ghost-paper" onClick={closeModal}>Cancel</button><button className="go" disabled={!blocks.length} ref={continueButtonRef} title={!blocks.length?"Select at least one block to continue":undefined}>Continue to review</button></div></footer></section></div>}
  </>;
}
