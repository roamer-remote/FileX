# Copyright (c) 2026 徐泽宇
"""workspace 相关 API 数据模式模块。

Authors:
    徐泽宇
"""

from pydantic import BaseModel, Field

from models.workspace import WORKSPACE_ROLES


class WorkspaceResponse(BaseModel):
    """知识空间响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-23

        Attributes:
            id: ID（int）。
            name: 名称（str）。
            slug: Slug（str）。
            kind: 类型（str）。
            owner_user_id: owner用户ID（int | None）。
            my_role: my角色（str）。
            created_at: 创建时间（str）。
    """
    id: int
    name: str
    slug: str
    kind: str
    owner_user_id: int | None
    my_role: str
    created_at: str


class WorkspaceCreateRequest(BaseModel):
    """知识空间创建请求 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-23

        Attributes:
            name: 名称（str）。
    """
    name: str = Field(..., min_length=1, max_length=100)


class WorkspaceUpdateRequest(BaseModel):
    """知识空间更新请求 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-23

        Attributes:
            name: 名称（str）。
    """
    name: str = Field(..., min_length=1, max_length=100)


class WorkspaceMemberResponse(BaseModel):
    """知识空间成员响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-23

        Attributes:
            user_id: 用户ID（int）。
            username: 用户名（str）。
            role: 角色（str）。
    """
    user_id: int
    username: str
    role: str


class WorkspaceMemberUpsertRequest(BaseModel):
    """知识空间成员upsert请求 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-23

        Attributes:
            user_id: 用户ID（int）。
            role: 角色（str）。
    """
    user_id: int
    role: str = Field(..., pattern="^(viewer|contributor|curator|admin|auditor)$")


class ResourceGrantResponse(BaseModel):
    """资源授权响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-23

        Attributes:
            id: ID（int）。
            resource_type: 资源类型（str）。
            resource_id: 资源ID（int）。
            grantee_user_id: grantee用户ID（int）。
            grantee_username: grantee用户名（str）。
            permission: 权限（str）。
            created_at: 创建时间（str）。
    """
    id: int
    resource_type: str
    resource_id: int
    grantee_user_id: int
    grantee_username: str
    permission: str
    created_at: str


class ResourceGrantCreateRequest(BaseModel):
    """资源授权创建请求 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-23

        Attributes:
            resource_type: 资源类型（str）。
            resource_id: 资源ID（int）。
            grantee_user_id: grantee用户ID（int）。
            permission: 权限（str）。
    """
    resource_type: str = Field(..., pattern="^(file|folder)$")
    resource_id: int
    grantee_user_id: int
    permission: str = Field(default="view", pattern="^(view|edit)$")


class KbSearchAuditItem(BaseModel):
    """资料库检索审计条目 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-23

        Attributes:
            id: ID（int）。
            user_id: 用户ID（int）。
            username: 用户名（str）。
            workspace_id: 知识空间ID（int）。
            query: query（str）。
            hit_file_ids: hit文件ids（str | None）。
            top_k: topk（int）。
            created_at: 创建时间（str）。
    """
    id: int
    user_id: int
    username: str
    workspace_id: int
    query: str
    hit_file_ids: str | None
    top_k: int
    created_at: str


class FileMdVersionResponse(BaseModel):
    """文件Markdown版本响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-23

        Attributes:
            id: ID（int）。
            file_id: 文件ID（int）。
            version: 版本（int）。
            content: 内容（str）。
            created_by_user_id: 创建by用户ID（int | None）。
            created_at: 创建时间（str）。
    """
    id: int
    file_id: int
    version: int
    content: str
    created_by_user_id: int | None
    created_at: str


class FilePublishStatusRequest(BaseModel):
    """文件发布状态请求 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-24

        Attributes:
            publish_status: 发布状态（str）。
    """
    publish_status: str = Field(..., pattern="^(draft|published)$")


class AdminWorkspaceListItem(BaseModel):
    """管理知识空间列表条目 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-24

        Attributes:
            id: ID（int）。
            name: 名称（str）。
            slug: Slug（str）。
            kind: 类型（str）。
            owner_user_id: owner用户ID（int | None）。
            owner_username: owner用户名（str | None）。
            member_count: 成员数量（int）。
            created_at: 创建时间（str）。
    """
    id: int
    name: str
    slug: str
    kind: str
    owner_user_id: int | None
    owner_username: str | None
    member_count: int
    created_at: str


class AdminWorkspaceCreateRequest(BaseModel):
    """管理知识空间创建请求 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Attributes:
            name: 名称（str）。
            owner_user_id: owner用户ID（int）。
    """
    name: str = Field(..., min_length=1, max_length=100)
    owner_user_id: int


class MdVersionRestoreRequest(BaseModel):
    """Markdown版本restore请求 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Attributes:
            version_id: 版本ID（int）。
    """
    version_id: int
