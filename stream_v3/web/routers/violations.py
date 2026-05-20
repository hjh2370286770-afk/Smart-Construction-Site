"""
违规记录路由
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from typing import List, Optional
from datetime import datetime
from pathlib import Path
import json
import uuid
import os

from ..models import ViolationResponse
from ..dependencies import get_stream_manager, get_config_manager

router = APIRouter(prefix="/violations", tags=["violations"])


def _get_camera_name(camera_id: str, config_manager) -> Optional[str]:
    """获取摄像头名称"""
    if not config_manager:
        return None
    for site in config_manager.sites:
        for cam in site.cameras:
            if cam.id == camera_id:
                return cam.name
    return None


def _get_site_info(camera_id: str, config_manager) -> tuple:
    """获取工地信息"""
    if not config_manager:
        return None, None
    for site in config_manager.sites:
        for cam in site.cameras:
            if cam.id == camera_id:
                return site.id, site.name
    return None, None


def _build_image_url(filepath: str, base_url: str = "/api") -> Optional[str]:
    """构建图片URL"""
    if not filepath:
        return None
    # 将绝对路径转换为相对路径并返回URL
    try:
        # 检查文件是否存在
        if Path(filepath).exists():
            return f"{base_url}/violations/image?path={filepath}"
    except:
        pass
    return None


@router.get("", response_model=List[ViolationResponse])
async def get_violations(
    camera_id: Optional[str] = Query(None, description="筛选特定摄像头"),
    site_id: Optional[str] = Query(None, description="筛选特定工地"),
    start_time: Optional[str] = Query(None, description="开始时间 (YYYYMMDD_HHMMSS)"),
    end_time: Optional[str] = Query(None, description="结束时间 (YYYYMMDD_HHMMSS)"),
    violation_type: Optional[str] = Query(None, description="违规类型"),
    limit: int = Query(100, ge=1, le=1000, description="返回记录数量限制"),
    offset: int = Query(0, ge=0, description="偏移量")
):
    """
    查询违规记录
    
    支持按摄像头、工地、时间范围筛选
    """
    stream_manager = get_stream_manager()
    config_manager = get_config_manager()
    
    all_violations = []
    
    # 1. 从处理器获取实时违规记录
    if stream_manager:
        processors_to_check = []
        
        if camera_id and camera_id in stream_manager.processors:
            processors_to_check = [stream_manager.processors[camera_id]]
        elif site_id:
            # 筛选特定工地的摄像头
            if config_manager:
                for site in config_manager.sites:
                    if site.id == site_id:
                        for cam in site.cameras:
                            if cam.id in stream_manager.processors:
                                processors_to_check.append(stream_manager.processors[cam.id])
        elif camera_id is None:
            processors_to_check = list(stream_manager.processors.values())
        
        for processor in processors_to_check:
            for log_entry in processor.violation_log:
                # 时间筛选
                if start_time and log_entry.get("timestamp", "") < start_time:
                    continue
                if end_time and log_entry.get("timestamp", "") > end_time:
                    continue
                
                # 违规类型筛选
                if violation_type:
                    types = log_entry.get("violation_types", [])
                    if violation_type not in types:
                        continue
                
                cam_name = _get_camera_name(log_entry.get("camera_id", ""), config_manager)
                s_id, s_name = _get_site_info(log_entry.get("camera_id", ""), config_manager)
                image_url = _build_image_url(log_entry.get("filepath", ""))
                
                all_violations.append(ViolationResponse(
                    id=str(uuid.uuid4()),
                    timestamp=log_entry.get("timestamp", ""),
                    camera_id=log_entry.get("camera_id", ""),
                    camera_name=cam_name,
                    site_id=s_id,
                    site_name=s_name,
                    person_id=log_entry.get("person_id"),
                    violation_types=log_entry.get("violation_types", []),
                    severity=log_entry.get("severity", "medium"),
                    image_url=image_url,
                    description=log_entry.get("description", "")
                ))
    
    # 2. 从日志文件加载历史记录
    if config_manager:
        output_base = Path("./output")
        
        sites_to_check = []
        if site_id:
            sites_to_check = [s for s in config_manager.sites if s.id == site_id]
        else:
            sites_to_check = config_manager.sites
            
        for site in sites_to_check:
            for cam in site.cameras:
                if camera_id and cam.id != camera_id:
                    continue
                
                log_file = output_base / site.id / cam.id / "violation_log.json"
                if log_file.exists():
                    try:
                        with open(log_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            for v in data.get("violations", []):
                                # 时间筛选
                                if start_time and v.get("timestamp", "") < start_time:
                                    continue
                                if end_time and v.get("timestamp", "") > end_time:
                                    continue
                                
                                # 违规类型筛选
                                if violation_type:
                                    types = v.get("violation_types", [])
                                    if violation_type not in types:
                                        continue
                                
                                # 检查是否已存在（避免重复）
                                exists = any(
                                    vv.timestamp == v.get("timestamp") and 
                                    vv.camera_id == v.get("camera_id")
                                    for vv in all_violations
                                )
                                if not exists:
                                    image_url = _build_image_url(v.get("filepath", ""))
                                    
                                    all_violations.append(ViolationResponse(
                                        id=str(uuid.uuid4()),
                                        timestamp=v.get("timestamp", ""),
                                        camera_id=v.get("camera_id", ""),
                                        camera_name=cam.name,
                                        site_id=site.id,
                                        site_name=site.name,
                                        person_id=v.get("person_id"),
                                        violation_types=v.get("violation_types", []),
                                        severity=v.get("severity", "medium"),
                                        image_url=image_url,
                                        description=v.get("description", "")
                                    ))
                    except Exception as e:
                        logger.warning(f"读取违规日志失败 {log_file}: {e}")
    
    # 按时间倒序排列
    all_violations.sort(key=lambda x: x.timestamp, reverse=True)
    
    # 分页
    total = len(all_violations)
    items = all_violations[offset:offset + limit]
    
    return items


@router.get("/stats")
async def get_violation_stats(
    camera_id: Optional[str] = Query(None, description="筛选特定摄像头"),
    site_id: Optional[str] = Query(None, description="筛选特定工地")
):
    """
    获取违规统计信息
    """
    stream_manager = get_stream_manager()
    config_manager = get_config_manager()
    
    stats = {
        "total": 0,
        "by_type": {},
        "by_severity": {},
        "by_camera": {},
        "by_site": {}
    }
    
    output_base = Path("./output")
    
    # 统计所有日志文件
    sites_to_check = []
    if site_id and config_manager:
        sites_to_check = [s for s in config_manager.sites if s.id == site_id]
    elif config_manager:
        sites_to_check = config_manager.sites
    
    for site in sites_to_check:
        for cam in site.cameras:
            if camera_id and cam.id != camera_id:
                continue
            
            log_file = output_base / site.id / cam.id / "violation_log.json"
            if log_file.exists():
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        count = len(data.get("violations", []))
                        stats["total"] += count
                        
                        # 按摄像头统计
                        stats["by_camera"][cam.id] = count
                        
                        # 按工地统计
                        if site.id not in stats["by_site"]:
                            stats["by_site"][site.id] = 0
                        stats["by_site"][site.id] += count
                        
                        # 详细统计
                        for v in data.get("violations", []):
                            # 按类型统计
                            for vt in v.get("violation_types", []):
                                stats["by_type"][vt] = stats["by_type"].get(vt, 0) + 1
                            
                            # 按严重程度统计
                            sev = v.get("severity", "medium")
                            stats["by_severity"][sev] = stats["by_severity"].get(sev, 0) + 1
                except:
                    pass
    
    return stats


@router.get("/types")
async def get_violation_types():
    """
    获取所有违规类型
    """
    return [
        {"id": "no_helmet", "name": "未戴安全帽", "category": "ppe"},
        {"id": "no_vest", "name": "未穿反光衣", "category": "ppe"},
        {"id": "no_mask", "name": "未戴口罩", "category": "ppe"},
        {"id": "no_harness", "name": "未系安全带", "category": "ppe"},
        {"id": "unfinished_wall", "name": "墙面未完成", "category": "wall"},
        {"id": "severe_defect", "name": "严重缺陷", "category": "wall"},
        {"id": "tool_idle", "name": "刀具空闲", "category": "tool"},
    ]


@router.get("/image")
async def get_violation_image(path: str):
    """
    获取违规截图
    """
    file_path = Path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="图片不存在")
    
    return FileResponse(str(file_path))


import logging
logger = logging.getLogger(__name__)
