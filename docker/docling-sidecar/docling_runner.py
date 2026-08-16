# Copyright (c) 2026 徐泽宇
"""Run Docling pipeline and map output to FileX 050 contract."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CacheTier = Literal["job", "content", "none"]


def _models_dir() -> Path:
    return Path(os.environ.get("DOCLING_MODELS_DIR") or "/models")


def _cache_root() -> Path:
    return Path(os.environ.get("DOCLING_CACHE_DIR") or "/cache")


def _parse_timeout_sec() -> int:
    return max(1, int(os.environ.get("DOCLING_PARSE_TIMEOUT_SEC") or "550"))


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
    tz = _local_timezone()
    if when is None:
        when = datetime.now(tz)
    elif when.tzinfo is None:
        when = when.replace(tzinfo=tz)
    else:
        when = when.astimezone(tz)
    return when.strftime("%Y-%m-%d %H:%M:%S")


def _item_page_idx(item: Any) -> int | None:
    prov = getattr(item, "prov", None) or []
    if not prov:
        return None
    try:
        page = int(prov[0].page_no)
    except (TypeError, ValueError, IndexError, AttributeError):
        return None
    return page - 1 if page >= 1 else page


def _save_picture_item(item: Any, dest: Path) -> bool:
    image = getattr(item, "image", None)
    if image is None:
        return False
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if hasattr(image, "save"):
            image.save(dest)
            return dest.is_file()
        if hasattr(image, "pil_image"):
            image.pil_image.save(dest)
            return dest.is_file()
    except Exception as exc:
        logger.warning("skip docling picture save: %s", exc)
    return False


def _export_content_list(doc: Any, assets_dir: Path) -> list[dict]:
    blocks: list[dict] = []
    img_counter = 0
    for item, _level in doc.iterate_items():
        page_idx = _item_page_idx(item)
        label = str(getattr(item, "label", "") or "").lower()
        type_name = type(item).__name__.lower()

        if "table" in label or "table" in type_name:
            body = ""
            if hasattr(item, "export_to_markdown"):
                try:
                    body = str(item.export_to_markdown(doc=doc) or "").strip()
                except TypeError:
                    body = str(item.export_to_markdown() or "").strip()
            if not body:
                body = str(getattr(item, "text", "") or "").strip()
            if not body:
                continue
            entry: dict[str, Any] = {"type": "table", "table_body": body}
            if page_idx is not None:
                entry["page_idx"] = page_idx
            blocks.append(entry)
            continue

        if "picture" in label or "figure" in label or "picture" in type_name:
            img_counter += 1
            img_name = f"img_{img_counter}.png"
            if _save_picture_item(item, assets_dir / img_name):
                entry = {"type": "picture", "img_path": img_name}
                if page_idx is not None:
                    entry["page_idx"] = page_idx
                blocks.append(entry)
            continue

        if "formula" in label or "equation" in label:
            latex = str(getattr(item, "text", "") or "").strip()
            if not latex:
                continue
            entry = {"type": "formula", "latex": latex}
            if page_idx is not None:
                entry["page_idx"] = page_idx
            blocks.append(entry)
            continue

        text = str(getattr(item, "text", "") or "").strip()
        if text:
            entry = {"type": "text", "text": text}
            if page_idx is not None:
                entry["page_idx"] = page_idx
            blocks.append(entry)

    return blocks


def _build_payload_from_doc(doc: Any, assets_dir: Path) -> dict[str, Any]:
    markdown = str(doc.export_to_markdown() or "")
    content_list = _export_content_list(doc, assets_dir)
    if not markdown.strip() and not content_list:
        raise ValueError("docling produced empty output")
    payload: dict[str, Any] = {"markdown": markdown}
    if content_list:
        payload["content_list"] = content_list
    if assets_dir.is_dir() and any(assets_dir.iterdir()):
        payload["assets_dir"] = str(assets_dir.resolve())
    return payload


def _convert_document(src: Path, out_dir: Path) -> dict[str, Any]:
    """Run Docling conversion; separated for unit-test mocking."""
    artifacts = _models_dir() / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DOCLING_ARTIFACTS_PATH", str(artifacts))

    from docling.document_converter import DocumentConverter

    out_dir.mkdir(parents=True, exist_ok=True)
    converter = DocumentConverter()
    result = converter.convert(str(src))
    doc = result.document
    return _build_payload_from_doc(doc, out_dir)


def _try_load_existing(parse_root: Path) -> dict[str, Any] | None:
    meta_path = parse_root / "payload.json"
    if not meta_path.is_file():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    markdown = str(data.get("markdown") or data.get("text") or "")
    content_list = data.get("content_list")
    if not markdown.strip() and not content_list:
        return None
    assets_dir = data.get("assets_dir")
    if assets_dir is not None:
        assets_path = Path(str(assets_dir))
        if assets_path.is_dir():
            data["assets_dir"] = str(assets_path.resolve())
        else:
            data.pop("assets_dir", None)
    return data


def _try_load_content_cache(md5: str) -> dict[str, Any] | None:
    content_root = _content_cache_root(md5)
    parse_root = content_root / "out"
    cached = _try_load_existing(parse_root)
    if cached is None and parse_root.is_dir():
        shutil.rmtree(content_root, ignore_errors=True)
    return cached


def _persist_payload(*, parse_root: Path, payload: dict[str, Any]) -> None:
    meta_path = parse_root / "payload.json"
    tmp_path = meta_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(meta_path)


def _promote_to_content_cache(*, md5: str, parse_root: Path, src: Path) -> None:
    content_root = _content_cache_root(md5)
    out_dest = content_root / "out"
    if out_dest.exists():
        shutil.rmtree(out_dest, ignore_errors=True)
    shutil.copytree(parse_root, out_dest, dirs_exist_ok=True)
    stat = src.stat()
    meta = {
        "md5": md5,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "parsed_at": format_local_ts(),
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
        segment = f"f{file_id}"
        if job_id is not None:
            segment = f"{segment}_j{job_id}"
        work = _cache_root() / "parse" / segment
        out_dir = work / "out"
        work.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir, work, None

    work = Path(tempfile.mkdtemp(prefix="filex-docling-"))
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
) -> None:
    finished_at = format_local_ts()
    logger.info(
        "docling parse done received_at=%s finished_at=%s elapsed_sec=%.1f "
        "name=%s file_id=%s job_id=%s cache_hit=%s cache_tier=%s ok=%s",
        received_at,
        finished_at,
        elapsed_sec,
        original_name,
        file_id,
        job_id,
        cache_hit,
        cache_tier,
        ok,
    )


def run_docling_pipeline(
    file_path: str,
    original_name: str,
    *,
    file_id: int | None = None,
    job_id: int | None = None,
    bypass_cache: bool = False,
) -> dict[str, Any]:
    """Parse a document with Docling.

    bypass_cache: when True, skip job/content cache reads (still writes on MQ runs).
    """
    src = Path(file_path)
    if not src.is_file():
        raise FileNotFoundError(f"file not found: {file_path}")

    received_at = format_local_ts()
    started_mono = time.monotonic()
    file_md5 = _file_md5(src)
    parse_root, work_dir, temp_work = _parse_output_dir(file_id=file_id, job_id=job_id)

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
            )
            return cached

        content_cached = _try_load_content_cache(file_md5)
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
            )
            return content_cached

    if work_dir is not None and parse_root.exists() and next(parse_root.iterdir(), None) is not None:
        shutil.rmtree(work_dir, ignore_errors=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        parse_root.mkdir(parents=True, exist_ok=True)

    file_size = src.stat().st_size
    logger.info(
        "docling parse start received_at=%s name=%s file_id=%s job_id=%s size=%s out=%s bypass_cache=%s",
        received_at,
        original_name,
        file_id,
        job_id,
        file_size,
        parse_root,
        bypass_cache,
    )

    timeout_sec = _parse_timeout_sec()
    ok = False
    try:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="docling-convert") as pool:
            future = pool.submit(_convert_document, src, parse_root)
            try:
                payload = future.result(timeout=timeout_sec)
            except FuturesTimeoutError as exc:
                raise RuntimeError(f"docling parse timeout > {timeout_sec}s") from exc

        _persist_payload(parse_root=parse_root, payload=payload)
        if file_id is not None:
            _promote_to_content_cache(md5=file_md5, parse_root=parse_root, src=src)
        ok = True
        return payload
    finally:
        _log_parse_done(
            received_at=received_at,
            original_name=original_name,
            file_id=file_id,
            job_id=job_id,
            elapsed_sec=time.monotonic() - started_mono,
            cache_hit=False,
            cache_tier="none",
            ok=ok,
        )
        if temp_work is not None:
            shutil.rmtree(temp_work, ignore_errors=True)
