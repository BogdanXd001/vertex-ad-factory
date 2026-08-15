from __future__ import annotations

import argparse
import json

from .config import settings
from .database import Database
from .orchestrator import Orchestrator


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


if __name__ == "__main__":
    main()

