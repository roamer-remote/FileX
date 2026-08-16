# Copyright (c) 2026 徐泽宇
"""059 P2 管理端 RBAC API schemas。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DepartmentResponse(BaseModel):
    id: int
    name: str
    parent_id: int | None
    sort_order: int
    created_at: str
    is_builtin: bool = False


class DepartmentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    parent_id: int
    sort_order: int = 0


class DepartmentUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    parent_id: int | None = None
    sort_order: int | None = None


class GroupResponse(BaseModel):
    id: int
    name: str
    description: str | None
    created_at: str


class GroupCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)


class GroupUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)


class EnterpriseRoleResponse(BaseModel):
    id: int
    slug: str
    name: str
    description: str | None
    is_builtin: bool
    is_active: bool
    created_at: str


class EnterpriseRoleCreateRequest(BaseModel):
    slug: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)


class EnterpriseRoleUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    is_active: bool | None = None


class EnterpriseRoleDeleteResponse(BaseModel):
    deleted_user_role_assignments: int
    deleted_acl_rows: int
    message: str


class UserOrgGroupItem(BaseModel):
    id: int
    name: str


class AdminUserOrgResponse(BaseModel):
    user_id: int
    primary_department_id: int
    primary_department_name: str
    groups: list[UserOrgGroupItem]


class AdminUserOrgUpdateRequest(BaseModel):
    primary_department_id: int
    group_ids: list[int] = Field(default_factory=list)


class WorkspaceMemberRolesUpdateRequest(BaseModel):
    role_ids: list[int] = Field(default_factory=list)


class WorkspaceMemberRolesResponse(BaseModel):
    user_id: int
    role_ids: list[int]
    role_slugs: list[str]
    rollback_warning: bool = False


class FolderAclEntryInput(BaseModel):
    folder_id: int | None = None
    subject_type: str = Field(..., pattern=r"^(user|role|group|department)$")
    subject_id: int
    permission: str = Field(..., pattern=r"^(list|read|write|manage)$")


class FolderAclSubjectEntryInput(BaseModel):
    subject_type: str = Field(..., pattern=r"^(user|role|group|department)$")
    subject_id: int
    permission: str = Field(..., pattern=r"^(list|read|write|manage)$")


class FolderAclEntryResponse(BaseModel):
    id: int
    folder_id: int | None
    subject_type: str
    subject_id: int
    permission: str
    created_at: str
    updated_at: str


class FolderAclBulkPutRequest(BaseModel):
    entries: list[FolderAclEntryInput] = Field(default_factory=list)


class FolderAclFolderPutRequest(BaseModel):
    entries: list[FolderAclSubjectEntryInput] = Field(default_factory=list)


class FolderAclPutSummaryResponse(BaseModel):
    upserted: int
    updated: int
    rollback_warning: bool = False
