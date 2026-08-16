/** FileX system flows help */
export const SYSTEM_HELP_HTML = `
<header class="wlg-help-hero">
  <p class="wlg-help-hero-kicker">System flows</p>
  <p class="wlg-help-hero-desc">From <strong>Web upload</strong>, <strong>agent URL ingest</strong>, to <strong>Ding maintain</strong> on existing materials — how data moves across containers.</p>
  <div class="wlg-help-hero-chips" aria-hidden="true">
    <span class="wlg-help-chip">Web upload</span>
    <span class="wlg-help-chip">Agent ingest</span>
    <span class="wlg-help-chip">Docker topology</span>
    <span class="wlg-help-chip">Vector index</span>
  </div>
</header>

<section class="wlg-help-card wlg-help-card--slate">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">◎</span>
    <h3 class="wlg-help-h">Deployment topology</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>Typical production Compose stack (local dev may run API/indexer on the host).</p>
    <div class="wlg-help-topology" role="img" aria-label="FileX topology">
      <div class="wlg-help-topo-panel wlg-help-topo-panel--docker">
        <p class="wlg-help-topo-title">Docker containers</p>
        <div class="wlg-help-topo-grid">
          <span class="wlg-help-topo-chip">filex<em>API + static UI</em></span>
          <span class="wlg-help-topo-chip">filex-postgres<em>DB + pgvector</em></span>
          <span class="wlg-help-topo-chip">filex-rabbitmq<em>index / note-generation queues</em></span>
          <span class="wlg-help-topo-chip">filex-redis<em>Ding runtime</em></span>
          <span class="wlg-help-topo-chip">filex-kb-indexer<em>serial vector worker</em></span>
          <span class="wlg-help-topo-chip">filex-kb-post<em>post entity/SAG/RAPTOR</em></span>
          <span class="wlg-help-topo-chip">filex-kb-extract<em>PDF/Office → notes</em></span>
          <span class="wlg-help-topo-chip">filex-kb-rerank<em>search rerank only</em></span>
        </div>
      </div>
      <div class="wlg-help-topo-panel wlg-help-topo-panel--host">
        <p class="wlg-help-topo-title">Host (outside Docker)</p>
        <div class="wlg-help-topo-grid">
          <span class="wlg-help-topo-chip">Ollama :11434<em>bge-m3 embeddings</em></span>
        </div>
        <p class="wlg-help-topo-link"><code>kb-indexer</code> calls Ollama via <code>host.docker.internal</code>. Embeddings are <strong>not</strong> built in the rerank container.</p>
      </div>
    </div>
    <p class="wlg-help-note">Sidebar queue &amp; index columns update via WebSocket (<code>/api/ws/mq-status</code>, <code>/api/ws/kb-index</code>).</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--sky">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">1</span>
    <h3 class="wlg-help-h">After Web upload</h3>
  </div>
  <div class="wlg-help-card-body">
    <p><code>POST /api/files/upload</code> (JWT, optional <code>workspace_id</code> / <code>folder_id</code>).</p>
    <div class="wlg-help-flow" aria-label="Web upload flow">
      <div class="wlg-help-flow-row">
        <div class="wlg-help-flow-node wlg-help-flow-node--user">Web upload</div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--svc">filex<small>MD5 dedup</small></div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--store">uploads volume</div>
      </div>
      <div class="wlg-help-flow-arrow-v">↓ types that generate notes</div>
      <div class="wlg-help-flow-row">
        <div class="wlg-help-flow-node wlg-help-flow-node--queue">note-generation queue</div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--worker">kb-extract</div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--store">{ws}/okf</div>
      </div>
      <div class="wlg-help-flow-arrow-v">↓</div>
      <div class="wlg-help-flow-row">
        <div class="wlg-help-flow-node wlg-help-flow-node--queue">index queue</div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--worker">kb-indexer</div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--host">Ollama</div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--store">pgvector</div>
      </div>
    </div>
    <ul class="wlg-help-list">
      <li>New uploads store OKF Concept notes under <code>uploads/{workspace_id}/okf/sources/…/*.md</code> (aligned with OKF bundle paths); legacy materials may still use read-only <code>.md_notes/{id}.md</code>.</li>
      <li>Web upload does not auto LLM-polish notes; note generation uses OCR / MarkItDown only.</li>
      <li>Editing a material note in preview re-enqueues indexing.</li>
    </ul>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--mint">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">2</span>
    <h3 class="wlg-help-h">Agent with an external URL</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>Ding agent uses <code>fb_</code> API Key → <code>filex_ingest_url.py --capture-only</code> → read &amp; name → specialist copy processing + professional review &amp; revision (prepare / merge / finalize) → <code>POST /api/external/files</code> + tags → index pipeline.</p>
    <p class="wlg-help-note">Third-party URLs do not need <code>X-FileX-Share-Token</code>. Agent may attach Markdown via <code>files-with-md</code>.</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--violet">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">3</span>
    <h3 class="wlg-help-h">FileX link → agent maintain</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>Share re-ingest: download with token → <code>POST /api/external/files</code> + header <code>X-FileX-Share-Token</code> (same owner + MD5).</p>
    <p>In-library maintain: <code>files-awaiting-ai</code> → wait for notes → read/polish → <code>PUT …/md</code> + tags → auto reindex. Rebuild-all-index does <strong>not</strong> change note text.</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--slate">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">◎</span>
    <h3 class="wlg-help-h">Materials library index</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>Use the top nav <strong>KB INDEX</strong> link, or the same label on the lobby floating toolbar, to open <code>/knowledge-base</code>.</p>
    <p>Tab: <strong>Preview</strong> (catalog / wiki pages / linked info; toolbar includes rebuild index). Your last selected tab is saved to your account and restored after login on another device.</p>
  </div>
</section>
`.trim()
