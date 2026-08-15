from __future__ import annotations

import subprocess
from pathlib import Path

from ..config import Settings


def install_comfyui_dashboard(
    settings: Settings,
    comfy_root: Path,
    restart: bool = False,
) -> dict:
    comfy_root = Path(comfy_root).resolve()
    custom_nodes = comfy_root / "custom_nodes"
    if not (comfy_root / "main.py").is_file() or not custom_nodes.is_dir():
        raise ValueError(f"Not a ComfyUI installation: {comfy_root}")

    source = (
        settings.project_root / "comfyui_extension" / "vertex_ad_factory_ui"
    ).resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"Dashboard extension is missing: {source}")
    destination = custom_nodes / "vertex_ad_factory_ui"
    changed = False
    if destination.is_symlink():
        if destination.resolve() != source:
            destination.unlink()
            destination.symlink_to(source, target_is_directory=True)
            changed = True
    elif destination.exists():
        raise FileExistsError(
            f"Refusing to replace existing non-symlink path: {destination}"
        )
    else:
        destination.symlink_to(source, target_is_directory=True)
        changed = True

    restarted = False
    if restart:
        subprocess.run(
            ["supervisorctl", "restart", "comfyui"],
            check=True,
            text=True,
        )
        restarted = True
    return {
        "source": str(source),
        "destination": str(destination),
        "installed": True,
        "changed": changed,
        "restarted": restarted,
        "dashboard_path": "/vertex-ad-factory/",
    }
