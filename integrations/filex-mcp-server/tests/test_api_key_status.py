import json
import shutil
import subprocess
import sys
from io import BytesIO, StringIO
from pathlib import Path
from urllib.error import HTTPError

import pytest
import httpx

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ROOT.parents[1] / "skill" / "ding" / "agent"))


class FakeResponse:
    def __init__(self, payload, status=200, raw: bytes | None = None):
        self.payload = payload
        self.status = status
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        if self.raw is not None:
            return self.raw
        return json.dumps(self.payload).encode("utf-8")


class FakeOpener:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def open(self, request, timeout=30):
        self.requests.append((request, timeout))
        return FakeResponse(self.payload)


class QueueOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout=30):
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, bytes):
            return FakeResponse(None, raw=response)
        return FakeResponse(response)


class CapturingOpener:
    """Records request details for assertion."""

    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def open(self, request, timeout=30):
        req_info = {
            "full_url": request.full_url,
            "method": request.method,
            "headers": dict(request.headers),
            "timeout": timeout,
        }
        if request.data is not None:
            req_info["body"] = request.data
        self.requests.append(req_info)
        return FakeResponse(self.payload)



def test_api_key_status_calls_probe_endpoint_with_bearer_header():
    from filex_mcp_server.client import FileXClient

    opener = FakeOpener({"valid": True, "reason": None, "username": "alice"})
    client = FileXClient(
        origin="https://ding.example/",
        api_key="fb_secret_key_1234",
        opener=opener,
    )

    result = client.api_key_status()

    assert result["valid"] is True
    request, timeout = opener.requests[0]
    assert request.full_url == "https://ding.example/api/external/api-key-status"
    assert request.get_header("Authorization") == "Bearer fb_secret_key_1234"
    assert timeout == 30


def test_api_key_status_omits_authorization_when_key_missing():
    from filex_mcp_server.client import FileXClient

    opener = FakeOpener({"valid": False, "reason": "missing_authorization"})
    client = FileXClient(origin="https://ding.example", api_key="", opener=opener)

    result = client.api_key_status()

    assert result["reason"] == "missing_authorization"
    request, _timeout = opener.requests[0]
    assert request.get_header("Authorization") is None


def test_http_error_message_does_not_leak_full_api_key():
    from filex_mcp_server.client import FileXClient, FileXHTTPError

    class ErrorOpener:
        def open(self, request, timeout=30):
            raise HTTPError(
                request.full_url,
                503,
                "Service Unavailable",
                hdrs=None,
                fp=None,
            )

    client = FileXClient(
        origin="https://ding.example",
        api_key="fb_super_secret_9999",
        opener=ErrorOpener(),
    )

    with pytest.raises(FileXHTTPError) as exc:
        client.api_key_status()

    message = str(exc.value)
    assert "503" in message
    assert "fb_super_secret_9999" not in message
    assert "9999" in message


def test_http_error_message_includes_backend_detail():
    from filex_mcp_server.client import FileXClient, FileXHTTPError

    class ErrorOpener:
        def open(self, request, timeout=30):
            raise HTTPError(
                request.full_url,
                403,
                "Forbidden",
                hdrs=None,
                fp=BytesIO(json.dumps({"detail": "用户账号已经停用！请联系管理员"}).encode("utf-8")),
            )

    client = FileXClient(
        origin="https://ding.example",
        api_key="fb_secret_key_1234",
        opener=ErrorOpener(),
    )

    with pytest.raises(FileXHTTPError) as exc:
        client.api_key_status()

    message = str(exc.value)
    assert "403" in message
    assert "用户账号已经停用" in message
    assert "fb_secret_key_1234" not in message


@pytest.mark.parametrize(
    "payload",
    [
        {
            "valid": False,
            "reason": "license_expired",
            "hint": "联系管理员续期 License",
            "username": None,
        },
        {
            "valid": False,
            "reason": "user_inactive",
            "hint": "用户账号已经停用",
            "username": "inactiveuser",
        },
        {
            "valid": False,
            "reason": "invalid_api_key",
            "hint": "无效密钥",
            "username": None,
        },
        {
            "valid": False,
            "reason": "missing_authorization",
            "hint": "缺少 Authorization",
            "username": None,
        },
    ],
)
def test_mcp_call_api_key_status_preserves_invalid_status_payload(payload):
    from filex_mcp_server.server import FileXMCPServer

    opener = FakeOpener(payload)
    server = FileXMCPServer(
        origin="https://ding.example",
        api_key="fb_key",
        opener=opener,
    )

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "filex_api_key_status", "arguments": {}},
        }
    )

    text = response["result"]["content"][0]["text"]
    parsed = json.loads(text)
    assert parsed["valid"] is False
    assert parsed["reason"] == payload["reason"]
    assert parsed["hint"] == payload["hint"]
    assert parsed["username"] == payload["username"]


