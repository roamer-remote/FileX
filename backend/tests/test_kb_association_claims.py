# Copyright (c) 2026 徐泽宇
"""144: durable association facts preserve workspace boundaries and file lifecycle."""

from types import SimpleNamespace
from unittest.mock import patch
from datetime import timedelta

from sqlalchemy import event
from sqlalchemy.exc import IntegrityError, OperationalError

from models.file import File as FileModel
from models.kb_association import (
    KbAssociationIndexState,
    KbEntity,
    KbEntityAlias,
    KbEntityMention,
    KbEvidenceClaim,
)
from models.kb_association_job import KbAssociationJob
from models.kb_association_reconcile import KbAssociationReconcileCheckpoint
from models.enterprise_rbac import FolderAcl, PERM_LIST, PERM_MANAGE, PERM_READ, SUBJECT_USER
from models.folder import Folder
from models.workspace import Workspace
from schemas.kb import KbAssociationExploreRequest
from services.kb_association_claim_service import delete_association_artifacts_for_file
from services.kb_association_extract_service import _association_llm_rows, _locator
from services.kb_chunking import chunk_markdown
from services.kb_association_job_service import (
    claim_association_job,
    enqueue_association_job,
    reconcile_association_jobs,
    reconcile_association_file,
    reconcile_workspace_page,
    run_one_association_job,
)
from services.kb_association_version import (
    ASSOCIATION_EXTRACTOR_VERSION,
    association_content_fingerprint,
    association_source_fingerprint,
)
from tests.conftest import _create_user
from utils.timezone import naive_db_now
from services.auth_service import create_access_token
from services.system_setting_service import (
    KEY_ENTERPRISE_RBAC_ENABLED,
    KEY_SHARED_WORKSPACES_ENABLED,
    update_settings,
)
from services.workspace_service import create_shared_workspace, set_member_role
from services.kb_association_explore_service import (
    _apply_evidence_budget,
    _plan_query_constraints,
    _qualifiers_conflict,
    _time_interval,
    extract_association_anchors,
    explore_associations,
)
import services.kb_association_explore_service as association_explore_mod


def _file(db, user_id: int, workspace_id: int, name: str) -> FileModel:
    file = FileModel(
        filename=name,
        original_name=name,
        file_path=f"/tmp/{name}",
        file_size=1,
        mime_type="text/markdown",
        user_id=user_id,
        workspace_id=workspace_id,
        has_md=True,
    )
    db.add(file)
    db.flush()
    return file


def test_identity_key_is_unique_only_within_workspace(db_session, regular_user):
    other_user = _create_user(db_session, "association-other")
    ws1 = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
    ws2 = db_session.query(Workspace).filter(Workspace.owner_user_id == other_user.id).one()
    db_session.add_all(
        [
            KbEntity(workspace_id=ws1.id, entity_type="person", canonical_name="A", normalized_name="a", identity_key="email:a@example.com"),
            KbEntity(workspace_id=ws2.id, entity_type="person", canonical_name="A", normalized_name="a", identity_key="email:a@example.com"),
        ]
    )
    db_session.commit()

    db_session.add(
        KbEntity(workspace_id=ws1.id, entity_type="person", canonical_name="A", normalized_name="a", identity_key="email:a@example.com")
    )
    try:
        db_session.commit()
        assert False, "same workspace canonical identity must be unique"
    except IntegrityError:
        db_session.rollback()


def test_delete_association_artifacts_for_file_keeps_shared_entity_until_last_mention(
    db_session, regular_user
):
    workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
    first = _file(db_session, regular_user.id, workspace.id, "first.md")
    second = _file(db_session, regular_user.id, workspace.id, "second.md")
    entity = KbEntity(workspace_id=workspace.id, entity_type="person", canonical_name="徐泽宇", normalized_name="徐泽宇", identity_key="email:x@example.com")
    db_session.add(entity)
    db_session.flush()
    first_mention = KbEntityMention(
        user_id=regular_user.id,
        workspace_id=workspace.id,
        file_id=first.id,
        entity_id=entity.id,
        entity_type="person",
        surface="徐泽宇",
        normalized_surface="徐泽宇",
        resolution_status="resolved",
    )
    second_mention = KbEntityMention(
        user_id=regular_user.id,
        workspace_id=workspace.id,
        file_id=second.id,
        entity_id=entity.id,
        entity_type="person",
        surface="徐泽宇",
        normalized_surface="徐泽宇",
        resolution_status="resolved",
    )
    db_session.add_all((first_mention, second_mention))
    db_session.flush()
    db_session.add_all(
        [
            KbEntityAlias(
                entity_id=entity.id,
                mention_id=first_mention.id,
                source_file_id=first.id,
                normalized_alias="徐泽宇",
            ),
            KbEvidenceClaim(
                user_id=regular_user.id,
                workspace_id=workspace.id,
                file_id=first.id,
                subject_mention_id=first_mention.id,
                predicate="worked_on",
                claim_hash="first-worked-on",
            ),
            KbAssociationIndexState(
                file_id=first.id,
                workspace_id=workspace.id,
                source_fingerprint="v1",
                status="ready",
            ),
        ]
    )
    db_session.commit()

    delete_association_artifacts_for_file(db_session, first.id)
    db_session.commit()

    assert db_session.query(KbEntityMention).filter_by(file_id=first.id).count() == 0
    assert db_session.query(KbEntityAlias).filter_by(source_file_id=first.id).count() == 0
    assert db_session.query(KbEvidenceClaim).filter_by(file_id=first.id).count() == 0
    assert db_session.query(KbAssociationIndexState).filter_by(file_id=first.id).count() == 0
    assert db_session.query(KbEntity).filter_by(id=entity.id).count() == 1

    entity_id = int(entity.id)
    delete_association_artifacts_for_file(db_session, second.id)
    db_session.commit()
    assert db_session.query(KbEntity).filter_by(id=entity_id).count() == 0


