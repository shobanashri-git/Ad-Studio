"""Thin RunningHub API client.

Wraps the four openapi endpoints used by the pipeline:
  upload  -> push an input file, get back a fileName
  create  -> run a workflow by workflowId with a nodeInfoList of overrides
  status  -> QUEUED / RUNNING / SUCCESS / FAILED
  outputs -> output file URLs for a finished task

Auth is a bearer API key (Personal membership+). The Host header must match
the base host exactly; pick the region base that matches your key:
  https://www.runninghub.ai  (intl)
  https://www.runninghub.cn  (mainland)
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

import httpx


class RunningHubError(RuntimeError):
    """Raised when RunningHub returns a non-success task state or HTTP error."""


@dataclass
class NodeOverride:
    """One entry in a create call's nodeInfoList."""
    node_id: str
    field_name: str
    field_value: Any

    def to_json(self) -> dict:
        return {
            "nodeId": self.node_id,
            "fieldName": self.field_name,
            "fieldValue": self.field_value,
        }


class RunningHubClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ):
        self.api_key = api_key or os.environ.get("RH_API_KEY", "")
        self.base_url = (base_url or os.environ.get("RH_BASE_URL", "https://www.runninghub.ai")).rstrip("/")
        if not self.api_key:
            raise RunningHubError("RH_API_KEY is not set")
        # Host header must match the base host exactly.
        host = self.base_url.split("://", 1)[-1]
        self._headers = {"Host": host}
        self._timeout = timeout

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, headers=self._headers, timeout=self._timeout)

    async def account_status(self) -> dict:
        """Return account status (remaining coins, running tasks). Best-effort:
        returns {} on any error so the UI can degrade gracefully."""
        try:
            async with self._client() as c:
                r = await c.post("/uc/openapi/accountStatus", json={"apikey": self.api_key})
            data = self._json(r, "accountStatus")
            body = data.get("data", data)
            return body if isinstance(body, dict) else {}
        except Exception:
            return {}

    async def upload(self, path: str) -> str:
        """Upload a local file, return the RunningHub fileName to reference in overrides."""
        async with self._client() as c:
            with open(path, "rb") as fh:
                files = {"file": (os.path.basename(path), fh)}
                data = {"apiKey": self.api_key}
                r = await c.post("/task/openapi/upload", data=data, files=files)
        return self._extract(r, "upload", key="fileName")

    async def create(self, workflow_id: str, overrides: list) -> str:
        """Run a workflow with node overrides, return a taskId.

        `overrides` is any list of objects exposing .to_json() -> {nodeId,
        fieldName, fieldValue} (see patcher.Override / NodeOverride)."""
        payload = {
            "apiKey": self.api_key,
            "workflowId": workflow_id,
            "nodeInfoList": [o.to_json() for o in overrides],
        }
        async with self._client() as c:
            r = await c.post("/task/openapi/create", json=payload)
        return self._extract(r, "create", key="taskId")

    async def status(self, task_id: str) -> str:
        payload = {"apiKey": self.api_key, "taskId": task_id}
        async with self._client() as c:
            r = await c.post("/task/openapi/status", json=payload)
        return self._extract(r, "status", key="status")

    async def outputs(self, task_id: str) -> list[str]:
        """Return the list of output file URLs for a finished task."""
        payload = {"apiKey": self.api_key, "taskId": task_id}
        async with self._client() as c:
            r = await c.post("/task/openapi/outputs", json=payload)
        data = self._json(r, "outputs")
        items = data.get("data") or []
        urls: list[str] = []
        for it in items:
            if isinstance(it, str):
                urls.append(it)
            elif isinstance(it, dict):
                u = it.get("fileUrl") or it.get("url") or it.get("fileName")
                if u:
                    urls.append(u)
        return urls

    async def wait(
        self,
        task_id: str,
        on_status=None,
        poll_interval: float = 3.0,
        max_polls: int = 400,
    ) -> list[str]:
        """Poll until SUCCESS (return outputs) or FAILED (raise)."""
        for _ in range(max_polls):
            st = await self.status(task_id)
            if on_status:
                on_status(st)
            if st == "SUCCESS":
                return await self.outputs(task_id)
            if st == "FAILED":
                raise RunningHubError(f"task {task_id} FAILED")
            await asyncio.sleep(poll_interval)
        raise RunningHubError(f"task {task_id} timed out after {max_polls} polls")

    # ---- response helpers ----
    def _json(self, r: httpx.Response, where: str) -> dict:
        if r.status_code >= 400:
            raise RunningHubError(f"{where}: HTTP {r.status_code} — {r.text[:300]}")
        try:
            data = r.json()
        except Exception as e:
            raise RunningHubError(f"{where}: non-JSON response — {r.text[:300]}") from e
        # RunningHub wraps results in {code, msg, data}; code 0 == ok.
        if isinstance(data, dict) and data.get("code") not in (0, None, "0"):
            raise RunningHubError(f"{where}: {data.get('msg') or data}")
        return data

    def _extract(self, r: httpx.Response, where: str, key: str) -> Any:
        data = self._json(r, where)
        body = data.get("data", data)
        # RunningHub sometimes returns the value directly in `data` as a scalar
        # (e.g. status -> data: "RUNNING") rather than nested under `key`.
        if isinstance(body, (str, int, float)):
            return body
        if isinstance(body, dict) and key in body:
            return body[key]
        if key in data:
            return data[key]
        raise RunningHubError(f"{where}: '{key}' not in response — {str(data)[:300]}")
