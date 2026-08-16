# FileX MCP Server

Official MCP (Model Context Protocol) stdio adapter for FileX. Provides AI agents (Claude Desktop, Cursor, Codex, OpenAI Agents, LangGraph hosts) with structured tools that call the existing FileX HTTP API — no direct database access, no bypass of backend auth/ACL/license/audit.

## Prerequisites

- Python ≥ 3.10
- A running FileX instance with a valid API Key (`fb_` prefix)
- `FILEX_ORIGIN` — site root URL, no trailing slash (e.g. `https://ding.yyyou.top`)
- `FILEX_API_KEY` — full API Key string
- `FILEX_DING_AGENT_DIR` — installed `ding/agent` directory, required for the high-level
  `filex_ding_query` tool (contains `filex_ding_router_cli.py`)

## Quick Start

```bash
cd integrations/filex-mcp-server
pip install -e .

# Smoke-test: list tools (JSON-RPC on stdio)
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python -m filex_mcp_server
```

## Configuration

### Claude Desktop

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "filex": {
      "command": "python",
      "args": ["-m", "filex_mcp_server"],
      "env": {
        "FILEX_ORIGIN": "https://ding.yyyou.top",
        "FILEX_API_KEY": "fb_your_key_here",
        "FILEX_DING_AGENT_DIR": "/path/to/ding/agent",
        "PYTHONPATH": "/path/to/filex/integrations/filex-mcp-server/src"
      }
    }
  }
}
```

### Cursor

`.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "filex": {
      "command": "/path/to/.venv/bin/python",
      "args": ["-m", "filex_mcp_server"],
      "env": {
        "FILEX_ORIGIN": "https://ding.yyyou.top",
        "FILEX_API_KEY": "fb_your_key_here",
        "FILEX_DING_AGENT_DIR": "/path/to/ding/agent",
        "PYTHONPATH": "/path/to/filex/integrations/filex-mcp-server/src"
      }
    }
  }
}
```

### Codex (Codex CLI / Desktop)

Use the Codex CLI to add the stdio server; do not create a legacy `mcp.json` file:

```bash
codex mcp add filex \
  --env FILEX_ORIGIN=https://ding.yyyou.top \
  --env FILEX_API_KEY=fb_your_key_here \
  --env FILEX_DING_AGENT_DIR=/path/to/ding/agent \
  --env PYTHONPATH=/path/to/filex/integrations/filex-mcp-server/src \
  -- /path/to/.venv/bin/python -m filex_mcp_server
```

If the CLI is unavailable, add the following entry to Codex `config.toml` instead:

```toml
[mcp_servers.filex]
command = "/path/to/.venv/bin/python"
args = ["-m", "filex_mcp_server"]

[mcp_servers.filex.env]
FILEX_ORIGIN = "https://ding.yyyou.top"
FILEX_API_KEY = "fb_your_key_here"
FILEX_DING_AGENT_DIR = "/path/to/ding/agent"
PYTHONPATH = "/path/to/filex/integrations/filex-mcp-server/src"
```

### Generic (any MCP host)

```bash
FILEX_ORIGIN=https://ding.yyyou.top \
FILEX_API_KEY=fb_your_key_here \
FILEX_DING_AGENT_DIR=/path/to/ding/agent \
PYTHONPATH=/path/to/filex/integrations/filex-mcp-server/src \
python -m filex_mcp_server
```

The server speaks JSON-RPC 2.0 over stdio (protocol version `2024-11-05`).

## Tools

| Tool | HTTP API | Risk | Description |
|------|----------|------|-------------|
| `filex_api_key_status` | `GET /api/external/api-key-status` | Read | Probe Key, License, username |
| `filex_list_workspaces` | `GET /api/workspaces` | Read | List visible workspaces |
| `filex_list_folders` | `GET /api/folders?workspace_id=` | Read | List folder tree (workspace_id required) |
| `filex_ding_query` | Installed `filex_ding_router_cli.py` | Read | High-level `/ding` and FileX user-facing answer path; requires `query`, `thread_id`, optional `finalize=true` |
| `filex_search_kb` | `POST /api/knowledge-base/search` | Read | Low-level raw retrieval; do not use as `/ding` user-facing answer path |
| `filex_get_md_content` | `GET …/md-content/{md5}` or `GET /api/files/{id}/md` | Read | Read markdown note (md5_hash / file_id exactly one) |
| `filex_upload_file` | `POST /api/external/files` | Write | Upload file (multipart, suggested ≤ 100MB), optional workspace_id / folder_id |
| `filex_set_tags` | `PUT /api/external/files/{id}/tags` | Write | Merge tags (union, preserves existing tags) |
| `filex_wait_extract_ready` | Poll `GET /api/files/{id}` | Read | Wait for extract_status ready/not_needed (polling mode, 300s timeout) |

## Security

- Tools **never** return the full API Key in responses; logs mask the key.
- `filex_ding_query` invokes only the configured installed router CLI and returns its JSON
  `RouterResult`; process failures, timeouts, and malformed output become a generic MCP error.
- All calls go through `{FILEX_ORIGIN}/api/…` — no direct DB/Redis/RabbitMQ access.
- Workspace/folder/file visibility is server-side only (MCP layer does not infer ACLs).
- Upload and tag operations carry the API Key owner's identity for audit.

## Development

```bash
cd integrations/filex-mcp-server
pip install -e ".[dev]"

# Run tests
python -m pytest -q

# Run with verbose output
python -m pytest -v
```

### Architecture

```
Agent (MCP host)
    │ JSON-RPC 2.0 over stdio
    ▼
server.py (FileXMCPServer)
    │ tool dispatch + validation
    ▼
client.py (FileXClient)
    │ HTTP (urllib, zero external deps)
    ▼
FileX Backend ({FILEX_ORIGIN}/api/…)
```

- `client.py` — HTTP client, multipart upload, polling, error detail extraction, key masking
- `server.py` — JSON-RPC 2.0 handler, tool schemas, argument validation
- `tests/test_api_key_status.py` — contract tests covering all 8 tools

## Version

See `pyproject.toml` and `src/filex_mcp_server/__init__.py`. Bumped alongside the FileX skill version in `skill/ding/skill.version`.
