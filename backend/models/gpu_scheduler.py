# Copyright (c) 2026 徐泽宇
"""Durable GPU scheduler lease and route outbox records (T-3)."""

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from database import Base


class GpuSchedulerLease(Base):
    __tablename__ = "gpu_scheduler_leases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gpu_id = Column(String(64), nullable=False, unique=True, index=True)
    owner_id = Column(String(128), nullable=False)
    fencing_token = Column(String(128), nullable=False)
    state = Column(String(32), nullable=False, server_default="active")
    lease_expires_at = Column(DateTime, nullable=False)
    heartbeat_at = Column(DateTime, nullable=False)
    active_job_id = Column(String(128), nullable=True)
    release_ack_at = Column(DateTime, nullable=True)
    watchdog_empty_confirmations = Column(Integer, nullable=False, server_default="0")
    last_watchdog_at = Column(DateTime, nullable=True)
    handover_epoch = Column(Integer, nullable=False, server_default="0")
    model_group = Column(String(32), nullable=True)
    batch_started_at = Column(DateTime, nullable=True)
    batch_size = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class GpuSchedulerOutbox(Base):
    __tablename__ = "gpu_scheduler_outbox"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_gpu_scheduler_outbox_idempotency_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_kind = Column(String(32), nullable=False)
    job_id = Column(String(128), nullable=False, index=True)
    file_id = Column(Integer, nullable=True, index=True)
    idempotency_key = Column(String(160), nullable=False)
    payload = Column(JSON, nullable=False)
    state = Column(String(32), nullable=False, server_default="queued", index=True)
    attempt = Column(Integer, nullable=False, server_default="0")
    handover_epoch = Column(Integer, nullable=False, server_default="0")
    published_at = Column(DateTime, nullable=True)
    acked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class GpuSchedulerState(Base):
    """GPU 调度观测状态（164 §9 可观测性）：当前/最近模型组、最近一次切换耗时与失败原因。

    单行表（id=1），由 gpu-scheduler worker 在模型组切换/失败时写入，
    管理端 admin/mq-status 读取用于展示；任何一次写入失败都不影响调度主流程。
    """

    __tablename__ = "gpu_scheduler_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_group = Column(String(16), nullable=False, server_default="none")
    model_status = Column(String(32), nullable=False, server_default="unloaded")
    switch_started_at = Column(DateTime, nullable=True)
    switch_finished_at = Column(DateTime, nullable=True)
    last_switch_duration_ms = Column(Integer, nullable=True)
    last_failure_kind = Column(String(32), nullable=True)
    last_failure_reason = Column(Text, nullable=True)
    last_failure_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