def test_association_llm_claim_requires_literal_excerpt_in_declared_chunk():
    chunks = [
        SimpleNamespace(id=10, text="第一段没有共同项目"),
        SimpleNamespace(id=11, text="徐泽宇与邓良玉在世范软件项目协作。"),
    ]
    with patch(
        "services.kb_association_extract_service.chat_json",
        return_value={
            "claims": [
                {
                    "source": "徐泽宇",
                    "target": "世范软件项目",
                    "predicate": "worked_on",
                    "source_chunk_id": 11,
                    "excerpt": "徐泽宇与邓良玉在世范软件项目协作。",
                    "qualifiers": {"period": "2024"},
                },
                {
                    "source": "徐泽宇",
                    "target": "世范软件项目",
                    "predicate": "worked_on",
                    "source_chunk_id": 10,
                    "excerpt": "徐泽宇与邓良玉在世范软件项目协作。",
                },
            ]
        },
    ):
        rows = _association_llm_rows(None, chunks)  # type: ignore[arg-type]

    assert len(rows) == 1
    assert rows[0]["source_chunk_id"] == 11
    assert rows[0]["excerpt"] in chunks[1].text


def test_association_locator_uses_normalized_context_with_real_chunker_offsets():
    markdown = "\n第一段  \n\n\n  第二段包含关键摘录\n"
    pieces = chunk_markdown(markdown, chunk_size=500, overlap=0)
    piece = next(item for item in pieces if "关键摘录" in item.text)
    chunk = SimpleNamespace(
        id=71,
        text=piece.text,
        heading_path=piece.heading_path,
        char_start=piece.char_start,
        char_end=piece.char_end,
    )
    locator = _locator(chunk, excerpt="关键摘录")
    assert locator is not None
    assert locator["hash_mode"] == "excerpt_context_v1"
    assert " ".join(locator["context_excerpt"].split()) in " ".join(markdown.split())


def test_association_llm_prompt_keeps_late_document_chunks():
    late = "徐泽宇与邓良玉在世范软件项目协作。"
    chunks = [
        SimpleNamespace(id=1, text="前言"),
        SimpleNamespace(id=2, text=("前段内容 " * 10000) + late),
    ]
    with patch(
        "services.kb_association_extract_service.chat_json",
        return_value={"claims": [{
            "source": "徐泽宇",
            "target": "邓良玉",
            "predicate": "worked_with",
            "source_chunk_id": 2,
            "excerpt": late,
        }]},
    ) as chat:
        rows = _association_llm_rows(None, chunks)  # type: ignore[arg-type]
    assert rows and rows[0]["source_chunk_id"] == 2
    prompts = [call.args[0] for call in chat.call_args_list]
    assert len(prompts) >= 2
    assert all(len(prompt) <= 40000 + 512 for prompt in prompts)
    assert any(late in prompt for prompt in prompts)


def test_association_llm_batch_failure_is_fail_open():
    chunks = [SimpleNamespace(id=1, text="规则事实"), SimpleNamespace(id=2, text="LLM 事实")]
    with patch(
        "services.kb_association_extract_service.chat_json",
        side_effect=RuntimeError("llm down"),
    ):
        assert _association_llm_rows(None, chunks) == []  # type: ignore[arg-type]


def test_association_llm_dedup_preserves_qualifiers():
    chunks = [SimpleNamespace(id=3, text="徐泽宇与邓良玉分别在 2023、2024 年合作。")]
    with patch(
        "services.kb_association_extract_service.chat_json",
        return_value={"claims": [
            {"source": "徐泽宇", "target": "邓良玉", "predicate": "worked_with", "source_chunk_id": 3, "excerpt": "2023", "qualifiers": {"year": "2023"}},
            {"source": "徐泽宇", "target": "邓良玉", "predicate": "worked_with", "source_chunk_id": 3, "excerpt": "2024", "qualifiers": {"year": "2024"}},
        ]},
    ):
        rows = _association_llm_rows(None, chunks)  # type: ignore[arg-type]
    assert len(rows) == 2


def test_association_enqueue_is_idempotent_per_file_generation(db_session, regular_user):
    workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
    file = _file(db_session, regular_user.id, workspace.id, "generation.md")
    file.md_content_rev = 7
    file.md_content_hash = "hash-v1"
    first = enqueue_association_job(db_session, file)
    second = enqueue_association_job(db_session, file)
    assert first is second
    assert first.source_fingerprint == association_source_fingerprint(file)
    assert first.generation == 7

    file.md_content_rev = 8
    file.md_content_hash = "hash-v2"
    next_job = enqueue_association_job(db_session, file)
    assert next_job.id != first.id
    assert next_job.generation == 8
    assert db_session.query(KbAssociationJob).filter_by(file_id=file.id).count() == 2

    file.md_content_hash = "hash-v3"
    fingerprint_job = enqueue_association_job(db_session, file)
    assert fingerprint_job.id != next_job.id
    assert fingerprint_job.generation == next_job.generation


def test_association_job_claim_and_worker_terminal_success(db_session, regular_user):
    workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
    file = _file(db_session, regular_user.id, workspace.id, "worker.md")
    job = enqueue_association_job(db_session, file)
    db_session.commit()

    with patch("services.kb_association_extract_service.rebuild_association_facts_for_file"):
        assert run_one_association_job(db_session, worker_id="test-worker") is True

    persisted = db_session.query(KbAssociationJob).filter_by(id=job.id).one()
    assert persisted.status == "done"
    assert persisted.attempts == 1