def test_mcp_server_exposes_api_key_status_tool():
    from filex_mcp_server.server import FileXMCPServer

    server = FileXMCPServer(origin="https://ding.example", api_key="fb_key")

    response = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    assert response["id"] == 1
    tools = response["result"]["tools"]
    assert [tool["name"] for tool in tools] == [
        "filex_api_key_status",
        "filex_list_workspaces",
        "filex_list_folders",
        "filex_ding_query",
        "filex_ding_cross_compare",
        "filex_search_kb",
        "filex_get_md_content",
        "filex_upload_file",
        "filex_set_tags",
        "filex_wait_extract_ready",
    ]
    assert [tool["name"] for tool in tools].index("filex_ding_query") < [
        tool["name"] for tool in tools
    ].index("filex_search_kb")
    ding_query_tool = next(tool for tool in tools if tool["name"] == "filex_ding_query")
    assert ding_query_tool["inputSchema"]["required"] == ["query", "thread_id", "workspace_id"]
    assert ding_query_tool["inputSchema"]["properties"]["finalize"]["default"] is True
    compare_tool = next(tool for tool in tools if tool["name"] == "filex_ding_cross_compare")
    assert compare_tool["inputSchema"]["required"] == ["entity_a", "entity_b", "workspace_id"]
    assert "workspace_id" in compare_tool["inputSchema"]["properties"]
    folders_tool = next(tool for tool in tools if tool["name"] == "filex_list_folders")
    assert folders_tool["inputSchema"]["required"] == ["workspace_id"]
    search_tool = next(tool for tool in tools if tool["name"] == "filex_search_kb")
    assert search_tool["description"] == (
        "Low-level raw retrieval for single-entity or non-relational queries. Multi-entity relation queries (e.g., person A and person B) are rejected — use filex_ding_query instead."
    )
    md_tool = next(tool for tool in tools if tool["name"] == "filex_get_md_content")
    assert "Exactly one" in md_tool["description"]
    assert set(md_tool["inputSchema"]["properties"]) == {"md5_hash", "file_id"}
    assert md_tool["inputSchema"]["oneOf"] == [
        {"required": ["md5_hash"], "not": {"required": ["file_id"]}},
        {"required": ["file_id"], "not": {"required": ["md5_hash"]}},
    ]


def test_mcp_cross_compare_requires_workspace_id():
    from filex_mcp_server.server import FileXMCPServer

    with pytest.raises(ValueError, match="workspace_id"):
        FileXMCPServer("https://ding.example", "fb_key")._call_tool(
            "filex_ding_cross_compare", {"entity_a": "A", "entity_b": "B"}
        )


def test_mcp_cross_compare_passes_caller_context_and_keeps_acl_failure_safe(monkeypatch):
    from filex_mcp_server.server import FileXMCPServer
    from filex_langgraph_tools import AuthenticatedRequestContext, AuthenticatedTransport

    context = AuthenticatedRequestContext(
        AuthenticatedTransport("https://ding.example", "fb_key"), 7, (7,), 42
    )
    seen = {}
    monkeypatch.setattr(
        "filex_langgraph_tools.resolve_authenticated_request_context",
        lambda **kwargs: context,
    )

    def compare(entities, *, request_context):
        seen["context"] = request_context
        return {
            "cross_verified": False,
            "missing_verification": "ACL_BLOCKED",
            "coverage_receipt": {
                "version": "2.0",
                "answerable": False,
                "dimensions": [{"id": "relation", "status": "blocked"}],
            },
        }

    monkeypatch.setattr("filex_langgraph_intent_router._cross_compare_entities", compare)
    payload = FileXMCPServer("https://ding.example", "fb_key")._call_tool(
        "filex_ding_cross_compare",
        {"entity_a": "A", "entity_b": "B", "workspace_id": 7},
    )
    assert seen["context"] is context
    assert payload["missing_verification"] == "ACL_BLOCKED"
    assert payload["coverage_receipt"]["dimensions"][0]["status"] == "not_covered"
    assert "file_id" not in payload


