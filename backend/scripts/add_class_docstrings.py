#!/usr/bin/env python3
"""批量为 Python 源码添加模块头与 Google 风格类 docstring。

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

AUTHOR = "徐泽宇"
COPYRIGHT = f"Copyright (c) 2026 {AUTHOR}"
COPYRIGHT_SYMBOL = f"© 2026 {AUTHOR}"

ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = (ROOT / "backend", ROOT / "skill")
SKIP_DIR_NAMES = {"__pycache__", ".venv", "venv", "node_modules", ".git"}
SKIP_PATH_PARTS = {Path("backend/alembic/versions")}

WORD_CN: dict[str, str] = {
    "user": "用户",
    "file": "文件",
    "folder": "文件夹",
    "workspace": "知识空间",
    "share": "分享",
    "link": "链接",
    "token": "令牌",
    "password": "密码",
    "login": "登录",
    "register": "注册",
    "auth": "认证",
    "admin": "管理",
    "api": "API",
    "key": "密钥",
    "request": "请求",
    "response": "响应",
    "status": "状态",
    "error": "错误",
    "exception": "异常",
    "service": "服务",
    "manager": "管理器",
    "middleware": "中间件",
    "model": "模型",
    "schema": "模式",
    "config": "配置",
    "setting": "设置",
    "settings": "设置",
    "license": "授权",
    "wiki": "Wiki",
    "kb": "资料库",
    "index": "索引",
    "extract": "提取",
    "chunk": "分块",
    "tag": "标签",
    "search": "检索",
    "audit": "审计",
    "log": "日志",
    "operation": "操作",
    "message": "消息",
    "queue": "队列",
    "job": "任务",
    "report": "报告",
    "library": "资料库",
    "context": "上下文",
    "graph": "图",
    "path": "路径",
    "compile": "编译",
    "candidate": "候选",
    "page": "页面",
    "kind": "类型",
    "grant": "授权",
    "resource": "资源",
    "member": "成员",
    "role": "角色",
    "wechat": "微信",
    "oauth": "OAuth",
    "state": "状态",
    "skill": "技能",
    "runtime": "运行时",
    "external": "外部",
    "upload": "上传",
    "download": "下载",
    "preview": "预览",
    "verify": "校验",
    "change": "修改",
    "create": "创建",
    "update": "更新",
    "delete": "删除",
    "list": "列表",
    "detail": "详情",
    "info": "信息",
    "meta": "元数据",
    "body": "请求体",
    "item": "条目",
    "items": "条目列表",
    "result": "结果",
    "payload": "载荷",
    "data": "数据",
    "content": "内容",
    "name": "名称",
    "type": "类型",
    "size": "大小",
    "hash": "哈希",
    "mime": "MIME",
    "original": "原始",
    "parent": "父级",
    "child": "子级",
    "active": "启用",
    "valid": "有效",
    "reason": "原因",
    "code": "代码",
    "expires": "过期",
    "trial": "试用",
    "customer": "客户",
    "test": "测试",
    "mock": "模拟",
    "client": "客户端",
    "provider": "提供者",
    "base": "基类",
    "ollama": "Ollama",
    "embed": "嵌入",
    "rerank": "重排",
    "markdown": "Markdown",
    "md": "Markdown",
    "pubmed": "PubMed",
    "maintain": "维护",
    "agent": "智能体",
    "dual": "双路",
    "finalize": "收尾",
    "capture": "采集",
    "url": "URL",
    "ws": "WebSocket",
    "mq": "消息队列",
    "vector": "向量",
    "hybrid": "混合",
    "debug": "调试",
    "boost": "加权",
    "expansion": "扩展",
    "provenance": "溯源",
    "coref": "共引",
    "topic": "主题",
    "slug": "Slug",
    "lint": "体检",
    "batch": "批量",
    "reindex": "重索引",
    "reextract": "重提取",
    "pending": "待处理",
    "ready": "就绪",
    "failed": "失败",
    "attempt": "尝试",
    "max": "最大",
    "min": "最小",
    "count": "数量",
    "total": "总计",
    "enabled": "启用",
    "disabled": "禁用",
    "created": "创建",
    "updated": "更新",
    "at": "时间",
    "id": "ID",
    "rev": "版本号",
    "openid": "OpenID",
    "unionid": "UnionID",
    "nickname": "昵称",
    "avatar": "头像",
    "username": "用户名",
    "filename": "文件名",
    "publish": "发布",
    "indexed": "已索引",
    "stale": "过期",
    "anchor": "锚点",
    "version": "版本",
    "entry": "条目",
    "actor": "操作者",
    "target": "目标",
    "action": "动作",
    "prefix": "前缀",
    "reveal": "揭示",
    "patch": "补丁",
    "activate": "激活",
    "invalid": "无效",
    "expired": "过期",
    "health": "健康",
    "manifest": "清单",
    "module": "模块",
    "modules": "模块",
    "history": "历史",
    "rollback": "回滚",
    "editor": "编辑器",
    "repository": "仓库",
    "cache": "缓存",
    "worker": "Worker",
    "consumer": "消费者",
    "backlog": "积压",
    "handler": "处理器",
    "router": "路由",
    "endpoint": "端点",
    "openapi": "OpenAPI",
    "production": "生产",
    "development": "开发",
    "bootstrap": "引导",
    "secret": "密钥",
    "hmac": "HMAC",
    "signature": "签名",
    "issue": "签发",
    "refresh": "刷新",
    "rebuild": "重建",
    "normalize": "规范化",
    "basename": "基名",
    "thumbnail": "缩略图",
    "office": "Office",
    "image": "图片",
    "pdf": "PDF",
    "html": "HTML",
    "text": "文本",
    "plain": "纯文本",
    "structure": "结构",
    "profile": "配置",
    "ops": "操作",
    "citation": "引用",
    "edges": "边",
    "nodes": "节点",
    "vis": "可视化",
    "tree": "树",
    "selection": "选择",
    "virtual": "虚拟",
    "root": "根",
    "materials": "资料",
    "material": "资料",
    "source": "来源",
    "entity": "实体",
    "concept": "概念",
    "synthesis": "综合",
    "webhook": "Webhook",
    "explain": "解释",
    "map": "地图",
    "expand": "扩展",
    "neighbor": "邻居",
    "seed": "种子",
    "depth": "深度",
    "notes": "笔记",
    "has": "拥有",
    "awaiting": "待处理",
    "ai": "AI",
    "files": "文件",
    "with": "含",
    "md5": "MD5",
    "tags": "标签",
    "merge": "合并",
    "replace": "替换",
    "copy": "复制",
    "is": "是否",
    "administrator": "管理员",
    "pwd": "密码",
    "bound": "绑定",
    "qrcode": "二维码",
    "callback": "回调",
    "app": "应用",
    "redirect": "重定向",
    "uri": "URI",
    "ttl": "TTL",
    "minutes": "分钟",
    "gate": "网关",
    "logging": "日志",
    "permission": "权限",
    "permissions": "权限",
    "acl": "ACL",
    "shared": "共享",
    "personal": "个人",
    "cross": "跨",
    "fts": "全文检索",
    "dlq": "死信队列",
    "prefetch": "预取",
    "dedup": "去重",
    "union": "并集",
    "inactive": "下架",
    "only": "仅",
    "prepare": "准备",
}


def split_camel(name: str) -> list[str]:
    parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    parts = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", parts)
    return [p.lower() for p in parts.split() if p]


def words_to_cn(tokens: list[str]) -> str:
    out: list[str] = []
    for token in tokens:
        out.append(WORD_CN.get(token, token))
    return "".join(out)


def classify_path(rel: Path) -> str:
    parts = rel.parts
    if "tests" in parts or parts[-1].startswith("test_"):
        return "单元测试"
    if "models" in parts:
        return "ORM 数据库模型"
    if "schemas" in parts:
        return "Pydantic 数据模式"
    if "services" in parts:
        return "业务服务"
    if "middleware" in parts:
        return "中间件"
    if "routers" in parts:
        return "API 路由辅助类型"
    if "messaging" in parts:
        return "消息与 WebSocket 组件"
    if "workers" in parts:
        return "后台 Worker 组件"
    if "utils" in parts:
        return "工具类型"
    if "scripts" in parts:
        return "脚本辅助类型"
    if "agent" in parts or "skill" in parts:
        return "钉技能 Agent 组件"
    if "extract" in parts:
        return "正文提取组件"
    if "alembic" in parts:
        return "数据库迁移组件"
    return "类型定义"


def module_summary(rel: Path) -> str:
    stem = rel.stem
    if stem == "__init__":
        parent = rel.parent.name
        return f"{parent} 包初始化模块。"
    if "tests" in rel.parts:
        topic = stem.removeprefix("test_").replace("_", " ")
        return f"{topic} 相关测试模块。"
    if "models" in rel.parts:
        return f"{stem} 相关 ORM 模型模块。"
    if "schemas" in rel.parts:
        return f"{stem} 相关 API 数据模式模块。"
    if "services" in rel.parts:
        return f"{stem} 业务逻辑模块。"
    if "routers" in rel.parts:
        return f"{stem} HTTP 路由模块。"
    if "middleware" in rel.parts:
        return f"{stem} 中间件模块。"
    if "workers" in rel.parts:
        return f"{stem} 后台任务模块。"
    if "scripts" in rel.parts:
        return f"{stem} 运维脚本模块。"
    if "skill" in rel.parts:
        return f"{stem} 钉技能模块。"
    return f"{stem.replace('_', ' ')} 模块。"


def class_summary(name: str, rel: Path, bases: list[str]) -> str:
    tokens = split_camel(name)
    cn = words_to_cn(tokens)
    category = classify_path(rel)
    if name == "Config":
        return "Pydantic 模型配置。"
    if name.startswith("Test"):
        subject = words_to_cn(split_camel(name.removeprefix("Test")))
        return f"{subject} {category}。"
    if "Error" in name or "Exception" in name:
        return f"{cn}异常类型。"
    if any(b.endswith("BaseModel") for b in bases):
        return f"{cn} {category.replace('ORM 数据库模型', '数据模式').replace('单元测试', '数据模式')}。"
    if any(b.endswith("Base") for b in bases) and "models" in rel.parts:
        return f"{cn} ORM 数据库模型。"
    if name.endswith("Middleware"):
        return f"{cn} ASGI 中间件。"
    if "Manager" in name:
        return f"{cn} 管理器。"
    if "Service" in name:
        return f"{cn} 业务服务。"
    return f"{cn} {category}。"


def snake_to_cn(field: str) -> str:
    parts = field.split("_")
    return "".join(WORD_CN.get(p, p) for p in parts)


def annotation_to_str(node: ast.expr | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def extract_attributes(class_node: ast.ClassDef) -> list[tuple[str, str]]:
    attrs: list[tuple[str, str]] = []
    for item in class_node.body:
        if isinstance(item, ast.Expr):
            continue
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            ann = annotation_to_str(item.annotation)
            desc = snake_to_cn(item.target.id)
            attrs.append((item.target.id, f"{desc}（{ann}）" if ann else desc))
        elif isinstance(item, ast.Assign):
            for target in item.targets:
                if not isinstance(target, ast.Name):
                    continue
                name = target.id
                if name.startswith("_") and name != "__tablename__":
                    continue
                value = item.value
                if isinstance(value, ast.Call):
                    func = value.func
                    if isinstance(func, ast.Attribute) and func.attr == "Column":
                        attrs.append((name, f"{snake_to_cn(name)}数据库列"))
                    elif isinstance(func, ast.Name) and func.id in {"Column", "Field"}:
                        kind = "数据库列" if func.id == "Column" else "字段"
                        attrs.append((name, f"{snake_to_cn(name)}{kind}"))
                    elif isinstance(func, ast.Attribute) and func.attr == "Field":
                        attrs.append((name, f"{snake_to_cn(name)}字段"))
                elif isinstance(value, ast.Constant):
                    if name == "__tablename__":
                        continue
                    attrs.append((name, f"{snake_to_cn(name)}常量"))
        if len(attrs) >= 12:
            break
    return attrs


def git_blame_date(repo_root: Path, rel: Path, lineno: int) -> str | None:
    try:
        proc = subprocess.run(
            [
                "git",
                "blame",
                "--line-porcelain",
                "-L",
                f"{lineno},{lineno}",
                "--",
                str(rel),
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    for line in proc.stdout.splitlines():
        if line.startswith("author-time "):
            try:
                ts = int(line.split()[1])
                return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            except (IndexError, ValueError, OSError):
                return None
    return None


def has_module_header(source: str) -> bool:
    return "Copyright" in source[:800] or f"Authors:\n    {AUTHOR}" in source[:1200]


def class_has_docstring(class_node: ast.ClassDef) -> bool:
    if not class_node.body:
        return False
    first = class_node.body[0]
    return (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    )


def leading_special_lines(lines: list[str]) -> int:
    """模块头插入点：shebang/编码声明之后、``__future__`` 与 import 之前。"""
    idx = 0
    while idx < len(lines):
        stripped = lines[idx].strip()
        if not stripped:
            idx += 1
            continue
        if stripped.startswith("#!") or stripped.startswith("# -*-") or stripped.startswith("# coding"):
            idx += 1
            continue
        if stripped.startswith('"""') or stripped.startswith("'''"):
            break
        break
    return idx


