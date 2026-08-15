from __future__ import annotations

from .config import Settings, settings
from .database import Database
from .models import AdJob


class Orchestrator:
    def __init__(self, app_settings: Settings = settings) -> None:
        self.settings = app_settings
        self.settings.ensure_directories()
        self.database = Database(self.settings.database_path)
        self.database.initialize()

    def create_job(
        self,
        product_name: str,
        angle: str,
        language: str = "ro",
        target_duration_seconds: int = 30,
    ) -> AdJob:
        job = AdJob(
            product_name=product_name,
            angle=angle,
            language=language,
            target_duration_seconds=target_duration_seconds,
        )
        self.database.create_job(job)
        (self.settings.runs_dir / job.job_id).mkdir(parents=True, exist_ok=False)
        return job