@pytest.mark.parametrize("case", ["legal", "no_hit", "truncated", "acl_search", "acl_get_md"])
def test_mcp_cross_compare_real_compare_fixtures(monkeypatch, case):
    from filex_mcp_server.server import FileXMCPServer
    from filex_langgraph_tools import AuthenticatedRequestContext, AuthenticatedTransport

    context = AuthenticatedRequestContext(
        AuthenticatedTransport("https://ding.example", "fb_key"), 7, (7,), 42
    )
    monkeypatch.setattr("filex_langgraph_tools.resolve_authenticated_request_context", lambda **_: context)

    if case.startswith("acl_"):
        calls = []
        class ForbiddenClient:
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def post(self, *args, **kwargs):
                return httpx.Response(403, request=httpx.Request("POST", "http://filex.test"))
            def get(self, *args, **kwargs):
                calls.append("get")
                return httpx.Response(403, request=httpx.Request("GET", "http://filex.test"))
        monkeypatch.setattr("filex_langgraph_tools.httpx.Client", lambda **kw: ForbiddenClient())

    def search(query, **kwargs):
        assert kwargs["request_context"] is context
        if case == "acl_get_md":
            return {"items": [{"file_id": 1}]}
        if case == "no_hit":
            return {"items": []}
        count = 4 if case == "truncated" else 1
        return {"items": [{"file_id": i} for i in range(1, count + 1)]}

    def get_md(file_id, **kwargs):
        assert kwargs["request_context"] is context
        return "实体A在ABC公司任职。\n\n实体B也在ABC公司任职。"

    if case == "acl_get_md":
        monkeypatch.setattr("filex_langgraph_intent_router.search_tool", search)
    elif not case.startswith("acl_"):
        monkeypatch.setattr("filex_langgraph_intent_router.search_tool", search)
        monkeypatch.setattr("filex_langgraph_intent_router.get_md_tool", get_md)
    payload = FileXMCPServer("https://ding.example", "fb_key")._call_tool(
        "filex_ding_cross_compare",
        {"entity_a": "A", "entity_b": "B", "workspace_id": 7},
    )
    assert payload["cross_verified"] is (case == "legal")
    assert payload["coverage_receipt"]["version"] == "v1"
    assert payload["coverage_receipt"]["dimensions"][0]["status"] == ("covered" if case == "legal" else "not_covered")
    if case.startswith("acl_"):
        assert payload["missing_verification"] == "ACL_BLOCKED"
        assert not {"entity_files", "entity_sections", "cross_points"}.intersection(payload)
    if case == "acl_get_md":
        assert "get" in calls
    assert "file_id" not in payload["coverage_receipt"]


def test_mcp_initialize_returns_protocol_and_capabilities():
    from filex_mcp_server.server import FileXMCPServer

    server = FileXMCPServer(origin="https://ding.example", api_key="fb_key")

    response = server.handle_request({"jsonrpc": "2.0", "id": 4, "method": "initialize"})

    result = response["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["capabilities"] == {"tools": {}}
    assert result["serverInfo"]["name"] == "filex-mcp-server"
    assert "filex_ding_query" in result["instructions"][:512]
    assert "filex_search_kb" in result["instructions"][:512]


def test_ding_query_calls_installed_router_cli(monkeypatch, tmp_path):
    from filex_mcp_server.server import FileXMCPServer

    agent_dir = tmp_path / "ding" / "agent"
    cli = agent_dir / "filex_ding_router_cli.py"
    cli.parent.mkdir(parents=True)
    cli.write_text("# fixture\n", encoding="utf-8")
    calls = []
    monkeypatch.setenv("FILEX_DING_AGENT_DIR", str(agent_dir))
    monkeypatch.setattr(
        "filex_mcp_server.server.subprocess.run",
        lambda argv, **kw: calls.append(argv)
        or subprocess.CompletedProcess(
            argv, 0, stdout='{"kind":"kb_answer","answer":"ok","coverage_receipt":{"version":"v1","answerable":true,"selected_file_ids":[1]}}\n', stderr=""
        ),
    )

    payload = FileXMCPServer("https://ding.example", "fb_key")._call_tool(
        "filex_ding_query", {"query": "查资料", "thread_id": "t-1", "workspace_id": 1, "finalize": True}
    )

    assert payload == {
        "kind": "kb_answer",
        "answer": "ok",
        "coverage_receipt": {"version": "v1", "answerable": True, "selected_file_ids": [1]},
    }
    assert calls[0][0] == sys.executable
    assert calls[0][1] == str(cli)
    assert calls[0][2:] == ["--thread-id=t-1", "--workspace-id=1", "--finalize", "--", "查资料"]


def test_mcp_ding_query_blocks_unverified_cross_entity_answer(monkeypatch, tmp_path):
    from filex_mcp_server.server import FileXMCPServer

    agent_dir = tmp_path / "ding" / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "filex_ding_router_cli.py").write_text("# fixture\n", encoding="utf-8")
    monkeypatch.setenv("FILEX_DING_AGENT_DIR", str(agent_dir))
    monkeypatch.setattr(
        "filex_mcp_server.server.subprocess.run",
        lambda argv, **kw: subprocess.CompletedProcess(
            argv, 0, stdout='{"kind":"kb_answer","kb_answer":"他们是同事","cross_verified":false,"missing_verification":"未找到共同任职证据","coverage_receipt":{"version":"v1","answerable":false,"selected_file_ids":[1,2]}}\n', stderr=""
        ),
    )

    payload = FileXMCPServer("https://ding.example", "fb_key")._call_tool(
        "filex_ding_query", {"query": "A 和 B 是同事吗", "thread_id": "t-1", "workspace_id": 1}
    )

    assert payload["kind"] == "insufficient_evidence"
    assert "证据不足，无法确认" in payload["kb_answer"]
    assert "他们是同事" not in payload["kb_answer"]
    assert payload["coverage_receipt"]["version"] == "v1"
    assert payload["coverage_receipt"]["answerable"] is False
    assert payload["coverage_receipt"]["selected_file_ids"] == [1, 2]
    assert payload["coverage_receipt"]["compatibility"]["lossy_projection"] is True


