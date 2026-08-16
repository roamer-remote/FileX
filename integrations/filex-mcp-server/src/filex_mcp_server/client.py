from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import quote, urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

LOGGER = logging.getLogger("filex_mcp_server.client")
JSONValue = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
JSONObject = dict[str, JSONValue]
JSONArray = list[JSONValue]


class FileXHTTPError(RuntimeError):
    """Raised when FileX HTTP API cannot be reached or returns an error."""


def mask_api_key(api_key: str) -> str:
    if not api_key:
        return "<missing>"
    suffix = api_key[-4:] if len(api_key) >= 4 else api_key
    return f"{api_key[:3]}...{suffix}" if api_key.startswith("fb_") else f"...{suffix}"


def _build_multipart_body(file_path: str, fields: dict[str, str | int]) -> tuple[bytes, str]:
    boundary = f"----FileXMCPFormBoundary{uuid.uuid4().hex[:16]}"

    filename = os.path.basename(file_path)
    with open(file_path, "rb") as fh:
        file_bytes = fh.read()

    lines = [
        f"--{boundary}",
        f'Content-Disposition: form-data; name="file"; filename="{filename}"',
        "Content-Type: application/octet-stream",
        "",
    ]
    body_head = "\r\n".join(lines) + "\r\n"

    tail_lines: list[str] = []
    for key, value in fields.items():
        tail_lines.append(f"--{boundary}")
        tail_lines.append(f'Content-Disposition: form-data; name="{key}"')
        tail_lines.append("")
        tail_lines.append(str(value))
    tail_lines.append(f"--{boundary}--")
    tail_lines.append("")
    body_tail = "\r\n".join(tail_lines)

    full_body = body_head.encode("utf-8") + file_bytes + body_tail.encode("utf-8")
    return full_body, boundary


