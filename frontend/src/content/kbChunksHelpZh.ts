/** 索引块帮助正文（HTML，供帮助弹窗渲染） */
export const KB_CHUNKS_HELP_HTML = `
<header class="wlg-help-hero">
  <p class="wlg-help-hero-kicker">检索索引</p>
  <p class="wlg-help-hero-desc">资料上传后会<strong>分块并嵌入向量</strong>，智能检索按这些「索引块」命中内容。在此可浏览、微调块文本与检索关键词，<strong>不改动资料笔记原文</strong>。</p>
  <div class="wlg-help-hero-chips" aria-hidden="true">
    <span class="wlg-help-chip">分块列表</span>
    <span class="wlg-help-chip">人工干预</span>
    <span class="wlg-help-chip">试搜验证</span>
  </div>
</header>

<section class="wlg-help-card wlg-help-card--sky">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">1</span>
    <h3 class="wlg-help-h">在哪里打开？</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>在资料<strong>预览</strong>窗口顶部切换到 <strong>「索引块」</strong> 标签页。顶栏显示索引状态、块总数、向量维度与嵌入模型（如 <code>bge-m3:latest</code>）。</p>
    <p class="wlg-help-note">仅当资料已完成索引（状态 <code>ready</code>）时才有块列表；否则可按提示尝试「重新索引」。</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--mint">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">2</span>
    <h3 class="wlg-help-h">表格各列含义</h3>
  </div>
  <div class="wlg-help-card-body wlg-help-card-body--stack">
    <ul class="wlg-help-list">
      <li><strong>块</strong>：序号，与检索结果中的 chunk 编号对应。</li>
      <li><strong>标题路径</strong>：该块在资料笔记大纲中的位置（若有）。</li>
      <li><strong>块类型</strong>：段落、标题、表格、代码等结构类型。</li>
      <li><strong>内容类型</strong>：多模态块时显示图、表、公式等标记。</li>
      <li><strong>元数据</strong>：页码、笔记侧资产 ID 等结构化信息摘要。</li>
      <li><strong>位置</strong>：在原文或笔记中的定位标签。</li>
      <li><strong>文本</strong>：参与检索与嵌入的正文片段预览。</li>
      <li><strong>检索关键词</strong>：人工追加的加权词，逗号分隔。</li>
    </ul>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--violet">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">3</span>
    <h3 class="wlg-help-h">点击行：查看与编辑</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>点击任意一行打开侧栏详情。若你是资料<strong>所有者</strong>或<strong>管理员</strong>，可编辑块正文与检索关键词，保存后系统会更新全文检索并重新嵌入向量。</p>
    <ul class="wlg-help-list wlg-help-list--checks">
      <li>修改<strong>仅写入检索索引</strong>，不会回写资料笔记或原件 PDF</li>
      <li>企业资料中仅有阅读权限的成员可浏览，不可保存</li>
      <li>图 / 表 / 公式等多模态块正文只读，仍可调整检索关键词</li>
    </ul>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--amber">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">↻</span>
    <h3 class="wlg-help-h">重新索引 vs 强制重建</h3>
  </div>
  <div class="wlg-help-card-body">
    <p><strong>重新索引</strong>：按当前资料笔记重新生成索引；若存在人工修改过的块，系统会<strong>保留</strong>这些覆盖。</p>
    <p><strong>强制以资料笔记重建</strong>：清除全部人工修改，完全依据当前资料笔记重新分块与嵌入，<strong>不可撤销</strong>。</p>
    <p class="wlg-help-note"><strong>大文件（资料笔记字符数超过系统阈值）</strong>：列表「重新检索」与强制重建默认<strong>跳过后处理</strong>（实体关系 / SAG / RAPTOR），主要耗时在向量分块与嵌入，通常数分钟内完成（生产 340：post 约 22ms）。管理员可在系统参数中<strong>仅运维场景</strong>开启「大文件仍跑完整后处理」；生产实测全路径 post 可达<strong>约 50 分钟</strong>（340 job 1775），且依赖 ollama 摘要稳定性。</p>
    <p class="wlg-help-note">若顶栏出现「索引与笔记不一致」提示，说明有人工干预；需要与笔记完全对齐时请用强制重建，或在侧栏保存前确认是否保留手工修正。</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--sky">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">◎</span>
    <h3 class="wlg-help-h">试搜：验证检索效果</h3>
  </div>
  <div class="wlg-help-card-body">
    <p>在块详情侧栏底部可点 <strong>「试搜」</strong>，将块文本带入「检索评测」页快速验证该片段能否被语义检索命中。</p>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--rose">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">!</span>
    <h3 class="wlg-help-h">常见注意</h3>
  </div>
  <div class="wlg-help-card-body">
    <ul class="wlg-help-list">
      <li>想让检索跟随笔记内容变化：先<strong>更新并保存资料笔记</strong>，再视情况重新索引。</li>
      <li>检索关键词用于加权命中，不能替代正文；正文为空时无法保存。</li>
      <li>不支持在此合并或拆分块边界；大块结构由索引管线自动切分。</li>
    </ul>
  </div>
</section>
`.trim()