@pytest.mark.parametrize("query", ["-diagnose", "--help"])
@pytest.mark.parametrize("finalize", [True, False])
def test_mcp_ding_query_matches_real_cli_for_option_like_query(monkeypatch, tmp_path, query, finalize):
    from filex_mcp_server.server import FileXMCPServer

    agent_dir = tmp_path / "ding" / "agent"
    agent_dir.mkdir(parents=True)
    shutil.copyfile(
        ROOT.parents[1] / "skill" / "ding" / "agent" / "filex_ding_router_cli.py",
        agent_dir / "filex_ding_router_cli.py",
    )
    (agent_dir / "filex_ding_auto_update.py").write_text(
        "class UpdateError(Exception):\n    pass\n\n\ndef ensure_ding_updated():\n    return None\n",
        encoding="utf-8",
    )
    (agent_dir / "filex_langgraph_intent_router.py").write_text(
        "class RouterResult:\n"
        "    def __init__(self, query, thread_id, finalize):\n"
        "        self.query = query\n"
        "        self.thread_id = thread_id\n"
        "        self.finalize = finalize\n\n"
        "    def to_dict(self):\n"
        "        return {\n"
        "            'kind': 'kb_answer',\n"
        "            'answer': self.query,\n"
        "            'message': self.thread_id,\n"
        "            'view_url': '/fixture',\n"
        "            'gaps': ['fixture-gap'],\n"
        "            'confidence': 0.9,\n"
        "            'finalize': self.finalize,\n"
        "        }\n\n"
        "def run_ding_router(query, *, thread_id, finalize):\n"
        "    return RouterResult(query, thread_id, finalize)\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FILEX_DING_AGENT_DIR", str(agent_dir))
    cli = agent_dir / "filex_ding_router_cli.py"
    cli_result = subprocess.run(
        [
            sys.executable,
            str(cli),
            "--thread-id=t-145",
            "--finalize" if finalize else "--no-finalize",
            "--",
            query,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    mcp_response = FileXMCPServer("https://ding.example", "fb_key").handle_request(
        {
            "jsonrpc": "2.0",
            "id": 147,
            "method": "tools/call",
            "params": {
                "name": "filex_ding_query",
                "arguments": {"query": query, "thread_id": "t-145", "workspace_id": 1, "finalize": finalize},
            },
        }
    )

    cli_payload = json.loads(cli_result.stdout)
    mcp_payload = json.loads(mcp_response["result"]["content"][0]["text"])
    contract_keys = ("kind", "answer", "message", "view_url", "gaps", "confidence")
    assert {key: mcp_payload.get(key) for key in contract_keys} == {
        key: cli_payload.get(key) for key in contract_keys
    }
    assert mcp_payload["finalize"] is finalize


def test_readme_codex_configuration_uses_cli_or_toml_not_legacy_mcp_json():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "Codex `mcp.json`" not in readme
    assert "~/.codex/mcp.json" not in readme
    assert "codex mcp add" in readme
    assert "[mcp_servers.filex]" in readme


@pytest.mark.parametrize("arguments", [{}, {"query": "", "thread_id": "t-1"}, {"query": "q"}, {"query": "q", "thread_id": ""}])
def test_mcp_ding_query_requires_non_empty_query_and_thread_id(arguments):
    from filex_mcp_server.server import FileXMCPServer

    response = FileXMCPServer("https://ding.example", "fb_key").handle_request(
        {
            "jsonrpc": "2.0",
            "id": 145,
            "method": "tools/call",
            "params": {"name": "filex_ding_query", "arguments": {**arguments, "workspace_id": 1}},
        }
    )

    assert response["error"]["code"] == -32602
    assert response["error"]["message"] in {"query is required", "thread_id is required"}


@pytest.mark.parametrize(
    "runner",
    [
        lambda argv, **kw: subprocess.CompletedProcess(argv, 2, stdout="", stderr="fb_secret_1234"),
        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, stdout="not-json", stderr=""),
        lambda argv, **kw: (_ for _ in ()).throw(subprocess.TimeoutExpired(argv, 180)),
    ],
)
def test_mcp_ding_query_runner_failures_return_safe_mcp_error(monkeypatch, tmp_path, runner):
    from filex_mcp_server.server import FileXMCPServer

    agent_dir = tmp_path / "ding" / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "filex_ding_router_cli.py").write_text("# fixture\n", encoding="utf-8")
    monkeypatch.setenv("FILEX_DING_AGENT_DIR", str(agent_dir))
    monkeypatch.setattr("filex_mcp_server.server.subprocess.run", runner)

    response = FileXMCPServer("https://ding.example", "fb_key").handle_request(
        {
            "jsonrpc": "2.0",
            "id": 146,
            "method": "tools/call",
            "params": {"name": "filex_ding_query", "arguments": {"query": "q", "thread_id": "t-1", "workspace_id": 1}},
        }
    )

    assert response["error"]["code"] == -32000
    assert response["error"]["message"] == "Ding router request failed"
    assert "fb_secret_1234" not in response["error"]["message"]


