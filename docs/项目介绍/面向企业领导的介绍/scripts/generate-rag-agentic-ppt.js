#!/usr/bin/env node
/**
 * 生成「RAG与Agentic演讲」15 页 PPT，并写入完整逐字稿到演讲者备注。
 */
const pptxgen = require("pptxgenjs");
const path = require("path");

const OUT = path.join(
  __dirname,
  "..",
  "RAG与Agentic演讲-15页.pptx"
);

// Ocean Gradient — 企业 AI / 信任感
const C = {
  midnight: "21295C",
  deep: "065A82",
  teal: "1C7293",
  mint: "02C39A",
  ice: "CADCFC",
  light: "F0F4F8",
  white: "FFFFFF",
  text: "1E293B",
  muted: "64748B",
  coral: "F96167",
};

const FONT_H = "Trebuchet MS";
const FONT_B = "Calibri";

const NOTES = [
  // 第 1 页
  `各位好，感谢大家抽时间过来。

我先问个实在的问题：你们公司上了大模型之后，业务同事最常抱怨的是什么？

我听到的往往不是「不够聪明」，而是这么几句：
「它不知道咱们内部的制度。」
「听着挺像那么回事，但我不敢拿去汇报。」
「能不能别陪我聊天，帮我把事办完？」

您看，其实就三件事：自己的数据接不上、回答不敢信、光说不干活。

今天想跟大家聊的，就是这件事：从 Chat（对话）到 Agentic（自主规划式智能体）——怎么用 RAG（检索增强生成）让 AI 真正读懂企业。

模型会换代，但企业 70% 的知识仍在沉睡。Agent 能行动，RAG 让它有据可依，钉！让这一切可落地。`,

  // 第 2 页
  `这两年 AI 产品，大致走了三个阶段，大家应该有体感。

最早是 Chat（对话）——你问它答，挺能说的，但不会动手，脑子里也只有训练时见过的那些公网东西。

再往后是 Agent（智能体）——开始能干活了，搜网页、跑代码、调 API（应用程序接口），从「会说」变成「会做」。

现在大家在谈 Agentic（自主规划式智能体）——不光执行一步，还能自己拆任务、记东西、做错了改路子、慢慢积累经验。

记法很简单：Chat 会说，Agent 会做，Agentic 会琢磨、会纠错、会越用越熟。

【停顿】

后面整条线，我就按这个顺序讲：

大模型能力很强 → 智能体能行动了 → 可企业数据在墙里面 → 要靠 RAG（检索增强生成）把私域知识接上来 → 钉！ 提供 Data+AI（数据+人工智能）这块底座。

好，咱们进入正题。`,

  // 第 3 页
  `先说说，为什么企业现在开始认真看 Agent（智能体）。

过去 Chat 时代，最多让它写个介绍、润色封邮件。现在业务同事要的是另一回事：「帮我盯竞品、整理成表、写进纪要、顺便通知相关人。」——这是一串动作，不是一段话。Agent 的价值在这儿。

再就是那些烦人的重复活：检索、摘要、归类、填报、对账……人天天干，机器可以帮着串起来，人只管拍板和例外。

还有，搜索、计算、业务系统、读文档，可以像搭积木一样组合。说实话，咱们离「数字助理」近不近，很多时候不取决于模型又大了一点，而是工具链终于接上了。

而且 Agent 不是一锤子买卖。工具能加，经验能留，技能能升级——能力是长出来的，不是交付完就结束。

【互动】可举 1 个业务例子：「帮我整理本周竞品动态并写入纪要」。`,

  // 第 4 页
  `但光说好听的，今天这场就白来了。落地的时候，有四个坑，我见得特别多。

第一个是私域数据够不着。

大模型训练时，看的主要是公网。行业里有个说法：公网（明网）大概 20%，深网、邮件、制度、项目档案这些，70% 以上在企业自己手里。模型训练没见过，运行时也够不着。Agent 再强，接不上自己的库，说白了就是个更聪明的公网助手。

第二个是幻觉（Hallucination）——胡编。

它本质是猜下一个词，不是查数据库。制度、文献、条款，它都能给你编出来。自己用用可能笑笑，放到合规、研发、医疗，那就是事故。

第三个是上下文装不下。

窗口再大，也不可能把公司几十年文档一次全塞进去，成本和延迟都受不了。得问什么找什么，不能不管啥都硬塞。

第四个是说不清出处。

领导一定会问：依据哪份文件？谁有权看？以后能不能查？普通 Chat 很难给一条让人放心的引用链。能力越大，权限和审计越不能省——这事儿和能力是一枚硬币的两面。

【停顿】让「70%」数字沉淀；这是引出 RAG 的桥。

前三个坑，核心解法都指向 RAG（检索增强生成）；第四个，得靠平台治理——后面讲 钉！ 时会展开。`,

  // 第 5 页
  `那 Agentic 到底比 Agent 多在哪？我习惯讲四件事。

第一件，会拆任务。

比如「写份竞品分析」——对机器来说太大了。得拆：先定名单，再查内外部资料，摘录、对比、写结论，最后还得标清楚引用从哪来。技术上叫什么思维链、规划执行，业务同事记住一句就行：大活要拆成能核对的小步。

第二件，会用工具。

外面有搜索、浏览器、代码、公开 API（应用程序接口）；里面有 ERP、工单、企业资料库。在企业里，资料库不是锦上添花，是跟数据库、业务系统一样重要的工具。

第三件，有记忆。

短期记当前对话；长期靠 RAG、向量库、知识图谱记制度、案例、项目沉淀；还有 SOP（标准作业程序）、技能包记「这类事该怎么干」。
这儿有个常见误会：RAG 不是把整库塞进 Prompt（提示词），而是问到了再捞，捞到了再说。

第四件，会反省。

引用对不对？该看的文档都看了吗？搜不到怎么办？——换词、扩大范围、实在不行交给人，别硬编。企业要的不是黑盒机灵，是事后说得清楚的过程。

【停顿】

收个尾：Agentic ≈ 大语言模型 + 会规划 + 会用工具 + RAG 记忆 + 错了能改。
没 RAG，记性基本是空的；不会反省，搜不到就开始编。`,

  // 第 6 页
  `把镜头拉远一点，进化其实两条线在走。

一条是大模型自己变强：能看图听音了，工具调用（function calling，函数调用）更顺了，慢思考、推理链也让复杂调度靠谱不少。扫描件、会议录音、图纸，终于能进同一条知识流水线。

另一条是智能体系统在变：这比天天追榜单实在。

一是大小模型搭配——小事用小模型，便宜快；大事用大模型；OCR（识图取字）、ASR（语音转文字）交给专业模型。架构合理，往往比死磕一个「当前最强」模型更省钱。

二是私域数据得接进来，RAG 基本是标配了：上传、解析、切块、向量化、建索引，回答时带引用——像开卷考，可以翻资料，但不能瞎写。

三是越用越厚——工具在加（MCP 协议、API、钉技能），知识在结构化（Wiki、标签、图谱），检索还能 A/B 测着调。

【停顿】

Gartner 那边也在讲类似的事：企业 AI 的重心，正从「追新模型」转到「把沉睡的资料盘活」和「把智能体管起来」。模型年年换，资料不会自己变聪明。`,

  // 第 7 页
  `落到现场，我常见三类头疼。

资料睡着。企业 70%～90% 的非结构化东西——PDF、邮件、纪要、制度——存得住，机器读不懂。AI 来了，先别急着买更大模型，先让资料能读、能搜、能引用。

资料散着。网盘、邮件、业务系统、个人电脑，格式五花八门。团队大量时间花在搬文件、转格式，不是花在知识上。

管不起来。谁能看？共享库怎么授权？API Key 谁在用？智能体答的话能不能追到原文？这些答不上来，POC（概念验证）做得再漂亮，也上不了生产。

【停顿】

给大家留个简式，回去评估能用：

企业 AI 值多少钱 ≈ 私域数据好不好 × RAG/图谱行不行 × Agent 编排顺不顺 × 安全治理到不到位。

哪一项接近零，整体就接近零。只买模型、不建资料库，这几年踩坑最多的就是这个。`,

  // 第 8 页
  `讲产品之前，先把 RAG 说清楚——因为总有人会问：「不就是弄个向量库吗？」

不完全是。

扔 PDF 进向量库，只是第一步。怎么切、怎么标权限、怎么更新索引、怎么评测，每一步都影响敢不敢用。
RAG 也替代不了微调（fine-tuning）——微调更适合语气、术语；事实类知识，还是检索更靠谱、更好更新。

RAG 干的事其实不复杂：你提问 → 从授权资料库里找相关片段 → 把片段交给模型 → 照着证据回答，最好带上出处。

我常打个比方：开卷考试。模型是考生，RAG 是允许带的「企业参考资料」。考得好不好，看资料整不整齐、搜得准不准。

成熟度也分几档：
入门是分块加向量检索；再往上是混合检索、重排序、查长句；再往上是 Wiki 互链、标签图谱，知识能长能连；最高档是智能体觉得不够再搜、再扩——跟规划拧成一圈。

【停顿】

企业真要用的，一般不是入门演示，得往 L2、L3 走。钉！ 主要精力也花在这儿。`,

  // 第 9 页
  `钉！ 是什么？一句话：

帮企业把私域知识收进来、管起来、搜得到，并且让智能体拿来就能用。

不是再做一个聊天窗口。核心就三个问题：
多源资料怎么统一整理？整理完怎么安全地搜、关联、成图谱？智能体怎么别每个项目从零写 Prompt（提示词）？

跟豆包、元宝那种 Chat 也不一样——它们陪聊，钉！ 站在智能体后面，当知识底座和治理层。`,

  // 第 10 页
  `平台能力我概括六块，不用全记，知道方向就行。

云原生——容器化，能私有化，也能按负载扩。
可组装——摄取、索引、检索、Wiki、Agent API 拆开用，别搞巨石。
一站式——上传、出资料笔记、建索引、Web 或钉技能检索，一条线跑通，少啃六个月自建 RAG 的苦。
能治理——个人库、共享库分开，ACL（访问控制）管权限，操作有日志，API Key（接口密钥）能上下架、能审计。
技能标准化——库内检索、文献入库、Wiki 体检等，装钉技能、配密钥就能调 钉！ 的 API，少折腾 Prompt。
2AI 文档——资料落成 Markdown（轻量标记文档），人看得懂、AI 好切、好索引、好互链。

不必逐条念表；挑一站式、能治理、技能标准化展开 30 秒，其余一带而过。`,

  // 第 11 页
  `跟网盘最大的差别，是知识会长大。

文件上传 → 抽出资料笔记 → 切块建索引 → Wiki 主题页互链 → 标签拉成图谱 → 智能体检索、展开上下文 → 人继续上传、改标签 → 又转一圈。

PDF、Office、图片 OCR（识图取字）都能进流水线；Wiki 能互链、能体检；标签能看出「哪些资料老在一块出现」；检索是语义加全文两套，还能做评测对比。

【停顿】

有句话值得带走：知识不是死仓库，是越整理、越关联、越用越活的网。`,

  // 第 12 页
  `业务上能感到的好处，我归纳四件实事。

不用再从十几个系统手工拷 PDF 了，上传就能提取、能搜。
不光问「有没有这份文件」，还能问「哪些资料在讲同一件事」。
回答能按工作空间（Workspace）和权限过滤，带文件名、带摘录，少靠「把温度调低」赌它不编。
人整理 Wiki、打标签，库变聪明，智能体更好用，人更愿意往里沉淀——越用越厚，别越用越乱。

研发查规范、合规问制度、智能体库内搜加外网入库，都是现成场景。细节可以看钉技能文档。`,

  // 第 13 页
  `信息安全的同事，我知道你们等这儿很久了。

数据上：不出域，私有化部署，检索走内网；最小权限，个人库、集团库分开，共享库还能细授权；能审计，谁干了什么查得到；回答只给授权范围内的片段，不把整库端给模型。

模型上：可以 LLM 本地化（比如 Ollama 内网跑），敏感内容不外发；换底座模型，资料库和权限不用推倒重来。

【停顿】

安全不是锦上添花，不上线门槛。`,

  // 第 14 页
  `最后聊钱，实在点。

用大模型，要么云端 API，按 Token（词元）花钱，弹性好，得算长期账和数据出境；要么本地部署，GPU 和运维前期贵，适合强合规、调用量大。

别漏隐性成本：自建 RAG 管线，三五六个工程师月很常见；多系统对接、洗数据，比想的多；技能、Prompt 还得持续维护——上线不是终点。

钉！ 私有化想帮的是：摄取、索引、检索、Wiki、Agent API 都产品化了，少重复造轮子；模型可换，不被一家绑死；库越大，复用的沉淀越多，越往后越划算。`,

  // 第 15 页
  `最后用三句话收尾。

模型年年换，企业资料不会自己变聪明——把数据资产化，才是主战场。
Agent 往后走 Agentic，但敢不敢用，看 RAG 和治理——能干活，还得说得清依据。
钉！ 不是又一个聊天机器人，是让智能体站在企业自己的知识上面。

想试点的话，我建议四周就够起步：

第一周，选一个知识空间，把制度、产品、项目核心文档导进来；
第二周，跑通资料笔记和语义检索，人工抽几条看引用准不准；
第三周，接一个钉技能场景，库内搜或文献入库都行；
第四周，测检索效果，调标签和 Wiki 结构。

【停顿】

三个问题我先帮大家想好答案：

RAG 和微调怎么选？ 事实、常更新的，先 RAG；语气、术语固定的，再考虑微调。多数企业先 RAG 后微调。

幻觉能清零吗？ 不敢承诺零，但引用溯源、权限内检索、关键决策人工复核，能降到业务能接受。

小团队怎么起步？ 一个空间、一批核心文档、一个场景——小步快跑，比大而全的 POC 容易成。

说到底，企业后面拼什么？很大程度拼：私域知识能不能被 AI 安全、准确、持续地用。

Chat 解决会不会说，Agent 解决会不会做，Agentic 解决会不会琢磨和积累，RAG 和 Data+AI 平台解决的是——说得有没有依据。

会后想聊试点、私有化，随时找我们。谢谢大家。`,
];

