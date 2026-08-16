from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
EVALUATOR = REPO_ROOT / "backend" / "scripts" / "skill_eval.py"


def _run_evaluator(skill_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(EVALUATOR), str(skill_dir)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_common_skill_files(skill_dir: Path) -> None:
    (skill_dir / "modules").mkdir(parents=True)
    (skill_dir / "references").mkdir()
    (skill_dir / "agent").mkdir()
    (skill_dir / "evals").mkdir()
    (skill_dir / "modules" / "kb-search.md").write_text(
        "# KB search\n\n## 目录\n\n- [0. 入口](#0-入口)\n\n"
        "## 0. 入口\n## 1. 检索\n## 2. 展开\n## 3. 整合\n"
        "## 4. 审核\n## 5. 作答\n## 6. Humanize\n",
        encoding="utf-8",
    )
    (skill_dir / "modules" / "routing.md").write_text("# Routing\n", encoding="utf-8")
    (skill_dir / "modules" / "maintain.md").write_text(
        "# Maintain\n\nUse dual-path-synthesis.\n", encoding="utf-8"
    )
    (skill_dir / "modules" / "url-ingest.md").write_text(
        "# URL ingest\n\nUse dual-path-synthesis.\n", encoding="utf-8"
    )
    (skill_dir / "modules" / "dual-path-synthesis.md").write_text(
        "# Dual path\n", encoding="utf-8"
    )
    (skill_dir / "skill.version").write_text("2.0.98\n", encoding="utf-8")
    (skill_dir / "skill.meta.json").write_text(
        json.dumps({"bootstrap_min_version": "2.0.0"}) + "\n",
        encoding="utf-8",
    )
    (skill_dir / "skill.changelog.json").write_text(
        json.dumps(
            {
                "latest": "2.0.98",
                "entries": [{"version": "2.0.98", "changes": ["runtime"]}],
                "modules": {"2.0.98": ["kb-search", "api-ref"]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    requirements = "httpx>=0.28.0,<0.29.0\nlanggraph-checkpoint-sqlite>=3.1.0,<3.2.0\n"
    (skill_dir / "agent" / "requirements.txt").write_text(requirements, encoding="utf-8")
    (skill_dir / "agent" / "requirements-langgraph.example.txt").write_text(
        requirements + "langgraph>=1.2.7,<1.3.0\n",
        encoding="utf-8",
    )


def _valid_evals() -> dict[str, object]:
    trigger_cases = [
        {
            "id": f"trigger-{idx:02d}",
            "query": f"FileX 近邻请求 {idx}",
            "should_trigger": idx % 2 == 0,
            "tags": ["near_miss"],
        }
        for idx in range(20)
    ]
    required_tags = [
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
    ]
    behavior_cases = [
        {
            "id": f"behavior-{idx:02d}",
            "query": f"/ding fixture {idx}",
            "tags": [tag],
            "expected": {"route": "kb_answer"},
            "fixture": {"search_items": []},
            "assertions": ["route", "mcp_cli_equivalence"],
        }
        for idx, tag in enumerate(required_tags)
    ]
    return {
        "schema_version": 1,
        "skill_name": "ding",
        "trigger_cases": trigger_cases,
        "behavior_cases": behavior_cases,
    }


def test_evaluator_accepts_complete_runtime_contract(tmp_path: Path) -> None:
    skill_dir = tmp_path / "ding"
    _write_common_skill_files(skill_dir)
    (skill_dir / "SKILL.md").write_text(
        """---
name: ding
description: 钉（FileX 智能体资料库）：仅在 /ding、钉或 FileX 明确上下文、钉安装备忘时使用。
metadata:
  version: 2.0.98
---
# 钉
## 硬性原则
- FileX 鉴权只用 API Key。
- 库内结论只使用已验证证据。
- 未获同意不访问外网。

[检索流程](modules/kb-search.md)
""",
        encoding="utf-8",
    )
    (skill_dir / "references" / "filex-agent-api.md").write_text(
        """# API
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/query-understand` | 查询理解 |
| POST | `/fulltext-reason` | 全文推理 |

AUTO 表头：`file_id | original_name | mime_type | has_md | tags | created_at`
""",
        encoding="utf-8",
    )
    (skill_dir / "evals" / "evals.json").write_text(
        json.dumps(_valid_evals(), ensure_ascii=False),
        encoding="utf-8",
    )

    completed = _run_evaluator(skill_dir)

    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_evaluator_reports_each_runtime_contract_violation(tmp_path: Path) -> None:
    skill_dir = tmp_path / "ding"
    _write_common_skill_files(skill_dir)
    (skill_dir / "SKILL.md").write_text(
        """---
name: ding
description: 普通查/问/找/总结全部触发钉。
metadata:
  version: 2.0.98
---
# 钉
## 硬性原则
"""
        + "\n".join(f"- 原则 {idx}" for idx in range(26))
        + "\n\n[越界规格](../../specs/145/spec.md)\n",
        encoding="utf-8",
    )
    (skill_dir / "references" / "filex-agent-api.md").write_text(
        "AUTO 表头：`id | file_id | original_name | mime_type | md5 | has_md | tags | created_at`\n",
        encoding="utf-8",
    )
    (skill_dir / "skill.changelog.json").write_text(
        json.dumps({"latest": "2.0.97", "entries": [], "modules": {}}) + "\n",
        encoding="utf-8",
    )
    (skill_dir / "agent" / "requirements-langgraph.example.txt").write_text(
        "httpx>=0.27.0\nlanggraph-checkpoint-sqlite>=2.0.0\n",
        encoding="utf-8",
    )
    (skill_dir / "evals" / "evals.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "skill_name": "ding",
                "trigger_cases": [{"id": "one", "query": "查", "should_trigger": True}],
                "behavior_cases": [{"id": "one", "query": "/ding", "tags": []}],
            }
        ),
        encoding="utf-8",
    )

    completed = _run_evaluator(skill_dir)
    output = completed.stdout + completed.stderr

    assert completed.returncode == 1
    for expected in (
        "description 含全局普通动词触发",
        "硬性原则过于冗长",
        "缺少端点: /query-understand",
        "缺少端点: /fulltext-reason",
        "Runtime 链接越出技能包",
        "AUTO 表头与后端契约不一致",
        "changelog latest 与 skill.version 不一致",
        "requirements 共享依赖缺少兼容上下界",
        "trigger eval 不足 20 条",
        "behavior eval 不足 10 条",
        "behavior eval 缺少必选标签",
    ):
        assert expected in output
