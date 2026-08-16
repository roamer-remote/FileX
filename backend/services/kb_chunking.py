# Copyright (c) 2026 徐泽宇
"""Paragraph-aware text chunking for KB indexing.

Authors:
    徐泽宇

Copyright:
    © 2026 徐泽宇
"""

from __future__ import annotations

from dataclasses import dataclass

from config import KB_CHUNK_OVERLAP, KB_CHUNK_SIZE
from services.extract.loc_markers import ChunkLocation, split_body_by_loc_markers
from utils.text_sanitize import strip_nul_bytes


@dataclass(frozen=True)
class TextChunk:
    """文本分块 业务服务。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-29

        Attributes:
            text: 文本（str）。
            char_start: charstart（int）。
            char_end: charend（int）。
            heading_path: heading路径（str | None）。
            block_type: block类型（str）。
    """
    text: str
    char_start: int
    char_end: int
    heading_path: str | None = None
    block_type: str = "paragraph"
    loc_type: str | None = None
    loc_start: int | None = None
    loc_end: int | None = None
    loc_label: str | None = None


def _with_location(chunk: TextChunk, loc: ChunkLocation | None, *, offset: int) -> TextChunk:
    if loc is None:
        return TextChunk(
            text=chunk.text,
            char_start=chunk.char_start + offset,
            char_end=chunk.char_end + offset,
            heading_path=chunk.heading_path,
            block_type=chunk.block_type,
        )
    return TextChunk(
        text=chunk.text,
        char_start=chunk.char_start + offset,
        char_end=chunk.char_end + offset,
        heading_path=chunk.heading_path,
        block_type=chunk.block_type,
        loc_type=loc.loc_type,
        loc_start=loc.loc_start,
        loc_end=loc.loc_end,
        loc_label=loc.loc_label,
    )


def format_chunk_for_embed(text: str, heading_path: str | None = None) -> str:
    """DEPRECATED: 请使用 build_embed_input 并传入完整 file 元数据。"""
    from services.kb_chunk_embed_input import build_embed_input

    return build_embed_input(
        body=text,
        heading_path=heading_path,
        workspace_name=None,
        tags=[],
        content_kind=None,
        original_name=None,
    )



def _coalesce_short_pieces(pieces: list[str], *, size: int, min_piece: int) -> list[str]:
    if not pieces:
        return []
    out: list[str] = []
    for piece in pieces:
        if not piece:
            continue
        if out and len(out[-1]) + len(piece) + 2 <= size:
            out[-1] = f"{out[-1]}\n\n{piece}".strip()
            continue
        out.append(piece)
    i = 0
    while i < len(out):
        if len(out[i]) >= min_piece or len(out) == 1:
            i += 1
            continue
        if i > 0 and len(out[i - 1]) + len(out[i]) + 2 <= size:
            out[i - 1] = f"{out[i - 1]}\n\n{out[i]}".strip()
            out.pop(i)
            continue
        if i + 1 < len(out) and len(out[i]) + len(out[i + 1]) + 2 <= size:
            out[i] = f"{out[i]}\n\n{out[i + 1]}".strip()
            out.pop(i + 1)
            continue
        i += 1
    return out