def find_class_insert_line(lines: list[str], class_lineno: int) -> int:
    idx = class_lineno - 1
    while idx < len(lines):
        if lines[idx].rstrip().endswith(":"):
            return idx + 1
        idx += 1
    return class_lineno


def split_keepends(block: str) -> list[str]:
    if not block:
        return []
    parts = block.splitlines(keepends=True)
    if parts and not parts[-1].endswith("\n"):
        parts[-1] += "\n"
    return parts


def insert_block(lines: list[str], index: int, block: str) -> None:
    lines[index:index] = split_keepends(block)


def build_class_docstring(
    summary: str,
    since: str | None,
    attrs: list[tuple[str, str]],
    indent: str,
) -> str:
    inner = indent + "    "
    doc_lines = [f'{indent}"""{summary}', ""]
    doc_lines.append(f"{inner}Authors:")
    doc_lines.append(f"{inner}    {AUTHOR}")
    doc_lines.append("")
    doc_lines.append(f"{inner}Copyright:")
    doc_lines.append(f"{inner}    {COPYRIGHT_SYMBOL}")
    if since:
        doc_lines.append("")
        doc_lines.append(f"{inner}Since:")
        doc_lines.append(f"{inner}    {since}")
    if attrs:
        doc_lines.append("")
        doc_lines.append(f"{inner}Attributes:")
        for name, desc in attrs:
            doc_lines.append(f"{inner}    {name}: {desc}。")
    doc_lines.append(f'{indent}"""')
    return "\n".join(doc_lines) + "\n"


