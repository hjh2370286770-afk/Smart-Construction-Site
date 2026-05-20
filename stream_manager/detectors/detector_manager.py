#!/usr/bin/env python3
"""
检测器管理器 - 统一管理所有检测模型
根据场景类型自动选择对应的检测器
"""

import logging
from typing import Dict, Optional, Any, List
from pathlib import Path
import numpy as np

from helmet_detector import HelmetDetector
from vest_detector import ReflectiveVestDetector
from vehicle_counter import VehicleCounter
from safety_equipment_detector import SafetyEquipmentDetector
from ppe_detector import PPEDetector

logger = logging.getLogger(__name__)


class DetectorManager:
    """
    检测器管理器
    
    统一管理所有检测模型，根据场景类型自动路由
    """
    
    def __init__(self, models_dir: str = ".."):
        self.models_dir = Path(models_dir)
        self.detectors: Dict[str, Any] = {}
        self._initialized = False
        self._stream_scene_map: Dict[str, str] = {}  # 流ID到场景类型的映射
        
    def initialize(self, detector_configs: Optional[Dict] = None):
        """
        初始化所有检测器
        
        Args:
            detector_configs: 检测器配置字典
        """
        configs = detector_configs or {}
        
        # 1. 安全帽检测器（单独使用）
        try:
            helmet_config = configs.get("helmet", {})
            self.detectors["safety_helmet"] = HelmetDetector(
                model_path=str(self.models_dir / helmet_config.get("model", "yolov8n.pt")),
                conf_threshold=helmet_config.get("conf_threshold", 0.5)
            )
            logger.info("HelmetDetector initialized")
        except Exception as e:
            logger.error(f"Failed to initialize HelmetDetector: {e}")
            
        # 2. 反光衣检测器（单独使用）
        try:
            vest_config = configs.get("vest", {})
            self.detectors["reflective_vest"] = ReflectiveVestDetector(
                model_path=str(self.models_dir / vest_config.get("model", "yolov8n.pt")),
                conf_threshold=vest_config.get("conf_threshold", 0.5)
            )
            logger.info("ReflectiveVestDetector initialized")
        except Exception as e:
            logger.error(f"Failed to initialize ReflectiveVestDetector: {e}")
            
        # 3. 安全装备综合检测器（安全帽+反光衣）
        try:
            safety_config = configs.get("safety_equipment", {})
            self.detectors["safety_equipment"] = SafetyEquipmentDetector(
                model_path=str(self.models_dir / safety_config.get("model", "yolov8n.pt")),
                conf_threshold=safety_config.get("conf_threshold", 0.5),
                use_custom_model=safety_config.get("use_custom_model", False)
            )
            logger.info("SafetyEquipmentDetector initialized")
        except Exception as e:
            logger.error(f"Failed to initialize SafetyEquipmentDetector: {e}")
            
        # 4. PPE综合检测器（新的专用模型）
        try:
            ppe_config = configs.get("ppe", {})
            self.detectors["ppe_detection"] = PPEDetector(
                model_path=ppe_config.get("model_path"),  # None表示使用默认路径
                conf_threshold=ppe_config.get("conf_threshold", 0.4),
                device=ppe_config.get("device")
            )
            logger.info("PPEDetector initialized")
        except Exception as e:
            logger.error(f"Failed to initialize PPEDetector: {e}")
            
        # 5. 车辆计数器
        try:
            vehicle_config = configs.get("vehicle", {})
            self.detectors["vehicle_count"] = VehicleCounter(
                model_path=str(self.models_dir / vehicle_config.get("model", "yolov8n.pt")),
                conf_threshold=vehicle_config.get("conf_threshold", 0.5)
            )
            logger.info("VehicleCounter initialized")
        except Exception as e:
            logger.error(f"Failed to initialize VehicleCounter: {e}")
            
        self._initialized = True
        logger.info(f"DetectorManager initialized with {len(self.detectors)} detectors")
        
    def detect(self, frame: np.ndarray, scene_type: str, **kwargs) -> Dict:
        """
        执行检测
        
        Args:
            frame: 输入图像
            scene_type: 场景类型
            **kwargs: 额外参数
            
        Returns:
            检测结果字典
        """
        if not self._initialized:
            return {"success": False, "error": "DetectorManager not initialized"}
            
        # 场景类型映射
        scene_mapping = {
            "safety_helmet": "safety_helmet",
            "helmet": "safety_helmet",
            "reflective_vest": "reflective_vest",
            "vest": "reflective_vest",
            "safety_equipment": "safety_equipment",  # 综合检测（颜色分析）
            "safety": "safety_equipment",
            "ppe": "ppe_detection",  # PPE专用模型检测（推荐）
            "ppe_detection": "ppe_detection",
            "construction_safety": "ppe_detection",  # 工地安全检测
            "vehicle_count": "vehicle_count",
            "vehicle": "vehicle_count",
            "car": "vehicle_count",
        }
        
        detector_key = scene_mapping.get(scene_type, scene_type)
        detector = self.detectors.get(detector_key)
        
        if detector is None:
            return {
                "success": False, 
                "error": f"No detector found for scene: {scene_type}"
            }
            
        try:
            # 根据检测器类型调用不同方法
            if detector_key == "safety_helmet":
                return self._detect_helmet(detector, frame)
            elif detector_key == "reflective_vest":
                return self._detect_vest(detector, frame)
            elif detector_key == "safety_equipment":
                timestamp = kwargs.get("timestamp", 0)
                return self._detect_safety_equipment(detector, frame, timestamp)
            elif detector_key == "ppe_detection":
                timestamp = kwargs.get("timestamp", 0)
                return self._detect_ppe(detector, frame, timestamp)
            elif detector_key == "vehicle_count":
                timestamp = kwargs.get("timestamp", 0)
                return self._detect_vehicle(detector, frame, timestamp)
            else:
                return {"success": False, "error": f"Unknown detector: {detector_key}"}
                
        except Exception as e:
            logger.error(f"Detection failed for {scene_type}: {e}")
            return {"success": False, "error": str(e)}
            
    def _detect_helmet(self, detector: HelmetDetector, frame: np.ndarray) -> Dict:
        """安全帽检测"""
        detections = detector.detect(frame)
        summary = detector.get_summary(detections)
        
        return {
            "success": True,
            "scene_type": "safety_helmet",
            "detections": [
                {
                    "class_name": "person_with_helmet" if d.has_helmet else "person_no_helmet",
                    "confidence": d.confidence,
                    "bbox": d.bbox,
                    "helmet_color": d.helmet_color,
                    "person_bbox": d.person_bbox
                }
                for d in detections
            ],
            "summary": summary,
            "count": len(detections),
            "violation_count": summary.get("without_helmet", 0)
        }
        
    def _detect_vest(self, detector: ReflectiveVestDetector, frame: np.ndarray) -> Dict:
        """反光衣检测"""
        detections = detector.detect(frame)
        summary = detector.get_summary(detections)
        
        return {
            "success": True,
            "scene_type": "reflective_vest",
            "detections": [
                {
                    "class_name": "person_with_vest" if d.has_vest else "person_no_vest",
                    "confidence": d.confidence,
                    "bbox": d.bbox,
                    "vest_color": d.vest_color,
                    "reflective_score": d.reflective_score,
                    "person_bbox": d.person_bbox
                }
                for d in detections
            ],
            "summary": summary,
            "count": len(detections),
            "violation_count": summary.get("without_vest", 0)
        }
        
    def _detect_safety_equipment(self, detector: SafetyEquipmentDetector, frame: np.ndarray, timestamp: float) -> Dict:
        """安全装备综合检测（安全帽+反光衣）- 基于颜色分析"""
        detections = detector.detect(frame, timestamp)
        summary = detector.get_summary(detections)
        
        return {
            "success": True,
            "scene_type": "safety_equipment",
            "detections": [
                {
                    "track_id": d.track_id,
                    "class_name": "person",
                    "confidence": d.confidence,
                    "bbox": d.person_bbox,
                    "has_helmet": d.has_helmet,
                    "helmet_color": d.helmet_color,
                    "has_vest": d.has_vest,
                    "vest_color": d.vest_color,
                    "is_compliant": d.is_compliant,
                    "violation_type": d.violation_type
                }
                for d in detections
            ],
            "summary": summary,
            "count": len(detections),
            "violation_count": summary["total_persons"] - summary["compliant"],
            "compliance_rate": summary["compliance_rate"]
        }
        
    def _detect_ppe(self, detector: PPEDetector, frame: np.ndarray, timestamp: float) -> Dict:
        """PPE综合检测（安全帽+反光衣+口罩）- 基于专用模型"""
        detections = detector.detect(frame, timestamp)
        summary = detector.get_summary(detections)
        
        return {
            "success": True,
            "scene_type": "ppe_detection",
            "detections": [
                {
                    "track_id": d.track_id,
                    "class_name": "person",
                    "confidence": d.confidence,
                    "bbox": d.person_bbox,
                    "has_helmet": d.has_helmet,
                    "helmet_confidence": d.helmet_confidence,
                    "has_vest": d.has_vest,
                    "vest_confidence": d.vest_confidence,
                    "has_mask": d.has_mask,
                    "mask_confidence": d.mask_confidence,
                    "is_compliant": d.is_compliant,
                    "violation_type": d.violation_type
                }
                for d in detections
            ],
            "summary": summary,
            "count": len(detections),
            "violation_count": summary["total_persons"] - summary["compliant"],
            "compliance_rate": summary["compliance_rate"]
        }
        
    def _detect_vehicle(self, detector: VehicleCounter, frame: np.ndarray, timestamp: float) -> Dict:
        """车辆检测"""
        tracks = detector.detect_and_track(frame, timestamp)
        summary = detector.get_summary()
        
        return {
            "success": True,
            "scene_type": "vehicle_count",
            "detections": [
                {
                    "track_id": t.track_id,
                    "class_name": t.vehicle_type,
                    "confidence": t.confidence,
                    "bbox": t.bbox,
                    "direction": t.direction,
                    "entered": t.entered,
                    "exited": t.exited
                }
                for t in tracks
            ],
            "summary": summary,
            "count": len(tracks),
            "total_in": summary.get("total_in", 0),
            "total_out": summary.get("total_out", 0)
        }
        
    def draw_results(self, 
                     frame: np.ndarray, 
                     scene_type: str, 
                     detection_result: Dict) -> np.ndarray:
        """
        绘制检测结果
        
        Args:
            frame: 原图
            scene_type: 场景类型
            detection_result: 检测结果
            
        Returns:
            绘制后的图像
        """
        if not detection_result.get("success"):
            return frame
            
        # 获取对应的检测器
        scene_mapping = {
            "safety_helmet": "safety_helmet",
            "helmet": "safety_helmet",
            "reflective_vest": "reflective_vest",
            "vest": "reflective_vest",
            "vehicle_count": "vehicle_count",
        }
        
        detector_key = scene_mapping.get(scene_type, scene_type)
        detector = self.detectors.get(detector_key)
        
        if detector is None:
            return frame
            
        # 根据场景类型绘制
        if detector_key == "safety_helmet":
            # 从结果重建检测对象
            from helmet_detector import HelmetDetection
            detections = []
            for d in detection_result.get("detections", []):
                det = HelmetDetection(
                    bbox=d["bbox"],
                    confidence=d["confidence"],
                    has_helmet=d["class_name"] == "person_with_helmet",
                    helmet_color=d.get("helmet_color"),
                    person_bbox=d.get("person_bbox")
                )
                detections.append(det)
            return detector.draw_results(frame, detections)
            
        elif detector_key == "reflective_vest":
            from vest_detector import VestDetection
            detections = []
            for d in detection_result.get("detections", []):
                det = VestDetection(
                    bbox=d["bbox"],
                    confidence=d["confidence"],
                    has_vest=d["class_name"] == "person_with_vest",
                    vest_color=d.get("vest_color"),
                    person_bbox=d.get("person_bbox"),
                    reflective_score=d.get("reflective_score", 0)
                )
                detections.append(det)
            return detector.draw_results(frame, detections)
            
        elif detector_key == "safety_equipment":
            # 安全装备综合检测绘制
            from safety_equipment_detector import PersonSafety
            detections = []
            for d in detection_result.get("detections", []):
                det = PersonSafety(
                    track_id=d["track_id"],
                    person_bbox=d["bbox"],
                    confidence=d["confidence"],
                    has_helmet=d.get("has_helmet", False),
                    helmet_color=d.get("helmet_color"),
                    has_vest=d.get("has_vest", False),
                    vest_color=d.get("vest_color"),
                    reflective_score=d.get("reflective_score", 0)
                )
                detections.append(det)
            return detector.draw_results(frame, detections)
            
        elif detector_key == "ppe_detection":
            # PPE检测绘制
            from ppe_detector import PPEDetection
            detections = []
            for d in detection_result.get("detections", []):
                det = PPEDetection(
                    track_id=d["track_id"],
                    person_bbox=d["bbox"],
                    confidence=d["confidence"],
                    has_helmet=d.get("has_helmet", False),
                    helmet_confidence=d.get("helmet_confidence", 0),
                    has_vest=d.get("has_vest", False),
                    vest_confidence=d.get("vest_confidence", 0),
                    has_mask=d.get("has_mask", False),
                    mask_confidence=d.get("mask_confidence", 0)
                )
                detections.append(det)
            return detector.draw_results(frame, detections)
            
        elif detector_key == "vehicle_count":
            from vehicle_counter import Vehicle
            tracks = []
            for d in detection_result.get("detections", []):
                track = Vehicle(
                    track_id=d["track_id"],
                    vehicle_type=d["class_name"],
                    bbox=d["bbox"],
                    confidence=d["confidence"],
                    center=((d["bbox"][0] + d["bbox"][2]) / 2, 
                           (d["bbox"][1] + d["bbox"][3]) / 2),
                    direction=d.get("direction")
                )
                tracks.append(track)
            return detector.draw_results(frame, tracks)
            
        return frame
        
    def get_detector(self, scene_type: str) -> Optional[Any]:
        """获取指定场景的检测器"""
        return self.detectors.get(scene_type)
        
    def list_detectors(self) -> List[str]:
        """列出所有可用的检测器"""
        return list(self.detectors.keys())
        
    def configure_vehicle_line(self, 
                               line_name: str,
                               start_point: tuple,
                               end_point: tuple,
                               in_direction: str = "bottom"):
        """
        配置车辆计数线
        
        需要在 initialize 之后调用
        """
        detector = self.detectors.get("vehicle_count")
        if detector:
            detector.add_count_line(line_name, start_point, end_point, in_direction)
            logger.info(f"Vehicle count line configured: {line_name}")
            
    def register_stream_scene(self, stream_id: str, scene_type: str):
        """
        注册视频流到场景类型的映射
        
        用于动态管理多个视频流，每个流可以有不同的检测场景
        """
        self._stream_scene_map[stream_id] = scene_type
        logger.info(f"Registered stream {stream_id} -> {scene_type}")
        
    def get_stream_scene(self, stream_id: str) -> Optional[str]:
        """获取视频流对应的场景类型"""
        return self._stream_scene_map.get(stream_id)
        
    def list_stream_scenes(self) -> Dict[str, str]:
        """列出所有视频流的场景映射"""
        return self._stream_scene_map.copy()