def _split_long_segment_recursive(segment: str, size: int, overlap: int) -> list[str]:
    min_piece = max(128, size // 4)
    if len(segment) <= size:
        return [segment]
    separators = ["。", "\n\n", "\n", " "]
    for sep in separators:
        if sep not in segment:
            continue
        parts: list[str] = []
        start = 0
        while start < len(segment):
            end = min(len(segment), start + size)
            if end >= len(segment):
                tail = segment[start:].strip()
                if tail:
                    parts.append(tail)
                break
            window = segment[start:end]
            split_at = window.rfind(sep)
            if split_at <= 0:
                split_at = size
            else:
                split_at += len(sep)
            piece = segment[start : start + split_at].strip()
            if piece:
                parts.append(piece)
            start += max(1, split_at - overlap)
        merged = _coalesce_short_pieces(parts, size=size, min_piece=min_piece)
        if merged and all(len(x) <= size for x in merged):
            return merged
    pieces: list[str] = []
    i = 0
    while i < len(segment):
        piece = segment[i : i + size].strip()
        if piece:
            pieces.append(piece)
        i += max(1, size - overlap)
    return _coalesce_short_pieces(pieces, size=size, min_piece=min_piece)



def chunk_text(
    body: str,
    *,
    chunk_size: int | None = None,
    overlap: int | None = None,
    split_recursive: bool = False,
) -> list[TextChunk]:
    size = chunk_size if chunk_size is not None else KB_CHUNK_SIZE
    ov = overlap if overlap is not None else KB_CHUNK_OVERLAP
    if size <= 0:
        raise ValueError("chunk_size must be positive")
    if ov < 0 or ov >= size:
        raise ValueError("overlap must be in [0, chunk_size)")

    text = strip_nul_bytes(body).strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks: list[TextChunk] = []
    buf = ""
    buf_start = 0
    cursor = 0

    def flush_buffer(end_pos: int) -> None:
        nonlocal buf, buf_start
        if not buf.strip():
            buf = ""
            return
        start = buf_start
        end = end_pos
        chunks.append(TextChunk(text=buf.strip(), char_start=start, char_end=end, block_type="paragraph"))
        if ov > 0 and len(buf) > ov:
            tail = buf[-ov:]
            buf_start = end - len(tail)
            buf = tail
        else:
            buf = ""
            buf_start = end

    for para in paragraphs:
        para_start = cursor
        para_end = para_start + len(para)
        cursor = para_end + 2

        candidate = (buf + '\n\n' + para).strip() if buf else para
        if len(candidate) <= size:
            if not buf:
                buf_start = para_start
            buf = candidate
            continue

        if buf:
            flush_buffer(para_start)
        if len(para) <= size:
            buf = para
            buf_start = para_start
            continue

        if split_recursive:
            split_pieces = _split_long_segment_recursive(para, size, ov)
            offset = 0
            for piece in split_pieces:
                abs_start = para_start + offset
                abs_end = abs_start + len(piece)
                chunks.append(
                    TextChunk(text=piece.strip(), char_start=abs_start, char_end=abs_end, block_type="paragraph")
                )
                offset += max(1, len(piece) - ov)
            continue

        i = 0
        while i < len(para):
            piece = para[i : i + size]
            abs_start = para_start + i
            abs_end = abs_start + len(piece)
            chunks.append(
                TextChunk(text=piece.strip(), char_start=abs_start, char_end=abs_end, block_type="paragraph")
            )
            i += max(1, size - ov)

    if buf:
        flush_buffer(cursor)

    return chunks


def _chunk_blocks(
    blocks: list,
    *,
    chunk_size: int,
    overlap: int,
    split_recursive: bool = False,
) -> list[TextChunk]:
    from services.kb_markdown_structure import MdBlock

    chunks: list[TextChunk] = []
    for block in blocks:
        if not isinstance(block, MdBlock):
            continue
        if len(block.text) <= chunk_size:
            chunks.append(
                TextChunk(
                    text=block.text,
                    char_start=block.char_start,
                    char_end=block.char_end,
                    heading_path=block.heading_path,
                    block_type=block.block_type,
                )
            )
            continue
        for piece in chunk_text(
            block.text,
            chunk_size=chunk_size,
            overlap=overlap,
            split_recursive=split_recursive,
        ):
            chunks.append(
                TextChunk(
                    text=piece.text,
                    char_start=block.char_start + piece.char_start,
                    char_end=block.char_start + piece.char_end,
                    heading_path=block.heading_path,
                    block_type=block.block_type,
                )
            )
    return chunks


def chunk_markdown(
    body: str,
    *,
    chunk_size: int | None = None,
    overlap: int | None = None,
    split_recursive: bool = False,
) -> list[TextChunk]:
    """Structure-aware chunking: headings/tables/code blocks, then size split within sections."""
    from services.kb_markdown_structure import split_markdown_blocks

    size = chunk_size if chunk_size is not None else KB_CHUNK_SIZE
    ov = overlap if overlap is not None else KB_CHUNK_OVERLAP
    text = strip_nul_bytes(body).strip()
    if not text:
        return []

    segments = split_body_by_loc_markers(text)
    has_loc = any(loc is not None for loc, _ in segments)
    if not has_loc:
        blocks = split_markdown_blocks(text)
        if not blocks:
            return chunk_text(text, chunk_size=size, overlap=ov, split_recursive=split_recursive)
        return _chunk_blocks(blocks, chunk_size=size, overlap=ov, split_recursive=split_recursive)

    chunks: list[TextChunk] = []
    search_from = 0
    for loc, segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        idx = text.find(segment, search_from)
        if idx < 0:
            idx = search_from
        blocks = split_markdown_blocks(segment)
        if not blocks:
            seg_chunks = chunk_text(segment, chunk_size=size, overlap=ov, split_recursive=split_recursive)
        else:
            seg_chunks = _chunk_blocks(blocks, chunk_size=size, overlap=ov, split_recursive=split_recursive)
        for piece in seg_chunks:
            chunks.append(_with_location(piece, loc, offset=idx))
        search_from = idx + len(segment)
    return chunks
