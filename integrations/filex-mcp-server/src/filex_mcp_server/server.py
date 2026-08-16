from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, TextIO

from . import __version__
from .client import FileXClient, FileXHTTPError

LOGGER = logging.getLogger("filex_mcp_server")
_UNKNOWN_TOOL = object()


def _project_receipt_v1(receipt: dict[str, Any]) -> dict[str, Any]:
    """Keep the MCP v1 boundary independent from the optional Ding package."""
    projected = dict(receipt)
    dimensions = []
    original = {
        str(d.get("id")): d.get("status")
        for d in receipt.get("dimensions", [])
        if isinstance(d, dict) and d.get("id")
    }
    for raw in receipt.get("dimensions", []):
        if not isinstance(raw, dict):
            continue
        dimension = dict(raw)
        dimension["status"] = "covered" if raw.get("status") == "covered" else "not_covered"
        dimension.pop("legacy_status", None)
        dimension.pop("reason_codes", None)
        dimensions.append(dimension)
    projected["version"] = "v1"
    projected["dimensions"] = dimensions
    projected["answerable"] = bool(receipt.get("answerable")) and all(d["status"] == "covered" for d in dimensions)
    projected["compatibility"] = {
        "lossy_projection": True,
        "original_status": original,
    }
    projected["insufficient_reasons"] = list(receipt.get("insufficient_reasons") or [])
    if any(status in {"conflicted", "blocked"} for status in original.values()):
        projected["insufficient_reasons"].append("coverage_receipt_v2_terminal_state")
    return projected


class DingRouterError(Exception):
    """A safe-to-return failure from the installed Ding router CLI."""


def _run_ding_query(
    arguments: dict[str, Any],
    *,
    origin: str,
    api_key: str,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    """Delegate a user-facing Ding question to the installed router CLI."""
    query = arguments.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query is required")
    thread_id = arguments.get("thread_id")
    if not isinstance(thread_id, str) or not thread_id.strip():
        raise ValueError("thread_id is required")
    finalize = arguments.get("finalize", True)
    if not isinstance(finalize, bool):
        raise ValueError("filex_ding_query finalize must be a boolean")
    workspace_id = arguments.get("workspace_id")
    if workspace_id is not None and (isinstance(workspace_id, bool) or not isinstance(workspace_id, int)):
        raise ValueError("filex_ding_query workspace_id must be an integer")
    if workspace_id is None:
        raise ValueError("filex_ding_query workspace_id is required for ACL-scoped answers")

    agent_dir = os.getenv("FILEX_DING_AGENT_DIR")
    cli = Path(agent_dir) / "filex_ding_router_cli.py" if agent_dir else None
    if cli is None or not cli.is_file():
        raise DingRouterError("Ding router request failed")

    command = [
        sys.executable,
        str(cli),
        f"--thread-id={thread_id}",
        "--finalize" if finalize else "--no-finalize",
        "--",
        query,
    ]
    if workspace_id is not None:
        command.insert(3, f"--workspace-id={workspace_id}")
    try:
        child_env = os.environ.copy()
        child_env.update(
            {
                "FILEX_ORIGIN": origin.rstrip("/"),
                "FILEX_API_KEY": api_key,
            }
        )
        if workspace_id is not None:
            child_env["FILEX_WORKSPACE_ID"] = str(workspace_id)
        completed = runner(
            command, capture_output=True, text=True, timeout=180, check=False, env=child_env
        )
    except (OSError, subprocess.TimeoutExpired):
        raise DingRouterError("Ding router request failed") from None
    if completed.returncode != 0:
        raise DingRouterError("Ding router request failed")
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError):
        raise DingRouterError("Ding router request failed") from None
    if not isinstance(payload, dict):
        raise DingRouterError("Ding router request failed")
    return payload


