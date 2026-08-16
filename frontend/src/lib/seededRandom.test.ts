import { describe, expect, it } from "vitest"
import { createSeededRandom } from "./seededRandom"
import { layoutComponentForce } from "./tagGraphLayout"

describe("seededRandom", () => {
  it("same seed yields same sequence", () => {
    const a = createSeededRandom("test")
    const b = createSeededRandom("test")
    expect([a(), a(), a()]).toEqual([b(), b(), b()])
  })
})

describe("layoutComponentForce determinism", () => {
  it("same members produce identical positions", () => {
    const members = ["a", "b", "c"]
    const links = [
      { source: "a", target: "b", value: 1 },
      { source: "b", target: "c", value: 1 },
    ]
    const m1 = layoutComponentForce(members, links)
    const m2 = layoutComponentForce(members, links)
    for (const k of members) {
      expect(m1.get(k)).toEqual(m2.get(k))
    }
  })
})