def test_association_stale_max_attempt_job_is_committed_as_failed(db_session, regular_user):
    workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
    file = _file(db_session, regular_user.id, workspace.id, "poison.md")
    job = KbAssociationJob(
        user_id=regular_user.id,
        file_id=file.id,
        workspace_id=workspace.id,
        source_fingerprint="poison",
        generation=0,
        status="running",
        attempts=3,
        worker_id="dead-worker",
        heartbeat_at=naive_db_now() - timedelta(seconds=900),
    )
    db_session.add(job)
    db_session.commit()

    assert claim_association_job(db_session, worker_id="recovery-worker") is None
    persisted = db_session.query(KbAssociationJob).filter_by(id=job.id).one()
    assert persisted.status == "failed"
    assert persisted.last_error == "stale association lease recovered"


def test_association_worker_supersedes_job_when_file_generation_changes(db_session, regular_user):
    workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
    file = _file(db_session, regular_user.id, workspace.id, "changed.md")
    file.md_content_rev = 1
    file.md_content_hash = "before"
    job = enqueue_association_job(db_session, file)
    db_session.commit()

    file.md_content_rev = 2
    file.md_content_hash = "after"
    db_session.commit()
    with patch("services.kb_association_extract_service.rebuild_association_facts_for_file"):
        assert run_one_association_job(db_session, worker_id="reconcile-worker") is True
    persisted = db_session.query(KbAssociationJob).filter_by(id=job.id).one()
    assert persisted.status == "superseded"


def test_association_reconcile_requeues_failed_current_generation(db_session, regular_user):
    workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
    file = _file(db_session, regular_user.id, workspace.id, "reconcile.md")
    job = enqueue_association_job(db_session, file)
    job.status = "failed"
    job.last_error = "temporary"
    db_session.commit()

    assert reconcile_association_jobs(db_session, workspace_id=workspace.id) == 1
    persisted = db_session.query(KbAssociationJob).filter_by(id=job.id).one()
    assert persisted.status == "queued"
    assert persisted.last_error is None


def test_association_reconcile_does_not_revive_terminal_max_attempt_job(db_session, regular_user):
    workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
    file = _file(db_session, regular_user.id, workspace.id, "poison-reconcile.md")
    job = enqueue_association_job(db_session, file)
    job.status = "failed"
    job.attempts = 3
    db_session.commit()
    assert reconcile_association_jobs(db_session, workspace_id=workspace.id) == 0
    assert db_session.query(KbAssociationJob).filter_by(id=job.id).one().status == "failed"


def test_association_reconcile_cursor_advances_across_pages(db_session, regular_user):
    workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
    first = _file(db_session, regular_user.id, workspace.id, "page-first.md")
    second = _file(db_session, regular_user.id, workspace.id, "page-second.md")
    db_session.commit()
    assert reconcile_association_jobs(db_session, workspace_id=workspace.id, batch_size=1) == 1
    assert reconcile_association_jobs(
        db_session, workspace_id=workspace.id, batch_size=1, after_id=first.id
    ) == 1
    assert db_session.query(KbAssociationJob).filter(
        KbAssociationJob.file_id.in_([first.id, second.id])
    ).count() == 2


def test_association_request_accepts_query_and_anchor_entities():
    query_request = KbAssociationExploreRequest(query="Alice and Bob worked together")
    explicit_request = KbAssociationExploreRequest(
        query="关系", anchor_entities=["Alice", "Bob"]
    )
    assert query_request.query.startswith("Alice")
    assert explicit_request.anchor_entities == ["Alice", "Bob"]


def test_association_workspace_reconcile_persists_checkpoint(db_session, regular_user):
    workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
    _file(db_session, regular_user.id, workspace.id, "checkpoint.md")
    result = reconcile_workspace_page(db_session, workspace_id=workspace.id, batch_size=1)
    assert result["next_cursor"] > 0
    checkpoint = db_session.query(KbAssociationReconcileCheckpoint).filter_by(workspace_id=workspace.id).one()
    assert checkpoint.cursor == result["next_cursor"]


def test_association_reconcile_new_round_repairs_old_file_gap(db_session, regular_user):
    workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
    file = _file(db_session, regular_user.id, workspace.id, "round-gap.md")
    while True:
        page = reconcile_workspace_page(db_session, workspace_id=workspace.id, batch_size=100)
        if not page["has_more"]:
            break
    db_session.query(KbAssociationJob).filter_by(file_id=file.id).delete()
    db_session.commit()
    while True:
        page = reconcile_workspace_page(db_session, workspace_id=workspace.id, batch_size=100)
        if not page["has_more"]:
            break
    assert db_session.query(KbAssociationJob).filter_by(file_id=file.id).count() == 1
    assert page["scan_round"] >= 2


def test_association_reconcile_rebuilds_pre_locator_version_done_job(db_session, regular_user):
    workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
    file = _file(db_session, regular_user.id, workspace.id, "legacy-locator-job.md")
    file.md_content_hash = "unchanged-content"
    db_session.add(KbAssociationJob(
        user_id=regular_user.id, file_id=file.id, workspace_id=workspace.id,
        source_fingerprint="unchanged-content", generation=0, status="done",
    ))
    db_session.commit()
    assert reconcile_association_jobs(db_session, workspace_id=workspace.id) == 1
    jobs = db_session.query(KbAssociationJob).filter_by(file_id=file.id).order_by(KbAssociationJob.id).all()
    assert len(jobs) == 2
    assert jobs[-1].status == "queued"
    assert jobs[-1].source_fingerprint != "unchanged-content"


