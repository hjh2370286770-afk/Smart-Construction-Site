"""
摄像头路由
"""

from fastapi import APIRouter, HTTPException
from typing import List, Optional
import base64
import io
import cv2
import numpy as np

from ..models import (
    CameraResponse, CameraStatusResponse, CameraStats,
    StartStopResponse, SnapshotResponse
)
from ..dependencies import get_config_manager, get_stream_manager

router = APIRouter(prefix="/cameras", tags=["cameras"])


@router.get("", response_model=List[CameraResponse])
async def get_all_cameras():
    """
    获取所有摄像头信息
    """
    config_manager = get_config_manager()
    stream_manager = get_stream_manager()
    
    if not config_manager:
        raise HTTPException(status_code=503, detail="配置管理器未初始化")
    
    cameras = []
    for site in config_manager.sites:
        for cam in site.cameras:
            # 获取状态（如果流管理器已初始化）
            status = None
            if stream_manager and cam.id in stream_manager.processors:
                processor = stream_manager.processors[cam.id]
                status = processor.status.value
            
            cameras.append(CameraResponse(
                id=cam.id,
                name=cam.name,
                site_id=site.id,
                site_name=site.name,
                url=cam.url,
                type=cam.type,
                enabled=cam.enabled,
                models=cam.models,
                status=status
            ))
    
    return cameras


@router.get("/{camera_id}/status", response_model=CameraStatusResponse)
async def get_camera_status(camera_id: str):
    """
    获取指定摄像头的状态
    """
    stream_manager = get_stream_manager()
    config_manager = get_config_manager()
    
    if not stream_manager or not config_manager:
        raise HTTPException(status_code=503, detail="服务未初始化")
    
    # 查找摄像头配置
    camera_config = None
    for site in config_manager.sites:
        for cam in site.cameras:
            if cam.id == camera_id:
                camera_config = cam
                break
        if camera_config:
            break
    
    if not camera_config:
        raise HTTPException(status_code=404, detail=f"摄像头 {camera_id} 不存在")
    
    # 获取处理器状态
    if camera_id in stream_manager.processors:
        processor = stream_manager.processors[camera_id]
        status_data = processor.get_status()
        return CameraStatusResponse(
            camera_id=camera_id,
            name=camera_config.name,
            status=status_data["status"],
            enabled=status_data["enabled"],
            stats=status_data["stats"]
        )
    else:
        # 摄像头存在但未启动
        return CameraStatusResponse(
            camera_id=camera_id,
            name=camera_config.name,
            status="stopped",
            enabled=camera_config.enabled,
            stats={
                "frame_count": 0,
                "fps": 0.0,
                "detection_count": 0,
                "violation_count": 0,
                "reconnect_count": 0,
                "error_count": 0
            }
        )


@router.post("/{camera_id}/start", response_model=StartStopResponse)
async def start_camera(camera_id: str):
    """
    启动指定摄像头
    """
    stream_manager = get_stream_manager()
    config_manager = get_config_manager()
    
    if not stream_manager or not config_manager:
        raise HTTPException(status_code=503, detail="服务未初始化")
    
    # 检查摄像头是否存在
    camera_exists = False
    for site in config_manager.sites:
        for cam in site.cameras:
            if cam.id == camera_id:
                camera_exists = True
                break
        if camera_exists:
            break
    
    if not camera_exists:
        raise HTTPException(status_code=404, detail=f"摄像头 {camera_id} 不存在")
    
    # 检查处理器是否存在，不存在则创建
    if camera_id not in stream_manager.processors:
        from core import MultiStreamManager
        # 重新初始化该摄像头
        for site in config_manager.sites:
            for cam in site.cameras:
                if cam.id == camera_id:
                    stream_manager._create_processor(site, cam)
                    break
    
    if camera_id in stream_manager.processors:
        try:
            await stream_manager.start_camera(camera_id)
            return StartStopResponse(
                success=True,
                message=f"摄像头 {camera_id} 已启动",
                camera_id=camera_id
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"启动失败: {str(e)}")
    else:
        raise HTTPException(status_code=500, detail="无法创建处理器")


@router.post("/{camera_id}/stop", response_model=StartStopResponse)
async def stop_camera(camera_id: str):
    """
    停止指定摄像头
    """
    stream_manager = get_stream_manager()
    
    if not stream_manager:
        raise HTTPException(status_code=503, detail="服务未初始化")
    
    if camera_id not in stream_manager.processors:
        raise HTTPException(status_code=404, detail=f"摄像头 {camera_id} 未运行")
    
    try:
        await stream_manager.stop_camera(camera_id)
        return StartStopResponse(
            success=True,
            message=f"摄像头 {camera_id} 已停止",
            camera_id=camera_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"停止失败: {str(e)}")


@router.get("/{camera_id}/snapshot", response_model=SnapshotResponse)
async def get_camera_snapshot(camera_id: str):
    """
    获取摄像头当前帧截图
    
    返回 Base64 编码的 JPEG 图片
    """
    stream_manager = get_stream_manager()
    
    if not stream_manager:
        raise HTTPException(status_code=503, detail="服务未初始化")
    
    if camera_id not in stream_manager.processors:
        raise HTTPException(status_code=404, detail=f"摄像头 {camera_id} 未运行")
    
    processor = stream_manager.processors[camera_id]
    
    # 尝试获取当前帧（通过视频捕获）
    try:
        import cv2
        from datetime import datetime
        
        # 打开视频流获取一帧
        cap = cv2.VideoCapture(processor.config.url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        if not cap.isOpened():
            raise HTTPException(status_code=500, detail="无法连接到视频流")
        
        ret, frame = cap.read()
        cap.release()
        
        if not ret or frame is None:
            raise HTTPException(status_code=500, detail="无法获取视频帧")
        
        # 调整分辨率
        target_resolution = processor.config.resolution
        if frame.shape[1] != target_resolution[0] or frame.shape[0] != target_resolution[1]:
            frame = cv2.resize(frame, target_resolution)
        
        # 绘制检测结果（如果有）
        if processor.last_detection:
            frame = processor.detector.draw_results(frame, processor.last_detection)
        
        # 编码为 JPEG
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        image_base64 = base64.b64encode(buffer).decode('utf-8')
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        return SnapshotResponse(
            camera_id=camera_id,
            timestamp=timestamp,
            image_base64=image_base64,
            message="截图成功"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"截图失败: {str(e)}")
