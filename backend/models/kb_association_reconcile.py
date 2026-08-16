"""Durable cursors for restart-safe association backfill."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, BigInteger, String
from sqlalchemy.sql import func

from database import Base


class KbAssociationReconcileCheckpoint(Base):
    __tablename__ = "kb_association_reconcile_checkpoints"

    workspace_id = Column(Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    cursor = Column(BigInteger, nullable=False, server_default="0")
    scan_round = Column(Integer, nullable=False, server_default="1")
    status = Column(String(16), nullable=False, server_default="running")
    last_error = Column(String(2000), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
