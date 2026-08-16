#!/usr/bin/env python3
# Copyright (c) 2026 徐泽宇
"""Skill module regression evaluator.

验证 ding skill module 的 API 端点引用与 curl 示例与 filex-agent-api.md 一致。
运行: cd backend && python -m scripts.skill_eval [--verbose]

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent  # backend/
SKILL_DIR = ROOT.parent / "skill" / "ding"  # repo root
MODULES_DIR = SKILL_DIR / "modules"
API_REF = SKILL_DIR / "references" / "filex-agent-api.md"
BOOTSTRAP = SKILL_DIR / "SKILL.md"
CHANGELOG_PATH = SKILL_DIR / "skill.changelog.json"
EVALS_PATH = SKILL_DIR / "evals" / "evals.json"

HARD_PRINCIPLES_MAX_LINES = 12
REQUIRED_BEHAVIOR_TAGS = {
    "kb_first",
    "no_hit_confirm",
    "explicit_external",
    "negative_gate",
    "forged_excerpt",
    "prompt_injection",
    "url_ingest_interrupt",
    "mcp_cli_equivalence",
    "humanize_immutable",
    "deleted_file_cache",
}
EXPECTED_AUTO_HEADER = (
    "file_id | original_name | mime_type | has_md | tags | created_at"
)


def configure_skill_dir(skill_dir: Path) -> None:
    """Point every evaluator check at one explicit Ding skill directory."""
    global SKILL_DIR, MODULES_DIR, API_REF, BOOTSTRAP, CHANGELOG_PATH, EVALS_PATH
    SKILL_DIR = skill_dir.resolve()
    MODULES_DIR = SKILL_DIR / "modules"
    API_REF = SKILL_DIR / "references" / "filex-agent-api.md"
    BOOTSTRAP = SKILL_DIR / "SKILL.md"
    CHANGELOG_PATH = SKILL_DIR / "skill.changelog.json"
    EVALS_PATH = SKILL_DIR / "evals" / "evals.json"


def load_file(path: Path) -> str:
    if not path.is_file():
        print(f"  ✗ 文件不存在: {path}")
        sys.exit(1)
    return path.read_text(encoding="utf-8")


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, f"文件不存在: {path.relative_to(SKILL_DIR)}"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"JSON 解析错误: {path.name}: {exc}"
    if not isinstance(value, dict):
        return None, f"JSON 根节点必须是 object: {path.name}"
    return value, None


def _frontmatter(text: str) -> str:
    match = re.match(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", text, re.DOTALL)
    return match.group(1) if match else ""


def test_trigger_description_scope() -> list[str]:
    """The globally visible description must not hijack ordinary verbs."""
    frontmatter = _frontmatter(load_file(BOOTSTRAP))
    name_match = re.search(r"^name:\s*([^\n]+)$", frontmatter, re.MULTILINE)
    if not name_match or name_match.group(1).strip() != "ding":
        return ["SKILL.md frontmatter 必须保留 name: ding"]
    description_match = re.search(
        r"^description:\s*(.+?)(?=\n[a-zA-Z_][\w-]*:|\Z)",
        frontmatter,
        re.MULTILINE | re.DOTALL,
    )
    description = " ".join(description_match.group(1).split()) if description_match else ""
    if not description:
        return ["SKILL.md frontmatter 缺少 description"]

    broad_patterns = (
        r"查/问/找/总结.*(?:全部|全局|即使|默认)",
        r"(?:全部|任何|普通).{0,8}查/问/找/总结",
        r"查、问、找、总结.*(?:全部|全局|即使|默认)",
    )
    if any(re.search(pattern, description) for pattern in broad_patterns):
        return ["description 含全局普通动词触发；须限定 /ding、钉/FileX 或安装备忘上下文"]
    required_context = ("/ding", "FileX", "钉")
    if not all(token in description for token in required_context):
        return ["description 未明确 /ding、钉与 FileX 触发上下文"]
    return ["✓ description 触发边界已收窄"]


def test_required_api_contracts() -> list[str]:
    text = load_file(API_REF)
    errors: list[str] = []
    for endpoint in ("/query-understand", "/fulltext-reason"):
        if endpoint not in text:
            errors.append(f"缺少端点: {endpoint}")
    if EXPECTED_AUTO_HEADER not in text:
        errors.append(
            "AUTO 表头与后端契约不一致；应为 " + EXPECTED_AUTO_HEADER
        )
    return errors or ["✓ 查询理解、全文推理与 AUTO 表头契约完整"]


def _iter_runtime_markdown() -> list[Path]:
    paths: set[Path] = set()
    for relative in ("SKILL.md", "README.md", "agent/README.md"):
        path = SKILL_DIR / relative
        if path.is_file():
            paths.add(path)
    for directory in (MODULES_DIR, SKILL_DIR / "references"):
        if directory.is_dir():
            paths.update(path for path in directory.rglob("*.md") if path.is_file())
    return sorted(paths)


def _local_markdown_targets(text: str) -> list[str]:
    targets: list[str] = []
    for raw in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", text):
        target = raw.strip().split(maxsplit=1)[0].strip("<>")
        if (
            not target
            or target in {"url", "…"}
            or target.startswith(("#", "http://", "https://", "mailto:"))
        ):
            continue
        targets.append(unquote(target.split("#", 1)[0].split("?", 1)[0]))
    return targets


def test_runtime_markdown_links() -> list[str]:
    errors: list[str] = []
    skill_root = SKILL_DIR.resolve()
    for path in _iter_runtime_markdown():
        for target in _local_markdown_targets(load_file(path)):
            resolved = (path.parent / target).resolve()
            try:
                relative = resolved.relative_to(skill_root)
            except ValueError:
                errors.append(
                    f"{path.relative_to(SKILL_DIR)}: Runtime 链接越出技能包: {target}"
                )
                continue
            if not resolved.exists():
                errors.append(
                    f"{path.relative_to(SKILL_DIR)}: 本地 Markdown 链接不存在: {relative}"
                )
    return errors or ["✓ Runtime Markdown 本地链接全部自包含且存在"]


def test_kb_search_execution_order() -> list[str]:
    text = load_file(MODULES_DIR / "kb-search.md")
    errors: list[str] = []
    if not re.search(r"^## 目录\s*$", text, re.MULTILINE):
        errors.append("kb-search.md 缺少 TOC（## 目录）")
    positions: list[int] = []
    for stage in range(7):
        match = re.search(rf"^## {stage}(?:\.|\s)", text, re.MULTILINE)
        if not match:
            errors.append(f"kb-search.md 缺少执行阶段 {stage}")
        else:
            positions.append(match.start())
    if len(positions) == 7 and positions != sorted(positions):
        errors.append("kb-search.md 执行阶段未按 0→6 排列")
    return errors or ["✓ kb-search TOC 与 0→6 执行顺序有效"]


def _parse_requirements(path: Path) -> dict[str, list[tuple[str, str]]]:
    requirements: dict[str, list[tuple[str, str]]] = {}
    for raw in load_file(path).splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith(("-", "http://", "https://")):
            continue
        name_match = re.match(r"([A-Za-z0-9_.-]+)", line)
        if not name_match:
            continue
        name = name_match.group(1).lower().replace("_", "-")
        specifiers = re.findall(r"(>=|<=|==|~=|>|<)\s*([^,;\s]+)", line)
        requirements[name] = specifiers
    return requirements


def _has_lower_and_upper(specifiers: list[tuple[str, str]]) -> bool:
    has_lower = any(operator in {">", ">=", "~=", "=="} for operator, _ in specifiers)
    has_upper = any(operator in {"<", "<=", "=="} for operator, _ in specifiers)
    return has_lower and has_upper


def test_shared_requirement_bounds() -> list[str]:
    first_path = SKILL_DIR / "agent" / "requirements.txt"
    second_path = SKILL_DIR / "agent" / "requirements-langgraph.example.txt"
    first = _parse_requirements(first_path)
    second = _parse_requirements(second_path)
    shared = set(first).intersection(second)
    errors: list[str] = []
    for name in sorted(shared):
        if not _has_lower_and_upper(first[name]) or not _has_lower_and_upper(second[name]):
            errors.append(
                f"requirements 共享依赖缺少兼容上下界: {name}"
            )
            continue
        first_bounds = set(first[name])
        second_bounds = set(second[name])
        if first_bounds != second_bounds:
            errors.append(
                f"requirements 共享依赖上下界不一致: {name} "
                f"({first[name]} != {second[name]})"
            )
    if not shared:
        errors.append("requirements 未发现共享依赖，无法验证联合兼容性")
    return errors or [f"✓ requirements 共享依赖上下界一致: {', '.join(sorted(shared))}"]


def test_evals_schema_and_coverage() -> list[str]:
    data, load_error = _load_json(EVALS_PATH)
    if load_error:
        return [f"evals.json {load_error}"]
    assert data is not None
    errors: list[str] = []
    if data.get("skill_name") != "ding":
        errors.append("evals.json skill_name 必须为 ding")
    triggers = data.get("trigger_cases")
    behaviors = data.get("behavior_cases")
    if not isinstance(triggers, list):
        triggers = []
        errors.append("evals.json trigger_cases 必须为数组")
    if not isinstance(behaviors, list):
        behaviors = []
        errors.append("evals.json behavior_cases 必须为数组")
    if len(triggers) < 20:
        errors.append(f"trigger eval 不足 20 条: {len(triggers)}")
    else:
        positive = sum(case.get("should_trigger") is True for case in triggers if isinstance(case, dict))
        negative = sum(case.get("should_trigger") is False for case in triggers if isinstance(case, dict))
        if positive < 8 or negative < 8:
            errors.append(
                f"trigger eval 正负近邻不均衡: should={positive}, should_not={negative}"
            )
    if len(behaviors) < 10:
        errors.append(f"behavior eval 不足 10 条: {len(behaviors)}")
    observed_tags = {
        str(tag)
        for case in behaviors
        if isinstance(case, dict)
        for tag in case.get("tags", [])
    }
    missing_tags = sorted(REQUIRED_BEHAVIOR_TAGS - observed_tags)
    if missing_tags:
        errors.append("behavior eval 缺少必选标签: " + ", ".join(missing_tags))
    for index, case in enumerate(behaviors):
        if not isinstance(case, dict):
            errors.append(f"behavior eval #{index} 必须为 object")
            continue
        for key in ("id", "query", "expected", "fixture", "assertions"):
            if key not in case:
                errors.append(f"behavior eval {case.get('id', index)} 缺少 {key}")
    return errors or [
        f"✓ eval coverage: trigger={len(triggers)}, behavior={len(behaviors)}, required_tags={len(REQUIRED_BEHAVIOR_TAGS)}"
    ]


def test_all_bootstrap_entries_exist() -> list[str]:
    """Bootstrap entry point must reference only existing modules."""
    errors: list[str] = []
    text = load_file(BOOTSTRAP)
    # Find all module references: modules/xxx.md
    refs = set(re.findall(r"`?modules/([a-z0-9_-]+)\.md`?", text))
    for ref in sorted(refs):
        if not (MODULES_DIR / f"{ref}.md").is_file():
            errors.append(f"bootstrap 引用了不存在的 module: modules/{ref}.md")
    if errors:
        return errors
    return ["✓ Bootstrap 引用全部有效"]


def test_module_curl_syntax() -> list[str]:
    """All curl examples in modules must be syntactically valid."""
    errors: list[str] = []
    for path in sorted(MODULES_DIR.glob("*.md")):
        text = load_file(path)
        curl_blocks = re.findall(r"```bash\n(.*?)```", text, re.DOTALL)
        for block in curl_blocks:
            for line in block.strip().split("\n"):
                line = line.strip()
                if line.startswith("curl ") and "--data-urlencode" in line:
                    # Verify paired quotes
                    if line.count('"') % 2 != 0:
                        errors.append(f"{path.name}: 引号不配对: {line[:60]}...")
                elif line.startswith("curl ") and "-d '" in line and line.count("'") % 2 != 0:
                    errors.append(f"{path.name}: 单引号不配对: {line[:60]}...")
    if errors:
        return errors
    return ["✓ 所有 curl 语法检查通过"]


def test_api_endpoint_coverage() -> list[str]:
    """Every /api/ endpoint in modules must appear in API reference (best-effort match)."""
    errors: list[str] = []
    api_text = load_file(API_REF)

    def _clean(p: str) -> str:
        p = p.split("?")[0].rstrip("/")
        p = re.sub(r"\{[^}]+\}", "{var}", p)
        return p

    # Build reference set — mostly relative paths from tables
    ref_paths: set[str] = set()
    ref_paths |= set(re.findall(r"\|\s*(?:GET|POST|PUT|DELETE|PATCH)\s*\|\s*`(/[a-z][^`]+)`", api_text))
    ref_paths |= set(re.findall(r"\*\*`(/[^`*]+)`\*\*", api_text))
    ref_paths |= set(re.findall(r"`(/api/[a-zA-Z0-9_\-/{}.]+)`", api_text))
    ref_paths |= set(re.findall(r"\{ORIGIN\}(/api/[^\s`\]]+)", api_text))
    cleaned_ref = {_clean(p) for p in ref_paths if p.startswith("/")}

    for path in sorted(MODULES_DIR.glob("*.md")):
        text = load_file(path)
        eps: set[str] = set()
        eps |= set(re.findall(r'["`]?(/api/[a-zA-Z0-9_\-/{}]+)["`?]', text))
        eps |= set(re.findall(r"\$FILEX_ORIGIN(/api/[a-zA-Z0-9_\-/{}]+)", text))
        eps |= set(re.findall(r"\{ORIGIN\}(/api/[a-zA-Z0-9_\-/{}]+)", text))
        eps |= set(re.findall(r'"\$FILEX_ORIGIN(/api/[a-zA-Z0-9_\-/{}]+)', text))

        for ep in eps:
            ep_clean = _clean(ep)
            # Strategy: strip /api/{section}/ to get relative form, match against ref
            found = False
            if ep_clean.startswith("/api/"):
                parts = ep_clean[len("/api/"):].split("/", 1)
                if len(parts) == 2 and parts[0]:
                    # /api/{section}/{rest} -> /{rest}
                    relative = "/" + parts[1]
                    found = _clean(relative) in cleaned_ref
            if not found and ep_clean.startswith("/api/"):
                # Fallback: strip just /api/ prefix
                found = ep_clean[len("/api"):] in cleaned_ref
            # Also try exact match
            if not found:
                found = ep_clean in cleaned_ref
            if not found:
                errors.append(f"{path.name}: 端点 '{ep}' 在 API 参考中未找到")
    if errors:
        return errors
    return ["✓ API 端点引用全部在参考文档中有定义"]


def test_module_cross_references() -> list[str]:
    """Each module referenced in routing must exist."""
    errors: list[str] = []
    routing_text = load_file(MODULES_DIR / "routing.md")
    module_refs = set(re.findall(r"\*\*(filex-[a-z_-]+|filebox-[a-z_-]+)\*\*", routing_text))

    # Map subflow IDs to module filenames (e.g., filex-kb-search -> kb-search.md)
    def _subflow_to_filename(sf: str) -> str:
        return sf.replace("filex-", "").replace("filebox-", "") + ".md"

    for ref in sorted(module_refs):
        filename = _subflow_to_filename(ref)
        mod_path = MODULES_DIR / filename
        if not mod_path.is_file():
            errors.append(f"routing.md 引用子流程 '{ref}' 但对应 module '{filename}' 不存在")
    if errors:
        return errors
    return ["✓ routing 模块引用全部存在"]


def test_changelog_schema() -> list[str]:
    """skill.changelog.json must have valid structure."""
    errors: list[str] = []
    if not CHANGELOG_PATH.is_file():
        return ["skill.changelog.json 不存在"]
    try:
        data = json.loads(CHANGELOG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"skill.changelog.json JSON 解析错误: {e}"]
    if "latest" not in data:
        errors.append("changelog 缺少 latest 字段")
    if "entries" not in data:
        errors.append("changelog 缺少 entries 字段")
    if "modules" not in data:
        errors.append("changelog 缺少 modules 字段")
    version_path = SKILL_DIR / "skill.version"
    version = version_path.read_text(encoding="utf-8").strip() if version_path.is_file() else ""
    if data.get("latest") != version:
        errors.append(
            f"changelog latest 与 skill.version 不一致: {data.get('latest')} != {version}"
        )
    entries = data.get("entries")
    if not isinstance(entries, list) or not any(
        isinstance(entry, dict) and entry.get("version") == version for entry in entries
    ):
        errors.append(f"changelog entries 缺少当前版本: {version}")
    modules = data.get("modules")
    if not isinstance(modules, dict) or not modules.get(version):
        errors.append(f"changelog modules 未记录当前版本受影响模块: {version}")
    if errors:
        return errors
    return ["✓ changelog 结构有效"]


def test_skill_version_consistency() -> list[str]:
    """SKILL.md frontmatter version must match skill.version."""
    errors: list[str] = []
    bootstrap = load_file(BOOTSTRAP)
    ver_match = re.search(r"version:\s*([0-9]+\.[0-9]+\.[0-9]+)", bootstrap)
    bootstrap_ver = ver_match.group(1) if ver_match else None

    ver_file = SKILL_DIR / "skill.version"
    disk_ver = ver_file.read_text(encoding="utf-8").strip() if ver_file.is_file() else None

    if bootstrap_ver != disk_ver:
        errors.append(f"版本不一致: SKILL.md={bootstrap_ver}, skill.version={disk_ver}")
    if errors:
        return errors
    return [f"✓ 版本一致: {bootstrap_ver}"]


def test_hard_principles_in_skill_md() -> list[str]:
    """Hard principles should exist and be concise."""
    errors: list[str] = []
    text = load_file(BOOTSTRAP)
    # Count line count of hard principles section
    principles_match = re.search(r"## 硬性原则\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
    if not principles_match:
        errors.append("SKILL.md 缺少「硬性原则」节")
        return errors
    lines = [l for l in principles_match.group(1).split("\n") if l.strip()]
    if len(lines) > HARD_PRINCIPLES_MAX_LINES:
        errors.append(
            f"硬性原则过于冗长（{len(lines)} 行），必须 ≤{HARD_PRINCIPLES_MAX_LINES} 行"
        )
    if errors:
        return errors
    return [f"✓ 硬性原则: {len(lines)} 行"]


def test_no_duplicate_routing_info() -> list[str]:
    """routing info should be in routing.md, not duplicated in SKILL.md."""
    errors: list[str] = []
    text = load_file(BOOTSTRAP)
    # SKILL.md should NOT contain routing trigger detail tables
    if "自然语言触发速查" in text:
        errors.append("SKILL.md 不应包含触发词速查表（应在 routing.md）")
    if "典型触发（任一即视为库内）" in text:
        errors.append("SKILL.md 不应包含库内检索触发词表（应在 routing.md）")
    if errors:
        return errors
    return ["✓ SKILL.md 无 routing 重复内容"]


def test_dual_path_cross_references() -> list[str]:
    """If maintain.md or url-ingest.md references dual-path-synthesis, the module must exist."""
    errors: list[str] = []
    dual_path_file = MODULES_DIR / "dual-path-synthesis.md"

    for name in ("maintain.md", "url-ingest.md"):
        text = load_file(MODULES_DIR / name)
        if "dual-path-synthesis" in text:
            if not dual_path_file.is_file():
                errors.append(f"{name} 引用 dual-path-synthesis 但 modules/dual-path-synthesis.md 不存在")
    if errors:
        return errors
    if dual_path_file.is_file():
        return ["✓ dual-path-synthesis 引用一致"]
    return ["✓ dual-path-synthesis 无引用（模块不存在）"]


def run_all() -> bool:
    tests = [
        ("Trigger description 边界", test_trigger_description_scope),
        ("Bootstrap 引用验证", test_all_bootstrap_entries_exist),
        ("Module curl 语法", test_module_curl_syntax),
        ("API 端点覆盖", test_api_endpoint_coverage),
        ("API Runtime 契约", test_required_api_contracts),
        ("Module 交叉引用", test_module_cross_references),
        ("Changelog 结构", test_changelog_schema),
        ("版本一致性", test_skill_version_consistency),
        ("硬性原则长度", test_hard_principles_in_skill_md),
        ("去重检查", test_no_duplicate_routing_info),
        ("dual-path 交叉引用", test_dual_path_cross_references),
        ("Runtime Markdown 链接", test_runtime_markdown_links),
        ("kb-search 执行顺序", test_kb_search_execution_order),
        ("requirements 联合边界", test_shared_requirement_bounds),
        ("eval schema 与覆盖", test_evals_schema_and_coverage),
    ]

    all_ok = True
    for name, fn in tests:
        print(f"\n▸ {name}")
        results = fn()
        for r in results:
            ok = r.startswith("✓")
            if not ok:
                all_ok = False
            print(f"  {'✅' if ok else '❌'} {r}")

    print(f"\n{'='*40}")
    if all_ok:
        print("✅ 全部检查通过")
    else:
        print("❌ 存在失败项，请修复后再部署")
    return all_ok


def main():
    parser = argparse.ArgumentParser(description="FileX Skill Module Evaluator")
    parser.add_argument(
        "skill_dir",
        nargs="?",
        type=Path,
        default=SKILL_DIR,
        help="待检查的 ding skill 目录（默认仓库 skill/ding）",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    args = parser.parse_args()
    configure_skill_dir(args.skill_dir)

    if not SKILL_DIR.is_dir():
        print(f"错误: skill 目录不存在 ({SKILL_DIR})")
        sys.exit(1)

    ok = run_all()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
