from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .clients.comfy import ComfyClient
from .config import settings
from .database import Database
from .orchestrator import Orchestrator
from .services.workflows import (
    FirstFrameBindings,
    bind_first_frame,
    load_api_workflow,
    save_api_workflow,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ad-factory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create or upgrade the SQLite database")

    create = subparsers.add_parser("create-job", help="Create a new ad job")
    create.add_argument("--product", required=True)
    create.add_argument("--angle", required=True)
    create.add_argument("--language", default="ro")
    create.add_argument("--duration", type=int, default=30)

    show = subparsers.add_parser("show-job", help="Show one job")
    show.add_argument("job_id")

    listing = subparsers.add_parser("list-jobs", help="List recent jobs")
    listing.add_argument("--limit", type=int, default=20)

    subparsers.add_parser("comfy-health", help="Check the local ComfyUI API")

    render = subparsers.add_parser(
        "render-first-frame", help="Create an API workflow without submitting it"
    )
    render.add_argument("--prompt", required=True)
    render.add_argument("--reference-image", default="A1_contradiction.png")
    render.add_argument("--output-prefix", default="vertex_ad_factory/preview")
    render.add_argument("--width", type=int, default=832)
    render.add_argument("--height", type=int, default=1216)
    render.add_argument("--seed", type=int)
    render.add_argument(
        "--destination",
        type=Path,
        default=settings.runs_dir / "preview_first_frame.api.json",
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings.ensure_directories()
    database = Database(settings.database_path)
    database.initialize()

    if args.command == "init-db":
        print(f"Database ready: {settings.database_path}")
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


if __name__ == "__main__":
    main()
