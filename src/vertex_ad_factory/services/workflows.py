from __future__ import annotations

import json
import secrets
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


Workflow = dict[str, dict[str, Any]]

EXPECTED_NODES = {
    "4": "CLIPTextEncode",
    "7": "EmptyLatentImage",
    "8": "KSampler",
    "10": "SaveImage",
    "11": "LoadImage",
}


@dataclass(frozen=True, slots=True)
class FirstFrameBindings:
    prompt: str
    reference_image: str = "A1_contradiction.png"
    output_prefix: str = "vertex_ad_factory/first_frame"
    width: int = 832
    height: int = 1216
    seed: int | None = None

    def resolved_seed(self) -> int:
        return self.seed if self.seed is not None else secrets.randbits(63)


def load_api_workflow(path: Path) -> Workflow:
    with path.open(encoding="utf-8") as file:
        workflow = json.load(file)
    if not isinstance(workflow, dict):
        raise ValueError("API workflow must be a JSON object")
    return workflow


def validate_first_frame_workflow(workflow: Workflow) -> None:
    errors: list[str] = []
    for node_id, expected_type in EXPECTED_NODES.items():
        node = workflow.get(node_id)
        if node is None:
            errors.append(f"missing node {node_id} ({expected_type})")
            continue
        actual_type = node.get("class_type")
        if actual_type != expected_type:
            errors.append(
                f"node {node_id}: expected {expected_type}, found {actual_type}"
            )
        if not isinstance(node.get("inputs"), dict):
            errors.append(f"node {node_id}: inputs must be an object")
    if errors:
        raise ValueError("Invalid first-frame workflow: " + "; ".join(errors))


def _validate_relative_path(value: str, field_name: str) -> str:
    normalized = value.strip().replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field_name} must be a safe relative path")
    return normalized


def bind_first_frame(
    base_workflow: Workflow,
    bindings: FirstFrameBindings,
) -> tuple[Workflow, int]:
    validate_first_frame_workflow(base_workflow)
    prompt = bindings.prompt.strip()
    if not prompt:
        raise ValueError("prompt cannot be empty")
    if bindings.width <= 0 or bindings.height <= 0:
        raise ValueError("width and height must be positive")
    if bindings.width % 16 or bindings.height % 16:
        raise ValueError("width and height must be divisible by 16")

    reference_image = _validate_relative_path(
        bindings.reference_image, "reference_image"
    )
    output_prefix = _validate_relative_path(bindings.output_prefix, "output_prefix")
    seed = bindings.resolved_seed()
    if not 0 <= seed < 2**64:
        raise ValueError("seed must be between 0 and 2^64-1")

    workflow = deepcopy(base_workflow)
    workflow["4"]["inputs"]["text"] = prompt
    workflow["7"]["inputs"]["width"] = bindings.width
    workflow["7"]["inputs"]["height"] = bindings.height
    workflow["8"]["inputs"]["seed"] = seed
    workflow["10"]["inputs"]["filename_prefix"] = output_prefix
    workflow["11"]["inputs"]["image"] = reference_image
    return workflow, seed


def save_api_workflow(workflow: Workflow, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(workflow, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