def ensure_module_header(source: str, rel: Path) -> tuple[str, bool]:
    """返回 (新源码, 是否修改)。"""
    if has_module_header(source):
        return source, False

    lines = source.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"

    tree = ast.parse(source)
    first = tree.body[0] if tree.body else None
    has_existing_doc = (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    )

    insert_at = leading_special_lines([ln.rstrip("\n") for ln in lines])
    if has_existing_doc:
        lines.insert(insert_at, f"# {COPYRIGHT}\n")
        tree = ast.parse("".join(lines))
        first = tree.body[0]
        doc = first.value.value
        if f"Authors:\n    {AUTHOR}" not in doc:
            merged = doc.rstrip() + f"\n\nAuthors:\n    {AUTHOR}\n\nCopyright:\n    {COPYRIGHT_SYMBOL}\n"
            start = first.lineno - 1
            end = first.end_lineno or first.lineno
            lines[start:end] = split_keepends('"""' + merged + '"""\n')
    else:
        insert_block(lines, insert_at, build_module_header(module_summary(rel)))

    return "".join(lines), True


def build_module_header(summary: str) -> str:
    return (
        f"# {COPYRIGHT}\n"
        f'"""{summary}\n\n'
        f"Authors:\n"
        f"    {AUTHOR}\n"
        f'"""\n\n'
    )


