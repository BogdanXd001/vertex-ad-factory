from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import aiohttp


class ComfyError(RuntimeError):
    """Raised when ComfyUI rejects or fails a request."""


@dataclass(frozen=True, slots=True)
class ComfyOutput:
    node_id: str
    filename: str
    subfolder: str
    output_type: str


class ComfyClient:
    def __init__(self, base_url: str, timeout_seconds: int = 1800) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> ComfyClient:
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        self._session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise RuntimeError("Use ComfyClient with 'async with'")
        return self._session

    async def _json_request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        async with self.session.request(method, url, **kwargs) as response:
            body = await response.text()
            if response.status >= 400:
                raise ComfyError(f"ComfyUI {response.status} at {path}: {body[:1000]}")
            if not body:
                return {}
            try:
                return await response.json()
            except (aiohttp.ContentTypeError, ValueError) as error:
                raise ComfyError(f"Invalid JSON from ComfyUI at {path}") from error

    async def system_stats(self) -> dict[str, Any]:
        return await self._json_request("GET", "/system_stats")

    async def queue_prompt(
        self,
        workflow: dict[str, Any],
        client_id: str | None = None,
    ) -> str:
        payload = {
            "prompt": workflow,
            "client_id": client_id or uuid4().hex,
        }
        response = await self._json_request("POST", "/prompt", json=payload)
        prompt_id = response.get("prompt_id")
        if not prompt_id:
            raise ComfyError(f"ComfyUI did not return prompt_id: {response}")
        return str(prompt_id)

    async def get_history(self, prompt_id: str) -> dict[str, Any] | None:
        response = await self._json_request("GET", f"/history/{prompt_id}")
        entry = response.get(prompt_id)
        return entry if isinstance(entry, dict) else None

    async def wait_for_completion(
        self,
        prompt_id: str,
        poll_seconds: float = 1.0,
    ) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.timeout_seconds
        while loop.time() < deadline:
            history = await self.get_history(prompt_id)
            if history is not None:
                status = history.get("status", {})
                if status.get("status_str") == "error":
                    messages = status.get("messages", [])
                    raise ComfyError(f"ComfyUI execution failed: {messages}")
                return history
            await asyncio.sleep(poll_seconds)
        raise TimeoutError(f"ComfyUI prompt timed out: {prompt_id}")

    @staticmethod
    def outputs_from_history(history: dict[str, Any]) -> list[ComfyOutput]:
        results: list[ComfyOutput] = []
        for node_id, node_output in history.get("outputs", {}).items():
            for item in node_output.get("images", []):
                results.append(
                    ComfyOutput(
                        node_id=str(node_id),
                        filename=str(item["filename"]),
                        subfolder=str(item.get("subfolder", "")),
                        output_type=str(item.get("type", "output")),
                    )
                )
        return results

