"""Bounded EML to Markdown extraction without persisting attachments."""

from __future__ import annotations

import re
from email import policy
from email.header import decode_header, make_header
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path

from services.extract.base import ExtractResult

MAX_MIME_PARTS = 1000
MAX_MIME_DEPTH = 20
MAX_HEADER_BYTES = 64 * 1024
MAX_BODY_BYTES = 10 * 1024 * 1024
MAX_MARKDOWN_BYTES = 20 * 1024 * 1024
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAIL_HEADER_NAMES = frozenset(
    {
        "from",
        "to",
        "cc",
        "bcc",
        "subject",
        "date",
        "sender",
        "reply-to",
        "message-id",
        "mime-version",
        "content-type",
        "content-transfer-encoding",
    }
)


class EmlResourceLimitError(ValueError):
    """The EML exceeded a bounded parser resource limit."""


class _HtmlToMarkdown(HTMLParser):
    _BLOCK_TAGS = {"p", "div", "section", "article", "header", "footer", "li", "tr", "br"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[no-untyped-def]
        tag = tag.lower()
        if tag in {"script", "style", "iframe", "object", "embed", "svg", "head"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append(f"\n{'#' * int(tag[1])} ")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "iframe", "object", "embed", "svg", "head"}:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if not self.skip_depth and tag in self._BLOCK_TAGS | {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(_escape_markdown_text(data))

    def markdown(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).strip()
    except (LookupError, UnicodeError, ValueError):
        return value.encode("utf-8", "replace").decode("utf-8", "replace").strip()


def _safe_field(value: str) -> str:
    return _escape_markdown_text(value.replace("\r", " ").replace("\n", " ")).strip()


def _escape_markdown_text(value: str) -> str:
    """Escape user-controlled text while preserving ordinary line breaks."""
    value = re.sub(r"(?i)javascript\s*:", "javascript\\:", value)
    value = value.replace("\\", "\\\\")
    for char in "`*_[]()#+-.!<>|{}":
        value = value.replace(char, f"\\{char}")
    return value.replace("\x00", "").replace("\r", "")


def _safe_code_text(value: str) -> str:
    """Keep attachment names literal inside a Markdown code span."""
    return value.replace("\x00", "").replace("\r", " ").replace("\n", " ").replace("\\", "\\\\").replace("`", "'").strip()


def _part_text(part) -> str:  # type: ignore[no-untyped-def]
    encoded = part.get_payload(decode=False)
    if isinstance(encoded, str):
        encoded_size = len(encoded.encode("utf-8", "replace"))
        transfer_encoding = str(part.get("Content-Transfer-Encoding") or "").lower().strip()
        if transfer_encoding == "quoted-printable":
            max_encoded_size = MAX_BODY_BYTES * 3 + 4096
        elif transfer_encoding == "base64":
            max_encoded_size = (MAX_BODY_BYTES * 4) // 3 + 4096
        else:
            max_encoded_size = MAX_BODY_BYTES + 4096
        if encoded_size > max_encoded_size:
            raise EmlResourceLimitError(f"邮件正文编码内容超过上限 {MAX_BODY_BYTES} 字节")
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        return ""
    if len(payload) > MAX_BODY_BYTES:
        raise EmlResourceLimitError(f"邮件正文超过上限 {MAX_BODY_BYTES} 字节")
    return payload.decode(part.get_content_charset() or "utf-8", "replace")


def _size_label(size: int | None) -> str:
    if size is None:
        return "大小未知"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _declared_size(part) -> int | None:  # type: ignore[no-untyped-def]
    value = str(part.get("Content-Length") or "").strip()
    try:
        size = int(value)
    except ValueError:
        return None
    return size if size >= 0 else None


def _collect_parts(message) -> tuple[list, list]:  # type: ignore[no-untyped-def]
    body_parts: list = []
    attachments: list = []
    count = 0

    def visit(part, depth: int) -> None:  # type: ignore[no-untyped-def]
        nonlocal count
        count += 1
        if count > MAX_MIME_PARTS:
            raise EmlResourceLimitError(f"MIME 部件超过上限 {MAX_MIME_PARTS}")
        if depth > MAX_MIME_DEPTH:
            raise EmlResourceLimitError(f"MIME 嵌套深度超过上限 {MAX_MIME_DEPTH}")
        for key, value in part.items():
            if len(key.encode("utf-8", "replace")) + len(str(value).encode("utf-8", "replace")) > MAX_HEADER_BYTES:
                raise EmlResourceLimitError(f"邮件头字段超过上限 {MAX_HEADER_BYTES} 字节")
        filename = _decode_header(part.get_filename())
        disposition = (part.get_content_disposition() or "").lower()
        if filename or disposition in {"attachment", "inline"} or part.get("Content-ID"):
            attachments.append(
                {"filename": filename or "（未命名附件）", "mime": part.get_content_type(),
                 "size": _declared_size(part),
                 "inline": disposition == "inline" or bool(part.get("Content-ID"))}
            )
            return
        if part.is_multipart():
            for child in part.iter_parts():
                visit(child, depth + 1)
            return
        if part.get_content_type() in {"text/plain", "text/html"}:
            body_parts.append(part)

    visit(message, 0)
    return body_parts, attachments


def extract_eml(path: str, *, file_id: int | None = None) -> ExtractResult:
    del file_id
    source_size = Path(path).stat().st_size
    if source_size > MAX_SOURCE_BYTES:
        raise EmlResourceLimitError(f"原始 EML 超过上限 {MAX_SOURCE_BYTES} 字节")
    raw = Path(path).read_bytes()
    if len(raw) > MAX_SOURCE_BYTES:
        raise EmlResourceLimitError(f"原始 EML 超过上限 {MAX_SOURCE_BYTES} 字节")
    message = BytesParser(policy=policy.default).parsebytes(raw)
    if not any(key.lower() in MAIL_HEADER_NAMES for key in message.keys()):
        raise ValueError("无有效 MIME 邮件头")
    body_parts, attachments = _collect_parts(message)
    plain = next((p for p in body_parts if p.get_content_type() == "text/plain"), None)
    html_part = next((p for p in body_parts if p.get_content_type() == "text/html"), None)
    body_type = "plain"
    body = _part_text(plain) if plain is not None else ""
    if not body.strip() and html_part is not None:
        body_type = "html"
        parser = _HtmlToMarkdown()
        parser.feed(_part_text(html_part))
        parser.close()
        body = parser.markdown()
    elif body_type == "plain":
        body = _escape_markdown_text(body)
    if len(body.encode("utf-8", "replace")) > MAX_BODY_BYTES:
        raise EmlResourceLimitError(f"邮件正文超过上限 {MAX_BODY_BYTES} 字节")
    subject = _decode_header(message.get("Subject")) or "无主题邮件"
    lines = [f"# {_safe_field(subject)}", "", "## 邮件信息", ""]
    for label, key in (("发件人", "From"), ("收件人", "To"), ("抄送", "Cc"), ("回复至", "Reply-To"), ("日期", "Date"), ("Message-ID", "Message-ID")):
        value = _decode_header(message.get(key))
        if value:
            lines.append(f"- {label}：{_safe_field(value)}")
    lines.extend(["", "## 正文", "", body.strip() or "（邮件正文为空）", "", "## 附件", ""])
    if not attachments:
        lines.append("无附件。")
    else:
        for item in attachments:
            name = _safe_code_text(item["filename"])
            inline = "，内嵌图片" if item["inline"] else ""
            lines.append(f"- `{name}`（{item['mime']}，大小：{_size_label(item['size'])}{inline}）")
    lines.extend(["", f"<!-- eml:body_type={body_type} -->"])
    markdown = "\n".join(lines).strip() + "\n"
    if len(markdown.encode("utf-8")) > MAX_MARKDOWN_BYTES:
        raise EmlResourceLimitError(f"Markdown 输出超过上限 {MAX_MARKDOWN_BYTES} 字节")
    return ExtractResult(text=markdown, engine="eml-parser")
