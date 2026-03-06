from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Storage:
    def __init__(self, database_url: str):
        # Supports sqlite:///./data/agent.db style URL.
        if not database_url.startswith("sqlite:///"):
            raise ValueError("Only sqlite:/// URLs are supported in v1")
        self.db_path = Path(database_url.replace("sqlite:///", ""))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def conn(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init_db(self) -> None:
        with self.conn() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_jobs (
                    job_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT
                )
                """
            )
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_reports (
                    job_id TEXT PRIMARY KEY,
                    report_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def create_job(self, symbol: str, request_payload: dict[str, Any]) -> str:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        with self.conn() as c:
            c.execute(
                """
                INSERT INTO analysis_jobs(job_id, symbol, request_json, status, progress, started_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, symbol.upper(), json.dumps(request_payload), "queued", 0, now),
            )
        return job_id

    def update_job(self, job_id: str, status: str, progress: int, error: str | None = None) -> None:
        finish = datetime.now(timezone.utc).isoformat() if status in {"done", "failed"} else None
        with self.conn() as c:
            c.execute(
                """
                UPDATE analysis_jobs
                SET status = ?, progress = ?, error = ?, finished_at = COALESCE(?, finished_at)
                WHERE job_id = ?
                """,
                (status, progress, error, finish, job_id),
            )

    def save_report(self, job_id: str, report_payload: dict[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.conn() as c:
            c.execute(
                """
                INSERT OR REPLACE INTO analysis_reports(job_id, report_json, created_at)
                VALUES (?, ?, ?)
                """,
                (job_id, json.dumps(report_payload), now),
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.conn() as c:
            row = c.execute(
                "SELECT job_id, status, progress, error, COALESCE(finished_at, started_at) AS updated_at FROM analysis_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if not row:
            return None
        return dict(row)

    def get_report(self, job_id: str) -> dict[str, Any] | None:
        with self.conn() as c:
            row = c.execute("SELECT report_json FROM analysis_reports WHERE job_id = ?", (job_id,)).fetchone()
        if not row:
            return None
        return json.loads(row["report_json"])
