#!/usr/bin/env python3
"""
场景路由引擎 - 根据场景类型动态选择和切换模型
"""

import logging
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass
from pathlib import Path
import numpy as np

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None
    logging.warning("ultralytics not installed, YOLO models will not be available")

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    """模型配置"""
    model_path: str
    conf_threshold: float = 0.5
    iou_threshold: float = 0.45
    classes: Optional[list] = None  # 指定检测的类别，None表示全部
    device: str = "auto"  # auto, cpu, cuda, mps


class SceneRouter:
    """
    场景路由引擎
    
    管理多个场景对应的模型，根据场景类型自动路由到对应模型
    """
    
    # 预定义场景配置
    DEFAULT_SCENES = {
        "safety_helmet": {
            "description": "安全帽检测",
            "model": "yolov8n.pt",  # 可以使用专门的预训练模型
            "classes": ["person", "helmet", "no_helmet"],
            "conf_threshold": 0.6,
        },
        "ppe_detection": {
            "description": "PPE综合检测（安全帽+反光衣+口罩）",
            "model": "detectors/models/ppe_best.pt",  # 专用PPE模型
            "classes": None,  # 使用模型所有类别
            "conf_threshold": 0.4,
        },
        "construction_safety": {
            "description": "工地安全检测",
            "model": "detectors/models/ppe_best.pt",
            "classes": None,
            "conf_threshold": 0.4,
        },
        "person_count": {
            "description": "人员计数",
            "model": "yolov8n.pt",
            "classes": ["person"],
            "conf_threshold": 0.5,
        },
        "danger_zone": {
            "description": "危险区域入侵检测",
            "model": "yolov8n.pt",
            "classes": ["person"],
            "conf_threshold": 0.5,
        },
        "vehicle_detect": {
            "description": "车辆检测",
            "model": "yolov8n.pt",
            "classes": ["car", "truck", "bus", "motorcycle"],
            "conf_threshold": 0.5,
        },
        "fire_smoke": {
            "description": "烟火检测",
            "model": "yolov8n.pt",  # 需要专门的烟火检测模型
            "classes": ["fire", "smoke"],
            "conf_threshold": 0.4,
        },
        "default": {
            "description": "通用检测",
            "model": "yolov8n.pt",
            "classes": None,
            "conf_threshold": 0.5,
        }
    }
    
    def __init__(self, models_dir: str = "."):
        self.models_dir = Path(models_dir)
        self.models: Dict[str, Any] = {}  # 已加载的模型缓存
        self.scene_configs: Dict[str, Dict] = {}
        self._preprocess_hooks: Dict[str, Callable] = {}
        self._postprocess_hooks: Dict[str, Callable] = {}
        
        # 初始化默认场景
        self._init_default_scenes()
        
    def _init_default_scenes(self):
        """初始化默认场景配置"""
        for scene_type, config in self.DEFAULT_SCENES.items():
            self.register_scene(scene_type, config)
            
    def register_scene(self, scene_type: str, config: Dict):
        """
        注册场景配置
        
        Args:
            scene_type: 场景类型标识
            config: 场景配置字典
        """
        self.scene_configs[scene_type] = config
        logger.info(f"Registered scene: {scene_type} - {config.get('description', '')}")
        
    def load_model(self, scene_type: str) -> Optional[Any]:
        """
        加载指定场景的模型
        
        Args:
            scene_type: 场景类型
            
        Returns:
            加载好的模型实例，如果YOLO不可用则返回None
        """
        if YOLO is None:
            logger.error("ultralytics not installed, cannot load YOLO model")
            return None
            
        if scene_type in self.models:
            return self.models[scene_type]
            
        config = self.scene_configs.get(scene_type, self.scene_configs.get("default"))
        model_path = self.models_dir / config.get("model", "yolov8n.pt")
        
        try:
            logger.info(f"Loading model for scene '{scene_type}': {model_path}")
            model = YOLO(str(model_path))
            self.models[scene_type] = model
            return model
        except Exception as e:
            logger.error(f"Failed to load model for scene '{scene_type}': {e}")
            return None
            
    def unload_model(self, scene_type: str):
        """卸载指定场景的模型"""
        if scene_type in self.models:
            del self.models[scene_type]
            logger.info(f"Unloaded model for scene: {scene_type}")
            
    def get_model(self, scene_type: str) -> Optional[Any]:
        """获取场景的模型（自动加载）"""
        if scene_type not in self.models:
            self.load_model(scene_type)
        return self.models.get(scene_type)
        
    def detect(self, frame: np.ndarray, scene_type: str) -> Dict:
        """
        对单帧进行目标检测
        
        Args:
            frame: numpy数组 (BGR格式)
            scene_type: 场景类型
            
        Returns:
            检测结果字典
        """
        model = self.get_model(scene_type)
        if model is None:
            return {"success": False, "error": "Model not available"}
            
        config = self.scene_configs.get(scene_type, self.scene_configs.get("default"))
        
        try:
            # 执行推理
            results = model(
                frame,
                conf=config.get("conf_threshold", 0.5),
                iou=config.get("iou_threshold", 0.45),
                classes=config.get("classes"),
                verbose=False
            )[0]
            
            # 解析结果
            detections = []
            for box in results.boxes:
                detection = {
                    "class_id": int(box.cls),
                    "class_name": results.names[int(box.cls)],
                    "confidence": float(box.conf),
                    "bbox": box.xyxy[0].tolist()  # [x1, y1, x2, y2]
                }
                detections.append(detection)
                
            return {
                "success": True,
                "scene_type": scene_type,
                "detections": detections,
                "count": len(detections),
                "speed": results.speed  # 推理耗时
            }
            
        except Exception as e:
            logger.error(f"Detection failed for scene '{scene_type}': {e}")
            return {"success": False, "error": str(e)}
            
    def register_preprocess_hook(self, scene_type: str, hook: Callable):
        """注册预处理钩子"""
        self._preprocess_hooks[scene_type] = hook
        
    def register_postprocess_hook(self, scene_type: str, hook: Callable):
        """注册后处理钩子"""
        self._postprocess_hooks[scene_type] = hook


# ==================== 使用示例 ====================

def demo():
    """演示用法"""
    import cv2
    
    # 创建场景路由器
    router = SceneRouter(models_dir="..")
    
    # 自定义场景配置
    router.register_scene("custom_scene", {
        "description": "自定义检测场景",
        "model": "yolov8n.pt",
        "classes": ["person", "car"],
        "conf_threshold": 0.6
    })
    
    # 加载测试图片（如果有）
    test_image = "test.jpg"
    if Path(test_image).exists():
        frame = cv2.imread(test_image)
        
        # 对不同场景进行检测
        for scene in ["safety_helmet", "person_count", "vehicle_detect"]:
            result = router.detect(frame, scene)
            print(f"\nScene: {scene}")
            print(f"Detections: {result.get('count', 0)}")
            for det in result.get("detections", [])[:3]:  # 只显示前3个
                print(f"  - {det['class_name']}: {det['confidence']:.2f}")
    else:
        print(f"Test image not found: {test_image}")
        print("Scene router initialized successfully")
        print(f"Available scenes: {list(router.scene_configs.keys())}")


if __name__ == "__main__":
    demo()
