from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from .clients.comfy import ComfyClient
from .config import settings
from .database import Database
from .models import JobStatus, Scene, SceneKind
from .orchestrator import Orchestrator
from .services.blueprints import load_blueprint
from .services.workflows import (
    FirstFrameBindings,
    bind_first_frame,
    load_api_workflow,
    save_api_workflow,
)
from .stages.first_frames import FirstFrameStage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ad-factory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create or upgrade the SQLite database")

    validate_blueprint = subparsers.add_parser(
        "validate-blueprint",
        help="Validate timing, A-roll ratio and scene routing in a JSON blueprint",
    )
    validate_blueprint.add_argument("blueprint", type=Path)

    create_from_blueprint = subparsers.add_parser(
        "create-from-blueprint",
        help="Create a planned job and all scenes from a validated blueprint",
    )
    create_from_blueprint.add_argument("blueprint", type=Path)

    create = subparsers.add_parser("create-job", help="Create a new ad job")
    create.add_argument("--product", required=True)
    create.add_argument("--angle", required=True)
    create.add_argument("--language", default="ro")
    create.add_argument("--duration", type=int, default=30)

    show = subparsers.add_parser("show-job", help="Show one job")
    show.add_argument("job_id")

    listing = subparsers.add_parser("list-jobs", help="List recent jobs")
    listing.add_argument("--limit", type=int, default=20)

    add_scene = subparsers.add_parser("add-scene", help="Add a planned scene")
    add_scene.add_argument("job_id")
    add_scene.add_argument("--position", type=int, required=True)
    add_scene.add_argument("--kind", choices=["a_roll", "b_roll"], required=True)
    add_scene.add_argument("--duration", type=int, choices=[4, 6, 8], required=True)
    add_scene.add_argument("--narration", required=True)
    add_scene.add_argument("--visual-prompt", required=True)

    list_scenes = subparsers.add_parser("list-scenes", help="List job scenes")
    list_scenes.add_argument("job_id")

    subparsers.add_parser("comfy-health", help="Check the local ComfyUI API")

    render = subparsers.add_parser(
        "render-first-frame", help="Create an API workflow without submitting it"
    )
    render.add_argument("--prompt", required=True)
    render.add_argument("--reference-image", default="A1_contradiction.png")
    render.add_argument("--output-prefix", default="vertex_ad_factory/preview")
    render.add_argument("--width", type=int, default=720)
    render.add_argument("--height", type=int, default=1280)
    render.add_argument("--seed", type=int)
    render.add_argument(
        "--destination",
        type=Path,
        default=settings.runs_dir / "preview_first_frame.api.json",
    )

    submit = subparsers.add_parser(
        "submit-first-frame", help="Generate one scene first frame in ComfyUI"
    )
    submit.add_argument("job_id")
    submit.add_argument("--position", type=int, required=True)
    submit.add_argument("--reference-image", default="A1_contradiction.png")
    submit.add_argument("--width", type=int, default=720)
    submit.add_argument("--height", type=int, default=1280)
    submit.add_argument("--seed", type=int)
    submit.add_argument("--force", action="store_true")

    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings.ensure_directories()
    database = Database(settings.database_path)
    database.initialize()

    if args.command == "init-db":
        print(f"Database ready: {settings.database_path}")
        return

    if args.command == "validate-blueprint":
        blueprint = load_blueprint(args.blueprint)
        print(json.dumps(blueprint.summary(), ensure_ascii=False, indent=2))
        return

    if args.command == "create-from-blueprint":
        blueprint = load_blueprint(args.blueprint)
        job = Orchestrator().create_from_blueprint(blueprint)
        print(
            json.dumps(
                {
                    "job_id": job.job_id,
                    "status": job.status.value,
                    "blueprint": blueprint.summary(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if args.command == "create-job":
        job = Orchestrator().create_job(
            product_name=args.product,
            angle=args.angle,
            language=args.language,
            target_duration_seconds=args.duration,
        )
        print(json.dumps({"job_id": job.job_id, "status": job.status.value}, indent=2))
        return

    if args.command == "show-job":
        job = database.get_job(args.job_id)
        if job is None:
            raise SystemExit(f"Unknown job: {args.job_id}")
        print(json.dumps(job, ensure_ascii=False, indent=2))
        return

    if args.command == "list-jobs":
        print(json.dumps(database.list_jobs(args.limit), ensure_ascii=False, indent=2))
        return

    if args.command == "add-scene":
        if database.get_job(args.job_id) is None:
            raise SystemExit(f"Unknown job: {args.job_id}")
        scene = database.add_scene(
            Scene(
                job_id=args.job_id,
                position=args.position,
                kind=SceneKind(args.kind),
                duration_seconds=args.duration,
                narration=args.narration,
                visual_prompt=args.visual_prompt,
            )
        )
        database.update_job_status(
            args.job_id, JobStatus.PLANNED, current_stage="planning"
        )
        print(
            json.dumps(
                {"scene_id": scene.scene_id, "position": scene.position}, indent=2
            )
        )
        return

    if args.command == "list-scenes":
        print(
            json.dumps(
                database.list_scenes(args.job_id), ensure_ascii=False, indent=2
            )
        )
        return

    if args.command == "comfy-health":
        async def check_health() -> dict:
            async with ComfyClient(settings.comfy_url, timeout_seconds=30) as client:
                return await client.system_stats()

        stats = asyncio.run(check_health())
        system = stats.get("system", {})
        devices = stats.get("devices", [])
        print(
            json.dumps(
                {
                    "url": settings.comfy_url,
                    "comfyui_version": system.get("comfyui_version"),
                    "python_version": system.get("python_version"),
                    "devices": [device.get("name") for device in devices],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if args.command == "render-first-frame":
        template_path = settings.workflows_dir / "aroll_first_frame.api.json"
        template = load_api_workflow(template_path)
        rendered, seed = bind_first_frame(
            template,
            FirstFrameBindings(
                prompt=args.prompt,
                reference_image=args.reference_image,
                output_prefix=args.output_prefix,
                width=args.width,
                height=args.height,
                seed=args.seed,
            ),
        )
        save_api_workflow(rendered, args.destination)
        print(
            json.dumps(
                {
                    "submitted": False,
                    "destination": str(args.destination),
                    "seed": seed,
                },
                indent=2,
            )
        )
        return

    if args.command == "submit-first-frame":
        result = asyncio.run(
            FirstFrameStage(settings, database).execute(
                job_id=args.job_id,
                position=args.position,
                reference_image=args.reference_image,
                seed=args.seed,
                width=args.width,
                height=args.height,
                force=args.force,
            )
        )
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()