function makeShadow() {
  return { type: "outer", color: "000000", blur: 4, offset: 2, angle: 135, opacity: 0.12 };
}

function addSlideNumber(slide, num, pres) {
  slide.addText(String(num), {
    x: 9.35, y: 5.15, w: 0.5, h: 0.3,
    fontSize: 10, color: C.muted, fontFace: FONT_B, align: "right", margin: 0,
  });
}

function addHeaderBar(slide, title, pres, dark = false) {
  const bg = dark ? C.midnight : C.light;
  slide.background = { color: bg };
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.85,
    fill: { color: dark ? C.deep : C.deep },
    line: { color: dark ? C.deep : C.deep, width: 0 },
  });
  slide.addText(title, {
    x: 0.5, y: 0.15, w: 9, h: 0.55,
    fontSize: 22, bold: true, color: C.white, fontFace: FONT_H, margin: 0, valign: "middle",
  });
}

function addQuote(slide, text, y, pres, w = 8.8) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y, w, h: 0.65,
    fill: { color: C.ice, transparency: 35 },
    line: { color: C.mint, width: 1 },
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y, w: 0.06, h: 0.65,
    fill: { color: C.mint },
    line: { color: C.mint, width: 0 },
  });
  slide.addText(text, {
    x: 0.75, y: y + 0.08, w: w - 0.4, h: 0.5,
    fontSize: 13, italic: true, color: C.deep, fontFace: FONT_B, margin: 0,
  });
}

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "钉！团队";
pres.title = "从 Chat 到 Agentic：RAG 如何让 AI 真正读懂企业";
pres.subject = "企业领导演讲";

