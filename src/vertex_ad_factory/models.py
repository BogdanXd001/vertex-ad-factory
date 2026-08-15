from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class JobStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    PLANNED = "planned"
    VOICE_READY = "voice_ready"
    FRAMES_READY = "frames_ready"
    VIDEOS_READY = "videos_ready"
    LIPSYNC_READY = "lipsync_ready"
    ASSEMBLED = "assembled"
    COMPLETED = "completed"
    WAITING_INPUT = "waiting_input"
    FAILED = "failed"


class SceneKind(StrEnum):
    A_ROLL = "a_roll"
    B_ROLL = "b_roll"


class VisualMode(StrEnum):
    EXPERT_PODCAST = "expert_podcast"
    EDUCATIONAL_ANIMATION = "educational_animation"
    APPLICATION_DEMO = "application_demo"
    PRODUCT_COMPOSITE = "product_composite"
    END_CARD = "end_card"


class AudioMode(StrEnum):
    ON_CAMERA = "on_camera"
    VOICEOVER = "voiceover"
    SILENT = "silent"


class SceneStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Stage(StrEnum):
    PLANNING = "planning"
    VOICEOVER = "voiceover"
    FIRST_FRAMES = "first_frames"
    IMAGE_TO_VIDEO = "image_to_video"
    LIPSYNC = "lipsync"
    ASSEMBLY = "assembly"


@dataclass(slots=True)
class AdJob:
    product_name: str
    angle: str
    language: str = "ro"
    target_duration_seconds: int = 30
    job_id: str = field(default_factory=lambda: uuid4().hex)
    status: JobStatus = JobStatus.CREATED
    current_stage: str = "created"
    error: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def validate(self) -> None:
        if not self.product_name.strip():
            raise ValueError("product_name cannot be empty")
        if not self.angle.strip():
            raise ValueError("angle cannot be empty")
        if self.target_duration_seconds <= 0:
            raise ValueError("target_duration_seconds must be positive")


@dataclass(slots=True)
class Scene:
    job_id: str
    position: int
    kind: SceneKind
    duration_seconds: int
    narration: str
    visual_prompt: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    scene_id: str = field(default_factory=lambda: uuid4().hex)
    status: SceneStatus = SceneStatus.PENDING
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def validate(self) -> None:
        if self.position < 1:
            raise ValueError("scene position must start at 1")
        if self.duration_seconds not in {4, 6, 8}:
            raise ValueError("scene duration must be one of: 4, 6, 8")
        if not self.narration.strip():
            raise ValueError("scene narration cannot be empty")
        if not isinstance(self.metadata, dict):
            raise ValueError("scene metadata must be an object")