def test_mcp_call_api_key_status_returns_json_text():
    from filex_mcp_server.server import FileXMCPServer

    opener = FakeOpener({"valid": True, "reason": None, "username": "alice"})
    server = FileXMCPServer(
        origin="https://ding.example",
        api_key="fb_key",
        opener=opener,
    )

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "filex_api_key_status", "arguments": {}},
        }
    )

    content = response["result"]["content"]
    assert content[0]["type"] == "text"
    assert json.loads(content[0]["text"])["username"] == "alice"


def test_client_read_only_tools_build_expected_http_requests():
    from filex_mcp_server.client import FileXClient

    opener = QueueOpener(
        [
            [{"id": 1, "name": "个人空间"}],
            [{"id": 9, "name": "论文", "parent_id": None}],
            {"items": [{"file_id": 42, "content": "hit"}]},
            b"# Markdown by md5",
            b"# Markdown by file id",
        ]
    )
    client = FileXClient(
        origin="https://ding.example/",
        api_key="fb_secret_key_1234",
        opener=opener,
    )

    assert client.list_workspaces()[0]["id"] == 1
    assert client.list_folders(workspace_id=3)[0]["name"] == "论文"
    assert client.search_kb(
        query="显微镜",
        top_k=5,
        workspace_id=3,
        cross_workspace=False,
        extra={"group_by_file": True},
    )["items"][0]["file_id"] == 42
    assert client.get_md_content(md5_hash="abc123") == "# Markdown by md5"
    assert client.get_md_content(file_id=42) == "# Markdown by file id"

    requests = [request for request, _timeout in opener.requests]
    assert requests[0].full_url == "https://ding.example/api/workspaces"
    assert requests[1].full_url == "https://ding.example/api/folders?workspace_id=3"
    assert requests[2].full_url == (
        "https://ding.example/api/knowledge-base/search?workspace_id=3&cross_workspace=false"
    )
    assert requests[2].get_method() == "POST"
    assert json.loads(requests[2].data.decode("utf-8")) == {
        "query": "显微镜",
        "top_k": 5,
        "group_by_file": True,
    }
    assert requests[3].full_url == "https://ding.example/api/external/md-content/abc123"
    assert requests[4].full_url == "https://ding.example/api/files/42/md"


def test_get_md_content_requires_exactly_one_identifier():
    from filex_mcp_server.client import FileXClient

    client = FileXClient(origin="https://ding.example", api_key="fb_key", opener=FakeOpener({}))

    with pytest.raises(ValueError, match="md5_hash or file_id"):
        client.get_md_content()
    with pytest.raises(ValueError, match="only one"):
        client.get_md_content(md5_hash="abc", file_id=1)


def test_mcp_call_read_only_tools_return_expected_content():
    from filex_mcp_server.server import FileXMCPServer

    opener = QueueOpener(
        [
            [{"id": 1, "name": "个人空间"}],
            [{"id": 9, "name": "论文", "parent_id": None}],
            {"items": [{"file_id": 42, "content": "hit"}]},
            b"# Markdown by file id",
        ]
    )
    server = FileXMCPServer(
        origin="https://ding.example",
        api_key="fb_key",
        opener=opener,
    )

    calls = [
        {"name": "filex_list_workspaces", "arguments": {}},
        {"name": "filex_list_folders", "arguments": {"workspace_id": 1}},
        {"name": "filex_search_kb", "arguments": {"query": "显微镜", "top_k": 5}},
        {"name": "filex_get_md_content", "arguments": {"file_id": 42}},
    ]
    responses = [
        server.handle_request({"jsonrpc": "2.0", "id": idx, "method": "tools/call", "params": call})
        for idx, call in enumerate(calls, start=10)
    ]

    assert json.loads(responses[0]["result"]["content"][0]["text"])[0]["name"] == "个人空间"
    assert json.loads(responses[1]["result"]["content"][0]["text"])[0]["id"] == 9
    assert json.loads(responses[2]["result"]["content"][0]["text"])["items"][0]["file_id"] == 42
    assert responses[3]["result"]["content"][0]["text"] == "# Markdown by file id"