// ── 第 1 页 · 封面 ──
{
  const slide = pres.addSlide();
  slide.background = { color: C.midnight };
  // 装饰渐变块
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 3.2, h: 5.625,
    fill: { color: C.deep, transparency: 20 },
    line: { color: C.deep, width: 0 },
  });
  slide.addShape(pres.shapes.OVAL, {
    x: 7.8, y: -0.8, w: 3.5, h: 3.5,
    fill: { color: C.teal, transparency: 60 },
    line: { color: C.teal, width: 0 },
  });
  slide.addShape(pres.shapes.OVAL, {
    x: 8.5, y: 4.2, w: 2.2, h: 2.2,
    fill: { color: C.mint, transparency: 70 },
    line: { color: C.mint, width: 0 },
  });
  slide.addText("从 Chat（对话）到 Agentic（自主规划式智能体）", {
    x: 0.6, y: 1.4, w: 8.8, h: 1.2,
    fontSize: 32, bold: true, color: C.white, fontFace: FONT_H, margin: 0,
  });
  slide.addText("RAG（检索增强生成）如何让 AI 真正读懂企业", {
    x: 0.6, y: 2.65, w: 8.5, h: 0.7,
    fontSize: 20, color: C.ice, fontFace: FONT_B, margin: 0,
  });
  slide.addText([
    { text: "钉！团队", options: { breakLine: true } },
    { text: "2026 年 6 月", options: {} },
  ], {
    x: 0.6, y: 4.5, w: 4, h: 0.8,
    fontSize: 14, color: C.ice, fontFace: FONT_B, margin: 0,
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: 3.55, w: 7.5, h: 0.75,
    fill: { color: C.teal, transparency: 25 },
    line: { color: C.mint, width: 0.5 },
  });
  slide.addText("模型会换代，企业 70% 的知识仍在沉睡。Agent 能行动，RAG 让它有据可依。", {
    x: 0.8, y: 3.65, w: 7.1, h: 0.55,
    fontSize: 13, color: C.white, fontFace: FONT_B, margin: 0,
  });
  slide.addNotes(NOTES[0]);
}

// ── 第 2 页 · 三阶段演进 ──
{
  const slide = pres.addSlide();
  addHeaderBar(slide, "我们到底在期待 AI 什么？", pres);
  const rows = [
    [
      { text: "阶段", options: { fill: { color: C.deep }, color: C.white, bold: true } },
      { text: "本质", options: { fill: { color: C.deep }, color: C.white, bold: true } },
      { text: "典型能力", options: { fill: { color: C.deep }, color: C.white, bold: true } },
      { text: "局限", options: { fill: { color: C.deep }, color: C.white, bold: true } },
    ],
    ["Chat（对话）", "对话式问答", "多轮对话、文本生成", "无行动，知识止于训练数据"],
    ["Agent（智能体）", "任务执行体", "工具调用、多步执行", "缺规划、反思与长期记忆"],
    ["Agentic（自主规划式）", "自主规划系统", "目标分解、反思纠错", "对私域数据与治理要求极高"],
  ];
  slide.addTable(rows, {
    x: 0.4, y: 1.05, w: 9.2, h: 2.1,
    fontSize: 11, fontFace: FONT_B,
    border: { pt: 0.5, color: C.ice },
    colW: [1.5, 1.3, 2.4, 3.0],
    rowH: [0.38, 0.5, 0.5, 0.5],
    autoPage: false,
  });
  // 演进箭头卡片
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 3.35, w: 9, h: 0.55,
    fill: { color: C.white },
    line: { color: C.teal, width: 1 },
    shadow: makeShadow(),
  });
  slide.addText("Chat 会说  →  Agent 会做  →  Agentic 会规划、会纠错、会积累", {
    x: 0.65, y: 3.45, w: 8.7, h: 0.4,
    fontSize: 14, bold: true, color: C.deep, fontFace: FONT_H, align: "center", margin: 0,
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 4.1, w: 9, h: 0.9,
    fill: { color: C.deep, transparency: 8 },
    line: { color: C.teal, width: 0.5 },
  });
  slide.addText("大模型爆发 → Agent 能行动 → 企业数据在墙内 → RAG 打通私域 → 钉！ Data+AI 底座", {
    x: 0.65, y: 4.25, w: 8.7, h: 0.6,
    fontSize: 12, color: C.text, fontFace: FONT_B, align: "center", margin: 0,
  });
  addSlideNumber(slide, 2, pres);
  slide.addNotes(NOTES[1]);
}

