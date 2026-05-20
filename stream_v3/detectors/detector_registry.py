"""
检测器注册表
提供统一的检测器管理和注册接口
"""

import logging
from typing import Dict, Type, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DetectorInfo:
    """检测器信息"""
    id: str                          # 检测器ID (如: ppe_detector, wall_detector_v2)
    name: str                        # 显示名称
    description: str                 # 描述
    category: str                    # 类别 (ppe, wall, vehicle, tool)
    supported_cameras: List[str]     # 支持的摄像头类型
    config_schema: Optional[Dict]    # 配置schema (可选)


class DetectorRegistry:
    """
    检测器注册表
    
    提供检测器的注册、查找、枚举功能
    """
    
    _instance = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._detectors: Dict[str, DetectorInfo] = {}
        self._detector_classes: Dict[str, Type] = {}
        self._initialized = True
        
        # 注册内置检测器
        self._register_builtin_detectors()
        
        logger.info(f"检测器注册表初始化完成，注册了 {len(self._detectors)} 个检测器")
    
    def _register_builtin_detectors(self):
        """注册内置检测器"""
        # PPE检测器
        self.register(
            detector_id="ppe_detector",
            name="PPE安全检测",
            description="检测安全帽、反光衣、口罩等个人防护装备",
            category="ppe",
            supported_cameras=["rtmp", "rtsp", "http"],
            config_schema={
                "conf_threshold": {"type": "float", "default": 0.45},
                "iou_threshold": {"type": "float", "default": 0.4}
            }
        )
        
        # 车辆检测器
        self.register(
            detector_id="vehicle_detector",
            name="车辆检测",
            description="检测施工车辆（渣土车、混凝土车等）",
            category="vehicle",
            supported_cameras=["rtmp", "rtsp", "http"],
            config_schema={
                "conf_threshold": {"type": "float", "default": 0.5}
            }
        )
        
        # 墙面缺陷检测器V1
        self.register(
            detector_id="wall_defect_detector",
            name="墙面缺陷检测V1",
            description="检测墙面裂缝、污渍、平整度问题",
            category="wall",
            supported_cameras=["rtmp", "rtsp", "http"],
            config_schema={
                "conf_threshold": {"type": "float", "default": 0.25}
            }
        )
        
        # 墙面缺陷检测器V2
        self.register(
            detector_id="wall_defect_detector_v2",
            name="墙面缺陷检测V2",
            description="检测墙面状态和设备工作状态（进阶版）",
            category="wall",
            supported_cameras=["rtmp", "rtsp", "http"],
            config_schema={
                "conf_threshold": {"type": "float", "default": 0.25}
            }
        )
        
        # 刀具检测器（基于V2）
        self.register(
            detector_id="tool_detector",
            name="刀具状态检测",
            description="检测建筑机器人刀具运动状态和设备工作状态",
            category="tool",
            supported_cameras=["rtmp", "rtsp", "http"],
            config_schema={
                "conf_threshold": {"type": "float", "default": 0.25}
            }
        )
        
        # 车辆清洗检测器
        self.register(
            detector_id="vehicle_wash_detector",
            name="车辆清洗检测",
            description="检测车辆进场、出场、清洗状态，识别车牌号码",
            category="vehicle",
            supported_cameras=["rtmp", "rtsp", "http"],
            config_schema={
                "conf_threshold": {"type": "float", "default": 0.5},
                "wash_zone": {"type": "object", "default": {"x1": 0.1, "y1": 0.3, "x2": 0.7, "y2": 0.8}},
                "wash_stop_time": {"type": "int", "default": 180}
            }
        )
    
    def register(
        self,
        detector_id: str,
        name: str,
        description: str,
        category: str,
        supported_cameras: List[str],
        detector_class: Optional[Type] = None,
        config_schema: Optional[Dict] = None
    ):
        """
        注册检测器
        
        Args:
            detector_id: 检测器唯一ID
            name: 显示名称
            description: 描述
            category: 类别
            supported_cameras: 支持的摄像头类型
            detector_class: 检测器类 (可选)
            config_schema: 配置schema (可选)
        """
        info = DetectorInfo(
            id=detector_id,
            name=name,
            description=description,
            category=category,
            supported_cameras=supported_cameras,
            config_schema=config_schema
        )
        
        self._detectors[detector_id] = info
        
        if detector_class:
            self._detector_classes[detector_id] = detector_class
        
        logger.info(f"注册检测器: {detector_id} ({name})")
    
    def register_class(self, detector_id: str, detector_class: Type):
        """
        注册检测器类
        
        Args:
            detector_id: 检测器ID
            detector_class: 检测器类
        """
        self._detector_classes[detector_id] = detector_class
        logger.info(f"注册检测器类: {detector_id} -> {detector_class.__name__}")
    
    def get(self, detector_id: str) -> Optional[DetectorInfo]:
        """获取检测器信息"""
        return self._detectors.get(detector_id)
    
    def get_class(self, detector_id: str) -> Optional[Type]:
        """获取检测器类"""
        return self._detector_classes.get(detector_id)
    
    def list_all(self) -> List[DetectorInfo]:
        """列出所有检测器"""
        return list(self._detectors.values())
    
    def list_by_category(self, category: str) -> List[DetectorInfo]:
        """按类别列出检测器"""
        return [d for d in self._detectors.values() if d.category == category]
    
    def exists(self, detector_id: str) -> bool:
        """检查检测器是否存在"""
        return detector_id in self._detectors
    
    def get_categories(self) -> List[str]:
        """获取所有检测器类别"""
        return list(set(d.category for d in self._detectors.values()))


# 全局实例
_detector_registry: Optional[DetectorRegistry] = None


def get_detector_registry() -> DetectorRegistry:
    """获取检测器注册表实例"""
    global _detector_registry
    if _detector_registry is None:
        _detector_registry = DetectorRegistry()
    return _detector_registry


def register_detector(
    detector_id: str,
    name: str,
    description: str,
    category: str,
    supported_cameras: List[str],
    detector_class: Optional[Type] = None,
    config_schema: Optional[Dict] = None
):
    """便捷函数：注册检测器"""
    registry = get_detector_registry()
    registry.register(
        detector_id=detector_id,
        name=name,
        description=description,
        category=category,
        supported_cameras=supported_cameras,
        detector_class=detector_class,
        config_schema=config_schema
    )
