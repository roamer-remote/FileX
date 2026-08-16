# Copyright (c) 2026 徐泽宇
"""file 相关 API 数据模式模块。

Authors:
    徐泽宇
"""

from pydantic import BaseModel, Field, model_validator
from typing import Optional


class FileTagAnchorItem(BaseModel):
    """文件标签锚点条目 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-18

        Attributes:
            anchor_id: 锚点ID（str）。
            tag: 标签（str）。
            occurrence_index: occurrence索引（int）。
            start_offset: startoffset（int）。
            end_offset: endoffset（int）。
    """
    anchor_id: str
    tag: str
    occurrence_index: int
    start_offset: int
    end_offset: int


class FileResponse(BaseModel):
    """文件响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-24

        Attributes:
            id: ID（int）。
            filename: 文件名（str）。
            original_name: 原始名称（str）。
            file_size: 文件大小（int）。
            mime_type: MIME类型（str）。
            folder_id: 文件夹ID（Optional[int]）。
            workspace_id: 知识空间ID（Optional[int]）。
            publish_status: 发布状态（str）。
            user_id: 用户ID（int）。
            username: 用户名（Optional[str]）。
            created_at: 创建时间（str）。
            updated_at: 更新时间（Optional[str]）。
    """
    id: int
    filename: str
    original_name: str
    file_size: int
    mime_type: str
    folder_id: Optional[int] = None
    workspace_id: Optional[int] = None
    publish_status: str = "published"
    user_id: int
    username: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None
    md5_hash: Optional[str] = None
    has_md: bool = False
    md_has_content: bool = Field(
        default=False,
        description="笔记文件存在且 strip 后非空",
    )
    deduplicated: bool = Field(
        default=False,
        description="本次上传因与同用户下已有文件 MD5 相同而未新建记录",
    )
    tags: list[str] = Field(default_factory=list)
    tag_anchors: list[FileTagAnchorItem] = Field(default_factory=list)
    has_thumbnail: bool = Field(
        default=False,
        description="是否存在首页列表用缩略图（磁盘 .thumbnails 下）",
    )
    index_status: str = Field(default="skipped", description="资料库向量索引状态")
    indexed_at: Optional[str] = None
    chunk_count: int = 0
    index_error: Optional[str] = None
    kb_post_status: str = Field(default="pending", description="资料库后处理状态 (entity/SAG/RAPTOR)")
    kb_post_error: Optional[str] = None
    kb_post_at: Optional[str] = None
    extract_status: str = Field(default="not_needed", description="正文提取状态")
    extracted_at: Optional[str] = None
    extract_error: Optional[str] = None
    extract_engine: Optional[str] = None
    preview_mime_type: Optional[str] = Field(
        default=None,
        description="浏览器预览响应 MIME override；有值时前端按该 MIME 选择预览器",
    )
    page_kind: str = Field(default="source")
    wiki_slug: Optional[str] = None
    okf_concept_path: Optional[str] = None
    okf_type: Optional[str] = None
    okf_metadata: dict | None = None
    wiki_links_stale: bool | None = None
    can_write: bool = Field(
        default=True,
        description="当前用户是否可修改元数据/移动/标签/笔记（effective write）",
    )
    can_manage: bool = Field(
        default=True,
        description="当前用户是否可删除（父目录 effective manage）",
    )

    class Config:
        """Pydantic 模型配置。

            Authors:
                徐泽宇

            Copyright:
                © 2026 徐泽宇

            Since:
                2026-05-11

            Attributes:
                from_attributes: fromattributes常量。
        """
        from_attributes = True


class ExternalUploadWithMdResponse(BaseModel):
    """外部单次请求：原文上传 + 可选 Markdown 笔记。"""

    file: FileResponse
    markdown_saved: bool = False


class FileTagsUpdateRequest(BaseModel):
    """文件标签更新请求 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-01

        Attributes:
            tags: 标签（list[str]）。
    """
    tags: list[str] = Field(default_factory=list)


class FileUpdateRequest(BaseModel):
    """文件更新请求 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-01

        Attributes:
            filename: 文件名（Optional[str]）。
            folder_id: 文件夹ID（Optional[int]）。
    """
    filename: Optional[str] = None
    folder_id: Optional[int] = None


class FileListResponse(BaseModel):
    """文件列表响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-01

        Attributes:
            items: 条目列表（list[FileResponse]）。
            total: 总计（int）。
            page: 页面（int）。
            page_size: 页面大小（int）。
            enumerate_truncated: enumeratetruncated（bool | None）。
    """
    items: list[FileResponse]
    total: int
    page: int
    page_size: int
    enumerate_truncated: bool | None = None


class FolderCreate(BaseModel):
    """文件夹创建 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-01

        Attributes:
            name: 名称（str）。
            parent_id: 父级ID（Optional[int]）。
    """
    name: str = Field(..., min_length=1, max_length=100)
    parent_id: Optional[int] = None


class FolderUpdate(BaseModel):
    """文件夹更新 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-19

        Attributes:
            name: 名称（Optional[str]）。
            parent_id: 父级ID（Optional[int]）；路由层须配合 raw body 区分未传与 null。
            sort_order: 同级排序（Optional[int]）。
    """
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    parent_id: Optional[int] = None
    sort_order: Optional[int] = Field(None, ge=0)

    @model_validator(mode="before")
    @classmethod
    def at_least_one_field(cls, data):
        if isinstance(data, dict) and not any(k in data for k in ("name", "parent_id", "sort_order")):
            raise ValueError("at_least_one_field")
        return data


class FileTypeStatItem(BaseModel):
    """文件类型stat条目 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-19

        Attributes:
            key: 密钥（str）。
            count: 数量（int）。
            percent: percent（float）。
    """
    key: str
    count: int
    percent: float


class FileStatsResponse(BaseModel):
    """文件stats响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-19

        Attributes:
            total_files: 总计文件（int）。
            total_characters: 总计characters（int）。
            indexed_count: 已索引数量（int）。
            tag_count: 标签数量（int）。
            document_type_count: document类型数量（int）。
            file_types: 文件types（list[FileTypeStatItem]）。
    """
    total_files: int
    total_characters: int
    indexed_count: int
    tag_count: int
    document_type_count: int
    file_types: list[FileTypeStatItem] = Field(default_factory=list)


class FolderResponse(BaseModel):
    """文件夹响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-01

        Attributes:
            id: ID（int）。
            name: 名称（str）。
            parent_id: 父级ID（Optional[int]）。
            user_id: 用户ID（int）。
            created_at: 创建时间（str）。
    """
    id: int
    name: str
    parent_id: Optional[int] = None
    sort_order: int = 0
    user_id: int
    created_at: str

    class Config:
        """Pydantic 模型配置。

            Authors:
                徐泽宇

            Copyright:
                © 2026 徐泽宇

            Attributes:
                from_attributes: fromattributes常量。
        """
        from_attributes = True


class FolderDirectFileCountsResponse(BaseModel):
    """各目录直接文件数（不含子目录）；未分类单独计数。"""

    uncategorized_file_count: int = 0
    folder_file_counts: dict[int, int] = Field(default_factory=dict)
    zero_acl_member: bool = False
    upload_allowed: bool = Field(
        default=True,
        description="当前用户对 upload_folder_id（缺省为未分类/根）是否具备上传 write 权限",
    )
