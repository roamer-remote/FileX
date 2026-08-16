/** FileX 系统流程帮助 */
export const SYSTEM_HELP_HTML = `
<header class="wlg-help-hero">
  <p class="wlg-help-hero-kicker">系统流程</p>
  <p class="wlg-help-hero-desc">从 <strong>Web 上传</strong>、<strong>智能体抓链接入库</strong>到 <strong>钉维护已有资料</strong>——看清数据在容器间如何流动。</p>
  <div class="wlg-help-hero-chips" aria-hidden="true">
    <span class="wlg-help-chip">Web 上传</span>
    <span class="wlg-help-chip">Agent 入库</span>
    <span class="wlg-help-chip">Docker 拓扑</span>
    <span class="wlg-help-chip">向量索引</span>
  </div>
</header>

<section class="wlg-help-card wlg-help-card--slate">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">◎</span>
    <h3 class="wlg-help-h">部署拓扑：容器与宿主机</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>生产环境典型 Compose 栈（本地开发时 API / indexer 可在宿主机跑，Postgres / RabbitMQ 仍常用容器）。</p>
    <div class="wlg-help-topology" role="img" aria-label="FileX 部署拓扑示意">
      <div class="wlg-help-topo-panel wlg-help-topo-panel--docker">
        <p class="wlg-help-topo-title">Docker 容器</p>
        <div class="wlg-help-topo-grid">
          <span class="wlg-help-topo-chip">filex<em>API + 静态前端</em></span>
          <span class="wlg-help-topo-chip">filex-postgres<em>业务库 + pgvector</em></span>
          <span class="wlg-help-topo-chip">filex-rabbitmq<em>索引 / 笔记生成队列</em></span>
          <span class="wlg-help-topo-chip">filex-redis<em>钉技能 Runtime</em></span>
          <span class="wlg-help-topo-chip">filex-kb-indexer<em>向量索引（串行）</em></span>
          <span class="wlg-help-topo-chip">filex-kb-post<em>后处理 entity/SAG/RAPTOR</em></span>
          <span class="wlg-help-topo-chip">filex-kb-extract<em>PDF/Office → 笔记</em></span>
          <span class="wlg-help-topo-chip">filex-kb-rerank<em>检索重排</em></span>
        </div>
        <p class="wlg-help-topo-link">持久化：<code>uploads/</code> 原文、空间级 <code>{ws}/okf/</code> OKF 笔记与 legacy <code>.md_notes/</code>；<code>postgres/data</code> 库文件。</p>
      </div>
      <div class="wlg-help-topo-panel wlg-help-topo-panel--host">
        <p class="wlg-help-topo-title">宿主机</p>
        <div class="wlg-help-topo-grid">
          <span class="wlg-help-topo-chip">Ollama :11434<em>embedding bge-m3</em></span>
        </div>
        <p class="wlg-help-topo-link"><code>kb-indexer</code> 经 <code>host.docker.internal</code> 调 Ollama；向量化<strong>不在</strong> rerank 容器内。</p>
      </div>
    </div>
    <div class="wlg-help-flow" aria-label="容器协作关系">
      <div class="wlg-help-flow-row">
        <div class="wlg-help-flow-node wlg-help-flow-node--user">浏览器 / 钉 Agent<small>JWT 或 fb_ Key</small></div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--svc">filex<small>REST + WS</small></div>
      </div>
      <div class="wlg-help-flow-arrow-v">↓</div>
      <div class="wlg-help-flow-row">
        <div class="wlg-help-flow-node wlg-help-flow-node--store">postgres<small>元数据 · chunks</small></div>
        <span class="wlg-help-flow-arrow-h">↔</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--queue">rabbitmq<small>kb.index / kb.post</small></div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--worker">kb-indexer<small>prefetch=1</small></div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--host">Ollama<small>embed</small></div>
      </div>
      <div class="wlg-help-flow-arrow-v">↓ 向量 ready 后可搜；后处理异步</div>
      <div class="wlg-help-flow-row">
        <div class="wlg-help-flow-node wlg-help-flow-node--queue">kb.post</div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--worker">kb-post<small>entity/SAG/RAPTOR</small></div>
      </div>
      <div class="wlg-help-flow-arrow-v">↓</div>
      <div class="wlg-help-flow-row">
        <div class="wlg-help-flow-node wlg-help-flow-node--worker">kb-extract<small>可选</small></div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--store">uploads<small>{ws}/okf</small></div>
      </div>
    </div>
    <p class="wlg-help-note"><strong>实时状态</strong>：侧栏排队与索引列经 WebSocket（<code>/api/ws/mq-status</code>、<code>/api/ws/kb-index</code>）推送。</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--sky">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">1</span>
    <h3 class="wlg-help-h">Web 上传文件后的处理</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>用户上传 → <code>POST /api/files/upload</code>（JWT，可选 <code>workspace_id</code> / <code>folder_id</code>）。</p>
    <div class="wlg-help-flow" aria-label="Web 上传流程">
      <div class="wlg-help-flow-row">
        <div class="wlg-help-flow-node wlg-help-flow-node--user">Web 上传</div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--svc">filex<small>MD5 去重</small></div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--store">uploads 卷</div>
      </div>
      <div class="wlg-help-flow-arrow-v">↓ 可生成笔记的类型</div>
      <div class="wlg-help-flow-row">
        <div class="wlg-help-flow-node wlg-help-flow-node--queue">笔记生成队列</div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--worker">kb-extract<small>OCR/Office</small></div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--store">{ws}/okf</div>
      </div>
      <div class="wlg-help-flow-arrow-v">↓</div>
      <div class="wlg-help-flow-row">
        <div class="wlg-help-flow-node wlg-help-flow-node--queue">index 队列</div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--worker">kb-indexer</div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--host">Ollama</div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--store">pgvector</div>
      </div>
    </div>
    <ul class="wlg-help-list">
      <li>索引完成后列表显示「可检索」；若开启后处理异步，次要 Badge「后处理中」表示 entity/SAG/RAPTOR 仍在后台运行。</li>
      <li>新上传 OKF Concept 笔记落在 <code>uploads/{workspace_id}/okf/sources/…/*.md</code>（与 OKF Bundle 相对路径一致）；旧资料可能仍只读 <code>.md_notes/{id}.md</code>。</li>
      <li>Web 上传不会自动 LLM 润色；笔记生成只用 OCR / MarkItDown 等。</li>
      <li>预览里编辑笔记并保存 → 再次入队索引。</li>
      <li>同步更新 <code>kb_index.md</code> AUTO 表与 WebSocket 列表状态。</li>
    </ul>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--mint">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">2</span>
    <h3 class="wlg-help-h">AI Agent 拿到外网链接</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>用户对钉说「把 URL 存入 FileX」→ <code>fb_</code> API Key，不用 Web JWT。</p>
    <div class="wlg-help-flow" aria-label="外网链接入库">
      <div class="wlg-help-flow-row">
        <div class="wlg-help-flow-node wlg-help-flow-node--user">外网 URL</div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--agent">ingest_url<small>capture-only</small></div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--agent">通读命名<small>≤20 字</small></div>
      </div>
      <div class="wlg-help-flow-arrow-v">↓ 双路合成</div>
      <div class="wlg-help-flow-row">
        <div class="wlg-help-flow-node wlg-help-flow-node--agent">prepare</div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--agent">A+B 并行</div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--agent">finalize</div>
      </div>
      <div class="wlg-help-flow-arrow-v">↓</div>
      <div class="wlg-help-flow-row">
        <div class="wlg-help-flow-node wlg-help-flow-node--svc">POST /external/files</div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--svc">PUT tags</div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--worker">索引管线</div>
      </div>
    </div>
    <p class="wlg-help-note">第三方 URL 无需 <code>X-FileX-Share-Token</code>；Agent 可附高质量 Markdown（<code>files-with-md</code>）跳过笔记生成。</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--violet">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">3</span>
    <h3 class="wlg-help-h">FileX 链接 → Agent 维护</h3>
  </div>
  <div class="wlg-help-card-body wlg-help-card-body--stack">
    <div class="wlg-help-subcard wlg-help-subcard--file">
      <h4 class="wlg-help-sub-h"><span class="wlg-help-sub-badge">分享</span>本站分享再入库</h4>
      <div class="wlg-help-flow" aria-label="分享入库">
        <div class="wlg-help-flow-row">
          <div class="wlg-help-flow-node wlg-help-flow-node--user">/share/{token}</div>
          <span class="wlg-help-flow-arrow-h">→</span>
          <div class="wlg-help-flow-node wlg-help-flow-node--agent">下载</div>
          <span class="wlg-help-flow-arrow-h">→</span>
          <div class="wlg-help-flow-node wlg-help-flow-node--svc">POST /external/files<small>X-FileX-Share-Token</small></div>
        </div>
      </div>
      <p class="wlg-help-note">Key 用户须为分享所有者，MD5 须一致。</p>
    </div>
    <div class="wlg-help-subcard wlg-help-subcard--wiki">
      <h4 class="wlg-help-sub-h"><span class="wlg-help-sub-badge">维护</span>库内整理</h4>
      <div class="wlg-help-flow" aria-label="库内维护">
        <div class="wlg-help-flow-row">
          <div class="wlg-help-flow-node wlg-help-flow-node--agent">api-key-status</div>
          <span class="wlg-help-flow-arrow-h">→</span>
          <div class="wlg-help-flow-node wlg-help-flow-node--svc">files-awaiting-ai</div>
        </div>
        <div class="wlg-help-flow-arrow-v">↓ wait_extract</div>
        <div class="wlg-help-flow-row">
          <div class="wlg-help-flow-node wlg-help-flow-node--agent">读 md · 润色</div>
          <span class="wlg-help-flow-arrow-h">→</span>
          <div class="wlg-help-flow-node wlg-help-flow-node--svc">PUT …/md</div>
          <span class="wlg-help-flow-arrow-h">→</span>
          <div class="wlg-help-flow-node wlg-help-flow-node--svc">PUT tags</div>
        </div>
        <div class="wlg-help-flow-arrow-v">↓ 自动 reindex · 可选 wiki-lint</div>
      </div>
    </div>
    <ul class="wlg-help-list wlg-help-list--checks">
      <li>写回笔记会触发向量重建；「重建全部索引」不改笔记正文。</li>
      <li>空间/目录以 <code>GET /api/workspaces</code>、<code>/api/folders</code> 响应为准。</li>
    </ul>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--amber">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">✦</span>
    <h3 class="wlg-help-h">检索与 rerank</h3>
  </div>
  <div class="wlg-help-card-body">
    <div class="wlg-help-flow" aria-label="检索 rerank">
      <div class="wlg-help-flow-row">
        <div class="wlg-help-flow-node wlg-help-flow-node--user">搜索</div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--svc">pgvector+FTS</div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--worker">kb-rerank</div>
        <span class="wlg-help-flow-arrow-h">→</span>
        <div class="wlg-help-flow-node wlg-help-flow-node--user">结果</div>
      </div>
    </div>
    <p class="wlg-help-note">rerank 只影响搜索排序，不参与建索引向量化。</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--slate">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">◎</span>
    <h3 class="wlg-help-h">资料库索引页</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>顶栏 <strong>资料库索引</strong>，或资料大厅右侧浮动工具栏中的同名按钮，进入 <code>/knowledge-base</code>。</p>
    <p>页面主 Tab 为<strong>预览</strong>（资料目录 / 主题页 / Wiki 关联目录；工具栏含「重建索引」）。上次打开的 Tab 会保存在账号偏好中，换设备登录后仍可恢复。</p>
  </div>
</section>
`.trim()
