from __future__ import annotations

from datetime import datetime

from models import Job


def top_jobs(jobs: list[Job], n: int = 10) -> list[Job]:
    scored = [j for j in jobs if j.score is not None]
    return sorted(scored, key=lambda j: j.score or 0, reverse=True)[:n]


def build_report(counts: dict, jobs: list[Job], n: int = 10) -> str:
    """A plain-text daily digest: header, the pipeline counts, then the top matches."""
    lines = [f"Job Search Action Center — {datetime.now().date().isoformat()}", ""]
    lines.append("Pipeline: " + " ".join(f"{k}={v}" for k, v in counts.items()))
    lines.append("")
    lines.append("Top matches:")
    tops = top_jobs(jobs, n)
    if not tops:
        lines.append("  (none scored yet)")
    else:
        for j in tops:
            lines.append(
                f"  {j.score:>5.1f}  {j.title} @ {j.company_canonical} [{j.tier or '-'}]"
            )
    return "\n".join(lines)
