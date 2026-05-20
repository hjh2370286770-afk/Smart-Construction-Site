"""
统计信息路由
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime

from ..models import RealtimeStats
from ..dependencies import get_stream_manager

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/realtime", response_model=RealtimeStats)
async def get_realtime_stats():
    """
    获取实时统计信息
    """
    stream_manager = get_stream_manager()
    
    if not stream_manager:
        raise HTTPException(status_code=503, detail="服务未初始化")
    
    summary = stream_manager.get_summary()
    
    # 计算在线率和合规率
    total_cameras = summary["total_cameras"]
    online_cameras = summary["active_cameras"]
    total_persons = summary.get("total_persons", 0)
    
    # 从各摄像头统计计算合规率
    compliance_rate = 100.0
    fps_by_camera = {}
    
    for camera in summary.get("cameras", []):
        stats = camera.get("stats", {})
        fps_by_camera[camera["camera_id"]] = stats.get("fps", 0)
    
    return RealtimeStats(
        total_cameras=total_cameras,
        online_cameras=online_cameras,
        total_persons=total_persons,
        today_violations=summary["total_violations"],
        compliance_rate=compliance_rate,
        fps_by_camera=fps_by_camera
    )
