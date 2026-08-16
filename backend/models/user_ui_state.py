# Copyright (c) 2026 徐泽宇
"""user_ui_state ORM — 每用户一行 UI 偏好 JSON 文档。"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB

from database import Base


class UserUiState(Base):
    """用户 Web UI 状态（039）。"""

    __tablename__ = "user_ui_state"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    state_json = Column(JSONB, nullable=False, server_default="{}")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