// ── 第 3 页 · Agent 优点 ──
{
  const slide = pres.addSlide();
  addHeaderBar(slide, "Agent 的优点：为什么企业开始押注", pres);
  const items = [
    { n: "01", t: "从问答到行动", d: "查资料、调 API、跑代码、触发工作流" },
    { n: "02", t: "任务自动化", d: "检索、摘要、归类、填报等重复性知识工作" },
    { n: "03", t: "能力可组合", d: "搜索 + 计算 + 企业系统 + 文档理解" },
    { n: "04", t: "持续迭代", d: "工具扩展与经验沉淀，能力可增长" },
  ];
  items.forEach((it, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = 0.5 + col * 4.7;
    const y = 1.1 + row * 1.85;
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 4.4, h: 1.55,
      fill: { color: C.white },
      line: { color: C.ice, width: 1 },
      shadow: makeShadow(),
    });
    slide.addShape(pres.shapes.OVAL, {
      x: x + 0.15, y: y + 0.2, w: 0.55, h: 0.55,
      fill: { color: C.teal },
      line: { color: C.teal, width: 0 },
    });
    slide.addText(it.n, {
      x: x + 0.15, y: y + 0.28, w: 0.55, h: 0.4,
      fontSize: 14, bold: true, color: C.white, align: "center", margin: 0,
    });
    slide.addText(it.t, {
      x: x + 0.85, y: y + 0.2, w: 3.4, h: 0.45,
      fontSize: 16, bold: true, color: C.deep, fontFace: FONT_H, margin: 0,
    });
    slide.addText(it.d, {
      x: x + 0.85, y: y + 0.7, w: 3.4, h: 0.7,
      fontSize: 12, color: C.muted, fontFace: FONT_B, margin: 0,
    });
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 4.6, y: 4.85, w: 0.8, h: 0.35,
    fill: { color: C.mint },
    line: { color: C.mint, width: 0 },
  });
  slide.addText("说 → 做", {
    x: 4.55, y: 4.88, w: 0.9, h: 0.3,
    fontSize: 11, bold: true, color: C.white, align: "center", margin: 0,
  });
  addSlideNumber(slide, 3, pres);
  slide.addNotes(NOTES[2]);
}

// ── 第 4 页 · Agent 边界 ──
{
  const slide = pres.addSlide();
  addHeaderBar(slide, "Agent 的边界：四个必须正视的硬伤", pres);
  const rows = [
    [
      { text: "问题", options: { fill: { color: C.coral }, color: C.white, bold: true } },
      { text: "表现", options: { fill: { color: C.coral }, color: C.white, bold: true } },
      { text: "根因", options: { fill: { color: C.coral }, color: C.white, bold: true } },
    ],
    ["私域数据不可及", "答不出内部制度、项目文档", "训练数据以公网为主"],
    ["幻觉 Hallucination", "捏造政策、虚构引用", "概率预测，非事实检索"],
    ["上下文有限", "长文档、跨项目装不下", "Token 窗口与成本约束"],
    ["缺乏治理与溯源", "不知答案来自哪份文件", "缺少引用链与权限边界"],
  ];
  slide.addTable(rows, {
    x: 0.4, y: 1.0, w: 6.2, h: 2.5,
    fontSize: 10, fontFace: FONT_B,
    border: { pt: 0.5, color: C.ice },
    colW: [1.5, 2.2, 2.5],
    autoPage: false,
  });
  // 数据可见性
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 6.85, y: 1.0, w: 2.65, h: 2.5,
    fill: { color: C.midnight },
    line: { color: C.teal, width: 1 },
  });
  slide.addText("数据可见性", {
    x: 7.0, y: 1.15, w: 2.3, h: 0.35,
    fontSize: 13, bold: true, color: C.ice, fontFace: FONT_H, margin: 0,
  });
  slide.addText("公网（明网）", {
    x: 7.0, y: 1.65, w: 1.5, h: 0.3, fontSize: 11, color: C.ice, fontFace: FONT_B, margin: 0,
  });
  slide.addText("≈ 20%", {
    x: 8.5, y: 1.6, w: 0.9, h: 0.4,
    fontSize: 22, bold: true, color: C.mint, align: "right", margin: 0,
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 7.0, y: 2.05, w: 2.3, h: 0.12,
    fill: { color: C.mint, transparency: 30 },
    line: { color: C.mint, width: 0 },
  });
  slide.addText("深网 / 私域 / 企业内部", {
    x: 7.0, y: 2.3, w: 1.8, h: 0.35, fontSize: 11, color: C.ice, fontFace: FONT_B, margin: 0,
  });
  slide.addText("≈ 70%+", {
    x: 8.3, y: 2.25, w: 1.1, h: 0.45,
    fontSize: 26, bold: true, color: C.mint, align: "right", margin: 0,
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 7.0, y: 2.75, w: 2.3, h: 0.55,
    fill: { color: C.mint, transparency: 15 },
    line: { color: C.mint, width: 0 },
  });
  addQuote(slide, "Agent 再强，若接不上企业自己的数据，上限就是「更聪明的公网助手」。", 3.75, pres, 9.0);
  addSlideNumber(slide, 4, pres);
  slide.addNotes(NOTES[3]);
}

// ── 第 5 页 · Agentic 四能力 ──
{
  const slide = pres.addSlide();
  addHeaderBar(slide, "Agentic 智能体：四大核心能力", pres);
  const caps = [
    ["目标分解", "大任务拆成可执行子步骤", "每步检索不同知识切片"],
    ["工具调用", "搜索、API、代码、企业系统", "资料库 API 是核心工具"],
    ["记忆机制", "短期上下文 + 长期沉淀", "RAG = 长期记忆的按需召回层"],
    ["反思与学习", "自检、换路、重规划", "检索为空时扩召回或降级人工"],
  ];
  caps.forEach((c, i) => {
    const y = 1.05 + i * 0.95;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 0.5, y, w: 0.45, h: 0.75,
      fill: { color: C.teal },
      line: { color: C.teal, width: 0 },
    });
    slide.addText(String(i + 1), {
      x: 0.5, y: y + 0.15, w: 0.45, h: 0.45,
      fontSize: 16, bold: true, color: C.white, align: "center", margin: 0,
    });
    slide.addText(c[0], {
      x: 1.1, y: y + 0.05, w: 1.6, h: 0.35,
      fontSize: 14, bold: true, color: C.deep, fontFace: FONT_H, margin: 0,
    });
    slide.addText(c[1], {
      x: 2.8, y: y + 0.05, w: 3.2, h: 0.35,
      fontSize: 11, color: C.text, fontFace: FONT_B, margin: 0,
    });
    slide.addText(c[2], {
      x: 6.1, y: y + 0.05, w: 3.4, h: 0.65,
      fontSize: 11, color: C.muted, fontFace: FONT_B, italic: true, margin: 0,
    });
  });
  // 闭环示意
  slide.addShape(pres.shapes.OVAL, {
    x: 7.2, y: 1.3, w: 2.3, h: 2.3,
    fill: { color: C.deep, transparency: 15 },
    line: { color: C.teal, width: 2 },
  });
  slide.addText("反思闭环", {
    x: 7.5, y: 2.0, w: 1.7, h: 0.4,
    fontSize: 13, bold: true, color: C.deep, align: "center", margin: 0,
  });
  slide.addText("目标→分解→工具→记忆→RAG", {
    x: 7.35, y: 2.45, w: 2.0, h: 0.5,
    fontSize: 9, color: C.muted, align: "center", margin: 0,
  });
  addQuote(slide, "Agentic = LLM + 规划 + 工具 + RAG 记忆 + 反思闭环", 4.85, pres, 9.0);
  addSlideNumber(slide, 5, pres);
  slide.addNotes(NOTES[4]);
}

