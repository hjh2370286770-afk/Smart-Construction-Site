"""
检测器管理路由
提供检测器的注册、查询、选择接口
"""

from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel

from detectors.detector_registry import get_detector_registry, DetectorInfo
from detectors import (
    PPEDetector, 
    VehicleDetector,
    WallDefectDetector,
    WallDefectDetectorV2
)

router = APIRouter(prefix="/detectors", tags=["detectors"])


# ============== 响应模型 ==============

class DetectorInfoResponse(BaseModel):
    """检测器信息响应"""
    id: str
    name: str
    description: str
    category: str
    supported_cameras: List[str]
    config_schema: Optional[dict]


class DetectorListResponse(BaseModel):
    """检测器列表响应"""
    detectors: List[DetectorInfoResponse]
    categories: List[str]


class DetectorCategoryResponse(BaseModel):
    """按类别检测器响应"""
    category: str
    detectors: List[DetectorInfoResponse]


# ============== 检测器路由 ==============

@router.get("", response_model=DetectorListResponse)
async def get_all_detectors():
    """
    获取所有已注册的检测器
    """
    registry = get_detector_registry()
    
    detectors = registry.list_all()
    categories = registry.get_categories()
    
    return DetectorListResponse(
        detectors=[
            DetectorInfoResponse(
                id=d.id,
                name=d.name,
                description=d.description,
                category=d.category,
                supported_cameras=d.supported_cameras,
                config_schema=d.config_schema
            )
            for d in detectors
        ],
        categories=categories
    )


@router.get("/categories", response_model=List[str])
async def get_detector_categories():
    """
    获取所有检测器类别
    """
    registry = get_detector_registry()
    return registry.get_categories()


@router.get("/category/{category}", response_model=DetectorCategoryResponse)
async def get_detectors_by_category(category: str):
    """
    按类别获取检测器
    """
    registry = get_detector_registry()
    detectors = registry.list_by_category(category)
    
    if not detectors:
        raise HTTPException(
            status_code=404, 
            detail=f"未找到类别 '{category}' 的检测器"
        )
    
    return DetectorCategoryResponse(
        category=category,
        detectors=[
            DetectorInfoResponse(
                id=d.id,
                name=d.name,
                description=d.description,
                category=d.category,
                supported_cameras=d.supported_cameras,
                config_schema=d.config_schema
            )
            for d in detectors
        ]
    )


@router.get("/{detector_id}", response_model=DetectorInfoResponse)
async def get_detector(detector_id: str):
    """
    获取指定检测器的详细信息
    """
    registry = get_detector_registry()
    detector = registry.get(detector_id)
    
    if not detector:
        raise HTTPException(
            status_code=404,
            detail=f"未找到检测器 '{detector_id}'"
        )
    
    return DetectorInfoResponse(
        id=detector.id,
        name=detector.name,
        description=detector.description,
        category=detector.category,
        supported_cameras=detector.supported_cameras,
        config_schema=detector.config_schema
    )


# ============== 检测器类注册 ==============

def register_detector_classes():
    """
    注册所有检测器类到注册表
    在应用启动时调用
    """
    registry = get_detector_registry()
    
    # 注册检测器类
    registry.register_class("ppe_detector", PPEDetector)
    registry.register_class("vehicle_detector", VehicleDetector)
    registry.register_class("wall_defect_detector", WallDefectDetector)
    registry.register_class("wall_defect_detector_v2", WallDefectDetectorV2)
    # tool_detector 使用 wall_defect_detector_v2 的逻辑
    
    return registry.list_all()
