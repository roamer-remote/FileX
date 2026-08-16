# Copyright (c) 2026 徐泽宇
"""Notion REST client for external sync (read-only)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterator

import httpx

from services.kb_external_sync.block_to_markdown import blocks_to_markdown
from services.sync_secret_service import redact_sync_secret

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
NOTION_TIMEOUT_SEC = 60.0


class NotionClientError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def parse_notion_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).astimezone(timezone.utc)


def page_title(page: dict[str, Any]) -> str:
    props = page.get("properties") or {}
    for prop in props.values():
        if prop.get("type") == "title":
            parts = prop.get("title") or []
            title = "".join(p.get("plain_text", "") for p in parts).strip()
            if title:
                return title
    return (page.get("id") or "untitled").replace("-", "")[:32]


class NotionClient:
    def __init__(self, token: str) -> None:
        self._token = token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{NOTION_API_BASE}{path}"
        try:
            with httpx.Client(timeout=NOTION_TIMEOUT_SEC) as client:
                resp = client.request(method, url, headers=self._headers(), **kwargs)
        except httpx.HTTPError as exc:
            msg = redact_sync_secret(str(exc), self._token)
            raise NotionClientError(msg) from exc
        if resp.status_code >= 400:
            detail = redact_sync_secret(resp.text[:500], self._token)
            raise NotionClientError(
                f"Notion API {resp.status_code}: {detail}",
                status_code=resp.status_code,
            )
        return resp.json()

    def test_connection(self, database_id: str) -> dict[str, Any]:
        dbid = (database_id or "").strip()
        if not dbid:
            raise NotionClientError("config_public_json.database_id 未配置")
        return self._request("GET", f"/databases/{dbid}")

    def iter_database_pages(self, database_id: str) -> Iterator[dict[str, Any]]:
        dbid = (database_id or "").strip()
        cursor: str | None = None
        while True:
            body: dict[str, Any] = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            data = self._request("POST", f"/databases/{dbid}/query", json=body)
            for row in data.get("results") or []:
                yield row
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

    def fetch_page_blocks(self, page_id: str) -> list[dict[str, Any]]:
        pid = (page_id or "").strip()
        blocks: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            data = self._request("GET", f"/blocks/{pid}/children", params=params)
            for block in data.get("results") or []:
                if block.get("has_children"):
                    block["children"] = self.fetch_page_blocks(block["id"])
                blocks.append(block)
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
        return blocks

    def page_to_markdown(self, page: dict[str, Any]) -> str:
        page_id = page.get("id") or ""
        title = page_title(page)
        blocks = self.fetch_page_blocks(page_id)
        body = blocks_to_markdown(blocks)
        if body.strip():
            return f"# {title}\n\n{body}".strip() + "\n"
        return f"# {title}\n"
