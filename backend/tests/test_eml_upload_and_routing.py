from models.file import File as FileModel
from services.extract.policy import EXTRACT_EXTENSIONS, needs_extract, supports_reextract
from services.file_service import get_mime_type
from services.extract.providers.registry import extract_with_provider


def test_eml_is_an_extractable_upload_type():
    assert "eml" in EXTRACT_EXTENSIONS
    assert get_mime_type("meeting.eml") == "message/rfc822"


def test_eml_file_can_be_reextracted(tmp_path):
    path = tmp_path / "meeting.eml"
    path.write_bytes(b"From: a@example.com\n\nbody")
    file_record = FileModel(original_name="meeting.eml", file_path=str(path), mime_type="message/rfc822")
    assert supports_reextract(file_record)


def test_explicit_nonlegacy_provider_cannot_override_eml(tmp_path):
    path = tmp_path / "meeting.eml"
    path.write_bytes(b"From: a@example.com\nSubject: x\n\nbody")
    from models.file import File as FileModel

    result = extract_with_provider(
        FileModel(original_name="meeting.eml", file_path=str(path), mime_type="message/rfc822"),
        provider_override="mineru",
    )
    assert result.engine == "eml-parser"


def test_eml_route_uses_persisted_mime_after_display_rename(tmp_path):
    path = tmp_path / "renamed.pdf"
    path.write_bytes(b"From: a@example.com\nSubject: x\n\nbody")
    file_record = FileModel(
        original_name="renamed.pdf",
        file_path=str(path),
        mime_type="message/rfc822",
    )

    result = extract_with_provider(file_record, provider_override="mineru")

    assert result.engine == "eml-parser"
    assert supports_reextract(file_record)
    assert needs_extract(file_record)


def test_non_eml_file_named_eml_does_not_enter_eml_parser(tmp_path, monkeypatch):
    path = tmp_path / "ordinary.eml"
    path.write_text("ordinary text", encoding="utf-8")
    file_record = FileModel(
        original_name="ordinary.eml",
        file_path=str(path),
        mime_type="text/plain",
    )

    import services.extract.providers.registry as registry

    monkeypatch.setattr(
        registry,
        "_legacy_extract",
        lambda _file, **_kwargs: type("Result", (), {"engine": "legacy"})(),
    )
    result = extract_with_provider(file_record)

    assert result.engine == "legacy"
    assert not supports_reextract(file_record)
    assert not needs_extract(file_record)


def test_legacy_router_uses_persisted_eml_type_after_display_rename(tmp_path, monkeypatch):
    path = tmp_path / "renamed.pdf"
    path.write_bytes(b"From: a@example.com\nSubject: x\n\nbody")
    file_record = FileModel(
        original_name="renamed.pdf",
        file_path=str(path),
        mime_type="message/rfc822",
    )

    import services.extract.router as router

    monkeypatch.setattr(
        router,
        "extract_pdf",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("EML must not enter PDF extraction")),
    )
    result = router.extract_text_from_file(file_record)

    assert result.engine == "eml-parser"
