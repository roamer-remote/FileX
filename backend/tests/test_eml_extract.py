from email.message import EmailMessage
from email.message import Message
from email.policy import default

import pytest

from services.extract.eml_extract import EmlResourceLimitError, extract_eml
import services.extract.eml_extract as eml_extract


def _write_message(tmp_path, message: EmailMessage, name: str = "mail.eml"):
    path = tmp_path / name
    path.write_bytes(message.as_bytes(policy=default))
    return path


def test_extract_eml_prefers_plain_text_and_lists_attachment_metadata(tmp_path):
    message = EmailMessage()
    message["Subject"] = "会议通知"
    message["From"] = "Alice <alice@example.com>"
    message["To"] = "Bob <bob@example.com>"
    message["Bcc"] = "Hidden <hidden@example.com>"
    message.set_content("请参加会议。")
    message.add_attachment(b"secret-bytes", maintype="application", subtype="pdf", filename="合同.pdf")

    result = extract_eml(str(_write_message(tmp_path, message)))

    assert result.engine == "eml-parser"
    assert "# 会议通知" in result.text
    assert "请参加会议。" in result.text
    assert "合同.pdf" in result.text
    assert "application/pdf" in result.text
    assert "secret-bytes" not in result.text
    assert "hidden@example.com" not in result.text


def test_extract_eml_converts_html_when_plain_text_is_absent(tmp_path):
    message = EmailMessage()
    message["Subject"] = "HTML mail"
    message.set_content("<h1>Hello</h1><p><script>alert(1)</script>World</p>", subtype="html")

    result = extract_eml(str(_write_message(tmp_path, message)))

    assert "# Hello" in result.text
    assert "World" in result.text
    assert "script" not in result.text.lower()
    assert "alert" not in result.text


def test_extract_eml_accepts_bounded_quoted_printable_body(tmp_path):
    message = EmailMessage()
    message["Subject"] = "encoded body"
    message.set_content("这是 quoted-printable 正文。", cte="quoted-printable")

    result = extract_eml(str(_write_message(tmp_path, message)))

    assert "quoted\\-printable 正文" in result.text


def test_extract_eml_rejects_non_mime_content(tmp_path):
    path = tmp_path / "fake.eml"
    path.write_bytes(b"this is not an email")

    with pytest.raises(ValueError, match="MIME"):
        extract_eml(str(path))


def test_extract_eml_rejects_arbitrary_header_impersonation(tmp_path):
    path = tmp_path / "fake-header.eml"
    path.write_bytes(b"X-Not-Mail: yes\n\nthis is not an email")

    with pytest.raises(ValueError, match="MIME"):
        extract_eml(str(path))


def test_extract_eml_enforces_part_limit(tmp_path):
    message = EmailMessage()
    message.set_content("body")
    for index in range(1001):
        message.add_attachment(b"x", maintype="application", subtype="octet-stream", filename=f"{index}.bin")

    with pytest.raises(EmlResourceLimitError, match="MIME 部件"):
        extract_eml(str(_write_message(tmp_path, message)))


def test_extract_eml_lists_nested_eml_without_recursing(tmp_path):
    nested = EmailMessage()
    nested["Subject"] = "nested secret"
    nested.set_content("nested body must not be indexed")
    outer = EmailMessage()
    outer["Subject"] = "outer"
    outer.set_content("outer body")
    outer.add_attachment(nested.as_bytes(), maintype="message", subtype="rfc822", filename="forwarded.eml")

    result = extract_eml(str(_write_message(tmp_path, outer)))

    assert "forwarded.eml" in result.text
    assert "nested secret" not in result.text
    assert "nested body must not be indexed" not in result.text


def test_extract_eml_lists_cid_inline_resource_without_saving_it(tmp_path):
    message = EmailMessage()
    message["Subject"] = "inline"
    message.set_content("body")
    message.add_attachment(b"image-bytes", maintype="image", subtype="png", cid="<logo@local>")

    result = extract_eml(str(_write_message(tmp_path, message)))

    assert "（未命名附件）" in result.text
    assert "内嵌图片" in result.text
    assert "image-bytes" not in result.text
    assert not list(tmp_path.glob("**/attachments/*"))


def test_extract_eml_does_not_decode_attachment_payload(tmp_path, monkeypatch):
    message = EmailMessage()
    message.set_content("body")
    message.add_attachment(b"secret-bytes", maintype="application", subtype="pdf", filename="secret.pdf")
    original_get_payload = Message.get_payload
    attachment_decode_calls = 0

    def guarded_get_payload(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal attachment_decode_calls
        if kwargs.get("decode") is True and self.get_content_disposition() == "attachment":
            attachment_decode_calls += 1
            raise AssertionError("attachment payload must not be decoded")
        return original_get_payload(self, *args, **kwargs)

    monkeypatch.setattr(Message, "get_payload", guarded_get_payload)
    result = extract_eml(str(_write_message(tmp_path, message)))

    assert "secret.pdf" in result.text
    assert attachment_decode_calls == 0


def test_extract_eml_escapes_plain_text_and_attachment_markdown(tmp_path):
    message = EmailMessage()
    message["Subject"] = "[subject](https://example.com)"
    message.set_content("# injected\n<img src=x onerror=alert(1)>\n[link](javascript:alert(1))")
    message.add_attachment(b"x", maintype="application", subtype="octet-stream", filename="`![x](evil)`")

    result = extract_eml(str(_write_message(tmp_path, message)))

    assert "\\<img" in result.text.lower()
    assert "javascript:" not in result.text.lower()
    assert "\\# injected" in result.text
    assert "'![x](evil)'" in result.text


def test_extract_eml_escapes_html_entities_after_conversion(tmp_path):
    message = EmailMessage()
    message.set_content("<p>&lt;img src=x onerror=alert(1)&gt;</p>", subtype="html")

    result = extract_eml(str(_write_message(tmp_path, message)))

    assert "\\<img" in result.text.lower()
    assert "onerror" in result.text.lower()


def test_extract_eml_rejects_oversized_source_before_parsing(tmp_path, monkeypatch):
    monkeypatch.setattr(eml_extract, "MAX_SOURCE_BYTES", 10)
    path = tmp_path / "large.eml"
    path.write_bytes(b"From: a@example.com\n\n0123456789")

    with pytest.raises(EmlResourceLimitError, match="原始 EML"):
        extract_eml(str(path))


def test_extract_eml_checks_nested_part_headers(tmp_path):
    message = EmailMessage()
    message.set_content("body")
    message.make_mixed()
    child = EmailMessage()
    child["X-Large-Header"] = "x" * (64 * 1024)
    child.set_content("nested")
    message.attach(child)

    with pytest.raises(EmlResourceLimitError, match="邮件头字段"):
        extract_eml(str(_write_message(tmp_path, message)))