// ── 第 6 页 · AI 两维度进化 ──
{
  const slide = pres.addSlide();
  addHeaderBar(slide, "AI 进化的两个维度", pres);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.0, w: 4.3, h: 3.8,
    fill: { color: C.white },
    line: { color: C.teal, width: 1 },
    shadow: makeShadow(),
  });
  slide.addText("维度一：大模型（LLM）在进化", {
    x: 0.65, y: 1.1, w: 4, h: 0.4,
    fontSize: 14, bold: true, color: C.deep, fontFace: FONT_H, margin: 0,
  });
  slide.addText([
    { text: "多模态", options: { bullet: true, breakLine: true } },
    { text: "文本 → 图 / 音 / 视频 — 扫描件、会议录音可入库", options: { bullet: true, breakLine: true } },
    { text: "Tools 工具调用", options: { bullet: true, breakLine: true } },
    { text: "原生 function calling — 与 Agent 编排更顺滑", options: { bullet: true, breakLine: true } },
    { text: "Think 深度思考", options: { bullet: true, breakLine: true } },
    { text: "推理链、慢思考 — 复杂调度质量提升", options: { bullet: true } },
  ], { x: 0.7, y: 1.55, w: 3.9, h: 3.0, fontSize: 11, color: C.text, fontFace: FONT_B });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.2, y: 1.0, w: 4.3, h: 3.8,
    fill: { color: C.midnight },
    line: { color: C.mint, width: 1 },
  });
  slide.addText("维度二：智能体系统在进化", {
    x: 5.35, y: 1.1, w: 4, h: 0.4,
    fontSize: 14, bold: true, color: C.ice, fontFace: FONT_H, margin: 0,
  });
  slide.addText([
    { text: "大小模型协作", options: { bullet: true, breakLine: true } },
    { text: "小模型预处理 / 大模型推理 / 专业模型 OCR·ASR", options: { bullet: true, breakLine: true } },
    { text: "私域数据接入 — RAG 成为标配", options: { bullet: true, breakLine: true } },
    { text: "工具库扩展 — MCP、API、技能包", options: { bullet: true, breakLine: true } },
    { text: "经验沉淀 — Wiki、标签、知识图谱", options: { bullet: true } },
  ], { x: 5.4, y: 1.55, w: 3.9, h: 3.0, fontSize: 11, color: C.ice, fontFace: FONT_B });
  slide.addText("模型月月新，但企业不应把战略押在追榜单上", {
    x: 0.5, y: 5.0, w: 9, h: 0.35,
    fontSize: 12, italic: true, color: C.muted, align: "center", fontFace: FONT_B, margin: 0,
  });
  addSlideNumber(slide, 6, pres);
  slide.addNotes(NOTES[5]);
}

// ── 第 7 页 · Gartner 视角 ──
{
  const slide = pres.addSlide();
  addHeaderBar(slide, "企业 AI 落地：Gartner 视角下的现实", pres);
  const rows = [
    [
      { text: "过去", options: { fill: { color: C.muted }, color: C.white, bold: true } },
      { text: "现在", options: { fill: { color: C.teal }, color: C.white, bold: true } },
    ],
    ["追逐最新大模型榜单", "数据资产化 + 知识工程 + Agent 编排"],
    ["POC 演示「能聊天」", "生产环境「能溯源、能授权、能运维」"],
  ];
  slide.addTable(rows, {
    x: 0.5, y: 1.0, w: 9, h: 1.1,
    fontSize: 12, fontFace: FONT_B,
    border: { pt: 0.5, color: C.ice },
    colW: [4.5, 4.5],
    autoPage: false,
  });
  const pains = [
    { t: "数据沉睡", d: "70–90% 非结构化数据 AI 不可读" },
    { t: "数据孤岛", d: "多系统、多格式，精力耗在搬运" },
    { t: "治理缺失", d: "谁可见、哪版为准、能否审计" },
  ];
  pains.forEach((p, i) => {
    const x = 0.5 + i * 3.1;
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.35, w: 2.85, h: 1.5,
      fill: { color: C.white },
      line: { color: C.coral, width: 1 },
      shadow: makeShadow(),
    });
    slide.addText(p.t, {
      x: x + 0.15, y: 2.5, w: 2.55, h: 0.4,
      fontSize: 14, bold: true, color: C.coral, fontFace: FONT_H, margin: 0,
    });
    slide.addText(p.d, {
      x: x + 0.15, y: 2.95, w: 2.55, h: 0.75,
      fontSize: 11, color: C.text, fontFace: FONT_B, margin: 0,
    });
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 4.15, w: 9, h: 0.85,
    fill: { color: C.deep },
    line: { color: C.deep, width: 0 },
  });
  slide.addText("企业 AI 价值 = 私域数据质量 × RAG/图谱能力 × Agent 编排 × 安全治理", {
    x: 0.65, y: 4.35, w: 8.7, h: 0.5,
    fontSize: 14, bold: true, color: C.white, align: "center", fontFace: FONT_H, margin: 0,
  });
  addSlideNumber(slide, 7, pres);
  slide.addNotes(NOTES[6]);
}

