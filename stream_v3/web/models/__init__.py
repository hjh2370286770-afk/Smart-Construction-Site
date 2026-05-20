"""
数据模型包
"""

from .schemas import (
    SiteResponse,
    CameraResponse,
    CameraStats,
    CameraStatusResponse,
    StartStopResponse,
    SnapshotResponse,
    ViolationResponse,
    ViolationListResponse,
    RealtimeStats,
    DailyStats,
    WebSocketMessage,
    ViolationEvent,
    StatusEvent,
)

__all__ = [
    "SiteResponse",
    "CameraResponse",
    "CameraStats",
    "CameraStatusResponse",
    "StartStopResponse",
    "SnapshotResponse",
    "ViolationResponse",
    "ViolationListResponse",
    "RealtimeStats",
    "DailyStats",
    "WebSocketMessage",
    "ViolationEvent",
    "StatusEvent",
]
