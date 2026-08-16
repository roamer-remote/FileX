import { marked } from 'marked'
import markedKatex from 'marked-katex-extension'

/** 笔记/资料预览共用 marked：GFM + KaTeX（HTML output，不输出 MathML） */
marked.setOptions({ breaks: true, gfm: true })
// marked.use 须在首次 marked.parse 之前调用；marked 为 ESM 单例，扩展对全项目生效
marked.use(
  markedKatex({
    throwOnError: false,
    output: 'html',
    // MinerU/OCR 笔记常见「点$...$的」、中文标点紧贴 $；标准模式要求 $ 前后空格/特定标点
    nonStandard: true,
  }),
)

export { marked as markedPreview }