// ── 第 8 页 · RAG ──
{
  const slide = pres.addSlide();
  addHeaderBar(slide, "RAG 是什么？在企业 Agent 中的位置", pres);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.0, w: 3.8, h: 2.0,
    fill: { color: C.white },
    line: { color: C.coral, width: 1 },
  });
  slide.addText("RAG 不是什么", {
    x: 0.65, y: 1.1, w: 3.5, h: 0.35,
    fontSize: 13, bold: true, color: C.coral, fontFace: FONT_H, margin: 0,
  });
  slide.addText([
    { text: "不是「把 PDF 扔进向量库」就完事", options: { bullet: true, breakLine: true } },
    { text: "不是 fine-tuning 微调的万能替代", options: { bullet: true } },
  ], { x: 0.7, y: 1.5, w: 3.5, h: 1.3, fontSize: 11, color: C.text, fontFace: FONT_B });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 4.5, y: 1.0, w: 5.0, h: 2.0,
    fill: { color: C.teal, transparency: 10 },
    line: { color: C.teal, width: 1 },
  });
  slide.addText("RAG 是什么", {
    x: 4.65, y: 1.1, w: 4.7, h: 0.35,
    fontSize: 13, bold: true, color: C.deep, fontFace: FONT_H, margin: 0,
  });
  slide.addText("检索增强生成：从授权资料库召回证据，再让模型基于证据回答。", {
    x: 4.7, y: 1.5, w: 4.6, h: 1.3,
    fontSize: 12, color: C.text, fontFace: FONT_B, margin: 0,
  });
  const matRows = [
    [
      { text: "层级", options: { fill: { color: C.deep }, color: C.white, bold: true } },
      { text: "能力", options: { fill: { color: C.deep }, color: C.white, bold: true } },
      { text: "典型特征", options: { fill: { color: C.deep }, color: C.white, bold: true } },
    ],
    ["L1 基础", "分块 + 向量检索 + 引用", "能答，召回率一般"],
    ["L2 增强", "混合检索、Rerank、查询扩展", "中文长句、文件名加权"],
    ["L3 知识工程", "Wiki 互链、标签图谱、主题页", "知识可演进、可关联"],
    ["L4 Agentic", "检索 → 判断不足 → 再检索", "与 Agent 规划闭环"],
  ];
  slide.addTable(matRows, {
    x: 0.5, y: 3.2, w: 9, h: 1.7,
    fontSize: 10, fontFace: FONT_B,
    border: { pt: 0.5, color: C.ice },
    colW: [1.2, 2.8, 5.0],
    autoPage: false,
  });
  slide.addText("类比：开卷考试 — 模型是考生，RAG 是企业参考资料", {
    x: 0.5, y: 5.05, w: 9, h: 0.35,
    fontSize: 11, italic: true, color: C.muted, align: "center", fontFace: FONT_B, margin: 0,
  });
  addSlideNumber(slide, 8, pres);
  slide.addNotes(NOTES[7]);
}

// ── 第 9 页 · 钉！定位 ──
{
  const slide = pres.addSlide();
  addHeaderBar(slide, "钉！定位：Data + AI 平台", pres, true);
  slide.addText("钉！ = 企业私域知识的采集、治理、检索与 Agent 技能交付平台", {
    x: 0.5, y: 1.05, w: 9, h: 0.55,
    fontSize: 16, bold: true, color: C.ice, fontFace: FONT_H, margin: 0,
  });
  const layers = [
    { l: "Agent 层", d: "钉技能 · 库内检索 · 文献入库 · Wiki 体检", c: C.mint },
    { l: "知识层", d: "RAG 检索 · Wiki 互链 · 标签图谱 · 混合检索", c: C.teal },
    { l: "数据层", d: "多源摄取 · 资料笔记 · 向量索引 · 工作空间隔离", c: C.deep },
  ];
  layers.forEach((ly, i) => {
    const y = 1.2 + i * 0.72;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 1.2, y, w: 7.6, h: 0.62,
      fill: { color: ly.c, transparency: i === 0 ? 0 : 15 },
      line: { color: ly.c, width: 1 },
    });
    slide.addText(ly.l, {
      x: 1.35, y: y + 0.1, w: 1.4, h: 0.35,
      fontSize: 13, bold: true, color: C.white, fontFace: FONT_H, margin: 0,
    });
    slide.addText(ly.d, {
      x: 2.85, y: y + 0.12, w: 5.7, h: 0.45,
      fontSize: 11, color: C.white, fontFace: FONT_B, margin: 0,
    });
  });
  const rows = [
    [
      { text: "企业痛点", options: { fill: { color: C.deep }, color: C.white, bold: true } },
      { text: "钉！回答", options: { fill: { color: C.deep }, color: C.white, bold: true } },
    ],
    ["资料散、格式杂", "统一摄取 → 资料笔记 → 可检索语料"],
    ["怕 AI 胡编", "RAG + workspace 隔离与引用溯源"],
    ["Agent 难落地", "规范化技能包，开箱即用"],
    ["知识不进化", "Wiki + 标签图谱，越用越厚"],
  ];
  slide.addTable(rows, {
    x: 0.5, y: 3.55, w: 9, h: 1.55,
    fontSize: 9, fontFace: FONT_B,
    border: { pt: 0.5, color: C.ice },
    colW: [2.2, 6.8],
    rowH: 0.32,
    autoPage: false,
  });
  addSlideNumber(slide, 9, pres);
  slide.addNotes(NOTES[8]);
}

// ── 第 10 页 · 六大能力 ──
{
  const slide = pres.addSlide();
  addHeaderBar(slide, "钉！六大平台能力", pres);
  const caps = [
    ["1", "云原生架构", "容器化、PostgreSQL + 消息队列 + 索引服务", "易部署、易扩容"],
    ["2", "可组装架构", "摄取、索引、检索、Wiki、Agent API 解耦", "按场景拼装"],
    ["3", "一站式交付", "上传 → 提取笔记 → 向量索引 → Web/钉技能", "少自建 RAG 管线"],
    ["4", "统一治理", "工作空间隔离、ACL、操作日志、API Key", "合规可审计"],
    ["5", "规范化技能", "库内检索、文献入库、Wiki 体检等 Skill", "Agent 开箱即用"],
    ["6", "2AI 标准化文档", "面向人与 AI 双消费的 Markdown 语料", "资料可演进、可互链"],
  ];
  const rows = [
    [
      { text: "#", options: { fill: { color: C.deep }, color: C.white, bold: true } },
      { text: "能力", options: { fill: { color: C.deep }, color: C.white, bold: true } },
      { text: "内涵", options: { fill: { color: C.deep }, color: C.white, bold: true } },
      { text: "听众可感知价值", options: { fill: { color: C.deep }, color: C.white, bold: true } },
    ],
    ...caps,
  ];
  slide.addTable(rows, {
    x: 0.35, y: 1.0, w: 9.3, h: 4.0,
    fontSize: 9, fontFace: FONT_B,
    border: { pt: 0.5, color: C.ice },
    colW: [0.4, 1.3, 4.5, 3.1],
    rowH: 0.42,
    autoPage: false,
  });
  addSlideNumber(slide, 10, pres);
  slide.addNotes(NOTES[9]);
}

