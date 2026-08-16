#!/usr/bin/env node
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
const ORIGIN = (process.env.FILEX_ORIGIN || "").replace(/\/$/, "");
const API_KEY = process.env.FILEX_API_KEY || "";
async function filexFetch(path, init = {}) {
  const headers = { Authorization: `Bearer ${API_KEY}`, ...(init.headers || {}) };
  const res = await fetch(`${ORIGIN}${path}`, { ...init, headers });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res;
}
const server = new Server({ name: "filex", version: "0.2.0" }, { capabilities: { tools: {} } });
server.setRequestHandler("tools/list", async () => ({
  tools: [
    { name: "kb_search", description: "POST /api/knowledge-base/search", inputSchema: { type: "object", properties: { query: { type: "string" }, top_k: { type: "number" }, citation_format: { type: "string" } }, required: ["query"] } },
    { name: "kb_list_files", description: "GET /api/files", inputSchema: { type: "object", properties: { workspace_id: { type: "number" } } } },
    { name: "kb_get_chunks", description: "GET chunks", inputSchema: { type: "object", properties: { file_id: { type: "number" } }, required: ["file_id"] } },
    { name: "kb_reindex", description: "POST reindex", inputSchema: { type: "object", properties: { file_id: { type: "number" } }, required: ["file_id"] } },
    { name: "kb_tags_put", description: "PUT tags", inputSchema: { type: "object", properties: { file_id: { type: "number" }, tags: { type: "array", items: { type: "string" } } }, required: ["file_id", "tags"] } },
  ],
}));
server.setRequestHandler("tools/call", async (req) => {
  const a = req.params.arguments || {};
  if (req.params.name === "kb_search") {
    const r = await filexFetch("/api/knowledge-base/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: a.query, top_k: a.top_k ?? 8, citation_format: a.citation_format ?? "markdown", group_by_file: true }) });
    return { content: [{ type: "text", text: JSON.stringify(await r.json(), null, 2) }] };
  }
  if (req.params.name === "kb_list_files") {
    const r = await filexFetch("/api/files");
    return { content: [{ type: "text", text: JSON.stringify(await r.json(), null, 2) }] };
  }
  if (req.params.name === "kb_get_chunks") {
    const r = await filexFetch(`/api/knowledge-base/files/${a.file_id}/chunks`);
    return { content: [{ type: "text", text: JSON.stringify(await r.json(), null, 2) }] };
  }
  if (req.params.name === "kb_reindex") {
    const r = await filexFetch(`/api/knowledge-base/files/${a.file_id}/reindex`, { method: "POST" });
    return { content: [{ type: "text", text: JSON.stringify(await r.json(), null, 2) }] };
  }
  if (req.params.name === "kb_tags_put") {
    const r = await filexFetch(`/api/files/${a.file_id}/tags`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tags: a.tags }) });
    return { content: [{ type: "text", text: JSON.stringify(await r.json(), null, 2) }] };
  }
  throw new Error("unknown tool");
});
await server.connect(new StdioServerTransport());
