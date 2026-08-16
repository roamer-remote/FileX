/** RAPTOR concept help (HTML for admin Ollama → RAPTOR sub-tab modal) */
export const RAPTOR_CONCEPT_HELP_HTML_EN = `
<header class="wlg-help-hero">
  <p class="wlg-help-hero-kicker">RAPTOR</p>
  <p class="wlg-help-hero-desc"><strong>Recursive Abstractive Processing for Tree-Organized Retrieval</strong></p>
  <p class="wlg-help-hero-desc">A hierarchical tree-indexed advanced RAG algorithm proposed by Stanford University in 2024.</p>
  <div class="wlg-help-hero-chips" aria-hidden="true">
    <span class="wlg-help-chip">Hierarchical summaries</span>
    <span class="wlg-help-chip">Tree retrieval</span>
    <span class="wlg-help-chip">Long-doc RAG</span>
  </div>
</header>

<section class="wlg-help-card wlg-help-card--sky">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">1</span>
    <h3 class="wlg-help-h">Problems with plain RAG</h3>
  </div>
  <div class="wlg-help-card-body wlg-help-card-body--stack">
    <p>Classic RAG uses fixed-size text chunks:</p>
    <ul class="wlg-help-list">
      <li><strong>Too small</strong>: loses global context; weak on synthesis questions</li>
      <li><strong>Too large</strong>: blurry embeddings; weaker precise fact retrieval</li>
    </ul>
    <p>RAPTOR keeps both <strong>fine-grained source text</strong> and <strong>coarse multi-level summaries</strong>.</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--mint">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">2</span>
    <h3 class="wlg-help-h">Core idea: bottom-up semantic tree</h3>
  </div>
  <div class="wlg-help-card-body wlg-help-card-body--stack">
    <ul class="wlg-help-list">
      <li><strong>Leaves</strong>: original small text chunks (detail)</li>
      <li><strong>Recursive cluster + summarize</strong>: group similar chunks; LLM summary becomes parent nodes</li>
      <li><strong>Iterate upward</strong>: merge and summarize until a root node (document-wide theme)</li>
    </ul>
    <p>One tree spans micro detail, mid-level section summaries, and macro document themes.</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--violet">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">3</span>
    <h3 class="wlg-help-h">Two retrieval modes</h3>
  </div>
  <div class="wlg-help-card-body wlg-help-card-body--stack">
    <p><strong>Tree traversal</strong></p>
    <p>Filter top-down from summary layers to details; good for very long docs and global questions.</p>
    <p><strong>Collapsed tree</strong></p>
    <p>Flatten all levels for unified vector search; recalls coarse and fine evidence at once; good for fact Q&amp;A.</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--amber">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">4</span>
    <h3 class="wlg-help-h">When to use</h3>
  </div>
  <div class="wlg-help-card-body">
    <ul class="wlg-help-list wlg-help-list--checks">
      <li>Long documents, books, multi-chapter knowledge bases</li>
      <li>Cross-section / cross-chapter reasoning questions</li>
      <li>Q&amp;A, summarization, long-text analysis RAG</li>
    </ul>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--slate">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">5</span>
    <h3 class="wlg-help-h">vs plain RAG</h3>
  </div>
  <div class="wlg-help-card-body wlg-help-card-body--stack">
    <p><strong>Plain RAG</strong>: single-layer chunks; source snippets only.</p>
    <p><strong>RAPTOR</strong>: multi-level tree index with source + summaries at each level; richer retrieval for long text.</p>
  </div>
</section>
`
