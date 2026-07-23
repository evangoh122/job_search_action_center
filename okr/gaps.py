"""Local-first learning-gap logging with a Drive-synced Markdown sink."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .store import GapRecord, OkrStore, SINGAPORE


class DriveMarkdownGapSink:
    """Append gaps to a Markdown file located in a Drive-synced directory."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, gap: GapRecord) -> None:
        marker = f"<!-- job-search-gap:{gap.id} -->"
        existing = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
        if marker in existing:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        local_time = gap.occurred_at.astimezone(SINGAPORE)
        context = ""
        if gap.context:
            details = "; ".join(f"{key}={value}" for key, value in sorted(gap.context.items()))
            context = f"\n  - Context: {details}"
        entry = (
            f"{marker}\n"
            f"- [{local_time:%Y-%m-%d %H:%M SGT}] **{gap.source}** "
            f"({gap.priority}): {gap.description}{context}\n"
        )
        prefix = "" if not existing or existing.endswith("\n") else "\n"
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(prefix + entry)


class GapService:
    """Persist each gap before attempting its immediate external sync."""

    def __init__(
        self,
        store: OkrStore,
        sink: DriveMarkdownGapSink | None,
        *,
        now: Callable[[], datetime],
    ) -> None:
        self.store = store
        self.sink = sink
        self.now = now

    def log(
        self,
        source: str,
        description: str,
        *,
        occurred_at: datetime | None = None,
        priority: str = "normal",
        context: dict[str, Any] | None = None,
        gap_id: str | None = None,
    ) -> GapRecord:
        gap = self.store.create_gap(
            source, description, occurred_at or self.now(), priority=priority,
            context=context, gap_id=gap_id,
        )
        self._sync(gap)
        return self.store.get_gap(gap.id)

    def retry_pending(self) -> list[GapRecord]:
        for gap in self.store.pending_gaps():
            self._sync(gap)
        return self.store.pending_gaps()

    def overdue(self, as_of: datetime | None = None) -> list[GapRecord]:
        current = as_of or self.now()
        return [gap for gap in self.store.pending_gaps() if gap.is_overdue(current)]

    def _sync(self, gap: GapRecord) -> None:
        if self.sink is None:
            return
        try:
            self.sink.append(gap)
        # The local record is already committed. A connector or filesystem
        # failure must therefore become retryable state, not undo gap capture.
        except Exception as exc:
            self.store.mark_gap_sync_failed(gap.id, f"{type(exc).__name__}: {exc}")
            return
        self.store.mark_gap_synced(gap.id, self.now())
