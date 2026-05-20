"""
Pydantic 数据模型
"""

from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime


# ========== 工地相关模型 ==========

class SiteResponse(BaseModel):
    """工地响应模型"""
    id: str
    name: str
    location: str
    description: str
    camera_count: int


# ========== 摄像头相关模型 ==========

class CameraResponse(BaseModel):
    """摄像头响应模型"""
    id: str
    name: str
    site_id: str
    site_name: str
    url: str
    type: str
    enabled: bool
    models: List[str]
    status: Optional[str] = None


class CameraStats(BaseModel):
    """摄像头统计"""
    frame_count: int
    fps: float
    detection_count: int
    violation_count: int
    reconnect_count: int
    error_count: int


class CameraStatusResponse(BaseModel):
    """摄像头状态响应"""
    camera_id: str
    name: str
    status: str
    enabled: bool
    stats: CameraStats


class StartStopResponse(BaseModel):
    """启动/停止响应"""
    success: bool
    message: str
    camera_id: str


class SnapshotResponse(BaseModel):
    """截图响应"""
    camera_id: str
    timestamp: str
    image_base64: str
    message: str


# ========== 违规记录相关模型 ==========

class ViolationResponse(BaseModel):
    """违规记录响应"""
    id: str
    timestamp: datetime
    camera_id: str
    camera_name: Optional[str] = None
    site_id: Optional[str] = None
    site_name: Optional[str] = None
    person_id: Optional[int] = None
    violation_types: List[str] = []
    severity: str = "medium"
    image_url: Optional[str] = None
    description: Optional[str] = None


class ViolationListResponse(BaseModel):
    """违规列表响应"""
    total: int
    items: List[ViolationResponse]


# ========== 统计相关模型 ==========

class RealtimeStats(BaseModel):
    """实时统计"""
    total_cameras: int
    online_cameras: int
    total_persons: int
    today_violations: int
    compliance_rate: float
    fps_by_camera: Dict[str, float]


class DailyStats(BaseModel):
    """每日统计"""
    date: str
    total_frames: int
    total_detections: int
    total_violations: int
    violation_by_type: Dict[str, int]


# ========== WebSocket 消息模型 ==========

class WebSocketMessage(BaseModel):
    """WebSocket 消息"""
    type: str  # violation, status, connected, ping, pong
    data: Dict[str, Any]


class ViolationEvent(BaseModel):
    """违规事件"""
    timestamp: str
    camera_id: str
    person_id: int
    violation_types: List[str]
    severity: str
    filepath: Optional[str] = None


class StatusEvent(BaseModel):
    """状态事件"""
    camera_id: str
    status: str
    stats: CameraStats
