from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod

from models import Contact, Job


class Repository(ABC):
    @abstractmethod
    def upsert_job(self, job: Job) -> None: ...

    @abstractmethod
    def get_job(self, job_id: str) -> Job | None: ...

    @abstractmethod
    def list_jobs(self) -> list[Job]: ...

    @abstractmethod
    def upsert_contact(self, c: Contact) -> None: ...

    @abstractmethod
    def incr_action(self, kind: str, day: str) -> int: ...

    @abstractmethod
    def count_actions(self, kind: str, day: str) -> int: ...


class SqliteRepository(Repository):
    def __init__(self, db_path: str = ":memory:"):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                dedupe_key TEXT UNIQUE NOT NULL,
                data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS contacts (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS action_counts (
                kind TEXT NOT NULL,
                day TEXT NOT NULL,
                n INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (kind, day)
            );
            """
        )
        self.conn.commit()

    def upsert_job(self, job: Job) -> None:
        self.conn.execute(
            """
            INSERT INTO jobs (id, dedupe_key, data)
            VALUES (?, ?, ?)
            ON CONFLICT(dedupe_key) DO UPDATE SET
                id = excluded.id,
                data = excluded.data
            """,
            (job.id, job.dedupe_key, json.dumps(job.model_dump(mode="json"))),
        )
        self.conn.commit()

    def get_job(self, job_id: str) -> Job | None:
        row = self.conn.execute(
            "SELECT data FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return Job.model_validate(json.loads(row["data"])) if row else None

    def list_jobs(self) -> list[Job]:
        rows = self.conn.execute("SELECT data FROM jobs").fetchall()
        return [Job.model_validate(json.loads(r["data"])) for r in rows]

    def upsert_contact(self, c: Contact) -> None:
        self.conn.execute(
            """
            INSERT INTO contacts (id, data)
            VALUES (?, ?)
            ON CONFLICT(id) DO UPDATE SET data = excluded.data
            """,
            (c.id, json.dumps(c.model_dump(mode="json"))),
        )
        self.conn.commit()

    def incr_action(self, kind: str, day: str) -> int:
        self.conn.execute(
            """
            INSERT INTO action_counts (kind, day, n)
            VALUES (?, ?, 1)
            ON CONFLICT(kind, day) DO UPDATE SET n = n + 1
            """,
            (kind, day),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT n FROM action_counts WHERE kind = ? AND day = ?", (kind, day)
        ).fetchone()
        return int(row["n"])

    def count_actions(self, kind: str, day: str) -> int:
        row = self.conn.execute(
            "SELECT n FROM action_counts WHERE kind = ? AND day = ?", (kind, day)
        ).fetchone()
        return int(row["n"]) if row else 0
