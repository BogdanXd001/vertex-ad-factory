from __future__ import annotations

import json
import sys
from pathlib import Path

from aiohttp import web
from server import PromptServer


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from vertex_ad_factory.config import settings  # noqa: E402
from vertex_ad_factory.control import PipelineManager, StartRequest  # noqa: E402


MANAGER = PipelineManager(settings)
INDEX_PATH = Path(__file__).parent / "web" / "index.html"


@PromptServer.instance.routes.get("/vertex-ad-factory")
async def dashboard_redirect(_: web.Request) -> web.Response:
    raise web.HTTPPermanentRedirect("/vertex-ad-factory/")


@PromptServer.instance.routes.get("/vertex-ad-factory/")
async def dashboard(_: web.Request) -> web.FileResponse:
    return web.FileResponse(INDEX_PATH)


@PromptServer.instance.routes.get("/vertex-ad-factory/api/status")
async def dashboard_status(_: web.Request) -> web.Response:
    return web.json_response(MANAGER.status())


@PromptServer.instance.routes.post("/vertex-ad-factory/api/config")
async def dashboard_config(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
        api_key = payload.get("api_key")
        if api_key == "":
            api_key = None
        config = MANAGER.runtime_store.update_voiceover(
            api_key=api_key,
            voice_id=str(payload.get("voice_id", "")),
            model_id=str(
                payload.get("model_id", "eleven_multilingual_v2")
            ),
            output_format=str(payload.get("output_format", "mp3_44100_128")),
        )
        return web.json_response(config.public_dict())
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        return web.json_response({"error": str(error)}, status=400)


@PromptServer.instance.routes.post("/vertex-ad-factory/api/start")
async def dashboard_start(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
        result = MANAGER.start(
            StartRequest(
                blueprint=str(payload.get("blueprint", "")),
                reference_image=str(
                    payload.get("reference_image", "A1_contradiction.png")
                ),
                seed=int(payload.get("seed", 42)),
                width=int(payload.get("width", 720)),
                height=int(payload.get("height", 1280)),
            )
        )
        return web.json_response(result, status=202)
    except (FileNotFoundError, TypeError, ValueError, json.JSONDecodeError) as error:
        return web.json_response({"error": str(error)}, status=400)


@PromptServer.instance.routes.post("/vertex-ad-factory/api/resume/{job_id}")
async def dashboard_resume(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
        result = MANAGER.resume(
            request.match_info["job_id"],
            StartRequest(
                blueprint="",
                reference_image=str(
                    payload.get("reference_image", "A1_contradiction.png")
                ),
                seed=int(payload.get("seed", 42)),
                width=int(payload.get("width", 720)),
                height=int(payload.get("height", 1280)),
            ),
        )
        return web.json_response(result, status=202)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return web.json_response({"error": str(error)}, status=400)


NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