class FileXMCPServer:
    def __init__(self, origin: str, api_key: str, opener: Any | None = None) -> None:
        self.client = FileXClient(origin=origin, api_key=api_key, opener=opener)

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method")
        request_id = request.get("id")

        if method == "notifications/initialized":
            return None
        if method == "initialize":
            return self._result(
                request_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "filex-mcp-server", "version": __version__},
                    "instructions": (
                        "CRITICAL: For /ding or FileX user-facing questions, you MUST call filex_ding_query. "
                        "filex_search_kb will REJECT multi-entity queries — do not use it for questions like "
                        "'Are A and B coworkers?' or 'What is the relationship between X and Y?'. "
                        "When filex_ding_query returns cross_verified=false, you MUST call filex_ding_cross_compare "
                        "to complete cross-entity verification before delivering a final answer. "
                        "Never deliver a final answer with unverified multi-entity evidence."
                    ),
                },
            )
        if method == "tools/list":
            return self._result(request_id, {"tools": self._tools()})
        if method == "tools/call":
            return self._handle_tool_call(request_id, request.get("params") or {})
        return self._error(request_id, -32601, f"Unknown method: {method}")

    def _handle_tool_call(self, request_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            payload = self._call_tool(name, arguments)
        except ValueError as exc:
            return self._error(request_id, -32602, str(exc))
        except DingRouterError as exc:
            LOGGER.info("Ding router tool call failed: %s", exc)
            return self._error(request_id, -32000, str(exc))
        except FileXHTTPError as exc:
            LOGGER.info("FileX tool call failed: %s", exc)
            return self._error(request_id, -32000, str(exc))
        if payload is _UNKNOWN_TOOL:
            return self._error(request_id, -32601, f"Unknown tool: {name}")

        # 147: 如果 payload 含 _mcp_marker，前置到 text 中
        marker = None
        if isinstance(payload, dict) and "_mcp_marker" in payload:
            marker = payload.pop("_mcp_marker")
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if marker:
            text = marker + "\n\n" + text
        return self._result(request_id, {"content": [{"type": "text", "text": text}]})

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if name == "filex_api_key_status":
            return self.client.api_key_status()
        if name == "filex_list_workspaces":
            return self.client.list_workspaces()
        if name == "filex_list_folders":
            workspace_id = self._integer_argument(name, arguments, "workspace_id")
            return self.client.list_folders(workspace_id=workspace_id)
        if name == "filex_ding_query":
            result = _run_ding_query(
                arguments,
                origin=self.client.origin,
                api_key=self.client.api_key,
                runner=subprocess.run,
            )
            if result.get("cross_verified") is False:
                reason = str(result.get("missing_verification") or "多实体交叉验证未完成")
                safe_result = {
                    "kind": "insufficient_evidence",
                    "kb_answer": f"证据不足，无法确认。原因：{reason}。",
                    "cross_verified": False,
                    "missing_verification": reason,
                }
                if isinstance(result.get("coverage_receipt"), dict):
                    safe_result["coverage_receipt"] = _project_receipt_v1(result["coverage_receipt"])
                return safe_result
            return result
        if name == "filex_ding_cross_compare":
            entity_a = arguments.get("entity_a")
            entity_b = arguments.get("entity_b")
            if not entity_a or not entity_b:
                raise ValueError("entity_a and entity_b are required")
            workspace_id = self._integer_argument(name, arguments, "workspace_id")
            from filex_langgraph_intent_router import _cross_compare_entities
            from filex_langgraph_tools import resolve_authenticated_request_context
            try:
                context = resolve_authenticated_request_context(
                    origin=self.client.origin,
                    api_key_value=self.client.api_key,
                    workspace_id=workspace_id,
                )
            except (PermissionError, ValueError, OSError):
                context = None
            result = _cross_compare_entities(
                [str(entity_a), str(entity_b)], request_context=context
            )
            if isinstance(result.get("coverage_receipt"), dict):
                result["coverage_receipt"] = _project_receipt_v1(result["coverage_receipt"])
            cv = result.get("cross_verified")
            if cv is False:
                msg = result.get("missing_verification") or "需要交叉比对但未完成"
                safe_result = {
                    "kind": "insufficient_evidence",
                    "kb_answer": f"证据不足，无法确认。原因：{msg}。",
                    "cross_verified": False,
                    "missing_verification": msg,
                    "_mcp_marker": f"⚠️ CROSS_VERIFIED=false — {msg}",
                }
                if isinstance(result.get("coverage_receipt"), dict):
                    safe_result["coverage_receipt"] = result["coverage_receipt"]
                return safe_result
            return result
        if name == "filex_search_kb":
            query = arguments.get("query")
            if not query:
                raise ValueError("query is required")
            # 147: 多实体门禁 — 检测到多实体关系查询时，拒绝并重定向到 filex_ding_query
            try:
                from filex_langgraph_common import is_multi_entity_relation_question
                if is_multi_entity_relation_question(str(query)):
                    raise ValueError(
                        "检测到多实体关系查询。请使用 filex_ding_query（而非 filex_search_kb）"
                        "来获得完整的交叉比对结果。" "filex_search_kb 仅用于单实体/非关系型检索。"
                    )
            except ImportError:
                pass  # agent 包不可用时降级，不阻断
            # All unknown arguments are passed through to FileX backend as body fields
            passthrough = {
                key: value
                for key, value in arguments.items()
                if key not in {"query", "top_k", "workspace_id", "cross_workspace"}
            }
            top_k = arguments.get("top_k")
            if top_k is not None and (not isinstance(top_k, int) or top_k <= 0):
                raise ValueError(f"{name} top_k must be a positive integer")
            return self.client.search_kb(
                query=str(query),
                top_k=top_k,
                workspace_id=arguments.get("workspace_id"),
                cross_workspace=arguments.get("cross_workspace"),
                extra=passthrough,
            )
        if name == "filex_get_md_content":
            md5_hash = arguments.get("md5_hash")
            if md5_hash is not None and not isinstance(md5_hash, str):
                raise ValueError(f"{name} md5_hash must be a string")
            return self.client.get_md_content(
                md5_hash=md5_hash,
                file_id=self._optional_integer_argument(name, arguments, "file_id"),
            )
        if name == "filex_upload_file":
            file_path = arguments.get("file_path")
            if not file_path:
                raise ValueError("file_path is required")
            return self.client.upload_file(
                file_path=str(file_path),
                workspace_id=self._optional_integer_argument(name, arguments, "workspace_id"),
                folder_id=self._optional_integer_argument(name, arguments, "folder_id"),
            )
        if name == "filex_set_tags":
            file_id = self._integer_argument(name, arguments, "file_id")
            raw_tags = arguments.get("tags")
            if not isinstance(raw_tags, list):
                raise ValueError("tags must be a list of strings")
            if not all(isinstance(t, str) for t in raw_tags):
                raise ValueError("tags must be a list of strings")
            tags = raw_tags
            if not tags:
                raise ValueError("tags must not be empty")
            return self.client.set_tags(file_id=file_id, tags=tags)
        if name == "filex_wait_extract_ready":
            file_id = self._integer_argument(name, arguments, "file_id")
            poll_interval = arguments.get("poll_interval")
            max_wait = arguments.get("max_wait")
            if poll_interval is not None:
                if not isinstance(poll_interval, (int, float)) or float(poll_interval) <= 0:
                    raise ValueError(f"{name} poll_interval must be a positive number")
            if max_wait is not None:
                if not isinstance(max_wait, (int, float)) or float(max_wait) <= 0:
                    raise ValueError(f"{name} max_wait must be a positive number")
            kwargs: dict[str, Any] = {}
            if poll_interval is not None:
                kwargs["poll_interval"] = float(poll_interval)
            if max_wait is not None:
                kwargs["max_wait"] = float(max_wait)
            return self.client.wait_extract_ready(file_id=file_id, **kwargs)
        return _UNKNOWN_TOOL

    @staticmethod
    def _integer_argument(tool_name: str, arguments: dict[str, Any], key: str) -> int:
        value = arguments.get(key)
        if value is None:
            raise ValueError(f"{key} is required")
        if isinstance(value, bool):
            raise ValueError(f"{tool_name} {key} must be an integer")
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                raise ValueError(f"{tool_name} {key} must be an integer") from None
        raise ValueError(f"{tool_name} {key} must be an integer")

    @staticmethod
    def _optional_integer_argument(tool_name: str, arguments: dict[str, Any], key: str) -> int | None:
        if key not in arguments or arguments.get(key) is None:
            return None
        return FileXMCPServer._integer_argument(tool_name, arguments, key)

    @staticmethod
    def _tools() -> list[dict[str, Any]]:
        return [
            FileXMCPServer._api_key_status_tool(),
            {
                "name": "filex_list_workspaces",
                "description": "List FileX workspaces visible to the current API Key.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
            {
                "name": "filex_list_folders",
                "description": "List the folder tree for a FileX workspace.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"workspace_id": {"type": "integer"}},
                    "required": ["workspace_id"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "filex_ding_query",
                "description": (
                    "Answer a /ding or FileX user-facing question through the installed Ding router. "
                    "Use this high-level entry point instead of raw retrieval."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The user-facing Ding question."},
                        "thread_id": {"type": "string", "description": "Stable conversation thread ID."},
                        "finalize": {
                            "type": "boolean",
                            "default": True,
                            "description": "Whether the Ding router should finalize this turn.",
                        },
                        "workspace_id": {"type": "integer", "description": "Authorized workspace for this answer."},
                    },
                    "required": ["query", "thread_id", "workspace_id"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "filex_ding_cross_compare",
                "description": (
                    "Cross-compare two named entities: search each, retrieve full MD, "
                    "extract entity-specific paragraphs, output cross-comparison results. "
                    "Use for multi-entity relation queries (e.g., 'Are A and B coworkers?'). "
                    "Only supports 2 entities; for 3+ entities call this tool pairwise."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "entity_a": {"type": "string", "description": "First named entity."},
                        "entity_b": {"type": "string", "description": "Second named entity."},
                        "thread_id": {"type": "string", "description": "Stable conversation thread ID."},
                        "workspace_id": {"type": "integer", "description": "Authorized workspace for this comparison."},
                    },
                    "required": ["entity_a", "entity_b", "workspace_id"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "filex_search_kb",
                "description": "Low-level raw retrieval for single-entity or non-relational queries. Multi-entity relation queries (e.g., person A and person B) are rejected — use filex_ding_query instead.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer"},
                        "workspace_id": {"type": "integer"},
                        "cross_workspace": {"type": "boolean"},
                    },
                    "required": ["query"],
                    "additionalProperties": True,
                },
            },
            {
                "name": "filex_get_md_content",
                "description": "Read FileX markdown note. Exactly one of md5_hash or file_id must be provided.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "md5_hash": {"type": "string"},
                        "file_id": {"type": "integer"},
                    },
                    "oneOf": [
                        {"required": ["md5_hash"], "not": {"required": ["file_id"]}},
                        {"required": ["file_id"], "not": {"required": ["md5_hash"]}},
                    ],
                    "additionalProperties": False,
                },
            },
            {
                "name": "filex_upload_file",
                "description": (
                    "Upload a local file to FileX through POST /api/external/files (multipart/form-data). "
                    "Supports optional workspace_id and folder_id. "
                    "Large files may take longer; callers should set adequate timeouts. "
                    "Returns file metadata including id, md5_hash, and extract_status."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Absolute path to the local file to upload.",
                        },
                        "workspace_id": {
                            "type": "integer",
                            "description": "Target workspace ID. Omit for personal workspace.",
                        },
                        "folder_id": {
                            "type": "integer",
                            "description": "Target folder ID within the workspace. Omit for uncategorized.",
                        },
                    },
                    "required": ["file_path"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "filex_set_tags",
                "description": (
                    "Merge tags onto a FileX file through PUT /api/external/files/{file_id}/tags. "
                    "Tags are merged (union) — existing tags not in the list are preserved."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "integer",
                            "description": "The file ID to tag.",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of tag strings to merge onto the file.",
                        },
                    },
                    "required": ["file_id", "tags"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "filex_wait_extract_ready",
                "description": (
                    "Polls GET /api/files/{file_id} (polling mode) until extract_status becomes 'ready' or 'not_needed'. "
                    "Raises an error on 'failed' or timeout. Default poll interval 2s, max wait 300s."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "integer",
                            "description": "The file ID whose extract status to wait for.",
                        },
                        "poll_interval": {
                            "type": "number",
                            "description": "Seconds between polls. Default 2.0.",
                        },
                        "max_wait": {
                            "type": "number",
                            "description": "Maximum total wait in seconds. Default 300.0.",
                        },
                    },
                    "required": ["file_id"],
                    "additionalProperties": False,
                },
            },
        ]

    @staticmethod
    def _api_key_status_tool() -> dict[str, Any]:
        return {
            "name": "filex_api_key_status",
            "description": "Probe FileX API Key and License status via GET /api/external/api-key-status.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        }

    @staticmethod
    def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }


def run_stdio(
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
) -> None:
    logging.basicConfig(level=os.getenv("FILEX_MCP_LOG_LEVEL", "INFO"))
    server = FileXMCPServer(
        origin=os.getenv("FILEX_ORIGIN", ""),
        api_key=os.getenv("FILEX_API_KEY", ""),
    )
    for line in input_stream:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = server.handle_request(request)
        except Exception as exc:  # pragma: no cover - stdio safety net
            LOGGER.exception("Unhandled MCP request failure (%s: %s)", type(exc).__name__, exc)
            response = FileXMCPServer._error(None, -32603, str(exc))
        if response is not None:
            output_stream.write(json.dumps(response, ensure_ascii=False) + "\n")
            output_stream.flush()