def test_association_file_reconcile_creates_current_generation(db_session, regular_user):
    workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
    file = _file(db_session, regular_user.id, workspace.id, "file-reconcile.md")
    file.md_content_rev = 9
    file.md_content_hash = "current"
    result = reconcile_association_file(db_session, file=file)
    assert result["created"] is True
    job = db_session.query(KbAssociationJob).filter_by(file_id=file.id).one()
    assert job.generation == 9
    assert job.source_fingerprint == association_source_fingerprint(file)


def test_association_file_reconcile_resets_only_exact_current_generation(db_session, regular_user):
    workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
    file = _file(db_session, regular_user.id, workspace.id, "file-reconcile-exact.md")
    file.md_content_rev = 2
    file.md_content_hash = "current"
    current = enqueue_association_job(db_session, file)
    current.status = "failed"
    db_session.flush()
    historical = KbAssociationJob(
        user_id=regular_user.id, file_id=file.id, workspace_id=workspace.id,
        source_fingerprint="old", generation=1, status="superseded",
    )
    db_session.add(historical)
    db_session.commit()
    assert historical.id > current.id
    result = reconcile_association_file(db_session, file=file)
    assert result == {"created": False, "reset": True, "job_id": current.id}
    assert db_session.query(KbAssociationJob).filter_by(id=current.id).one().status == "queued"
    assert db_session.query(KbAssociationJob).filter_by(id=historical.id).one().status == "superseded"


def test_association_query_only_planner_handles_mixed_entities():
    assert extract_association_anchors("OpenAI 与 星河项目 什么关系？") == ["OpenAI", "星河项目"]
    assert extract_association_anchors("OpenAI、星河项目与徐泽宇有什么关系？") == ["OpenAI", "星河项目", "徐泽宇"]
    assert extract_association_anchors("Alice and Project Aurora worked together") == ["Alice", "Project Aurora"]
    assert extract_association_anchors("徐泽宇和邓良玉在哪年合作？") == ["徐泽宇", "邓良玉"]


def test_association_query_constraints_are_structured_and_time_aware():
    constraint = _plan_query_constraints("徐泽宇和邓良玉在 2024 年是否合作？")[0]
    assert constraint.as_dict() == {
        "rule_id": "association.temporal_overlap.v1",
        "field": "qualifiers.time",
        "operator": "overlaps",
        "applies_to": "any_edge",
        "required": True,
        "value": {"start": 2024, "end": 2024},
    }
    assert _plan_query_constraints("徐泽宇和邓良玉是不是合作关系？") == []
    assert _qualifiers_conflict({"year": 2024, "role": "工程师"}, {"year": 2024, "location": "上海"}) is False
    assert _qualifiers_conflict({"year": 2024, "status": "active"}, {"year": 2024, "status": "inactive"}) is True
    assert _qualifiers_conflict({"year": 2023, "status": "active"}, {"year": 2024, "status": "inactive"}) is False
    assert _time_interval({"period": "2022-2024"}) == (2022, 2024)


def test_association_explore_rule_registry_distinguishes_missing_and_conflicting_facts(
    db_session, regular_user,
):
    workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
    file = _file(db_session, regular_user.id, workspace.id, "rule-registry.md")
    first = KbEntityMention(
        user_id=regular_user.id, workspace_id=workspace.id, file_id=file.id,
        entity_type="person", surface="徐泽宇", normalized_surface="徐泽宇",
        resolution_status="resolved",
    )
    second = KbEntityMention(
        user_id=regular_user.id, workspace_id=workspace.id, file_id=file.id,
        entity_type="person", surface="邓良玉", normalized_surface="邓良玉",
        resolution_status="resolved",
    )
    db_session.add_all([first, second])
    db_session.flush()
    claim = KbEvidenceClaim(
        user_id=regular_user.id, workspace_id=workspace.id, file_id=file.id,
        subject_mention_id=first.id, object_mention_id=second.id,
        predicate="worked_with", qualifiers={"location": "上海"},
        claim_hash="rule-location",
    )
    db_session.add_all([
        claim,
        KbAssociationIndexState(
            file_id=file.id, workspace_id=workspace.id,
            source_fingerprint="rules-v1", status="ready",
        ),
    ])
    db_session.commit()

    missing = explore_associations(
        db_session, regular_user, workspace_id=workspace.id,
        anchors=["徐泽宇", "邓良玉"], query="徐泽宇和邓良玉在哪年合作？",
    )
    assert missing["paths"][0]["level"] == "insufficient"
    assert missing["paths"][0]["rule_results"][0]["passed"] is False

    claim.qualifiers = {"year": 2024, "location": "上海"}
    db_session.add(KbEvidenceClaim(
        user_id=regular_user.id, workspace_id=workspace.id, file_id=file.id,
        subject_mention_id=first.id, object_mention_id=second.id,
        predicate="worked_with", qualifiers={"year": 2024, "role": "工程师"},
        claim_hash="rule-complementary",
    ))
    db_session.commit()
    compatible = explore_associations(
        db_session, regular_user, workspace_id=workspace.id,
        anchors=["徐泽宇", "邓良玉"], query="徐泽宇和邓良玉在 2024 年是否合作？",
    )
    assert compatible["paths"]
    assert all(path["level"] == "direct" for path in compatible["paths"])

    db_session.add_all([
        KbEvidenceClaim(
            user_id=regular_user.id, workspace_id=workspace.id, file_id=file.id,
            subject_mention_id=first.id, object_mention_id=second.id,
            predicate="worked_with", qualifiers={"year": 2024, "status": "active"},
            claim_hash="rule-active",
        ),
        KbEvidenceClaim(
            user_id=regular_user.id, workspace_id=workspace.id, file_id=file.id,
            subject_mention_id=first.id, object_mention_id=second.id,
            predicate="worked_with", qualifiers={"year": 2024, "status": "inactive"},
            claim_hash="rule-inactive",
        ),
    ])
    db_session.commit()
    conflicted = explore_associations(
        db_session, regular_user, workspace_id=workspace.id,
        anchors=["徐泽宇", "邓良玉"], query="徐泽宇和邓良玉在 2024 年是否合作？",
    )
    assert any(path["level"] == "conflicted" for path in conflicted["paths"])


