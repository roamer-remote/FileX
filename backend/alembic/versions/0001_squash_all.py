"""squash_all: 合并 28 个历史迁移为 1 个基准

取代了 5a57d5c257fb_initial_schema ~ v2w3x4y5z6a7_kb_search_filename_boost。
使用 CREATE TABLE IF NOT EXISTS 与 CREATE INDEX IF NOT EXISTS，
对新环境（空库）和旧环境（已有表）均安全。

Revision ID: 0001_squash_all
Revises:
Create Date: 2026-05-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_squash_all"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # pgvector：kb_chunks.embedding 依赖；新库须先于建表启用
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── Users ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            is_admin BOOLEAN,
            created_at TIMESTAMP DEFAULT now(),
            password_rev INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            avatar_mime VARCHAR(80),
            avatar_data BYTEA,
            last_login_at TIMESTAMP
        )
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_username_key ON users (username)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_id ON users (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_username ON users (username)")

    # ── Workspaces ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS workspaces (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            slug VARCHAR(64) NOT NULL,
            kind VARCHAR(16) NOT NULL DEFAULT 'shared',
            owner_user_id INTEGER,
            created_at TIMESTAMP DEFAULT now()
        )
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_workspaces_slug ON workspaces (slug)")

    # ── Workspace Members ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS workspace_members (
            workspace_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role VARCHAR(16) NOT NULL DEFAULT 'viewer',
            PRIMARY KEY (workspace_id, user_id)
        )
    """)

    # ── Folders ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS folders (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            parent_id INTEGER,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT now(),
            workspace_id INTEGER NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_folders_id ON folders (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_folders_workspace_id ON folders (workspace_id)")

    # ── Files ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id SERIAL PRIMARY KEY,
            filename VARCHAR(500) NOT NULL,
            original_name VARCHAR(500) NOT NULL,
            file_path VARCHAR(1000) NOT NULL,
            file_size INTEGER NOT NULL,
            mime_type VARCHAR(100) NOT NULL,
            md5_hash VARCHAR(32),
            has_md BOOLEAN,
            md_file_path VARCHAR(1000),
            folder_id INTEGER,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now(),
            index_status VARCHAR(16) NOT NULL DEFAULT 'skipped',
            indexed_at TIMESTAMP,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            index_error TEXT,
            extract_status VARCHAR(16) NOT NULL DEFAULT 'not_needed',
            extracted_at TIMESTAMP,
            extract_error TEXT,
            extract_engine VARCHAR(64),
            workspace_id INTEGER NOT NULL,
            publish_status VARCHAR(16) NOT NULL DEFAULT 'published',
            md_content_rev INTEGER NOT NULL DEFAULT 0,
            normalized_path VARCHAR(1000),
            index_source_hash VARCHAR(64)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_files_id ON files (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_files_workspace_id ON files (workspace_id)")

    # ── File Tags (many-to-many) ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS file_tags (
            file_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (file_id, tag_id)
        )
    """)

    # ── Tags ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            name VARCHAR(64) NOT NULL,
            workspace_id INTEGER NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_tags_id ON tags (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tags_user_id ON tags (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tags_workspace_id ON tags (workspace_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_tags_user_name ON tags (user_id, name)")

    # ── File Tag Anchors ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS file_tag_anchors (
            id SERIAL PRIMARY KEY,
            file_id INTEGER NOT NULL,
            tag_name VARCHAR(64) NOT NULL,
            occurrence_index INTEGER NOT NULL,
            anchor_id VARCHAR(128) NOT NULL,
            start_offset INTEGER NOT NULL,
            end_offset INTEGER NOT NULL
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_file_tag_anchors_file_id ON file_tag_anchors (file_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_file_tag_anchors_anchor_id ON file_tag_anchors (anchor_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_file_tag_anchors_id ON file_tag_anchors (id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_file_tag_anchor_occ ON file_tag_anchors (file_id, tag_name, occurrence_index)")

    # ── Share Links ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS share_links (
            id SERIAL PRIMARY KEY,
            file_id INTEGER NOT NULL,
            token VARCHAR(64) NOT NULL,
            password_hash VARCHAR(255),
            expires_at TIMESTAMP,
            max_downloads INTEGER,
            download_count INTEGER,
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_share_links_id ON share_links (id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS share_links_token_key ON share_links (token)")

    # ── Operation Logs ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS operation_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            action VARCHAR(50) NOT NULL,
            target_type VARCHAR(50),
            target_id INTEGER,
            detail TEXT,
            created_at TIMESTAMP DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_operation_logs_id ON operation_logs (id)")

    # ── API Keys ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id SERIAL PRIMARY KEY,
            key_hash VARCHAR(128) NOT NULL,
            name VARCHAR(100) NOT NULL,
            prefix VARCHAR(8) NOT NULL,
            user_id INTEGER NOT NULL,
            is_active BOOLEAN,
            created_at TIMESTAMP DEFAULT now(),
            last_used_at TIMESTAMP,
            key_secret_encrypted TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_api_keys_id ON api_keys (id)")

    # ── System Settings ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            id SERIAL PRIMARY KEY,
            setting_key VARCHAR(64) NOT NULL,
            value TEXT NOT NULL
        )
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_system_settings_setting_key ON system_settings (setting_key)")

    # ── Knowledge Base Chunks ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS kb_chunks (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            file_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            source VARCHAR(32) NOT NULL,
            text TEXT NOT NULL,
            char_start INTEGER NOT NULL,
            char_end INTEGER NOT NULL,
            embedding vector(1024) NOT NULL,
            embedding_model VARCHAR(64) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            heading_path VARCHAR(512),
            block_type VARCHAR(16),
            text_search TSVECTOR,
            workspace_id INTEGER NOT NULL,
            boost_keywords TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_kb_chunks_file_id ON kb_chunks (file_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_kb_chunks_file_chunk ON kb_chunks (file_id, chunk_index)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_kb_chunks_user_id ON kb_chunks (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_kb_chunks_text_search ON kb_chunks USING GIN (text_search)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_kb_chunks_embedding_hnsw ON kb_chunks USING hnsw (embedding vector_cosine_ops)")

    # ── Knowledge Base Extract Jobs ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS kb_extract_jobs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            file_id INTEGER NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'queued',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_kb_extract_jobs_file_id ON kb_extract_jobs (file_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_kb_extract_jobs_file_status ON kb_extract_jobs (file_id, status)")

    # ── Knowledge Base Index Jobs ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS kb_index_jobs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            file_id INTEGER NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'queued',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_kb_index_jobs_file_id ON kb_index_jobs (file_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_kb_index_jobs_status ON kb_index_jobs (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_kb_index_jobs_user_id ON kb_index_jobs (user_id)")

    # ── Resource Grants ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS resource_grants (
            id SERIAL PRIMARY KEY,
            workspace_id INTEGER NOT NULL,
            resource_type VARCHAR(16) NOT NULL,
            resource_id INTEGER NOT NULL,
            grantee_user_id INTEGER NOT NULL,
            permission VARCHAR(16) NOT NULL DEFAULT 'view',
            created_by_user_id INTEGER,
            created_at TIMESTAMP DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_resource_grants_workspace_id ON resource_grants (workspace_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_resource_grants_target_grantee ON resource_grants (workspace_id, resource_type, resource_id, grantee_user_id)")

    # ── File MD Versions ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS file_md_versions (
            id SERIAL PRIMARY KEY,
            file_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_by_user_id INTEGER,
            created_at TIMESTAMP DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_file_md_versions_file_id ON file_md_versions (file_id)")

    # ── KB Search Audit Logs ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS kb_search_audit_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            workspace_id INTEGER NOT NULL,
            query TEXT NOT NULL,
            hit_file_ids TEXT,
            top_k INTEGER NOT NULL DEFAULT 8,
            created_at TIMESTAMP DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_kb_search_audit_logs_created_at ON kb_search_audit_logs (created_at)")

    # ── Skill Files ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS skill_files (
            file_id VARCHAR(64) NOT NULL PRIMARY KEY,
            kind VARCHAR(16) NOT NULL,
            label VARCHAR(128) NOT NULL,
            relative_path VARCHAR(256) NOT NULL,
            content TEXT NOT NULL,
            content_sha256 VARCHAR(64) NOT NULL,
            etag VARCHAR(18) NOT NULL,
            revision INTEGER NOT NULL,
            updated_at TIMESTAMP DEFAULT now(),
            updated_by_user_id INTEGER
        )
    """)

    # ── Skill File Revisions ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS skill_file_revisions (
            id SERIAL PRIMARY KEY,
            file_id VARCHAR(64) NOT NULL,
            revision INTEGER NOT NULL,
            content TEXT NOT NULL,
            content_sha256 VARCHAR(64) NOT NULL,
            change_kind VARCHAR(16) NOT NULL,
            created_by_user_id INTEGER,
            created_at TIMESTAMP DEFAULT now(),
            comment VARCHAR(512)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_skill_file_revisions_file_id ON skill_file_revisions (file_id)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_skill_file_revisions_file_revision ON skill_file_revisions (file_id, revision)")


def downgrade() -> None:
    """不可降级：squash 合并不可逆。"""
    pass