def test_mcp_folders_requires_workspace_id_and_search_requires_query():
    from filex_mcp_server.server import FileXMCPServer

    server = FileXMCPServer(origin="https://ding.example", api_key="fb_key", opener=FakeOpener({}))

    folders = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 20,
            "method": "tools/call",
            "params": {"name": "filex_list_folders", "arguments": {}},
        }
    )
    search = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 21,
            "method": "tools/call",
            "params": {"name": "filex_search_kb", "arguments": {}},
        }
    )

    assert folders["error"]["code"] == -32602
    assert "workspace_id" in folders["error"]["message"]
    assert search["error"]["code"] == -32602
    assert "query" in search["error"]["message"]


def test_mcp_folder_workspace_id_type_error_is_agent_friendly():
    from filex_mcp_server.server import FileXMCPServer

    server = FileXMCPServer(origin="https://ding.example", api_key="fb_key", opener=FakeOpener({}))

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 22,
            "method": "tools/call",
            "params": {"name": "filex_list_folders", "arguments": {"workspace_id": "abc"}},
        }
    )

    assert response["error"]["code"] == -32602
    assert response["error"]["message"] == "filex_list_folders workspace_id must be an integer"
    assert "invalid literal" not in response["error"]["message"]


def test_client_json_return_annotations_are_explicit():
    from typing import Any, get_type_hints

    from filex_mcp_server.client import FileXClient

    assert get_type_hints(FileXClient._request_json)["return"] is not Any
    assert get_type_hints(FileXClient.list_workspaces)["return"] is not Any
    assert get_type_hints(FileXClient.list_folders)["return"] is not Any
    assert get_type_hints(FileXClient.search_kb)["return"] is not Any


def test_run_stdio_reads_jsonrpc_lines_and_writes_ordered_responses(monkeypatch):
    from filex_mcp_server.server import run_stdio

    monkeypatch.setenv("FILEX_ORIGIN", "https://ding.example")
    monkeypatch.setenv("FILEX_API_KEY", "fb_key")
    stdin = StringIO(
        "\n".join(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
                json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            ]
        )
        + "\n"
    )
    stdout = StringIO()

    run_stdio(input_stream=stdin, output_stream=stdout)

    lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert [line["id"] for line in lines] == [1, 2]
    assert lines[0]["result"]["serverInfo"]["name"] == "filex-mcp-server"
    assert lines[1]["result"]["tools"][0]["name"] == "filex_api_key_status"


def test_non_filex_api_key_prefix_logs_warning(caplog):
    from filex_mcp_server.client import FileXClient

    FileXClient(origin="https://ding.example", api_key="jwt_like_token")

    assert "fb_ prefix" in caplog.text


# --- Task 3 tests ---

def test_upload_file_sends_multipart_with_file_and_optional_fields():
    import os
    import tempfile

    from filex_mcp_server.client import FileXClient

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        f.write("hello filex")
        tmp_path = f.name

    try:
        opener = CapturingOpener({"id": 42, "md5_hash": "abc", "extract_status": "pending"})
        client = FileXClient(
            origin="https://ding.example",
            api_key="fb_key",
            opener=opener,
        )

        result = client.upload_file(file_path=tmp_path, workspace_id=1, folder_id=9)

        assert result["id"] == 42
        assert result["extract_status"] == "pending"

        req = opener.requests[0]
        assert req["method"] == "POST"
        assert req["full_url"] == "https://ding.example/api/external/files"
        assert req["headers"]["Authorization"] == "Bearer fb_key"
        assert "multipart/form-data" in req["headers"].get("Content-type", req["headers"].get("Content-Type", ""))
        assert b'name="file"' in req["body"]
        assert b"hello filex" in req["body"]
        assert b'name="workspace_id"' in req["body"]
        assert b'name="folder_id"' in req["body"]
    finally:
        os.unlink(tmp_path)


def test_upload_file_missing_file_raises_value_error():
    from filex_mcp_server.client import FileXClient

    client = FileXClient(origin="https://ding.example", api_key="fb_key", opener=FakeOpener({}))

    with pytest.raises(ValueError, match="File not found"):
        client.upload_file(file_path="/nonexistent/file.pdf")


def test_set_tags_sends_put_with_tags_body():
    from filex_mcp_server.client import FileXClient

    opener = CapturingOpener({"file_id": 42, "tags": ["ai", "论文"]})
    client = FileXClient(origin="https://ding.example", api_key="fb_key", opener=opener)

    result = client.set_tags(file_id=42, tags=["ai", "论文"])

    assert result["tags"] == ["ai", "论文"]
    req = opener.requests[0]
    assert req["method"] == "PUT"
    assert req["full_url"] == "https://ding.example/api/external/files/42/tags"
    assert json.loads(req["body"]) == {"tags": ["ai", "论文"]}