def test_association_explore_never_promotes_unresolved_or_ambiguous_mentions(
    db_session, regular_user,
):
    workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
    file = _file(db_session, regular_user.id, workspace.id, "identity-level-gate.md")
    mentions = []
    for surface, status in (
        ("已解析主体", "resolved"),
        ("未解析中点", "unresolved"),
        ("歧义目标", "ambiguous"),
    ):
        mention = KbEntityMention(
            user_id=regular_user.id, workspace_id=workspace.id, file_id=file.id,
            entity_type="person", surface=surface, normalized_surface=surface,
            resolution_status=status,
        )
        db_session.add(mention)
        mentions.append(mention)
    db_session.flush()
    db_session.add_all([
        KbEvidenceClaim(
            user_id=regular_user.id, workspace_id=workspace.id, file_id=file.id,
            subject_mention_id=mentions[0].id, object_mention_id=mentions[1].id,
            predicate="worked_with", claim_hash="identity-gate-first",
        ),
        KbEvidenceClaim(
            user_id=regular_user.id, workspace_id=workspace.id, file_id=file.id,
            subject_mention_id=mentions[1].id, object_mention_id=mentions[2].id,
            predicate="worked_with", claim_hash="identity-gate-second",
        ),
    ])
    db_session.commit()

    unresolved = explore_associations(
        db_session, regular_user, workspace_id=workspace.id,
        anchors=["已解析主体", "未解析中点"],
    )["paths"][0]
    assert unresolved["level"] == "adjacent_only"
    identity_rule = next(
        item for item in unresolved["rule_results"]
        if item["rule_id"] == "association.identity_resolution.v1"
    )
    assert identity_rule["passed"] is False
    assert identity_rule["reason"] == "unresolved_identity"

    mixed = explore_associations(
        db_session, regular_user, workspace_id=workspace.id,
        anchors=["已解析主体", "歧义目标"], max_hops=3,
    )["paths"][0]
    assert mixed["level"] == "adjacent_only"
    assert {
        row["status"] for row in mixed["rule_results"][-1]["failed_mentions"]
    } == {"unresolved", "ambiguous"}


def _object_conflict_fixture(
    db_session, regular_user, *, filename: str, second_year: int, same_value: bool,
    predicate: str = "located_in", first_surface: str = "上海", second_surface: str = "北京",
):
    workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
    file = _file(db_session, regular_user.id, workspace.id, filename)
    subject_surface = filename.removesuffix(".md")
    subject = KbEntityMention(
        user_id=regular_user.id, workspace_id=workspace.id, file_id=file.id,
        entity_type="org", surface=subject_surface, normalized_surface=subject_surface, resolution_status="resolved",
    )
    first = KbEntityMention(
        user_id=regular_user.id, workspace_id=workspace.id, file_id=file.id,
        entity_type="concept", surface=first_surface, normalized_surface=first_surface, resolution_status="resolved",
    )
    second_surface = first_surface if same_value else second_surface
    second = KbEntityMention(
        user_id=regular_user.id, workspace_id=workspace.id, file_id=file.id,
        entity_type="concept", surface=second_surface, normalized_surface=second_surface, resolution_status="resolved",
    )
    db_session.add_all([subject, first, second])
    db_session.flush()
    db_session.add_all([
        KbEvidenceClaim(
            user_id=regular_user.id, workspace_id=workspace.id, file_id=file.id,
            subject_mention_id=subject.id, object_mention_id=first.id,
            predicate=predicate, qualifiers={"year": 2024}, claim_hash=f"{filename}-first",
            source_locator={"excerpt": f"事实为{first_surface}"},
        ),
        KbEvidenceClaim(
            user_id=regular_user.id, workspace_id=workspace.id, file_id=file.id,
            subject_mention_id=subject.id, object_mention_id=second.id,
            predicate=predicate, qualifiers={"year": second_year}, claim_hash=f"{filename}-second",
            source_locator={"excerpt": f"事实为{second_surface}"},
        ),
        KbAssociationIndexState(
            file_id=file.id, workspace_id=workspace.id,
            source_fingerprint=filename, status="ready",
        ),
    ])
    db_session.commit()
    return workspace, file, subject_surface


def test_association_explore_detects_functional_object_conflict(db_session, regular_user):
    workspace, file, subject = _object_conflict_fixture(
        db_session, regular_user, filename="object-conflict.md", second_year=2024, same_value=False,
    )
    result = explore_associations(
        db_session, regular_user, workspace_id=workspace.id,
        anchors=[subject, "上海"], query=f"{subject}位于哪里？",
    )
    path = result["paths"][0]
    assert path["level"] == "conflicted"
    assert path["conflicts"][0]["reason"] == "object_value_conflict"
    assert {claim["predicate"] for claim in path["conflict_claims"]} == {"located_in"}
    assert {claim["claim_id"] for claim in path["claims"] + path["conflict_claims"]} == set(path["conflicts"][0]["claim_ids"])
    assert result["verification_file_ids"] == [file.id]


def test_association_explore_object_values_do_not_conflict_when_time_disjoint_or_equal(
    db_session, regular_user,
):
    for filename, second_year, same_value in (
        ("object-time-disjoint.md", 2023, False),
        ("object-same-value.md", 2024, True),
    ):
        workspace, _, subject = _object_conflict_fixture(
            db_session, regular_user, filename=filename,
            second_year=second_year, same_value=same_value,
        )
        result = explore_associations(
            db_session, regular_user, workspace_id=workspace.id,
            anchors=[subject, "上海"], query=f"{subject}在 2024 年位于哪里？",
        )
        assert result["paths"]
        assert all(path["level"] == "direct" for path in result["paths"])


