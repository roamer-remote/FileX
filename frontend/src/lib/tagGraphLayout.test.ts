import { describe, expect, it } from "vitest"
import {
  countConnectedComponents,
  findConnectedComponents,
  layoutComponentForce,
  packComponentPositions,
} from "./tagGraphLayout"

describe("tagGraphLayout", () => {
  it("treats each isolated node as its own component", () => {
    const nodes = [
      { id: "a", name: "a", value: 1 },
      { id: "b", name: "b", value: 1 },
      { id: "c", name: "c", value: 1 },
    ]
    const links = [{ source: "a", target: "b", value: 1 }]
    expect(countConnectedComponents(nodes, links)).toBe(2)
    const comps = findConnectedComponents(nodes, links)
    expect(comps).toHaveLength(2)
    const solo = comps.find((c) => c.length === 1)
    expect(solo).toEqual(["c"])
  })

  it("single component is one group", () => {
    const nodes = [
      { id: "a", name: "a", value: 2 },
      { id: "b", name: "b", value: 1 },
    ]
    const links = [{ source: "a", target: "b", value: 1 }]
    expect(countConnectedComponents(nodes, links)).toBe(1)
  })

  it("packs two components to separated x positions", () => {
    const nodes = [
      { id: "t1", name: "t1", value: 1 },
      { id: "t2", name: "t2", value: 1 },
      { id: "t3", name: "t3", value: 1 },
    ]
    const links = [{ source: "t1", target: "t2", value: 1 }]
    const packed = packComponentPositions({ nodes, links }, 800, 500, () => 24)
    const x1 = packed.get("t1")!.x
    const x3 = packed.get("t3")!.x
    expect(Math.abs(x1 - x3)).toBeGreaterThan(100)
  })

  it("layoutComponentForce returns origin for singleton", () => {
    const m = layoutComponentForce(["only"], [])
    expect(m.get("only")).toEqual({ x: 0, y: 0 })
  })
})
