/** 与 backend/utils/wiki_slug.normalize_wiki_slug 对齐的前端预览 */
export function normalizeWikiSlug(raw: string): string {
  let s = (raw || "").trim().normalize("NFKC")
  if (!s) return ""
  s = s.toLowerCase()
  s = s.replace(/[\s_]+/g, "-")
  s = [...s].filter((c) => c === "-" || /\p{L}/u.test(c) || /\p{N}/u.test(c)).join("")
  s = s.replace(/-+/g, "-").replace(/^-|-$/g, "")
  return s.slice(0, 128)
}
