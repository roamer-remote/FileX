# Copyright (c) 2026 徐泽宇
"""tag_graph 相关 API 数据模式模块。

Authors:
    徐泽宇
"""

from pydantic import BaseModel, Field


class TagGraphNode(BaseModel):
    """标签图node Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-09

        Attributes:
            id: ID（str）。
            name: 名称（str）。
            value: value（int）。
    """
    id: str
    name: str
    value: int = Field(description="拥有该标签的文件数（全库）")


class TagGraphLink(BaseModel):
    """标签图链接 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-23

        Attributes:
            source: 来源（str）。
            target: 目标（str）。
            value: value（int）。
    """
    source: str
    target: str
    value: int = Field(description="在展示文件集合内，两标签同文件共现的次数")


class TagGraphFileGroup(BaseModel):
    """标签图文件group Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-09

        Attributes:
            file_id: 文件ID（int）。
            label: label（str）。
            tags: 标签（list[str]）。
    """
    file_id: int
    label: str
    tags: list[str]


class TagGraphResponse(BaseModel):
    """标签图响应 Pydantic 数据模式。

        Authors:
            徐泽宇

        Copyright:
            © 2026 徐泽宇

        Since:
            2026-05-09

        Attributes:
            nodes: 节点（list[TagGraphNode]）。
            links: links（list[TagGraphLink]）。
            file_groups: 文件groups（list[TagGraphFileGroup]）。
            truncated: truncated（bool）。
            total_files_with_tags: 总计文件含标签（int）。
    """
    nodes: list[TagGraphNode]
    links: list[TagGraphLink]
    file_groups: list[TagGraphFileGroup] = []
    truncated: bool = False
    total_files_with_tags: int = 0


class TagHeatmapResponse(BaseModel):
    """标签共现矩阵：tags 行列顺序一致；matrix[i][j] 为标签 i 与 j 在同一文件中共同出现的文件数；对角线为带有该标签的文件数。"""

    tags: list[str]
    matrix: list[list[int]]
    truncated: bool = False
    total_tags: int = 0
