from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class Settings:
    project_root: Path = PROJECT_ROOT
    comfy_url: str = os.getenv("COMFY_URL", "http://127.0.0.1:18188")
    database_path: Path = Path(
        os.getenv("AD_FACTORY_DB", str(PROJECT_ROOT / "data" / "ad_factory.sqlite3"))
    )
    workflows_dir: Path = PROJECT_ROOT / "workflows"
    runs_dir: Path = PROJECT_ROOT / "runs"
    runtime_config_path: Path = PROJECT_ROOT / "data" / "runtime_config.json"

    def ensure_directories(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.workflows_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
