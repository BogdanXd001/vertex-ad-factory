from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..models import AudioMode, Scene, SceneKind, VisualMode


@dataclass(frozen=True, slots=True)
class BlueprintScene:
    position: int
    role: str
    kind: SceneKind
    visual_mode: VisualMode
    audio_mode: AudioMode
    duration_seconds: int
    narration: str
    visual_prompt: str
    motion_prompt: str
    reference_assets: tuple[str, ...]
    post_production: str
    requires_lipsync: bool

    def to_scene(self, job_id: str) -> Scene:
        return Scene(
            job_id=job_id,
            position=self.position,
            kind=self.kind,
            duration_seconds=self.duration_seconds,
            narration=self.narration,
            visual_prompt=self.visual_prompt,
            metadata={
                "role": self.role,
                "visual_mode": self.visual_mode.value,
                "audio_mode": self.audio_mode.value,
                "motion_prompt": self.motion_prompt,
                "reference_assets": list(self.reference_assets),
                "post_production": self.post_production,
                "requires_lipsync": self.requires_lipsync,
            },
        )


@dataclass(frozen=True, slots=True)
class HybridBlueprint:
    version: int
    name: str
    product_name: str
    angle: str
    language: str
    target_duration_seconds: int
    creative: dict[str, Any]
    scenes: tuple[BlueprintScene, ...]

    @property
    def a_roll_seconds(self) -> int:
        return sum(
            scene.duration_seconds
            for scene in self.scenes
            if scene.kind is SceneKind.A_ROLL
        )

    @property
    def b_roll_seconds(self) -> int:
        return self.target_duration_seconds - self.a_roll_seconds

    @property
    def a_roll_ratio(self) -> float:
        return self.a_roll_seconds / self.target_duration_seconds

    def validate(self) -> None:
        if self.version != 1:
            raise ValueError("blueprint version must be 1")
        if not self.name.strip():
            raise ValueError("blueprint name cannot be empty")
        if not self.product_name.strip() or not self.angle.strip():
            raise ValueError("product_name and angle cannot be empty")
        if self.target_duration_seconds <= 0:
            raise ValueError("target_duration_seconds must be positive")
        if not self.scenes:
            raise ValueError("blueprint must contain at least one scene")

        positions = [scene.position for scene in self.scenes]
        expected = list(range(1, len(self.scenes) + 1))
        if positions != expected:
            raise ValueError("scene positions must be contiguous and start at 1")

        total = sum(scene.duration_seconds for scene in self.scenes)
        if total != self.target_duration_seconds:
            raise ValueError(
                f"scene duration total is {total}, expected {self.target_duration_seconds}"
            )

        target_ratio = float(self.creative.get("aroll_target_ratio", 0.30))
        tolerance = float(self.creative.get("aroll_ratio_tolerance", 0.05))
        if not 0 < target_ratio < 1 or not 0 <= tolerance < 1:
            raise ValueError("A-roll ratio and tolerance must be between 0 and 1")
        if abs(self.a_roll_ratio - target_ratio) > tolerance:
            raise ValueError(
                f"A-roll ratio is {self.a_roll_ratio:.3f}; target is "
                f"{target_ratio:.3f} ± {tolerance:.3f}"
            )

        for scene in self.scenes:
            if scene.duration_seconds not in {4, 6, 8}:
                raise ValueError(
                    f"scene {scene.position} duration must be one of: 4, 6, 8"
                )
            if not scene.role.strip() or not scene.narration.strip():
                raise ValueError(f"scene {scene.position} role and narration are required")
            if not scene.visual_prompt.strip() or not scene.motion_prompt.strip():
                raise ValueError(
                    f"scene {scene.position} visual and motion prompts are required"
                )
            if scene.audio_mode is AudioMode.ON_CAMERA and not scene.requires_lipsync:
                raise ValueError(
                    f"scene {scene.position} is on-camera and must require lip-sync"
                )
            if scene.requires_lipsync and scene.kind is not SceneKind.A_ROLL:
                raise ValueError(
                    f"scene {scene.position} lip-sync is allowed only for A-roll"
                )

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "product_name": self.product_name,
            "target_duration_seconds": self.target_duration_seconds,
            "scene_count": len(self.scenes),
            "a_roll_seconds": self.a_roll_seconds,
            "b_roll_seconds": self.b_roll_seconds,
            "a_roll_ratio": round(self.a_roll_ratio, 3),
            "b_roll_ratio": round(1 - self.a_roll_ratio, 3),
        }

    def job_config(self) -> dict[str, Any]:
        return {
            "blueprint_version": self.version,
            "blueprint_name": self.name,
            "creative": self.creative,
        }


def _required_str(payload: dict[str, Any], key: str, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value.strip()


def parse_blueprint(payload: dict[str, Any]) -> HybridBlueprint:
    if not isinstance(payload, dict):
        raise ValueError("blueprint must be a JSON object")
    raw_scenes = payload.get("scenes")
    if not isinstance(raw_scenes, list):
        raise ValueError("blueprint.scenes must be an array")

    scenes: list[BlueprintScene] = []
    for index, raw in enumerate(raw_scenes, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"scene {index} must be an object")
        references = raw.get("reference_assets", [])
        if not isinstance(references, list) or not all(
            isinstance(item, str) and item.strip() for item in references
        ):
            raise ValueError(f"scene {index}.reference_assets must contain strings")
        requires_lipsync = raw.get("requires_lipsync", False)
        if not isinstance(requires_lipsync, bool):
            raise ValueError(f"scene {index}.requires_lipsync must be boolean")
        scenes.append(
            BlueprintScene(
                position=int(raw.get("position", 0)),
                role=_required_str(raw, "role", f"scene {index}"),
                kind=SceneKind(_required_str(raw, "kind", f"scene {index}")),
                visual_mode=VisualMode(
                    _required_str(raw, "visual_mode", f"scene {index}")
                ),
                audio_mode=AudioMode(
                    _required_str(raw, "audio_mode", f"scene {index}")
                ),
                duration_seconds=int(raw.get("duration_seconds", 0)),
                narration=_required_str(raw, "narration", f"scene {index}"),
                visual_prompt=_required_str(
                    raw, "visual_prompt", f"scene {index}"
                ),
                motion_prompt=_required_str(
                    raw, "motion_prompt", f"scene {index}"
                ),
                reference_assets=tuple(item.strip() for item in references),
                post_production=_required_str(
                    raw, "post_production", f"scene {index}"
                ),
                requires_lipsync=requires_lipsync,
            )
        )

    creative = payload.get("creative", {})
    if not isinstance(creative, dict):
        raise ValueError("blueprint.creative must be an object")
    blueprint = HybridBlueprint(
        version=int(payload.get("version", 0)),
        name=_required_str(payload, "name", "blueprint"),
        product_name=_required_str(payload, "product_name", "blueprint"),
        angle=_required_str(payload, "angle", "blueprint"),
        language=_required_str(payload, "language", "blueprint"),
        target_duration_seconds=int(payload.get("target_duration_seconds", 0)),
        creative=creative,
        scenes=tuple(scenes),
    )
    blueprint.validate()
    return blueprint


def load_blueprint(path: Path) -> HybridBlueprint:
    with Path(path).open(encoding="utf-8") as file:
        payload = json.load(file)
    return parse_blueprint(payload)