// ── 第 11 页 · 知识飞轮 ──
{
  const slide = pres.addSlide();
  addHeaderBar(slide, "知识如何「进化」：钉！差异化", pres);
  const steps = ["上传", "资料笔记", "向量索引", "Wiki 互链", "标签图谱", "Agent 检索"];
  steps.forEach((s, i) => {
    const x = 0.4 + i * 1.55;
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: 1.15, w: 1.35, h: 0.7,
      fill: { color: i % 2 === 0 ? C.teal : C.deep },
      line: { color: C.teal, width: 0.5 },
    });
    slide.addText(s, {
      x, y: 1.3, w: 1.35, h: 0.4,
      fontSize: 9, bold: true, color: C.white, align: "center", fontFace: FONT_B, margin: 0,
    });
    if (i < steps.length - 1) {
      slide.addText("→", {
        x: x + 1.3, y: 1.35, w: 0.3, h: 0.35,
        fontSize: 14, color: C.mint, align: "center", margin: 0,
      });
    }
  });
  slide.addShape(pres.shapes.OVAL, {
    x: 8.5, y: 1.0, w: 1.0, h: 1.0,
    fill: { color: C.mint, transparency: 30 },
    line: { color: C.mint, width: 2 },
  });
  slide.addText("↻", {
    x: 8.5, y: 1.2, w: 1.0, h: 0.6,
    fontSize: 28, color: C.deep, align: "center", margin: 0,
  });
  slide.addText([
    { text: "资料笔记流水线", options: { bullet: true, breakLine: true } },
    { text: "PDF / Office / 图片 OCR → 统一 Markdown", options: { bullet: true, breakLine: true } },
    { text: "Wiki 互链：[[file:id]] / [[wiki:slug]]，概念页编译与体检", options: { bullet: true, breakLine: true } },
    { text: "标签关系图：共现力导向图，支持 AND 筛选", options: { bullet: true, breakLine: true } },
    { text: "混合检索：向量语义 + FTS 全文，可评测调优", options: { bullet: true } },
  ], { x: 0.5, y: 2.2, w: 5.5, h: 2.5, fontSize: 12, color: C.text, fontFace: FONT_B });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 6.2, y: 2.2, w: 3.3, h: 2.5,
    fill: { color: C.midnight },
    line: { color: C.teal, width: 1 },
  });
  slide.addText("知识飞轮", {
    x: 6.4, y: 2.35, w: 3, h: 0.35,
    fontSize: 14, bold: true, color: C.ice, fontFace: FONT_H, margin: 0,
  });
  slide.addText("越整理 · 越关联 · 越用越活", {
    x: 6.4, y: 2.85, w: 2.9, h: 0.5,
    fontSize: 16, bold: true, color: C.mint, fontFace: FONT_H, margin: 0,
  });
  slide.addText("知识不是静态仓库，而是进化的网状体系", {
    x: 6.4, y: 3.55, w: 2.9, h: 0.9,
    fontSize: 11, color: C.ice, fontFace: FONT_B, margin: 0,
  });
  addSlideNumber(slide, 11, pres);
  slide.addNotes(NOTES[10]);
}

// ── 第 12 页 · 业务收益 ──
{
  const slide = pres.addSlide();
  addHeaderBar(slide, "钉！带来的业务收益", pres);
  const benefits = [
    { t: "多源私域数据规范化", d: "网盘、邮件、项目文档 → 统一可检索语料" },
    { t: "可挖掘、可关联", d: "不只找文件，还能找关系 — 标签、Wiki、共引" },
    { t: "Agent 可信回答", d: "RAG 按工作空间与 ACL 过滤，回答可带出处" },
    { t: "人机协作闭环", d: "人整理 Wiki → 库变聪明 → Agent 更好用" },
  ];
  benefits.forEach((b, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = 0.5 + col * 4.7;
    const y = 1.1 + row * 1.75;
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 4.4, h: 1.5,
      fill: { color: C.white },
      line: { color: C.mint, width: 1.5 },
      shadow: makeShadow(),
    });
    slide.addText(b.t, {
      x: x + 0.2, y: y + 0.15, w: 4, h: 0.45,
      fontSize: 14, bold: true, color: C.deep, fontFace: FONT_H, margin: 0,
    });
    slide.addText(b.d, {
      x: x + 0.2, y: y + 0.65, w: 4, h: 0.7,
      fontSize: 11, color: C.muted, fontFace: FONT_B, margin: 0,
    });
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 4.75, w: 9, h: 0.55,
    fill: { color: C.deep, transparency: 10 },
    line: { color: C.teal, width: 0.5 },
  });
  slide.addText("典型场景：研发查规范 · 合规问制度 · 智能体库内搜 + 外网文献入库", {
    x: 0.65, y: 4.88, w: 8.7, h: 0.35,
    fontSize: 11, color: C.text, align: "center", fontFace: FONT_B, margin: 0,
  });
  addSlideNumber(slide, 12, pres);
  slide.addNotes(NOTES[11]);
}

// ── 第 13 页 · 安全 ──
{
  const slide = pres.addSlide();
  addHeaderBar(slide, "安全与合规：准入门槛", pres);
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 1.0, w: 4.3, h: 3.5,
    fill: { color: C.white },
    line: { color: C.deep, width: 1 },
    shadow: makeShadow(),
  });
  slide.addText("数据安全", {
    x: 0.65, y: 1.1, w: 4, h: 0.35,
    fontSize: 14, bold: true, color: C.deep, fontFace: FONT_H, margin: 0,
  });
  const dRows = [
    ["非公开数据不出域", "私有化部署 + 内网 RAG"],
    ["最小权限", "个人/共享工作空间、ACL 授权"],
    ["可审计", "操作日志、API Key 上下架、分享溯源"],
  ];
  dRows.forEach((r, i) => {
    const y = 1.55 + i * 0.85;
    slide.addText(r[0], {
      x: 0.7, y, w: 1.8, h: 0.35,
      fontSize: 11, bold: true, color: C.teal, fontFace: FONT_B, margin: 0,
    });
    slide.addText(r[1], {
      x: 2.55, y, w: 2.1, h: 0.7,
      fontSize: 10, color: C.text, fontFace: FONT_B, margin: 0,
    });
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.2, y: 1.0, w: 4.3, h: 3.5,
    fill: { color: C.midnight },
    line: { color: C.mint, width: 1 },
  });
  slide.addText("模型安全", {
    x: 5.35, y: 1.1, w: 4, h: 0.35,
    fontSize: 14, bold: true, color: C.ice, fontFace: FONT_H, margin: 0,
  });
  slide.addText([
    { text: "LLM 本地化", options: { bullet: true, breakLine: true } },
    { text: "Ollama 等内网推理，敏感内容不外发", options: { bullet: true, breakLine: true } },
    { text: "模型与数据解耦", options: { bullet: true, breakLine: true } },
    { text: "换模型不丢资料库；权限独立于模型", options: { bullet: true } },
  ], { x: 5.4, y: 1.55, w: 3.9, h: 2.5, fontSize: 11, color: C.ice, fontFace: FONT_B });
  // 盾牌装饰
  slide.addShape(pres.shapes.OVAL, {
    x: 8.0, y: 2.5, w: 1.2, h: 1.2,
    fill: { color: C.mint, transparency: 40 },
    line: { color: C.mint, width: 2 },
  });
  addQuote(slide, "安全不是 Agent 的附加项，而是准入门槛。", 4.75, pres, 9.0);
  addSlideNumber(slide, 13, pres);
  slide.addNotes(NOTES[12]);
}