def test_association_explore_detects_mutually_exclusive_status_objects(db_session, regular_user):
    workspace, _, subject = _object_conflict_fixture(
        db_session, regular_user, filename="status-conflict.md", second_year=2024,
        same_value=False, predicate="employment_status",
        first_surface="在职", second_surface="离职",
    )
    result = explore_associations(
        db_session, regular_user, workspace_id=workspace.id,
        anchors=[subject, "在职"], query=f"{subject}当前是什么状态？",
    )
    assert result["paths"][0]["level"] == "conflicted"
    assert result["paths"][0]["conflicts"][0]["reason"] == "object_value_conflict"


def test_association_explore_enforces_atomic_evidence_budget(
    monkeypatch, db_session, regular_user,
):
    workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
    file = _file(db_session, regular_user.id, workspace.id, "evidence-budget.md")
    file.md_content_hash = "evidence-budget-content"
    source = KbEntityMention(
        user_id=regular_user.id, workspace_id=workspace.id, file_id=file.id,
        entity_type="org", surface="预算主体", normalized_surface="预算主体", resolution_status="unresolved",
    )
    target = KbEntityMention(
        user_id=regular_user.id, workspace_id=workspace.id, file_id=file.id,
        entity_type="concept", surface="预算目标", normalized_surface="预算目标", resolution_status="unresolved",
    )
    db_session.add_all([source, target])
    db_session.flush()
    for index in range(4):
        db_session.add(KbEvidenceClaim(
            user_id=regular_user.id, workspace_id=workspace.id, file_id=file.id,
            subject_mention_id=source.id, object_mention_id=target.id,
            predicate="related_to", qualifiers={"source": index}, claim_hash=f"budget-{index}",
        ))
    db_session.add(KbAssociationIndexState(
        file_id=file.id, workspace_id=workspace.id,
        source_fingerprint=association_source_fingerprint(file), status="ready",
    ))
    db_session.commit()

    monkeypatch.setattr(association_explore_mod, "MAX_EVIDENCE_CLAIMS", 4)
    exact = explore_associations(
        db_session, regular_user, workspace_id=workspace.id,
        anchors=["预算主体", "预算目标"], max_paths=10,
    )
    assert sum(len(path["claims"]) + len(path["conflict_claims"]) for path in exact["paths"]) == 4
    assert "evidence_limit" not in exact["truncation_reasons"]

    monkeypatch.setattr(association_explore_mod, "MAX_EVIDENCE_CLAIMS", 3)
    limited = explore_associations(
        db_session, regular_user, workspace_id=workspace.id,
        anchors=["预算主体", "预算目标"], max_paths=10,
    )
    assert sum(len(path["claims"]) + len(path["conflict_claims"]) for path in limited["paths"]) == 3
    assert limited["truncated"] is True
    assert "evidence_limit" in limited["truncation_reasons"]
    assert limited["verification_file_ids"] == [file.id]


def test_association_evidence_budget_exact_200_and_201_contract():
    exact_paths = [{"claims": [{"claim_id": index}], "conflict_claims": []} for index in range(200)]
    kept, truncated = _apply_evidence_budget(exact_paths, limit=200)
    assert len(kept) == 200
    assert truncated is False

    overflow_paths = exact_paths + [{"claims": [], "conflict_claims": [{"claim_id": 201}]}]
    kept, truncated = _apply_evidence_budget(overflow_paths, limit=200)
    assert len(kept) == 200
    assert truncated is True


def test_association_explore_drops_whole_conflict_path_at_evidence_boundary(
    monkeypatch, db_session, regular_user,
):
    workspace, file, subject = _object_conflict_fixture(
        db_session, regular_user, filename="conflict-budget.md", second_year=2024, same_value=False,
    )
    monkeypatch.setattr(association_explore_mod, "MAX_EVIDENCE_CLAIMS", 1)
    limited = explore_associations(
        db_session, regular_user, workspace_id=workspace.id,
        anchors=[subject, "上海"], max_paths=10,
    )
    assert limited["paths"] == []
    assert limited["verification_file_ids"] == []
    assert "evidence_limit" in limited["truncation_reasons"]

    monkeypatch.setattr(association_explore_mod, "MAX_EVIDENCE_CLAIMS", 2)
    exact = explore_associations(
        db_session, regular_user, workspace_id=workspace.id,
        anchors=[subject, "上海"], max_paths=10,
    )
    assert len(exact["paths"]) == 1
    assert len(exact["paths"][0]["claims"] + exact["paths"][0]["conflict_claims"]) == 2
    assert exact["verification_file_ids"] == [file.id]


def test_association_coverage_requires_current_version_fingerprint(db_session, regular_user):
    workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
    file = _file(db_session, regular_user.id, workspace.id, "version-coverage.md")
    file.md_content_hash = "same-document"
    state = KbAssociationIndexState(
        file_id=file.id, workspace_id=workspace.id,
        source_fingerprint="same-document", status="ready",
    )
    db_session.add(state)
    db_session.commit()
    stale = explore_associations(
        db_session, regular_user, workspace_id=workspace.id, anchors=["不存在甲", "不存在乙"],
    )
    assert stale["coverage"]["status"] == "incomplete"
    assert stale["coverage"]["ready_file_count"] == 0
    assert stale["coverage"]["pending_file_count"] == 1

    job = KbAssociationJob(
        user_id=regular_user.id, file_id=file.id, workspace_id=workspace.id,
        source_fingerprint=association_source_fingerprint(file), generation=0, status="queued",
    )
    db_session.add(job)
    for job_status in ("queued", "running", "done"):
        job.status = job_status
        db_session.commit()
        during_rebuild = explore_associations(
            db_session, regular_user, workspace_id=workspace.id, anchors=["不存在甲", "不存在乙"],
        )
        assert during_rebuild["coverage"]["status"] == "incomplete"
        assert during_rebuild["coverage"]["pending_file_count"] == 1

    state.source_fingerprint = association_source_fingerprint(file)
    state.extractor_version = ASSOCIATION_EXTRACTOR_VERSION
    state.content_fingerprint = association_content_fingerprint(file)
    db_session.commit()
    current = explore_associations(
        db_session, regular_user, workspace_id=workspace.id, anchors=["不存在甲", "不存在乙"],
    )
    assert current["coverage"]["status"] == "complete"
    assert current["coverage"]["ready_file_count"] == 1


