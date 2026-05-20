"""
基础检测器类
所有检测器都需要继承此类
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import cv2


@dataclass
class Detection:
    """检测结果"""
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    class_id: int
    class_name: str
    confidence: float
    track_id: Optional[int] = None
    
    # PPE 专用字段
    has_helmet: bool = False
    has_vest: bool = False
    has_mask: bool = False


@dataclass
class DetectionResult:
    """单帧检测结果"""
    detections: List[Detection]
    frame_id: int
    timestamp: float
    
    # 统计信息
    person_count: int = 0
    violations: List[Dict] = None
    
    def __post_init__(self):
        if self.violations is None:
            self.violations = []


class BaseDetector(ABC):
    """
    检测器基类
    所有具体检测器都需要继承此类
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化检测器
        
        Args:
            config: 检测器配置字典
        """
        self.config = config
        self.model = None
        self.class_names = []
        self.class_colors = {}
        self.violation_rules = []
        
        # 通用参数
        self.conf_threshold = config.get('params', {}).get('conf_threshold', 0.45)
        self.iou_threshold = config.get('params', {}).get('iou_threshold', 0.4)
        self.img_size = config.get('params', {}).get('img_size', 640)
        self.device = config.get('params', {}).get('device', 'auto')
        
        self._load_model()
        self._init_classes()
        
    @abstractmethod
    def _load_model(self):
        """加载模型 - 子类必须实现"""
        pass
        
    @abstractmethod
    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        执行检测 - 子类必须实现
        
        Args:
            frame: 输入图像 (BGR格式)
            
        Returns:
            检测结果列表
        """
        pass
        
    def _init_classes(self):
        """初始化类别信息"""
        classes = self.config.get('classes', [])
        for cls in classes:
            self.class_names.append(cls['name'])
            self.class_colors[cls['id']] = tuple(cls.get('color', [0, 255, 0]))
            
        self.violation_rules = self.config.get('violation_rules', [])
        
    def get_supported_classes(self) -> List[str]:
        """获取支持的检测类别"""
        return self.class_names
        
    def check_violations(self, detections: List[Detection]) -> List[Dict]:
        """
        检查违规情况
        
        Args:
            detections: 检测结果列表
            
        Returns:
            违规列表
        """
        violations = []
        
        for rule in self.violation_rules:
            violation = self._apply_rule(rule, detections)
            if violation:
                violations.append(violation)
                
        return violations
        
    def _apply_rule(self, rule: Dict, detections: List[Detection]) -> Optional[Dict]:
        """应用单条违规规则"""
        # 子类可以重写此方法实现自定义规则
        return None
        
    def draw_results(self, frame: np.ndarray, detections: List[Detection],
                     show_labels: bool = True, show_conf: bool = True) -> np.ndarray:
        """
        在图像上绘制检测结果
        
        Args:
            frame: 输入图像
            detections: 检测结果
            show_labels: 是否显示标签
            show_conf: 是否显示置信度
            
        Returns:
            绘制后的图像
        """
        result = frame.copy()
        
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            color = self.class_colors.get(det.class_id, (0, 255, 0))
            
            # 绘制边界框
            cv2.rectangle(result, (x1, y1), (x2, y2), color, 2)
            
            # 准备标签文本
            label_parts = [det.class_name]
            if det.track_id is not None:
                label_parts.append(f"ID:{det.track_id}")
            if show_conf:
                label_parts.append(f"{det.confidence:.2f}")
                
            label = " ".join(label_parts)
            
            # 绘制标签背景
            if show_labels:
                (text_w, text_h), _ = cv2.getTextSize(
                    label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2
                )
                cv2.rectangle(
                    result,
                    (x1, y1 - text_h - 10),
                    (x1 + text_w, y1),
                    color,
                    -1
                )
                cv2.putText(
                    result, label, (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2
                )
                
        return result
        
    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        return {
            "name": self.config.get('name', 'Unknown'),
            "type": self.config.get('type', 'unknown'),
            "version": self.config.get('version', '1.0'),
            "classes": self.class_names,
            "violation_rules": [r['name'] for r in self.violation_rules]
        }