// ── 第 14 页 · 成本 ──
{
  const slide = pres.addSlide();
  addHeaderBar(slide, "建设成本：如何算清账", pres);
  const rows = [
    [
      { text: "模式", options: { fill: { color: C.deep }, color: C.white, bold: true } },
      { text: "成本项", options: { fill: { color: C.deep }, color: C.white, bold: true } },
      { text: "特点", options: { fill: { color: C.deep }, color: C.white, bold: true } },
    ],
    ["云端 API", "按 Token 计费", "弹性好；需评估数据出境与长期费用"],
    ["本地部署", "GPU/CPU + 运维", "前期投入高；适合强合规、高并发"],
  ];
  slide.addTable(rows, {
    x: 0.5, y: 1.0, w: 9, h: 1.1,
    fontSize: 11, fontFace: FONT_B,
    border: { pt: 0.5, color: C.ice },
    colW: [1.5, 2.5, 5.0],
    autoPage: false,
  });
  slide.addText("常被忽略的隐性成本", {
    x: 0.5, y: 2.3, w: 4, h: 0.35,
    fontSize: 13, bold: true, color: C.coral, fontFace: FONT_H, margin: 0,
  });
  slide.addText([
    { text: "自建 RAG 管线（解析、分块、索引、评测）的人力", options: { bullet: true, breakLine: true } },
    { text: "多数据源对接与格式清洗", options: { bullet: true, breakLine: true } },
    { text: "Agent 技能维护与版本管理", options: { bullet: true } },
  ], { x: 0.5, y: 2.65, w: 4.5, h: 1.5, fontSize: 11, color: C.text, fontFace: FONT_B });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.2, y: 2.2, w: 4.3, h: 2.6,
    fill: { color: C.teal, transparency: 8 },
    line: { color: C.teal, width: 1 },
  });
  slide.addText("钉！私有化价值主张", {
    x: 5.35, y: 2.3, w: 4, h: 0.35,
    fontSize: 13, bold: true, color: C.deep, fontFace: FONT_H, margin: 0,
  });
  slide.addText([
    { text: "摊薄工程成本 — 摄取/索引/检索/Wiki/API 已产品化", options: { bullet: true, breakLine: true } },
    { text: "模型可替换 — 避免 vendor lock-in 厂商锁定", options: { bullet: true, breakLine: true } },
    { text: "规模经济 — 库越大，Agent 边际价值越高", options: { bullet: true } },
  ], { x: 5.4, y: 2.7, w: 4, h: 1.8, fontSize: 11, color: C.text, fontFace: FONT_B });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 4.55, w: 4.2, h: 0.7,
    fill: { color: C.muted, transparency: 20 },
    line: { color: C.muted, width: 0.5 },
  });
  slide.addText("自建 ≈ 6 个月", {
    x: 0.65, y: 4.7, w: 3.9, h: 0.4,
    fontSize: 14, bold: true, color: C.muted, align: "center", margin: 0,
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 5.0, y: 4.55, w: 4.5, h: 0.7,
    fill: { color: C.mint, transparency: 15 },
    line: { color: C.mint, width: 1 },
  });
  slide.addText("钉！试点 ≈ 4 周", {
    x: 5.15, y: 4.7, w: 4.2, h: 0.4,
    fontSize: 14, bold: true, color: C.deep, align: "center", margin: 0,
  });
  addSlideNumber(slide, 14, pres);
  slide.addNotes(NOTES[13]);
}

// ── 第 15 页 · 总结 ──
{
  const slide = pres.addSlide();
  slide.background = { color: C.midnight };
  slide.addText("总结与行动建议", {
    x: 0.5, y: 0.35, w: 9, h: 0.55,
    fontSize: 24, bold: true, color: C.white, fontFace: FONT_H, margin: 0,
  });
  const points = [
    "模型会换代，企业数据不会自动变聪明 — 资产化才是主战场",
    "Agent 的未来在 Agentic，但可信度在 RAG 与治理",
    "钉！不是又一个 Chatbot，而是让 Agent 站在企业知识之上",
  ];
  points.forEach((p, i) => {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 0.5, y: 1.05 + i * 0.75, w: 9, h: 0.6,
      fill: { color: C.deep, transparency: 30 },
      line: { color: C.teal, width: 0.5 },
    });
    slide.addText(String(i + 1), {
      x: 0.65, y: 1.15 + i * 0.75, w: 0.4, h: 0.4,
      fontSize: 16, bold: true, color: C.mint, margin: 0,
    });
    slide.addText(p, {
      x: 1.15, y: 1.12 + i * 0.75, w: 8.2, h: 0.5,
      fontSize: 13, color: C.ice, fontFace: FONT_B, margin: 0,
    });
  });
  slide.addText("建议试点路径（4 周）", {
    x: 0.5, y: 3.4, w: 4, h: 0.35,
    fontSize: 14, bold: true, color: C.mint, fontFace: FONT_H, margin: 0,
  });
  const weeks = [
    "第 1 周：选定知识空间 + 导入核心文档",
    "第 2 周：跑通资料笔记与语义检索，抽检引用",
    "第 3 周：接入 1 个钉技能场景",
    "第 4 周：评测检索效果，迭代标签与 Wiki",
  ];
  weeks.forEach((w, i) => {
    slide.addText(w, {
      x: 0.65, y: 3.8 + i * 0.38, w: 5.5, h: 0.35,
      fontSize: 11, color: C.ice, fontFace: FONT_B, margin: 0,
    });
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 6.0, y: 3.35, w: 3.5, h: 1.85,
    fill: { color: C.teal, transparency: 25 },
    line: { color: C.mint, width: 1 },
  });
  slide.addText("Q&A 预埋", {
    x: 6.15, y: 3.45, w: 3.2, h: 0.3,
    fontSize: 12, bold: true, color: C.white, fontFace: FONT_H, margin: 0,
  });
  slide.addText([
    { text: "RAG vs Fine-tuning？", options: { bullet: true, breakLine: true } },
    { text: "幻觉能降到 0 吗？", options: { bullet: true, breakLine: true } },
    { text: "小团队如何起步？", options: { bullet: true } },
  ], { x: 6.2, y: 3.8, w: 3.2, h: 1.3, fontSize: 10, color: C.ice, fontFace: FONT_B });
  slide.addText("欢迎交流试点方案与私有化部署评估", {
    x: 0.5, y: 5.15, w: 9, h: 0.35,
    fontSize: 12, color: C.mint, align: "center", fontFace: FONT_B, margin: 0,
  });
  addSlideNumber(slide, 15, pres);
  slide.addNotes(NOTES[14]);
}

pres.writeFile({ fileName: OUT }).then(() => {
  console.log("Generated:", OUT);
}).catch((err) => {
  console.error(err);
  process.exit(1);
});
