# Copyright (c) 2026 徐泽宇
"""Run MinerU pipeline and map output to FileX 030 contract."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CacheTier = Literal["job", "content", "none"]
SUPPORTED_RUNTIME_CONFIG_VERSION = 1
_DEFAULT_MEM_LIMIT_BYTES = 8 * 1024**3


@dataclass(frozen=True)
class _RuntimeConfig:
    min_batch_mode: str
    min_batch_inference_size: int
    min_batch_floor: int
    parse_method: str
    formula_enable: bool
    table_enable: bool
    parse_timeout_sec: int
    page_chunk_enabled: bool
    page_chunk_threshold: int
    page_chunk_pages: int
    table_auto_rotate: bool
    table_rotate_max_tables: int
    table_rotate_timeout_sec: int
    config_fingerprint: str


def _cache_root() -> Path:
    return Path(os.environ.get("MINERU_CACHE_DIR", "/cache"))


def _file_md5(path: Path, *, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.md5()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _content_cache_root(md5: str) -> Path:
    return _cache_root() / "content" / md5


def _local_timezone() -> ZoneInfo:
    name = (os.environ.get("FILEX_LOG_TIMEZONE") or os.environ.get("TZ") or "Asia/Shanghai").strip()
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Asia/Shanghai")


def format_local_ts(when: datetime | None = None) -> str:
    """Wall-clock timestamp to second (container TZ, default Asia/Shanghai)."""
    tz = _local_timezone()
    if when is None:
        when = datetime.now(tz)
    elif when.tzinfo is None:
        when = when.replace(tzinfo=tz)
    else:
        when = when.astimezone(tz)
    return when.strftime("%Y-%m-%d %H:%M:%S")


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name, default)).strip())
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _default_runtime_config() -> _RuntimeConfig:
    return _parse_runtime_config(None)


def _parse_runtime_config(raw: dict[str, Any] | None) -> _RuntimeConfig:
    data = raw or {}
    mode = str(data.get("min_batch_mode") or os.environ.get("MINERU_MIN_BATCH_MODE") or "auto").lower()
    if mode not in ("fixed", "auto"):
        mode = "auto"
    method = str(data.get("parse_method") or os.environ.get("MINERU_PARSE_METHOD") or "auto").lower()
    if method not in ("auto", "txt", "ocr"):
        method = "auto"
    fp = str(data.get("config_fingerprint") or "").strip()
    return _RuntimeConfig(
        min_batch_mode=mode,
        min_batch_inference_size=max(8, min(384, int(data.get("min_batch_inference_size") or _env_int("MINERU_MIN_BATCH_INFERENCE_SIZE", 32)))),
        min_batch_floor=max(8, min(384, int(data.get("min_batch_floor") or _env_int("MINERU_MIN_BATCH_FLOOR", 8)))),
        parse_method=method,
        formula_enable=bool(data.get("formula_enable")) if "formula_enable" in data else _env_bool("MINERU_FORMULA_ENABLE", True),
        table_enable=bool(data.get("table_enable")) if "table_enable" in data else _env_bool("MINERU_TABLE_ENABLE", True),
        parse_timeout_sec=max(60, min(3600, int(data.get("parse_timeout_sec") or _env_int("MINERU_PARSE_TIMEOUT_SEC", 850)))),
        page_chunk_enabled=bool(data.get("page_chunk_enabled")) if "page_chunk_enabled" in data else _env_bool("MINERU_PAGE_CHUNK_ENABLED", True),
        page_chunk_threshold=max(1, int(data.get("page_chunk_threshold") or _env_int("MINERU_PAGE_CHUNK_THRESHOLD", 120))),
        page_chunk_pages=max(8, min(200, int(data.get("page_chunk_pages") or _env_int("MINERU_PAGE_CHUNK_PAGES", 48)))),
        table_auto_rotate=bool(data.get("table_auto_rotate")) if "table_auto_rotate" in data else _env_bool("KB_EXTRACT_TABLE_AUTO_ROTATE", False),
        table_rotate_max_tables=max(1, int(data.get("table_rotate_max_tables") or _env_int("KB_EXTRACT_TABLE_ROTATE_MAX_TABLES", 8))),
        table_rotate_timeout_sec=max(1, int(data.get("table_rotate_timeout_sec") or _env_int("KB_EXTRACT_TABLE_ROTATE_TIMEOUT_SEC", 30))),
        config_fingerprint=fp,
    )


def _read_cgroup_memory_max() -> int:
    for path in (
        Path("/sys/fs/cgroup/memory.max"),
        Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
    ):
        try:
            if not path.is_file():
                continue
            raw = path.read_text(encoding="utf-8").strip()
            if raw in ("max", "9223372036854771712"):
                continue
            return int(raw)
        except (OSError, ValueError):
            continue
    return _DEFAULT_MEM_LIMIT_BYTES


def _resolve_effective_batch(page_count: int, mem_limit_bytes: int, cfg: _RuntimeConfig) -> int:
    if cfg.min_batch_mode == "fixed":
        return cfg.min_batch_inference_size
    ceiling = cfg.min_batch_inference_size
    floor = cfg.min_batch_floor
    mem_gb = mem_limit_bytes / (1024**3)
    batch = min(ceiling, max(floor, int(mem_gb * 4)))
    pages = max(0, int(page_count))
    if pages > 200:
        batch = max(floor, batch // 2)
    if pages > 400:
        batch = max(floor, batch // 2)
    return batch


def _estimate_chunk_count(page_count: int, cfg: _RuntimeConfig) -> int:
    pages = max(0, int(page_count))
    if not cfg.page_chunk_enabled or pages <= cfg.page_chunk_threshold:
        return 1
    return max(1, math.ceil(pages / cfg.page_chunk_pages))


def _pdf_page_count(path: Path) -> int:
    try:
        import fitz

        with fitz.open(path) as doc:
            return max(1, int(doc.page_count))
    except Exception:
        logger.warning("mineru: failed to read page_count for %s, assume 1", path)
        return 1


def _apply_table_rotation_env(cfg: _RuntimeConfig) -> None:
    os.environ["KB_EXTRACT_TABLE_AUTO_ROTATE"] = "1" if cfg.table_auto_rotate else "0"
    os.environ["KB_EXTRACT_TABLE_ROTATE_MAX_TABLES"] = str(cfg.table_rotate_max_tables)
    os.environ["KB_EXTRACT_TABLE_ROTATE_TIMEOUT_SEC"] = str(cfg.table_rotate_timeout_sec)


def _find_content_list_and_md(output_root: Path) -> tuple[list[dict] | None, str, Path | None]:
    content_list: list[dict] | None = None
    markdown = ""
    assets_dir: Path | None = None

    for path in output_root.rglob("*_content_list.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(raw, list):
            content_list = raw
        elif isinstance(raw, dict) and isinstance(raw.get("content_list"), list):
            content_list = raw["content_list"]
        assets_dir = path.parent
        break

    for path in output_root.rglob("*.md"):
        if path.name.endswith("_content_list.md"):
            continue
        markdown = path.read_text(encoding="utf-8")
        if assets_dir is None:
            assets_dir = path.parent
        break

    return content_list, markdown, assets_dir


def _build_payload_from_parse(parse_root: Path) -> dict[str, Any]:
    content_list, markdown, assets_dir = _find_content_list_and_md(parse_root)
    if not str(markdown).strip() and not content_list:
        raise ValueError("mineru produced empty output")
    payload: dict[str, Any] = {"markdown": markdown}
    if content_list is not None:
        payload["content_list"] = content_list
    if assets_dir is not None and assets_dir.is_dir():
        payload["assets_dir"] = str(assets_dir.resolve())
    return payload


def _try_load_existing(parse_root: Path) -> dict[str, Any] | None:
    if not parse_root.is_dir():
        return None
    try:
        return _build_payload_from_parse(parse_root)
    except ValueError:
        return None


def _try_load_content_cache(md5: str, *, config_fingerprint: str) -> dict[str, Any] | None:
    content_root = _content_cache_root(md5)
    meta_path = content_root / "meta.json"
    if config_fingerprint and meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            cached_fp = str(meta.get("config_fingerprint") or "").strip()
            if not cached_fp or cached_fp != config_fingerprint:
                logger.info(
                    "mineru content cache miss fingerprint cached=%s current=%s md5=%s",
                    cached_fp or "(missing)",
                    config_fingerprint,
                    md5,
                )
                return None
        except json.JSONDecodeError:
            return None
    elif config_fingerprint:
        return None
    parse_root = content_root / "out"
    if not parse_root.is_dir():
        return None
    try:
        return _build_payload_from_parse(parse_root)
    except ValueError:
        shutil.rmtree(content_root, ignore_errors=True)
        return None


def _promote_to_content_cache(
    *,
    md5: str,
    parse_root: Path,
    src: Path,
    config_fingerprint: str,
) -> None:
    content_root = _content_cache_root(md5)
    out_dest = content_root / "out"
    if out_dest.exists():
        shutil.rmtree(out_dest, ignore_errors=True)
    out_dest.mkdir(parents=True, exist_ok=True)
    if parse_root.is_dir():
        for item in parse_root.iterdir():
            dest = out_dest / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
    stat = src.stat()
    meta = {
        "md5": md5,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "parsed_at": format_local_ts(),
        "config_fingerprint": config_fingerprint,
    }
    meta_path = content_root / "meta.json"
    tmp_path = meta_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(meta_path)


def _parse_output_dir(
    *,
    file_id: int | None,
    job_id: int | None,
) -> tuple[Path, Path | None, Path | None]:
    if file_id is not None:
        cache_root = _cache_root()
        segment = f"f{file_id}"
        if job_id is not None:
            segment = f"{segment}_j{job_id}"
        work = cache_root / "parse" / segment
        out_dir = work / "out"
        work.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir, work, None

    work = Path(tempfile.mkdtemp(prefix="filex-mineru-"))
    out_dir = work / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir, None, work


def _log_parse_done(
    *,
    received_at: str,
    original_name: str,
    file_id: int | None,
    job_id: int | None,
    elapsed_sec: float,
    cache_hit: bool,
    cache_tier: CacheTier,
    ok: bool,
    cfg: _RuntimeConfig,
    page_count: int,
    chunk_count: int,
    effective_batch: int,
    ocr_model_usage: list[dict[str, str]],
) -> None:
    finished_at = format_local_ts()
    logger.info(
        "mineru parse done received_at=%s finished_at=%s elapsed_sec=%.1f "
        "name=%s file_id=%s job_id=%s cache_hit=%s cache_tier=%s ok=%s "
        "effective_batch=%s mode=%s pages=%s chunks=%s runtime_config_version=%s config_fingerprint=%s",
        received_at,
        finished_at,
        elapsed_sec,
        original_name,
        file_id,
        job_id,
        cache_hit,
        cache_tier,
        ok,
        effective_batch,
        cfg.min_batch_mode,
        page_count,
        chunk_count,
        SUPPORTED_RUNTIME_CONFIG_VERSION,
        cfg.config_fingerprint,
    )
    _log_ocr_model_usage(ocr_model_usage)


def _read_ocr_model_usage(parse_dir: Path) -> list[dict[str, str]]:
    path = parse_dir / "mineru_ocr_model_usage.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    models = raw.get("models") if isinstance(raw, dict) else None
    if not isinstance(models, list):
        return []
    usage: list[dict[str, str]] = []
    for model in models:
        if not isinstance(model, dict):
            continue
        component = str(model.get("component") or "").strip()
        name = str(model.get("model_name") or "").strip()
        model_path = str(model.get("model_path") or "").strip()
        if component and name and model_path:
            record = {"component": component, "model_name": name, "model_path": model_path}
            if not Path(model_path).is_absolute():
                continue
            usage.append(record)
    return usage


def _collect_ocr_model_usage(parse_root: Path) -> list[dict[str, str]]:
    usage: list[dict[str, str]] = []
    for chunk_dir in parse_root.glob("chunk_*"):
        usage.extend(_read_ocr_model_usage(chunk_dir))
    if not usage:
        usage = _read_ocr_model_usage(parse_root)
    unique = {(m["component"], m["model_name"], m["model_path"]): m for m in usage}
    return list(unique.values())


def _log_ocr_model_usage(usage: list[dict[str, str]]) -> None:
    for model in usage:
        logger.info(
            "mineru ocr_model component=%s model_name=%s model_path=%s",
            model["component"],
            model["model_name"],
            model["model_path"],
        )


def _build_mineru_cmd(
    *,
    parse_input: Path,
    mineru_out: Path,
    cfg: _RuntimeConfig,
    page_start: int | None = None,
    page_end: int | None = None,
) -> list[str]:
    cmd = [
        "python3",
        "/app/sidecar/mineru_v4_runner.py",
        "-p",
        str(parse_input),
        "-o",
        str(mineru_out),
        "-m",
        cfg.parse_method,
    ]
    if page_start is not None and page_end is not None:
        cmd.extend(["-s", str(page_start), "-e", str(page_end)])
    return cmd


def _mineru_log_cli_enabled() -> bool:
    return (os.environ.get("MINERU_LOG_CLI") or "").strip().lower() in ("1", "true", "yes", "on")


def _log_chunk_start(
    *,
    chunk_index: int,
    chunk_count: int,
    page_start: int | None,
    page_end: int | None,
    timeout_sec: int,
    out_dir: Path,
) -> float:
    logger.info(
        "mineru chunk start chunk=%s/%s pages=%s-%s timeout_sec=%s out=%s",
        chunk_index,
        chunk_count,
        page_start if page_start is not None else "-",
        page_end if page_end is not None else "-",
        timeout_sec,
        out_dir,
    )
    return time.monotonic()


def _log_chunk_done(*, chunk_index: int, chunk_count: int, elapsed_sec: float, ok: bool) -> None:
    logger.info(
        "mineru chunk done chunk=%s/%s elapsed_sec=%.1f ok=%s",
        chunk_index,
        chunk_count,
        elapsed_sec,
        ok,
    )


def _run_mineru_subprocess_streaming(
    cmd: list[str],
    *,
    env: dict[str, str],
    timeout_sec: int,
    cli_log_path: Path,
) -> None:
    cli_log_path.parent.mkdir(parents=True, exist_ok=True)
    collected: list[str] = []
    with cli_log_path.open("w", encoding="utf-8") as log_fp:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            bufsize=1,
        )
        assert proc.stdout is not None

        def _reader() -> None:
            for line in proc.stdout:
                line = line.rstrip("\n\r")
                if not line:
                    continue
                collected.append(line)
                logger.info("mineru cli | %s", line[:4000])
                log_fp.write(line + "\n")
                log_fp.flush()

        reader = threading.Thread(target=_reader, daemon=True)
        reader.start()
        try:
            rc = proc.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            reader.join(timeout=2)
            raise
        reader.join(timeout=5)
    if rc != 0:
        tail = "\n".join(collected[-40:]).strip()[:2000]
        raise RuntimeError(f"mineru CLI failed rc={rc}: {tail}")


def _run_mineru_subprocess(
    cmd: list[str],
    *,
    env: dict[str, str],
    timeout_sec: int,
    chunk_index: int = 0,
    chunk_count: int = 1,
    page_start: int | None = None,
    page_end: int | None = None,
    out_dir: Path | None = None,
) -> None:
    # libgomp 等运行时把空字符串当作非法线程数（WHB T-9 实测
    # OMP_NUM_THREADS="" 导致 CLI rc=1）。子进程前兜底剔除空值，
    # 避免部署配置遗漏时整批 GPU 任务失败。
    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "TORCH_NUM_THREADS"):
        if str(env.get(key) or "").strip() == "":
            env.pop(key, None)
    if out_dir is None:
        out_dir = Path(cmd[cmd.index("-o") + 1]) if "-o" in cmd else Path(".")
    started_mono = _log_chunk_start(
        chunk_index=chunk_index,
        chunk_count=chunk_count,
        page_start=page_start,
        page_end=page_end,
        timeout_sec=timeout_sec,
        out_dir=out_dir,
    )
    ok = False
    while True:
        try:
            if _mineru_log_cli_enabled():
                _run_mineru_subprocess_streaming(
                    cmd,
                    env=env,
                    timeout_sec=timeout_sec,
                    cli_log_path=out_dir / "mineru.cli.log",
                )
            else:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout_sec,
                    env=env,
                    check=False,
                )
                if proc.returncode != 0:
                    detail = (proc.stderr or proc.stdout or "").strip()[:2000]
                    raise RuntimeError(f"mineru CLI failed rc={proc.returncode}: {detail}")
            ok = True
            break
        except RuntimeError as exc:
            if env.get("MINERU_DEVICE", "cpu") == "cuda":
                raise RuntimeError(
                    "MinerU GPU execution failed; CPU fallback is disabled: "
                    f"{exc}"
                ) from exc
            raise
        finally:
            _log_chunk_done(
                chunk_index=chunk_index,
                chunk_count=chunk_count,
                elapsed_sec=time.monotonic() - started_mono,
                ok=ok,
            )


def _copy_assets_with_prefix(src_dir: Path, dest_dir: Path, *, chunk_index: int) -> dict[str, str]:
    """Recursively copy MinerU assets (e.g. auto/images/*) preserving relative paths."""
    mapping: dict[str, str] = {}
    if not src_dir.is_dir():
        return mapping
    dest_dir.mkdir(parents=True, exist_ok=True)
    src_root = src_dir.resolve()
    prefix = f"{chunk_index}_"
    for root, _dirs, files in os.walk(src_root):
        for name in files:
            src = Path(root) / name
            rel = os.path.relpath(src, src_root).replace("\\", "/")
            dest_rel = rel
            dest_path = dest_dir / dest_rel
            if dest_path.exists():
                parts = rel.split("/")
                parts[-1] = prefix + parts[-1]
                dest_rel = "/".join(parts)
                dest_path = dest_dir / dest_rel
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest_path)
            mapping[rel] = dest_rel
            basename = os.path.basename(rel)
            if basename not in mapping:
                mapping[basename] = os.path.basename(dest_rel)
    return mapping


def _rewrite_content_list_paths(
    content_list: list[dict],
    *,
    page_offset: int,
    asset_map: dict[str, str],
) -> list[dict]:
    out: list[dict] = []
    for item in content_list:
        row = dict(item)
        if "page_idx" in row and row["page_idx"] is not None:
            try:
                row["page_idx"] = int(row["page_idx"]) + page_offset
            except (TypeError, ValueError):
                pass
        img = row.get("img_path")
        if isinstance(img, str):
            rel = img.replace("\\", "/").lstrip("./")
            if rel in asset_map:
                row["img_path"] = asset_map[rel]
            else:
                basename = os.path.basename(rel)
                if basename in asset_map:
                    row["img_path"] = asset_map[basename]
        out.append(row)
    return out


def _merge_chunk_payloads(
    chunks: list[dict[str, Any]],
    merged_assets: Path,
) -> dict[str, Any]:
    markdown_parts: list[str] = []
    merged_cl: list[dict] = []
    for chunk in chunks:
        md = str(chunk.get("markdown") or "").strip()
        if md:
            markdown_parts.append(md)
        cl = chunk.get("content_list")
        if isinstance(cl, list):
            merged_cl.extend(cl)
    payload: dict[str, Any] = {"markdown": "\n\n".join(markdown_parts)}
    if merged_cl:
        payload["content_list"] = merged_cl
    if merged_assets.is_dir() and any(merged_assets.iterdir()):
        payload["assets_dir"] = str(merged_assets.resolve())
    if not str(payload["markdown"]).strip() and not merged_cl:
        raise ValueError("mineru chunk merge produced empty output")
    return payload


def _run_mineru_page_chunks(
    *,
    parse_input: Path,
    parse_root: Path,
    work_dir: Path | None,
    cfg: _RuntimeConfig,
    page_count: int,
    effective_batch: int,
) -> dict[str, Any]:
    chunk_pages = cfg.page_chunk_pages
    chunk_count = _estimate_chunk_count(page_count, cfg)
    merged_assets = (work_dir or parse_root.parent) / "merged_assets"
    if merged_assets.exists():
        shutil.rmtree(merged_assets, ignore_errors=True)
    merged_assets.mkdir(parents=True, exist_ok=True)

    chunk_payloads: list[dict[str, Any]] = []
    env = os.environ.copy()
    env.setdefault("MINERU_MODEL_SOURCE", "local")
    env["MINERU_MIN_BATCH_INFERENCE_SIZE"] = str(effective_batch)
    config_json = os.environ.get("MINERU_TOOLS_CONFIG_JSON")
    if config_json:
        env.setdefault("MINERU_TOOLS_CONFIG_JSON", config_json)

    for chunk_index in range(chunk_count):
        start = chunk_index * chunk_pages
        end = min(page_count - 1, start + chunk_pages - 1)
        chunk_out = parse_root / f"chunk_{chunk_index}"
        if chunk_out.exists():
            shutil.rmtree(chunk_out, ignore_errors=True)
        chunk_out.mkdir(parents=True, exist_ok=True)
        cmd = _build_mineru_cmd(
            parse_input=parse_input,
            mineru_out=chunk_out,
            cfg=cfg,
            page_start=start,
            page_end=end,
        )
        try:
            _run_mineru_subprocess(
                cmd,
                env=env,
                timeout_sec=cfg.parse_timeout_sec,
                chunk_index=chunk_index,
                chunk_count=chunk_count,
                page_start=start,
                page_end=end,
                out_dir=chunk_out,
            )
            chunk_payload = _build_payload_from_parse(chunk_out)
        except Exception as exc:
            raise RuntimeError(f"mineru chunk {chunk_index} failed: {exc}") from exc

        assets_src = chunk_payload.get("assets_dir")
        asset_map: dict[str, str] = {}
        if assets_src:
            asset_map = _copy_assets_with_prefix(Path(str(assets_src)), merged_assets, chunk_index=chunk_index)
        cl = chunk_payload.get("content_list")
        if isinstance(cl, list):
            chunk_payload["content_list"] = _rewrite_content_list_paths(
                cl,
                page_offset=start,
                asset_map=asset_map,
            )
        chunk_payloads.append(chunk_payload)

    return _merge_chunk_payloads(chunk_payloads, merged_assets)


def _write_payload_stub_for_cache(parse_root: Path, payload: dict[str, Any]) -> None:
    """Materialize merged payload under parse_root for content-cache promotion."""
    if parse_root.exists():
        shutil.rmtree(parse_root, ignore_errors=True)
    doc_dir = parse_root / "merged" / "auto"
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / "merged.md").write_text(str(payload.get("markdown") or ""), encoding="utf-8")
    cl = payload.get("content_list")
    if isinstance(cl, list):
        (doc_dir / "merged_content_list.json").write_text(json.dumps(cl, ensure_ascii=False), encoding="utf-8")
    assets = payload.get("assets_dir")
    if assets:
        src_assets = Path(str(assets))
        if src_assets.is_dir():
            dest = doc_dir / "assets"
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(src_assets, dest, dirs_exist_ok=True)


def _run_mineru_single(
    *,
    parse_input: Path,
    parse_root: Path,
    cfg: _RuntimeConfig,
    effective_batch: int,
    page_count: int,
) -> dict[str, Any]:
    env = os.environ.copy()
    env.setdefault("MINERU_MODEL_SOURCE", "local")
    env["MINERU_MIN_BATCH_INFERENCE_SIZE"] = str(effective_batch)
    config_json = os.environ.get("MINERU_TOOLS_CONFIG_JSON")
    if config_json:
        env.setdefault("MINERU_TOOLS_CONFIG_JSON", config_json)
    cmd = _build_mineru_cmd(parse_input=parse_input, mineru_out=parse_root, cfg=cfg)
    last_page = max(0, page_count - 1)
    _run_mineru_subprocess(
        cmd,
        env=env,
        timeout_sec=cfg.parse_timeout_sec,
        chunk_index=0,
        chunk_count=1,
        page_start=0,
        page_end=last_page,
        out_dir=parse_root,
    )
    return _build_payload_from_parse(parse_root)


def run_mineru_pipeline(
    file_path: str,
    original_name: str,
    *,
    file_id: int | None = None,
    job_id: int | None = None,
    bypass_cache: bool = False,
    runtime_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def _resolve_for_sidecar(p: str) -> Path:
        """Make best effort to find the file inside the sidecar's filesystem.

        The uploads content is mounted at /uploads. Accept /app/uploads, full host paths,
        or already-correct /uploads paths.
        """
        candidates = [p]
        norm = p.replace("\\", "/")
        # If someone sent a host absolute path or /app/uploads, map the tail under /uploads
        for bad in ("/app/uploads/", "/uploads/"):
            if bad in norm:
                rel = norm.split(bad, 1)[1].lstrip("/")
                candidates.append("/uploads/" + rel)
        # Try stripping any leading host prefix that ends with /backend/uploads or /uploads
        if "/backend/uploads/" in norm:
            rel = norm.split("/backend/uploads/", 1)[1]
            candidates.append("/uploads/" + rel.lstrip("/"))
        # Also try the raw norm if it starts with /uploads already
        if norm.startswith("/uploads/"):
            candidates.append(norm)
        for cand in candidates:
            pp = Path(cand)
            if pp.is_file():
                return pp
        return Path(p)  # will fail the check below with the original name in error

    src = _resolve_for_sidecar(file_path)
    if not src.is_file():
        raise FileNotFoundError(f"file not found: {file_path}")

    cfg = _parse_runtime_config(runtime_config)
    _apply_table_rotation_env(cfg)

    received_at = format_local_ts()
    started_mono = time.monotonic()
    file_md5 = _file_md5(src)
    parse_root, work_dir, temp_work = _parse_output_dir(file_id=file_id, job_id=job_id)

    page_count = _pdf_page_count(src)
    mem_limit = _read_cgroup_memory_max()
    effective_batch = _resolve_effective_batch(page_count, mem_limit, cfg)
    chunk_count = _estimate_chunk_count(page_count, cfg)

    if not bypass_cache:
        cached = _try_load_existing(parse_root)
        if cached is not None:
            _log_parse_done(
                received_at=received_at,
                original_name=original_name,
                file_id=file_id,
                job_id=job_id,
                elapsed_sec=time.monotonic() - started_mono,
                cache_hit=True,
                cache_tier="job",
                ok=True,
                cfg=cfg,
                page_count=page_count,
                chunk_count=chunk_count,
                effective_batch=effective_batch,
                ocr_model_usage=[],
            )
            return cached

        content_cached = _try_load_content_cache(file_md5, config_fingerprint=cfg.config_fingerprint)
        if content_cached is not None:
            _log_parse_done(
                received_at=received_at,
                original_name=original_name,
                file_id=file_id,
                job_id=job_id,
                elapsed_sec=time.monotonic() - started_mono,
                cache_hit=True,
                cache_tier="content",
                ok=True,
                cfg=cfg,
                page_count=page_count,
                chunk_count=chunk_count,
                effective_batch=effective_batch,
                ocr_model_usage=[],
            )
            return content_cached

    if work_dir is not None and parse_root.exists() and next(parse_root.iterdir(), None) is not None:
        shutil.rmtree(work_dir, ignore_errors=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        parse_root.mkdir(parents=True, exist_ok=True)

    file_size = src.stat().st_size
    logger.info(
        "mineru parse start received_at=%s name=%s file_id=%s job_id=%s size=%s pages=%s "
        "out=%s bypass_cache=%s effective_batch=%s chunks=%s config_fingerprint=%s",
        received_at,
        original_name,
        file_id,
        job_id,
        file_size,
        page_count,
        parse_root,
        bypass_cache,
        effective_batch,
        chunk_count,
        cfg.config_fingerprint,
    )

    parse_input = src
    rotation_records: list = []
    rotate_work = (work_dir / "rotate") if work_dir is not None else (parse_root.parent / "rotate")
    try:
        from table_rotation import inject_rotation_meta, preprocess_pdf_tables

        parse_input, rotation_records = preprocess_pdf_tables(src, rotate_work)
    except Exception as exc:
        logger.warning("table rotation hook skipped: %s", exc)
        parse_input = src
        rotation_records = []

    ok = False
    ocr_model_usage: list[dict[str, str]] = []
    try:
        if chunk_count > 1:
            payload = _run_mineru_page_chunks(
                parse_input=parse_input,
                parse_root=parse_root,
                work_dir=work_dir,
                cfg=cfg,
                page_count=page_count,
                effective_batch=effective_batch,
            )
        else:
            payload = _run_mineru_single(
                parse_input=parse_input,
                parse_root=parse_root,
                cfg=cfg,
                effective_batch=effective_batch,
                page_count=page_count,
            )
        ocr_model_usage = _collect_ocr_model_usage(parse_root)
        if ocr_model_usage:
            payload["ocr_model_usage"] = ocr_model_usage
        if rotation_records:
            from table_rotation import inject_rotation_meta

            payload = inject_rotation_meta(payload, rotation_records)
        if chunk_count > 1:
            _write_payload_stub_for_cache(parse_root, payload)
        if file_id is not None:
            _promote_to_content_cache(
                md5=file_md5,
                parse_root=parse_root,
                src=src,
                config_fingerprint=cfg.config_fingerprint,
            )
        ok = True
        return payload
    finally:
        if not ocr_model_usage:
            # The child writes the authoritative model selection before calling
            # do_parse, so retain it even when MinerU exits with an error.
            ocr_model_usage = _collect_ocr_model_usage(parse_root)
        _log_parse_done(
            received_at=received_at,
            original_name=original_name,
            file_id=file_id,
            job_id=job_id,
            elapsed_sec=time.monotonic() - started_mono,
            cache_hit=False,
            cache_tier="none",
            ok=ok,
            cfg=cfg,
            page_count=page_count,
            chunk_count=chunk_count,
            effective_batch=effective_batch,
            ocr_model_usage=ocr_model_usage,
        )
        if temp_work is not None:
            shutil.rmtree(temp_work, ignore_errors=True)
