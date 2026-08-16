import { describe, expect, it } from "vitest"
import { injectAnchorSpans, mergeNoteAnchorHits } from "./mdTagAnchors"

describe("injectAnchorSpans", () => {
  it("在标签词前插入空 span，不包裹 wiki 链接语法", () => {
    const raw = "[[个人简历|88]]"
    const out = injectAnchorSpans(raw, [
      { anchor_id: "fba-1-abc-1", start: 2, end: 6, tag: "个人简历" },
    ])
    expect(out).toBe("[[<span id=\"fba-1-abc-1\"></span>个人简历|88]]")
  })

  it("偏移与标签不一致时跳过", () => {
    const raw = "alpha beta"
    const out = injectAnchorSpans(raw, [
      { anchor_id: "fba-1-x-1", start: 0, end: 5, tag: "wrong" },
    ])
    expect(out).toBe("alpha beta")
  })
})

  it("mergeNoteAnchorHits 含 wiki 互链偏移", () => {
    const hits = mergeNoteAnchorHits([], [
      { anchor_id: "fwl-1-abc-1", start_offset: 0, end_offset: 14 },
    ])
    const out = injectAnchorSpans("[[file:123]] tail", hits)
    expect(out).toContain('<span id="fwl-1-abc-1"></span>')
  })