# ==================== 测试 ====================

def test():
    """测试检测器管理器"""
    import cv2
    
    # 创建管理器
    manager = DetectorManager(models_dir="..")
    
    # 配置并初始化
    configs = {
        "helmet": {"conf_threshold": 0.5},
        "vest": {"conf_threshold": 0.5},
        "vehicle": {"conf_threshold": 0.5}
    }
    manager.initialize(configs)
    
    # 配置车辆计数线（假设摄像头位置）
    manager.configure_vehicle_line("gate", (100, 300), (540, 300), "bottom")
    
    # 测试摄像头
    cap = cv2.VideoCapture(0)
    
    print("按键说明：")
    print("  1 - 安全帽检测模式")
    print("  2 - 反光衣检测模式")
    print("  3 - 车辆计数模式")
    print("  q - 退出")
    
    current_scene = "safety_helmet"
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        # 执行检测
        result = manager.detect(frame, current_scene)
        
        # 绘制结果
        display = manager.draw_results(frame, current_scene, result)
        
        # 显示当前模式
        cv2.putText(display, f"Mode: {current_scene}", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                   
        cv2.imshow("Detector Manager Test", display)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('1'):
            current_scene = "safety_helmet"
        elif key == ord('2'):
            current_scene = "reflective_vest"
        elif key == ord('3'):
            current_scene = "vehicle_count"
        elif key == ord('s'):
            print(f"\nScene: {current_scene}")
            print(f"Result: {result.get('summary', {})}")
            
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    test()
