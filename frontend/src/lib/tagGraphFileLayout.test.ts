import { describe, expect, it } from "vitest"
import { packFileClusterPositions } from "./tagGraphFileLayout"

describe("packFileClusterPositions", () => {
  it("places two file clusters left and right", () => {
    const data = {
      nodes: [
        { id: "t1", name: "t1", value: 2 },
        { id: "t2", name: "t2", value: 1 },
        { id: "t3", name: "t3", value: 1 },
      ],
      links: [
        { source: "t1", target: "t2", value: 1 },
        { source: "t1", target: "t3", value: 1 },
      ],
      file_groups: [
        { file_id: 1, label: "a.txt", tags: ["t1", "t2"] },
        { file_id: 2, label: "b.txt", tags: ["t1", "t3"] },
      ],
    }
    const pos = packFileClusterPositions(data, 800, 500, () => 40)
    expect(pos.size).toBe(3)
    const t1 = pos.get("t1")!
    const t2 = pos.get("t2")!
    const t3 = pos.get("t3")!
    expect(Math.hypot(t2.x - t3.x, t2.y - t3.y)).toBeGreaterThan(100)
  })

  it("pack is deterministic across calls", () => {
    const data = {
      nodes: [
        { id: "t1", name: "t1", value: 2 },
        { id: "t2", name: "t2", value: 1 },
      ],
      links: [{ source: "t1", target: "t2", value: 1 }],
      file_groups: [{ file_id: 1, label: "a.txt", tags: ["t1", "t2"] }],
    }
    const a = packFileClusterPositions(data, 800, 500, () => 40)
    const b = packFileClusterPositions(data, 800, 500, () => 40)
    expect([...a.entries()].sort()).toEqual([...b.entries()].sort())
  })

  it("merges shared tag to one coordinate", () => {
    const data = {
      nodes: [{ id: "shared", name: "shared", value: 2 }],
      links: [],
      file_groups: [
        { file_id: 1, label: "a", tags: ["shared", "a"] },
        { file_id: 2, label: "b", tags: ["shared", "b"] },
      ],
    }
    const pos = packFileClusterPositions(data, 600, 400, () => 32)
    expect(pos.size).toBe(3)
    expect(pos.has("shared")).toBe(true)
  })
})