def test_association_coverage_uses_one_constant_row_aggregate_for_10k_files(
    db_session, regular_user,
):
    workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
    db_session.execute(FileModel.__table__.insert(), [
        {
            "filename": f"coverage-{index}.md",
            "original_name": f"coverage-{index}.md",
            "file_path": f"/tmp/coverage-{index}.md",
            "file_size": 1,
            "mime_type": "text/markdown",
            "user_id": regular_user.id,
            "workspace_id": workspace.id,
            "has_md": True,
        }
        for index in range(10_000)
    ])
    db_session.flush()
    statements: list[str] = []
    bind = db_session.get_bind()
    visible_file_ids = association_explore_mod._visible_file_ids(
        db_session, regular_user, workspace.id,
    )

    def record_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(bind, "before_cursor_execute", record_statement)
    try:
        counts = association_explore_mod._coverage_counts(
            db_session,
            visible_file_ids,
        )
    finally:
        event.remove(bind, "before_cursor_execute", record_statement)

    assert counts == {
        "visible_file_count": 10_000,
        "ready_file_count": 0,
        "pending_file_count": 0,
        "failed_file_count": 0,
        "not_indexed_file_count": 10_000,
        "status": "incomplete",
    }
    assert len(statements) == 1
    assert "count(" in statements[0].lower()


