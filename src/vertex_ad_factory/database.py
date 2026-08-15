from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from .models import AdJob, JobStatus, Scene, utc_now


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    angle TEXT NOT NULL,
    language TEXT NOT NULL,
    target_duration_seconds INTEGER NOT NULL CHECK (target_duration_seconds > 0),
    status TEXT NOT NULL,
    current_stage TEXT NOT NULL,
    error TEXT,
    config_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scenes (
    scene_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('a_roll', 'b_roll')),
    duration_seconds INTEGER NOT NULL CHECK (duration_seconds IN (4, 6, 8)),
    narration TEXT NOT NULL,
    visual_prompt TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    output_json TEXT NOT NULL DEFAULT '{}',
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(job_id, position)
);

CREATE TABLE IF NOT EXISTS stage_runs (
    stage_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error TEXT,
    metrics_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_scenes_job_position ON scenes(job_id, position);
CREATE INDEX IF NOT EXISTS idx_stage_runs_job ON stage_runs(job_id, stage);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def create_job(self, job: AdJob, config: dict | None = None) -> AdJob:
        job.validate()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    job_id, product_name, angle, language,
                    target_duration_seconds, status, current_stage,
                    error, config_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.job_id,
                    job.product_name.strip(),
                    job.angle.strip(),
                    job.language,
                    job.target_duration_seconds,
                    job.status.value,
                    job.current_stage,
                    job.error,
                    json.dumps(config or {}, ensure_ascii=False),
                    job.created_at,
                    job.updated_at,
                ),
            )
        return job

    def get_job(self, job_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_jobs(self, limit: int = 20) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        current_stage: str,
        error: str | None = None,
    ) -> None:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = ?, current_stage = ?, error = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (status.value, current_stage, error, utc_now(), job_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown job: {job_id}")

    def add_scene(self, scene: Scene) -> Scene:
        scene.validate()
        payload = asdict(scene)
        payload["kind"] = scene.kind.value
        payload["status"] = scene.status.value
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO scenes (
                    scene_id, job_id, position, kind, duration_seconds,
                    narration, visual_prompt, status, created_at, updated_at
                ) VALUES (
                    :scene_id, :job_id, :position, :kind, :duration_seconds,
                    :narration, :visual_prompt, :status, :created_at, :updated_at
                )
                """,
                payload,
            )
        return scene

