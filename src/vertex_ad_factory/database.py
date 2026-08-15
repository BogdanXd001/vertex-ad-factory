from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from .models import AdJob, JobStatus, Scene, SceneStatus, Stage, utc_now


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

    def get_scene_by_position(self, job_id: str, position: int) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM scenes WHERE job_id = ? AND position = ?",
                (job_id, position),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["output"] = json.loads(result.pop("output_json"))
        return result

    def list_scenes(self, job_id: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM scenes WHERE job_id = ? ORDER BY position",
                (job_id,),
            ).fetchall()
        results: list[dict] = []
        for row in rows:
            result = dict(row)
            result["output"] = json.loads(result.pop("output_json"))
            results.append(result)
        return results

    def record_scene_output(
        self,
        scene_id: str,
        output_name: str,
        output: dict,
        status: SceneStatus = SceneStatus.PENDING,
        error: str | None = None,
    ) -> None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT output_json FROM scenes WHERE scene_id = ?", (scene_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown scene: {scene_id}")
            outputs = json.loads(row["output_json"])
            outputs[output_name] = output
            connection.execute(
                """
                UPDATE scenes
                SET output_json = ?, status = ?, error = ?, updated_at = ?
                WHERE scene_id = ?
                """,
                (
                    json.dumps(outputs, ensure_ascii=False),
                    status.value,
                    error,
                    utc_now(),
                    scene_id,
                ),
            )

    def start_stage_run(self, job_id: str, stage: Stage) -> int:
        if self.get_job(job_id) is None:
            raise KeyError(f"Unknown job: {job_id}")
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO stage_runs (job_id, stage, status, started_at)
                VALUES (?, ?, 'running', ?)
                """,
                (job_id, stage.value, utc_now()),
            )
        return int(cursor.lastrowid)

    def finish_stage_run(self, stage_run_id: int, metrics: dict) -> None:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE stage_runs
                SET status = 'completed', finished_at = ?, metrics_json = ?
                WHERE stage_run_id = ?
                """,
                (
                    utc_now(),
                    json.dumps(metrics, ensure_ascii=False),
                    stage_run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown stage run: {stage_run_id}")

    def fail_stage_run(self, stage_run_id: int, error: str) -> None:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE stage_runs
                SET status = 'failed', finished_at = ?, error = ?
                WHERE stage_run_id = ?
                """,
                (utc_now(), error, stage_run_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown stage run: {stage_run_id}")

    def all_scenes_have_output(self, job_id: str, output_name: str) -> bool:
        scenes = self.list_scenes(job_id)
        return bool(scenes) and all(output_name in scene["output"] for scene in scenes)
