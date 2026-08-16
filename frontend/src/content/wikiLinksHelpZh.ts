/** 笔记互链帮助正文（HTML，供帮助弹窗渲染） */
export const WIKI_LINKS_HELP_HTML = `
<header class="wlg-help-hero">
  <p class="wlg-help-hero-kicker">三步上手</p>
  <p class="wlg-help-hero-desc">在资料笔记写下 <strong>双方括号链接</strong> → 保存 → 在「资料关系」里看到连线，预览里可点击跳转。</p>
  <div class="wlg-help-hero-chips" aria-hidden="true">
    <span class="wlg-help-chip">资料笔记</span>
    <span class="wlg-help-chip">关系图</span>
    <span class="wlg-help-chip">反向链接</span>
  </div>
</header>

<section class="wlg-help-card wlg-help-card--sky">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">1</span>
    <h3 class="wlg-help-h">这是什么？</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>「资料关系」展示大家在资料笔记里亲手写下的引用网络——<em>这篇指向那篇</em>。</p>
    <div class="wlg-help-visual-hint" aria-hidden="true">
      <span class="wlg-help-node"></span>
      <span class="wlg-help-edge"></span>
      <span class="wlg-help-node wlg-help-node--dim"></span>
      <span class="wlg-help-legend">圆点 = 有笔记的资料 · 连线 = 笔记里的引用</span>
    </div>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--mint">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">2</span>
    <h3 class="wlg-help-h">链接写在哪里？</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>打开资料<strong>预览</strong> → 编辑<strong>资料笔记</strong>（没有可先新建或生成摘要）→ 在正文里写链接 → <strong>保存</strong>。</p>
    <p class="wlg-help-note">代码块里的文字不会被解析成链接。</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--violet">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">3</span>
    <h3 class="wlg-help-h">链接怎么写？</h3>
  </div>
  <div class="wlg-help-card-body wlg-help-card-body--stack">
    <div class="wlg-help-subcard wlg-help-subcard--file">
      <h4 class="wlg-help-sub-h"><span class="wlg-help-sub-badge">资料</span>指向另一篇资料</h4>
      <p>在资料列表可见每篇资料的<strong>编号</strong>（数字 ID）。写法：</p>
      <ul class="wlg-help-list">
        <li>双方括号里只写编号，如 <code>[[88]]</code></li>
        <li>或写 <code>file:</code> 加编号，如 <code>[[file:128]]</code></li>
      </ul>
      <div class="wlg-help-example" role="note" aria-label="笔记书写示例">
        <span class="wlg-help-example-tag">示例</span>
        <p class="wlg-help-example-heading">## 相关阅读</p>
        <p class="wlg-help-snippet"><code>[[file:128]]</code></p>
        <p class="wlg-help-snippet"><code>[[前期综述|88]]</code></p>
      </div>
    </div>
    <div class="wlg-help-subcard wlg-help-subcard--wiki">
      <h4 class="wlg-help-sub-h"><span class="wlg-help-sub-badge">主题</span>指向另一个主题页</h4>
      <p>主题可单独成页；slug 支持中文或英文连字符，例如 <code>重要人才</code>、<code>crispr-gene-editing</code>。</p>
      <p>写法：<code>[[wiki:名称]]</code>。主题尚未创建时会显示未连上；创建同名主题后，已保存的笔记会自动连上，关系图出现<strong>点线</strong>指向<strong>菱形</strong>主题节点。</p>
      <p class="wlg-help-note"><strong>待编译</strong>：当至少两篇笔记引用同一主题且尚无主题页时，可在「资料关系」看到待编译提示，并交给「钉」智能体批量整理主题页正文（FileX 本身不自动生成 LLM 内容）。</p>
      <div class="wlg-help-example" role="note" aria-label="笔记书写示例">
        <span class="wlg-help-example-tag">示例</span>
        <p class="wlg-help-example-heading">## 延伸阅读</p>
        <p class="wlg-help-snippet"><code>[[wiki:crispr-gene-editing]]</code></p>
        <p class="wlg-help-snippet"><code>[[wiki:重要人才]]</code></p>
      </div>
    </div>
    <div class="wlg-help-subcard wlg-help-subcard--coref">
      <h4 class="wlg-help-sub-h"><span class="wlg-help-sub-badge">共引</span>多篇资料写同一主题名</h4>
      <p>写法与上面相同，也是 <code>[[wiki:slug]]</code>——但<strong>不必先建主题页</strong>：当<strong>两篇及以上</strong>资料笔记里都写了<strong>同一个 slug</strong>，保存后资料关系图会出现它们之间的<strong>紫色实线</strong>（共引边），表示「都在讨论同一主题」。</p>
      <ul class="wlg-help-list">
        <li>资料 A、B 各写 <code>[[wiki:lab-protocol-alpha]]</code> → 图上 A 与 B 自动连一条紫色实线</li>
        <li>正文里只写普通关键词<strong>不会</strong>共引；相同<strong>标签</strong>也<strong>不会</strong>产生共引边</li>
        <li>slug 会自动规范化（大小写、空格与连字符），两边写同一主题名即可</li>
        <li>主题页尚未创建时<strong>只有</strong>资料之间的共引边；创建同名主题页后，共引边<strong>保留</strong>，并额外出现资料→主题的<strong>点线</strong></li>
      </ul>
      <div class="wlg-help-example" role="note" aria-label="共引书写示例">
        <span class="wlg-help-example-tag">示例 · 资料 A</span>
        <p class="wlg-help-snippet"><code>本篇与 [[wiki:crispr-gene-editing]] 相关。</code></p>
        <span class="wlg-help-example-tag">示例 · 资料 B</span>
        <p class="wlg-help-snippet"><code>同样涉及 [[wiki:crispr-gene-editing]]。</code></p>
      </div>
    </div>
    <p class="wlg-help-note"><strong>关系图线型速查</strong>：绿色实线 = 资料直连 <code>[[file:id]]</code>；紫色实线 = 共引（同一 <code>[[wiki:slug]]</code>）；点线 = 资料指向已存在的主题页；菱形 = 主题页节点。</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--amber">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">✦</span>
    <h3 class="wlg-help-h">让链接显示更好读</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>在双方括号里先写<strong>显示文字</strong>，加竖线 <code>|</code>，再写编号或 <code>wiki:</code> 主题名。</p>
    <div class="wlg-help-example wlg-help-example--compact" role="note">
      <p class="wlg-help-snippet"><code>[[CRISPR 基因编辑|wiki:crispr-gene-editing]]</code></p>
      <p class="wlg-help-snippet"><code>[[重要人才|wiki:重要人才]]</code></p>
      <p class="wlg-help-snippet"><code>[[实验方案 A|file:256]]</code></p>
    </div>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--sky">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">◎</span>
    <h3 class="wlg-help-h">怎么用这个关系图？</h3>
  </div>
  <div class="wlg-help-card-body">
    <ul class="wlg-help-list wlg-help-list--checks">
      <li>拖动画布、滚轮缩放，查看整体</li>
      <li>点击圆点打开该篇资料预览</li>
      <li>悬停可看资料名与引用数量</li>
      <li>节点过多时可点工具栏「刷新」更新</li>
    </ul>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--mint">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">↩</span>
    <h3 class="wlg-help-h">谁引用了当前这篇？</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>在资料预览中查看<strong>反向链接</strong>列表，点击可跳回来源笔记。</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--rose">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">!</span>
    <h3 class="wlg-help-h">虚线或「断链」？</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>常见原因：资料已删、编号写错、主题未建、或无权限查看目标。改正后<strong>重新保存笔记</strong>并点「刷新」。</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--slate">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">?</span>
    <h3 class="wlg-help-h">为什么图上是空的？</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>当前空间还没有人保存过互链。任选一篇常用资料，在笔记末尾加「相关阅读」并写 2～3 条链接，保存后回到本页点<strong>刷新</strong>。</p>
  </div>
</section>
`.trim()
