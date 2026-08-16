/** 新手引导（入门） */
export const GETTING_STARTED_HELP_HTML = `
<section class="wlg-help-card wlg-help-card--sky">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">1</span>
    <h3 class="wlg-help-h">在网页上传已有文档</h3>
  </div>
  <div class="wlg-help-card-body">
    <ul class="wlg-help-list">
      <li>打开左侧栏的<strong>上传</strong>，选择或拖拽文件（PDF、Word、图片等）。</li>
      <li>可按需选择<strong>目录</strong>，把资料放进对应文件夹。</li>
      <li>上传后系统会自动生成资料笔记并建立索引；列表里「索引」变为就绪即可检索。</li>
      <li>相同内容的文件不会重复存储（自动去重）。</li>
    </ul>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--mint">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">2</span>
    <h3 class="wlg-help-h">用 AI Agent 采集互联网资料</h3>
  </div>
  <div class="wlg-help-card-body">
    <ul class="wlg-help-list">
      <li>在顶栏按提示<strong>安装钉技能</strong>，并在「API 密钥」页创建密钥。</li>
      <li>对 Agent 直接说：把某个链接存进资料库，或帮我检索某个主题的最新公开资料并入库。</li>
      <li>外网文章、论文、网页等<strong>无需先下载再手动上传</strong>，Agent 会帮你抓取并写入资料库。</li>
      <li>顶栏「系统帮助」可查看更详细的 Agent 与容器流程（进阶）。</li>
    </ul>
  </div>
</section>

<section class="wlg-help-card wlg-help-card--violet">
  <div class="wlg-help-card-head">
    <span class="wlg-help-step">3</span>
    <h3 class="wlg-help-h">用 AI Agent 整理库内资料</h3>
  </div>
  <div class="wlg-help-card-body">
    <ul class="wlg-help-list">
      <li>在资料列表中，点击某一行的<strong>「AI 命令」</strong>，将复制的内容粘贴到已安装钉技能的 Agent 对话里。</li>
      <li>Agent 会读取该资料并与 FileX 配合，帮你撰写或润色资料笔记、打标签、完善 Wiki 互链，逐步把资料整理成可检索、可关联的知识页。</li>
      <li>你也可以在网页里预览资料、手动编辑笔记和标签；保存后会重新索引。</li>
      <li>整理完成后，用语义检索或资料关系图即可快速找到相关内容。</li>
    </ul>
  </div>
</section>
`