def test_wait_extract_ready_polls_until_ready():
    from filex_mcp_server.client import FileXClient

    responses = [
        {"id": 42, "extract_status": "pending"},
        {"id": 42, "extract_status": "extracting"},
        {"id": 42, "extract_status": "ready", "has_md": True},
    ]
    opener = QueueOpener(responses)
    client = FileXClient(origin="https://ding.example", api_key="fb_key", opener=opener)

    result = client.wait_extract_ready(file_id=42, poll_interval=0.01)

    assert result["extract_status"] == "ready"
    assert result["has_md"] is True
    assert len(opener.requests) == 3


def test_wait_extract_ready_not_needed_is_immediate_success():
    from filex_mcp_server.client import FileXClient

    opener = FakeOpener({"id": 42, "extract_status": "not_needed"})
    client = FileXClient(origin="https://ding.example", api_key="fb_key", opener=opener)

    result = client.wait_extract_ready(file_id=42, poll_interval=0.01)

    assert result["extract_status"] == "not_needed"
    assert len(opener.requests) == 1


def test_wait_extract_ready_failed_raises():
    from filex_mcp_server.client import FileXClient, FileXHTTPError

    opener = FakeOpener({"id": 42, "extract_status": "failed"})
    client = FileXClient(origin="https://ding.example", api_key="fb_key", opener=opener)

    with pytest.raises(FileXHTTPError, match="failed"):
        client.wait_extract_ready(file_id=42, poll_interval=0.01)


def test_wait_extract_ready_timeout_raises():
    from filex_mcp_server.client import FileXClient, FileXHTTPError

    opener = FakeOpener({"id": 42, "extract_status": "extracting"})
    client = FileXClient(origin="https://ding.example", api_key="fb_key", opener=opener)

    with pytest.raises(FileXHTTPError, match="Timed out"):
        client.wait_extract_ready(file_id=42, poll_interval=0.01, max_wait=0.02)


def test_mcp_call_upload_file_validates_file_path_required():
    from filex_mcp_server.server import FileXMCPServer

    server = FileXMCPServer(origin="https://ding.example", api_key="fb_key", opener=FakeOpener({}))

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 30,
            "method": "tools/call",
            "params": {"name": "filex_upload_file", "arguments": {}},
        }
    )

    assert response["error"]["code"] == -32602
    assert "file_path" in response["error"]["message"]


def test_mcp_call_set_tags_rejects_invalid_inputs():
    from filex_mcp_server.server import FileXMCPServer

    server = FileXMCPServer(origin="https://ding.example", api_key="fb_key", opener=FakeOpener({}))

    for bad in [{}, {"file_id": 1}, {"file_id": 1, "tags": []}, {"file_id": 1, "tags": "not-a-list"}]:
        response = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 31,
                "method": "tools/call",
                "params": {"name": "filex_set_tags", "arguments": bad},
            }
        )
        assert response["error"]["code"] == -32602, f"should reject {bad}"


def test_mcp_call_wait_extract_requires_file_id():
    from filex_mcp_server.server import FileXMCPServer

    server = FileXMCPServer(origin="https://ding.example", api_key="fb_key", opener=FakeOpener({}))

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 32,
            "method": "tools/call",
            "params": {"name": "filex_wait_extract_ready", "arguments": {}},
        }
    )

    assert response["error"]["code"] == -32602
    assert "file_id" in response["error"]["message"]


def test_mcp_set_tags_non_integer_file_id_is_agent_friendly():
    from filex_mcp_server.server import FileXMCPServer

    server = FileXMCPServer(origin="https://ding.example", api_key="fb_key", opener=FakeOpener({}))

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 50,
            "method": "tools/call",
            "params": {"name": "filex_set_tags", "arguments": {"file_id": "abc", "tags": ["x"]}},
        }
    )

    assert response["error"]["code"] == -32602
    assert response["error"]["message"] == "filex_set_tags file_id must be an integer"
    assert "invalid literal" not in response["error"]["message"]


def test_mcp_call_task3_tools_end_to_end():
    import os
    import tempfile

    from filex_mcp_server.server import FileXMCPServer

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        f.write("e2e test")
        tmp_path = f.name

    try:
        opener = QueueOpener(
            [
                {"id": 99, "md5_hash": "e2e", "extract_status": "pending"},
                {"id": 99, "tags": ["e2e", "test"]},
                {"id": 99, "extract_status": "ready"},
            ]
        )
        server = FileXMCPServer(origin="https://ding.example", api_key="fb_key", opener=opener)

        upload_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 40,
                "method": "tools/call",
                "params": {"name": "filex_upload_file", "arguments": {"file_path": tmp_path, "workspace_id": 1}},
            }
        )
        assert upload_resp["result"]["content"][0]["text"]
        upload_data = json.loads(upload_resp["result"]["content"][0]["text"])
        assert upload_data["id"] == 99
        assert upload_data["extract_status"] == "pending"

        tags_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 41,
                "method": "tools/call",
                "params": {"name": "filex_set_tags", "arguments": {"file_id": 99, "tags": ["e2e", "test"]}},
            }
        )
        tags_data = json.loads(tags_resp["result"]["content"][0]["text"])
        assert tags_data["tags"] == ["e2e", "test"]

        wait_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 42,
                "method": "tools/call",
                "params": {"name": "filex_wait_extract_ready", "arguments": {"file_id": 99}},
            }
        )
        wait_data = json.loads(wait_resp["result"]["content"][0]["text"])
        assert wait_data["extract_status"] == "ready"
    finally:
        os.unlink(tmp_path)