def process_file(path: Path, dry_run: bool = False) -> tuple[int, int]:
    rel = path.relative_to(ROOT)
    source = path.read_text(encoding="utf-8")
    try:
        ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        print(f"SKIP syntax error {rel}: {exc}", file=sys.stderr)
        return 0, 0

    module_added = 0
    class_added = 0

    source, changed = ensure_module_header(source, rel)
    if changed:
        module_added = 1

    while True:
        lines = source.splitlines(keepends=True)
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        tree = ast.parse(source, filename=str(path))
        classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and not class_has_docstring(n)]
        if not classes:
            break
        target = max(classes, key=lambda n: n.lineno)
        bases = [annotation_to_str(base) for base in target.bases]
        summary = class_summary(target.name, rel, bases)
        since = git_blame_date(ROOT, rel, target.lineno)
        attrs = extract_attributes(target)
        plain_lines = [ln.rstrip("\n") for ln in lines]
        insert_line = find_class_insert_line(plain_lines, target.lineno)
        if target.lineno < 1 or target.lineno > len(lines):
            print(f"SKIP bad lineno {rel}:{target.name}", file=sys.stderr)
            break
        class_line = lines[target.lineno - 1]
        indent_match = re.match(r"^(\s*)", class_line)
        class_indent = indent_match.group(1) if indent_match else ""
        body_indent = f"{class_indent}    "
        insert_block(lines, insert_line, build_class_docstring(summary, since, attrs, body_indent))
        source = "".join(lines)
        class_added += 1

    if module_added or class_added:
        if not dry_run:
            path.write_text(source, encoding="utf-8")
        print(f"{'DRY' if dry_run else 'OK'} {rel}: module+{module_added} classes+{class_added}")

    return module_added, class_added


def iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root_dir in SCAN_ROOTS:
        if not root_dir.exists():
            continue
        for path in root_dir.rglob("*.py"):
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            rel = path.relative_to(ROOT)
            skip = False
            for skip_part in SKIP_PATH_PARTS:
                try:
                    rel.relative_to(skip_part)
                    skip = True
                    break
                except ValueError:
                    continue
            if skip:
                continue
            files.append(path)
    return sorted(files)


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    total_m = total_c = 0
    for path in iter_python_files():
        m, c = process_file(path, dry_run=dry_run)
        total_m += m
        total_c += c
    print(f"Done: modules+{total_m}, classes+{total_c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
