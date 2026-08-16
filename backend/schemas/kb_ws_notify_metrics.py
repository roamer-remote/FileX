# Copyright (c) 2026 徐泽宇
"""054: KB WebSocket notify delivery metrics (admin read-only)."""

from pydantic import BaseModel, Field


class KbWsNotifyMetricsResponse(BaseModel):
    ws_connections_active: int = Field(serialization_alias="wsConnectionsActive")
    notify_broadcast_attempted: int = Field(serialization_alias="notifyBroadcastAttempted")
    notify_broadcast_delivered: int = Field(serialization_alias="notifyBroadcastDelivered")
    notify_broadcast_dropped_no_conn: int = Field(
        serialization_alias="notifyBroadcastDroppedNoConn"
    )
    notify_broadcast_send_failed: int = Field(serialization_alias="notifyBroadcastSendFailed")