def test_upload_file_key_masking_on_http_error():
    import os
    import tempfile
    from io import BytesIO
    from urllib.error import HTTPError

    from filex_mcp_server.client import FileXClient, FileXHTTPError

    class ErrorOpener:
        def open(self, request, timeout=30):
            raise HTTPError(
                request.full_url,
                413,
                "Payload Too Large",
                hdrs=None,
                fp=BytesIO(json.dumps({"detail": "文件过大"}).encode("utf-8")),
            )

    client = FileXClient(origin="https://ding.example", api_key="fb_secret_9999", opener=ErrorOpener())

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as f:
        f.write("x")
        tmp_path = f.name
    try:
        with pytest.raises(FileXHTTPError) as exc:
            client.upload_file(file_path=tmp_path)
        assert "413" in str(exc.value)
        assert "文件过大" in str(exc.value)
        assert "fb_secret_9999" not in str(exc.value)
    finally:
        os.unlink(tmp_path)


def test_multipart_body_handles_non_ascii_filename():
    import os
    import tempfile

    from filex_mcp_server.client import _build_multipart_body

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"pdf content")
        tmp_path = f.name

    # Rename to a path with Chinese characters
    chinese_path = tmp_path + "测试报告.pdf"
    os.rename(tmp_path, chinese_path)

    try:
        body_bytes, boundary = _build_multipart_body(chinese_path, {"workspace_id": 1})
        assert b"pdf content" in body_bytes
        assert '测试报告.pdf'.encode('utf-8') in body_bytes
        assert b'name="workspace_id"' in body_bytes
    finally:
        os.unlink(chinese_path)


def test_mcp_set_tags_rejects_non_string_elements():
    from filex_mcp_server.server import FileXMCPServer

    server = FileXMCPServer(origin="https://ding.example", api_key="fb_key", opener=FakeOpener({}))

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 60,
            "method": "tools/call",
            "params": {"name": "filex_set_tags", "arguments": {"file_id": 1, "tags": ["ok", 123]}},
        }
    )

    assert response["error"]["code"] == -32602
    assert "tags must be a list of strings" in response["error"]["message"]


def test_mcp_wait_extract_description_mentions_polling():
    from filex_mcp_server.server import FileXMCPServer

    server = FileXMCPServer(origin="https://ding.example", api_key="fb_key")
    response = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tools = response["result"]["tools"]
    wait_tool = next(t for t in tools if t["name"] == "filex_wait_extract_ready")
    assert "polling" in wait_tool["description"].lower()


# --- 终审 Major 修复测试 ---

def test_mcp_get_md_content_rejects_non_string_md5_hash():
    from filex_mcp_server.server import FileXMCPServer

    server = FileXMCPServer(origin="https://ding.example", api_key="fb_key", opener=FakeOpener({}))

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 70,
            "method": "tools/call",
            "params": {"name": "filex_get_md_content", "arguments": {"md5_hash": 123}},
        }
    )

    assert response["error"]["code"] == -32602
    assert "md5_hash must be a string" in response["error"]["message"]


def test_mcp_search_kb_rejects_invalid_top_k():
    from filex_mcp_server.server import FileXMCPServer

    server = FileXMCPServer(origin="https://ding.example", api_key="fb_key", opener=FakeOpener({}))

    for bad_top_k in ["abc", 0, -1]:
        response = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 71,
                "method": "tools/call",
                "params": {"name": "filex_search_kb", "arguments": {"query": "x", "top_k": bad_top_k}},
            }
        )
        assert response["error"]["code"] == -32602, f"top_k={bad_top_k} should be rejected"
        assert "top_k must be a positive integer" in response["error"]["message"]


def test_mcp_wait_extract_rejects_non_positive_intervals():
    from filex_mcp_server.server import FileXMCPServer

    server = FileXMCPServer(origin="https://ding.example", api_key="fb_key", opener=FakeOpener({}))

    for bad in [{"poll_interval": 0}, {"max_wait": -1}, {"poll_interval": -0.5}]:
        response = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 72,
                "method": "tools/call",
                "params": {"name": "filex_wait_extract_ready", "arguments": {"file_id": 1, **bad}},
            }
        )
        assert response["error"]["code"] == -32602, f"{bad} should be rejected"
        assert "must be a positive number" in response["error"]["message"]
