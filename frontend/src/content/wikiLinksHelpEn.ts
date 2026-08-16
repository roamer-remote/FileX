/** File relations help body (HTML for help modal) */
export const WIKI_LINKS_HELP_HTML = `
<header class="wlg-help-hero">
  <p class="wlg-help-hero-kicker">Quick start</p>
  <p class="wlg-help-hero-desc">Write <strong>double-bracket links</strong> in material notes → save → see connections on File relations, click through in preview.</p>
  <div class="wlg-help-hero-chips" aria-hidden="true">
    <span class="wlg-help-chip">Material note</span>
    <span class="wlg-help-chip">Link graph</span>
    <span class="wlg-help-chip">Backlinks</span>
  </div>
</header>

<section class="wlg-help-card wlg-help-card--sky">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">1</span>
    <h3 class="wlg-help-h">What is this?</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>The file relations graph shows references you write in material notes—<em>this file points to that file</em>.</p>
    <div class="wlg-help-visual-hint" aria-hidden="true">
      <span class="wlg-help-node"></span>
      <span class="wlg-help-edge"></span>
      <span class="wlg-help-node wlg-help-node--dim"></span>
      <span class="wlg-help-legend">Dots = files with notes · Lines = links in notes</span>
    </div>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--mint">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">2</span>
    <h3 class="wlg-help-h">Where do I write links?</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>Open file <strong>preview</strong> → edit the <strong>material note</strong> → write links in the body → <strong>save</strong>.</p>
    <p class="wlg-help-note">Text inside code blocks is not parsed as a link.</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--violet">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">3</span>
    <h3 class="wlg-help-h">How do I write a link?</h3>
  </div>
  <div class="wlg-help-card-body wlg-help-card-body--stack">
    <div class="wlg-help-subcard wlg-help-subcard--file">
      <h4 class="wlg-help-sub-h"><span class="wlg-help-sub-badge">File</span>Link to another file</h4>
      <p>Find each file’s numeric <strong>ID</strong> in the list. You can write:</p>
      <ul class="wlg-help-list">
        <li>Brackets with the ID only, e.g. <code>[[88]]</code></li>
        <li>Or <code>file:</code> plus ID, e.g. <code>[[file:128]]</code></li>
      </ul>
      <div class="wlg-help-example" role="note" aria-label="Note writing example">
        <span class="wlg-help-example-tag">Example</span>
        <p class="wlg-help-example-heading">## Related</p>
        <p class="wlg-help-snippet"><code>[[file:128]]</code></p>
        <p class="wlg-help-snippet"><code>[[Earlier review|88]]</code></p>
      </div>
    </div>
    <div class="wlg-help-subcard wlg-help-subcard--wiki">
      <h4 class="wlg-help-sub-h"><span class="wlg-help-sub-badge">Topic</span>Link to another topic page</h4>
      <p>Topics can have their own page with a hyphenated name like <code>crispr-gene-editing</code>.</p>
      <p>Write <code>[[wiki:name]]</code>. Broken until the topic exists; saved notes reconnect automatically. The graph shows a <strong>dotted</strong> line to a <strong>diamond</strong> topic node.</p>
      <p class="wlg-help-note"><strong>Pending compile</strong>: when at least two notes link the same topic without a topic page, see the badge on <strong>File relations</strong> and ask Ding to compile the page (FileX does not auto-generate LLM content).</p>
      <div class="wlg-help-example" role="note" aria-label="Note writing example">
        <span class="wlg-help-example-tag">Example</span>
        <p class="wlg-help-example-heading">## Further reading</p>
        <p class="wlg-help-snippet"><code>[[wiki:crispr-gene-editing]]</code></p>
      </div>
    </div>
    <div class="wlg-help-subcard wlg-help-subcard--coref">
      <h4 class="wlg-help-sub-h"><span class="wlg-help-sub-badge">Co-ref</span>Same topic name on multiple files</h4>
      <p>Same syntax: <code>[[wiki:slug]]</code> — but you <strong>do not need a topic page first</strong>. When <strong>two or more</strong> material notes use the <strong>same slug</strong> and you save, the graph draws a <strong>purple solid</strong> line between those files (co-reference): “these files discuss the same topic.”</p>
      <ul class="wlg-help-list">
        <li>File A and B each write <code>[[wiki:lab-protocol-alpha]]</code> → a purple solid line links A and B</li>
        <li>Plain keywords in the body <strong>do not</strong> co-ref; shared <strong>tags</strong> <strong>do not</strong> either</li>
        <li>Slugs are normalized (case, spaces, hyphens) — use the same topic name on both sides</li>
        <li>Before a topic page exists, only co-ref lines between files appear; after you create the topic page, co-ref lines <strong>stay</strong> and dotted lines to the topic are added</li>
      </ul>
      <div class="wlg-help-example" role="note" aria-label="Co-ref writing example">
        <span class="wlg-help-example-tag">Example · File A</span>
        <p class="wlg-help-snippet"><code>Related to [[wiki:crispr-gene-editing]].</code></p>
        <span class="wlg-help-example-tag">Example · File B</span>
        <p class="wlg-help-snippet"><code>Also covers [[wiki:crispr-gene-editing]].</code></p>
      </div>
    </div>
    <p class="wlg-help-note"><strong>Graph legend</strong>: green solid = direct <code>[[file:id]]</code>; purple solid = co-ref (same <code>[[wiki:slug]]</code>); dotted = link to an existing topic page; diamond = topic node.</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--amber">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">✦</span>
    <h3 class="wlg-help-h">Readable link labels</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>Put <strong>display text</strong>, a pipe <code>|</code>, then the ID or <code>wiki:</code> topic name inside the brackets.</p>
    <div class="wlg-help-example wlg-help-example--compact" role="note">
      <p class="wlg-help-snippet"><code>[[CRISPR gene editing|wiki:crispr-gene-editing]]</code></p>
      <p class="wlg-help-snippet"><code>[[Protocol A|file:256]]</code></p>
    </div>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--sky">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">◎</span>
    <h3 class="wlg-help-h">Using this graph</h3>
  </div>
  <div class="wlg-help-card-body">
    <ul class="wlg-help-list wlg-help-list--checks">
      <li>Pan and zoom the canvas</li>
      <li>Click a dot to open preview</li>
      <li>Hover for material name and link counts</li>
      <li>Click Refresh when the graph is truncated</li>
    </ul>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--mint">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">↩</span>
    <h3 class="wlg-help-h">Who links to this file?</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>See the <strong>backlink</strong> list in preview and jump to the source note.</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--rose">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">!</span>
    <h3 class="wlg-help-h">Dashed or broken links?</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>Usually: deleted file, wrong ID, missing topic, or no permission. Fix and <strong>save the note</strong>, then Refresh.</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--slate">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">?</span>
    <h3 class="wlg-help-h">Why is the graph empty?</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>Add a “Related” section with 2–3 links in a note you use often, save, then <strong>Refresh</strong> this page.</p>
  </div>
</section>
`.trim()
