"""
检测器模块

提供多种检测器实现：
- PPEDetector: PPE检测（安全帽、反光衣、口罩）
- VehicleDetector: 车辆检测
- WallDefectDetector: 墙面缺陷检测（裂缝、污渍）
- WallDefectDetectorV2: 墙面缺陷检测V2（墙面状态+设备状态）

使用方式：
    from detectors import PPEDetector, VehicleDetector, WallDefectDetector
    from detectors.detector_engine import create_detector_engine
"""

from .base_detector import BaseDetector, Detection, DetectionResult

__all__ = [
    'BaseDetector',
    'Detection',
    'DetectionResult',
]