def test_association_statement_timeout_returns_structured_truncation(
    monkeypatch, client, db_session, regular_user,
):
    token = create_access_token(regular_user.id, regular_user.password_rev)

    def raise_timeout(*_args, **_kwargs):
        raise OperationalError(
            "SELECT association", {},
            Exception("canceling statement due to statement timeout"),
        )

    monkeypatch.setattr(
        "services.kb_association_explore_service.explore_associations",
        raise_timeout,
    )
    response = client.post(
        "/api/knowledge-base/association-explore",
        headers={"Authorization": f"Bearer {token}"},
        json={"anchors": ["甲", "乙"], "max_hops": 2, "max_paths": 7},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["paths"] == []
    assert payload["truncated"] is True
    assert payload["truncation_reasons"] == ["statement_timeout"]
    assert payload["coverage"]["status"] == "incomplete"
    assert payload["coverage"]["counts_available"] is False
    assert payload["budgets"]["max_hops"] == 2
    assert payload["budgets"]["max_paths"] == 7


def test_association_reconcile_allows_enterprise_viewer_with_root_manage(
    client, db_session, regular_user,
):
    update_settings(db_session, {
        KEY_SHARED_WORKSPACES_ENABLED: "true",
        KEY_ENTERPRISE_RBAC_ENABLED: "true",
    })
    manager = _create_user(db_session, "association-enterprise-manager")
    workspace = create_shared_workspace(db_session, name="Association RBAC", owner=regular_user)
    folder = Folder(name="managed", workspace_id=workspace.id, user_id=regular_user.id, sort_order=0)
    db_session.add(folder)
    db_session.flush()
    file = _file(db_session, regular_user.id, workspace.id, "enterprise-managed-file.md")
    file.folder_id = folder.id
    set_member_role(db_session, workspace.id, manager.id, "viewer")
    db_session.add(FolderAcl(
        workspace_id=workspace.id,
        folder_id=None,
        subject_type=SUBJECT_USER,
        subject_id=manager.id,
        permission=PERM_MANAGE,
    ))
    db_session.add(FolderAcl(
        workspace_id=workspace.id,
        folder_id=folder.id,
        subject_type=SUBJECT_USER,
        subject_id=manager.id,
        permission=PERM_MANAGE,
    ))
    db_session.commit()
    token = create_access_token(manager.id, manager.password_rev)
    response = client.post(
        f"/api/knowledge-base/association-reconcile?workspace_id={workspace.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["workspace_id"] == workspace.id
    file_response = client.post(
        f"/api/knowledge-base/association-reconcile?workspace_id={workspace.id}&file_id={file.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert file_response.status_code == 200, file_response.text


def test_association_reconcile_denies_enterprise_viewer_without_manage(
    client, db_session, regular_user,
):
    update_settings(db_session, {
        KEY_SHARED_WORKSPACES_ENABLED: "true",
        KEY_ENTERPRISE_RBAC_ENABLED: "true",
    })
    viewer = _create_user(db_session, "association-enterprise-viewer")
    workspace = create_shared_workspace(db_session, name="Association RBAC deny", owner=regular_user)
    folder = Folder(name="read-only", workspace_id=workspace.id, user_id=regular_user.id, sort_order=0)
    db_session.add(folder)
    db_session.flush()
    file = _file(db_session, regular_user.id, workspace.id, "enterprise-read-file.md")
    file.folder_id = folder.id
    set_member_role(db_session, workspace.id, viewer.id, "viewer")
    db_session.add(FolderAcl(
        workspace_id=workspace.id, folder_id=folder.id,
        subject_type=SUBJECT_USER, subject_id=viewer.id, permission=PERM_READ,
    ))
    db_session.commit()
    token = create_access_token(viewer.id, viewer.password_rev)
    response = client.post(
        f"/api/knowledge-base/association-reconcile?workspace_id={workspace.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403, response.text
    file_response = client.post(
        f"/api/knowledge-base/association-reconcile?workspace_id={workspace.id}&file_id={file.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert file_response.status_code == 403, file_response.text


def test_association_file_reconcile_hides_unreadable_enterprise_file(
    client, db_session, regular_user,
):
    update_settings(db_session, {
        KEY_SHARED_WORKSPACES_ENABLED: "true",
        KEY_ENTERPRISE_RBAC_ENABLED: "true",
    })
    member = _create_user(db_session, "association-enterprise-hidden")
    workspace = create_shared_workspace(db_session, name="Association hidden", owner=regular_user)
    folder = Folder(name="hidden", workspace_id=workspace.id, user_id=regular_user.id, sort_order=0)
    db_session.add(folder)
    db_session.flush()
    file = _file(db_session, regular_user.id, workspace.id, "enterprise-hidden-file.md")
    file.folder_id = folder.id
    set_member_role(db_session, workspace.id, member.id, "viewer")
    db_session.add(FolderAcl(
        workspace_id=workspace.id, folder_id=folder.id,
        subject_type=SUBJECT_USER, subject_id=member.id, permission=PERM_LIST,
    ))
    db_session.commit()
    token = create_access_token(member.id, member.password_rev)
    response = client.post(
        f"/api/knowledge-base/association-reconcile?workspace_id={workspace.id}&file_id={file.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404, response.text


def test_association_reconcile_uses_curator_gate_without_enterprise_rbac(
    client, db_session, regular_user,
):
    update_settings(db_session, {
        KEY_SHARED_WORKSPACES_ENABLED: "true",
        KEY_ENTERPRISE_RBAC_ENABLED: "false",
    })
    member = _create_user(db_session, "association-legacy-member")
    workspace = create_shared_workspace(db_session, name="Association legacy", owner=regular_user)
    file = _file(db_session, regular_user.id, workspace.id, "legacy-file-reconcile.md")
    set_member_role(db_session, workspace.id, member.id, "viewer")
    db_session.commit()
    token = create_access_token(member.id, member.password_rev)
    url = f"/api/knowledge-base/association-reconcile?workspace_id={workspace.id}"
    assert client.post(url, headers={"Authorization": f"Bearer {token}"}).status_code == 403
    file_url = f"{url}&file_id={file.id}"
    assert client.post(file_url, headers={"Authorization": f"Bearer {token}"}).status_code == 403
    set_member_role(db_session, workspace.id, member.id, "curator")
    db_session.commit()
    assert client.post(url, headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert client.post(file_url, headers={"Authorization": f"Bearer {token}"}).status_code == 200



class TestAbortAssociationJobsForFileDelete:
    """148: abort_kb_association_jobs_for_file_delete marks queued/running jobs cancelled."""

    def test_abort_queued_job(self, db_session, regular_user):
        """T-4a: queued → cancelled."""
        from services.kb_association_job_service import (
            abort_kb_association_jobs_for_file_delete,
        )
        workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
        f = _file(db_session, regular_user.id, workspace.id, "abort-queued.md")
        job = KbAssociationJob(
            user_id=f.user_id,
            file_id=f.id,
            workspace_id=f.workspace_id,
            source_fingerprint="test-fp",
            generation=1,
            status="queued",
        )
        db_session.add(job)
        db_session.commit()

        ids = abort_kb_association_jobs_for_file_delete(db_session, f.id)
        db_session.commit()

        assert len(ids) == 1
        reloaded = db_session.query(KbAssociationJob).filter(KbAssociationJob.id == job.id).first()
        assert reloaded is not None
        assert reloaded.status == "cancelled"
        assert reloaded.last_error == "file deleted"

    def test_abort_running_job(self, db_session, regular_user):
        """T-4a: running → cancelled."""
        from services.kb_association_job_service import (
            abort_kb_association_jobs_for_file_delete,
        )
        workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
        f = _file(db_session, regular_user.id, workspace.id, "abort-running.md")
        job = KbAssociationJob(
            user_id=f.user_id,
            file_id=f.id,
            workspace_id=f.workspace_id,
            source_fingerprint="test-fp-2",
            generation=1,
            status="running",
            worker_id="test-worker",
        )
        db_session.add(job)
        db_session.commit()

        ids = abort_kb_association_jobs_for_file_delete(db_session, f.id)
        db_session.commit()

        assert len(ids) == 1
        reloaded = db_session.query(KbAssociationJob).filter(KbAssociationJob.id == job.id).first()
        assert reloaded is not None
        assert reloaded.status == "cancelled"
        assert reloaded.last_error == "file deleted"

    def test_abort_skips_done_job(self, db_session, regular_user):
        """done jobs are not affected."""
        from services.kb_association_job_service import (
            abort_kb_association_jobs_for_file_delete,
        )
        workspace = db_session.query(Workspace).filter(Workspace.owner_user_id == regular_user.id).one()
        f = _file(db_session, regular_user.id, workspace.id, "abort-done.md")
        job = KbAssociationJob(
            user_id=f.user_id,
            file_id=f.id,
            workspace_id=f.workspace_id,
            source_fingerprint="test-fp-3",
            generation=1,
            status="done",
        )
        db_session.add(job)
        db_session.commit()

        ids = abort_kb_association_jobs_for_file_delete(db_session, f.id)
        db_session.commit()

        assert len(ids) == 0
        reloaded = db_session.query(KbAssociationJob).filter(KbAssociationJob.id == job.id).first()
        assert reloaded.status == "done"
