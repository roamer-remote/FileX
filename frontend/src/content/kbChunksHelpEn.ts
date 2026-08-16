/** Index chunks help body (HTML for help modal) */
export const KB_CHUNKS_HELP_HTML = `
<header class="wlg-help-hero">
  <p class="wlg-help-hero-kicker">Search index</p>
  <p class="wlg-help-hero-desc">After upload, materials are <strong>chunked and embedded</strong> for semantic search. Here you can browse and tune chunk text and boost keywords—<strong>without changing the material note</strong>.</p>
  <div class="wlg-help-hero-chips" aria-hidden="true">
    <span class="wlg-help-chip">Chunk list</span>
    <span class="wlg-help-chip">Manual override</span>
    <span class="wlg-help-chip">Trial search</span>
  </div>
</header>

<section class="wlg-help-card wlg-help-card--sky">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">1</span>
    <h3 class="wlg-help-h">Where to open</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>In file <strong>preview</strong>, switch to the <strong>Index chunks</strong> tab. The header shows index status, total chunks, embedding dimension, and model (e.g. <code>bge-m3:latest</code>).</p>
    <p class="wlg-help-note">The table appears when status is <code>ready</code>; otherwise try <strong>Re-index</strong> from the empty state or header.</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--mint">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">2</span>
    <h3 class="wlg-help-h">Column guide</h3>
  </div>
  <div class="wlg-help-card-body wlg-help-card-body--stack">
    <ul class="wlg-help-list">
      <li><strong>Chunk</strong>: sequence number, matches chunk IDs in search results.</li>
      <li><strong>Heading path</strong>: outline location in the material note (if any).</li>
      <li><strong>Block type</strong>: paragraph, heading, table, code, etc.</li>
      <li><strong>Content kind</strong>: figure, table, equation for multimodal chunks.</li>
      <li><strong>Metadata</strong>: page, asset id, and other structured hints.</li>
      <li><strong>Location</strong>: citation label in source or note.</li>
      <li><strong>Text</strong>: snippet used for FTS and embedding.</li>
      <li><strong>Boost keywords</strong>: comma-separated terms that boost retrieval.</li>
    </ul>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--violet">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">3</span>
    <h3 class="wlg-help-h">Click a row: view and edit</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>Click any row to open the drawer. If you are the file <strong>owner</strong> or an <strong>admin</strong>, you can edit text and boost keywords; saving updates FTS and re-embeds the vector.</p>
    <ul class="wlg-help-list wlg-help-list--checks">
      <li>Changes apply to the <strong>search index only</strong>, not the material note or original file</li>
      <li>Shared workspace readers can browse but not save</li>
      <li>Multimodal chunks (figure/table/equation) have read-only body; boost keywords remain editable</li>
    </ul>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--amber">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">↻</span>
    <h3 class="wlg-help-h">Re-index vs force rebuild</h3>
  </div>
  <div class="wlg-help-card-body">
    <p><strong>Re-index</strong>: rebuild from the current material note; manual chunk overrides are <strong>kept</strong>.</p>
    <p><strong>Force rebuild from note</strong>: clears all manual overrides and re-chunks from the note—<strong>irreversible</strong>.</p>
    <p class="wlg-help-note"><strong>Large materials</strong> (note length above the system threshold): list “Reindex” / force rebuild <strong>skips heavy post-processing</strong> (entity/SAG/RAPTOR) by default; time is mostly chunking + embedding (production file 340: ~22ms post). Admins may enable full post-processing for large docs <strong>for ops only</strong>—production runs can reach <strong>~50 minutes</strong> (340 job 1775) and depend on ollama summary reliability.</p>
    <p class="wlg-help-note">An “index differs from note” banner means manual intervention exists; use force rebuild when you need full alignment with the note.</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--sky">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">◎</span>
    <h3 class="wlg-help-h">Trial search</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>In the chunk drawer, <strong>Trial search</strong> opens Smart search with the chunk text so you can verify retrieval quickly.</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--rose">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">!</span>
    <h3 class="wlg-help-h">Good to know</h3>
  </div>
  <div class="wlg-help-card-body">
    <ul class="wlg-help-list">
      <li>To follow note changes: <strong>save the material note</strong> first, then re-index if needed.</li>
      <li>Boost keywords add weight; they do not replace body text (empty body cannot be saved).</li>
      <li>Chunk boundaries cannot be merged or split here—they come from the indexing pipeline.</li>
    </ul>
  </div>
</section>
`.trim()