@dataclass
class FileXClient:
    origin: str
    api_key: str = ""
    timeout: int = 30
    opener: Any | None = None

    def __post_init__(self) -> None:
        self.origin = self.origin.rstrip("/")
        if self.api_key and not self.api_key.startswith("fb_"):
            LOGGER.warning("FILEX_API_KEY does not have fb_ prefix; it may not be a FileX API key")
        if self.opener is None:
            self.opener = build_opener()

    def api_key_status(self) -> JSONObject:
        return cast(JSONObject, self._request_json("GET", "/api/external/api-key-status"))

    def list_workspaces(self) -> JSONArray:
        return cast(JSONArray, self._request_json("GET", "/api/workspaces"))

    def list_folders(self, workspace_id: int) -> JSONArray:
        return cast(JSONArray, self._request_json("GET", f"/api/folders?{urlencode({'workspace_id': workspace_id})}"))

    def search_kb(
        self,
        query: str,
        top_k: int | None = None,
        workspace_id: int | None = None,
        cross_workspace: bool | None = None,
        extra: dict[str, Any] | None = None,
    ) -> JSONObject:
        params: dict[str, str | int] = {}
        if workspace_id is not None:
            params["workspace_id"] = workspace_id
        if cross_workspace is not None:
            params["cross_workspace"] = str(cross_workspace).lower()
        suffix = f"?{urlencode(params)}" if params else ""
        body: dict[str, Any] = {"query": query}
        if top_k is not None:
            body["top_k"] = top_k
        if extra:
            body.update(extra)
        return cast(JSONObject, self._request_json("POST", f"/api/knowledge-base/search{suffix}", json_body=body))

    def get_md_content(self, md5_hash: str | None = None, file_id: int | None = None) -> str:
        if md5_hash and file_id is not None:
            raise ValueError("Pass only one of md5_hash or file_id")
        if not md5_hash and file_id is None:
            raise ValueError("Pass md5_hash or file_id")
        if md5_hash:
            return self._request_text("GET", f"/api/external/md-content/{quote(md5_hash, safe='')}")
        return self._request_text("GET", f"/api/files/{file_id}/md")

    def upload_file(
        self,
        file_path: str,
        workspace_id: int | None = None,
        folder_id: int | None = None,
    ) -> JSONObject:
        if not os.path.isfile(file_path):
            raise ValueError(f"File not found: {file_path}")
        fields: dict[str, str | int] = {}
        if workspace_id is not None:
            fields["workspace_id"] = workspace_id
        if folder_id is not None:
            fields["folder_id"] = folder_id
        return cast(JSONObject, self._multipart_request("/api/external/files", file_path, fields))

    def set_tags(self, file_id: int, tags: list[str]) -> JSONObject:
        return cast(JSONObject, self._request_json("PUT", f"/api/external/files/{file_id}/tags", json_body={"tags": tags}))

    def wait_extract_ready(
        self,
        file_id: int,
        poll_interval: float = 2.0,
        max_wait: float = 300.0,
    ) -> JSONObject:
        deadline = time.monotonic() + max_wait
        while True:
            info = cast(JSONObject, self._request_json("GET", f"/api/files/{file_id}"))
            status = info.get("extract_status")
            if status in ("ready", "not_needed"):
                return info
            if status == "failed":
                raise FileXHTTPError(f"extract_status 'failed' for file_id={file_id}")
            if time.monotonic() >= deadline:
                raise FileXHTTPError(f"Timed out waiting for extract_status 'ready' for file_id={file_id} after {max_wait:.0f}s")
            time.sleep(poll_interval)

    def _multipart_request(self, path: str, file_path: str, fields: dict[str, str | int]) -> JSONValue:
        if not self.origin:
            raise FileXHTTPError("FILEX_ORIGIN is required")

        body_bytes, boundary = _build_multipart_body(file_path, fields)
        request = Request(f"{self.origin}{path}", data=body_bytes, method="POST")
        request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        request.add_header("Accept", "application/json")
        if self.api_key:
            request.add_header("Authorization", f"Bearer {self.api_key}")

        timeout = max(self.timeout, 120)
        raw = self._http_send(request, path, timeout=timeout)
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FileXHTTPError(f"FileX returned non-JSON response for {path}") from exc

    def _request_json(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
    ) -> JSONValue:
        raw = self._request(method, path, json_body=json_body)
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FileXHTTPError(f"FileX returned non-JSON response for {path}") from exc

    def _request_text(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
    ) -> str:
        return self._request(method, path, json_body=json_body)

    def _request(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
    ) -> str:
        if not self.origin:
            raise FileXHTTPError("FILEX_ORIGIN is required")

        data = None
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        request = Request(f"{self.origin}{path}", data=data, method=method)
        request.add_header("Accept", "application/json")
        if json_body is not None:
            request.add_header("Content-Type", "application/json")
        if self.api_key:
            request.add_header("Authorization", f"Bearer {self.api_key}")

        return self._http_send(request, path, timeout=self.timeout)

    def _http_send(self, request: Request, path: str, timeout: int) -> str:
        try:
            with self.opener.open(request, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except HTTPError as exc:
            detail = self._http_error_detail(exc)
            raise FileXHTTPError(
                f"FileX HTTP {exc.code} for {path}: {detail} (key {mask_api_key(self.api_key)})"
            ) from exc
        except URLError as exc:
            raise FileXHTTPError(
                f"FileX connection error for {path} with key {mask_api_key(self.api_key)}: {exc.reason}"
            ) from exc

    @staticmethod
    def _http_error_detail(exc: HTTPError) -> str:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            return exc.reason or f"HTTP {exc.code}"
        if not raw:
            return exc.reason or f"HTTP {exc.code}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return raw[:200]
        if isinstance(payload, dict):
            detail = payload.get("detail") or payload.get("reason") or payload
            if isinstance(detail, (dict, list)):
                return json.dumps(detail, ensure_ascii=False)[:200]
            return str(detail)[:200]
        return str(payload)[:200]
