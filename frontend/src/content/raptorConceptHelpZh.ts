/** RAPTOR 概念说明（HTML，供管理端 Ollama → RAPTOR 子 Tab 帮助弹窗） */
export const RAPTOR_CONCEPT_HELP_HTML_ZH = `
<header class="wlg-help-hero">
  <p class="wlg-help-hero-kicker">RAPTOR</p>
  <p class="wlg-help-hero-desc"><strong>Recursive Abstractive Processing for Tree-Organized Retrieval</strong></p>
  <p class="wlg-help-hero-desc">中文：<strong>面向树形检索的递归抽象处理</strong> — 斯坦福大学 2024 年提出的分层树状高级 RAG 索引算法。</p>
  <div class="wlg-help-hero-chips" aria-hidden="true">
    <span class="wlg-help-chip">层次摘要</span>
    <span class="wlg-help-chip">树形检索</span>
    <span class="wlg-help-chip">长文档 RAG</span>
  </div>
</header>

<section class="wlg-help-card wlg-help-card--sky">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">1</span>
    <h3 class="wlg-help-h">解决传统 RAG 的痛点</h3>
  </div>
  <div class="wlg-help-card-body wlg-help-card-body--stack">
    <p>普通 RAG 只用固定大小文本块：</p>
    <ul class="wlg-help-list">
      <li><strong>块太小</strong>：丢失全局上下文，回答综合类问题效果差</li>
      <li><strong>块太大</strong>：向量语义模糊，精准事实检索不准</li>
    </ul>
    <p>RAPTOR 同时保留<strong>细粒度原文</strong>与<strong>多层粗粒度摘要</strong>，兼顾细节与整体。</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--mint">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">2</span>
    <h3 class="wlg-help-h">核心原理：自下而上构建语义树</h3>
  </div>
  <div class="wlg-help-card-body wlg-help-card-body--stack">
    <ul class="wlg-help-list">
      <li><strong>叶子层</strong>：原始文本小块（基础细节）</li>
      <li><strong>递归聚类 + 摘要</strong>：把语义相近的块分组，用 LLM 生成该组摘要，作为上层节点</li>
      <li><strong>重复迭代</strong>：不断向上合并、总结，直到顶层根节点（全文总概括）</li>
    </ul>
    <p>一棵树包含多粒度语义：微观原文、中层段落摘要、宏观全文主题。</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--violet">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">3</span>
    <h3 class="wlg-help-h">两种检索模式</h3>
  </div>
  <div class="wlg-help-card-body wlg-help-card-body--stack">
    <p><strong>树遍历检索（Tree Traversal）</strong></p>
    <p>从顶层摘要往下逐层筛选，先锁定大主题，再深挖细节，减少无关内容；适合超长文档、全局类问题。</p>
    <p><strong>折叠树检索（Collapsed Tree）</strong></p>
    <p>把整棵树所有层级节点全部扁平化，统一向量检索，实现粗、细信息一次性召回；适合事实问答。</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--amber">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">4</span>
    <h3 class="wlg-help-h">适用场景</h3>
  </div>
  <div class="wlg-help-card-body">
    <ul class="wlg-help-list wlg-help-list--checks">
      <li>长篇文档、书籍、多章节知识库</li>
      <li>需要跨段落、跨章节综合推理的复杂提问</li>
      <li>问答、文档总结、长文本分析类 RAG 系统</li>
    </ul>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--slate">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">5</span>
    <h3 class="wlg-help-h">和普通 RAG 的区别</h3>
  </div>
  <div class="wlg-help-card-body wlg-help-card-body--stack">
    <p><strong>普通 RAG</strong>：单层分块，只有原文片段。</p>
    <p><strong>RAPTOR</strong>：多层树形索引，同时存储原文 + 各级摘要，检索维度更丰富，长文本效果显著提升。</p>
  </div>
</section>
`
