/** 可复现伪随机：同一 seed 始终产生相同序列（用于图布局，避免刷新后节点变椭圆/乱跳） */

export function hashString(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

export function createSeededRandom(seed: string | number): () => number {
  let state = typeof seed === "number" ? seed >>> 0 : hashString(seed)
  return () => {
    state = (state + 0x6d2b79f5) | 0
    let t = Math.imul(state ^ (state >>> 15), 1 | state)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
