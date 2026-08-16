# Copyright (c) 2026 徐泽宇
"""admin_skill 相关 API 数据模式模块。

Authors:
    徐泽宇
"""

from pydantic import BaseModel, Field


class AdminSkillFileItem(BaseModel):
    """管理技能文件条目 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-27

        Attributes:
            file_id: 文件ID（str）。
            label: label（str）。
            path: 路径（str）。
            kind: 类型（str）。
            group: group（str）。
            etag: etag（str）。
            sha256: sha256（str）。
            size_bytes: 大小bytes（int）。
            updated_at: 更新时间（str）。
    """
    file_id: str
    label: str
    path: str
    kind: str
    group: str
    etag: str
    sha256: str
    size_bytes: int
    updated_at: str


class AdminSkillFilesListResponse(BaseModel):
    """管理技能文件列表响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-27

        Attributes:
            writable: writable（bool）。
            data_ready: 数据就绪（bool）。
            cache_enabled: 缓存启用（bool）。
            skill_version: 技能版本（str | None）。
            disk_skill_version: disk技能版本（str | None）。
            bootstrap_min_version: 引导最小版本（str | None）。
            files: 文件（list[AdminSkillFileItem]）。
    """
    writable: bool
    data_ready: bool = True
    cache_enabled: bool = False
    skill_version: str | None = None
    disk_skill_version: str | None = None
    bootstrap_min_version: str | None = None
    files: list[AdminSkillFileItem]


class AdminSkillFileResponse(BaseModel):
    """管理技能文件响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-27

        Attributes:
            file_id: 文件ID（str）。
            content: 内容（str）。
            etag: etag（str）。
            sha256: sha256（str）。
            kind: 类型（str）。
            path: 路径（str）。
            label: label（str）。
            size_bytes: 大小bytes（int）。
            updated_at: 更新时间（str）。
    """
    file_id: str
    content: str
    etag: str
    sha256: str
    kind: str
    path: str
    label: str
    size_bytes: int
    updated_at: str


class AdminSkillSyncFromDiskResponse(BaseModel):
    """管理技能syncfromdisk响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-28

        Attributes:
            ok: ok（bool）。
            data_ready: 数据就绪（bool）。
            skill_dir: 技能dir（str | None）。
            synced: synced（list[str]）。
            added: added（list[str]）。
            updated: 更新（list[str]）。
            removed: removed（list[str]）。
            reason: 原因（str | None）。
    """
    ok: bool
    data_ready: bool
    skill_dir: str | None = None
    synced: list[str] = Field(default_factory=list)
    added: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    reason: str | None = None
