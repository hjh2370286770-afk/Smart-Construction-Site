"""
车辆检测器
基于 YOLOv8 的车辆检测和计数
继承自 BaseDetector
"""

import logging
from typing import List, Dict, Any, Optional
from collections import defaultdict

import numpy as np
import cv2

from .base_detector import BaseDetector, Detection

logger = logging.getLogger(__name__)


class VehicleDetector(BaseDetector):
    """
    车辆检测器
    
    检测内容：
    - 小汽车 (car)
    - 摩托车 (motorcycle)
    - 公交车 (bus)
    - 卡车 (truck)
    
    功能：
    - 车辆检测
    - 车辆计数
    - 车辆类型统计
    - 未授权车辆检测
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化车辆检测器
        
        Args:
            config: 配置字典
        """
        super().__init__(config)
        
        # 车辆计数相关
        self.vehicle_count: Dict[str, int] = defaultdict(int)
        self.total_count = 0
        self.detected_vehicles: set = set()  # 用于去重
        
        # 未授权车辆类型
        self.unauthorized_types = config.get('unauthorized_types', ['truck', 'bus'])
        
        logger.info(f"车辆检测器初始化完成")
        
    def _load_model(self):
        """加载 YOLOv8 模型"""
        try:
            from ultralytics import YOLO
            
            # 车辆检测使用预训练的 YOLOv8n
            model_path = self.config.get('path', 'yolov8n.pt')
            
            logger.info(f"加载模型: {model_path}")
            self.model = YOLO(model_path)
            
            # 设置设备
            if self.device == 'auto':
                import torch
                self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
                
        except ImportError:
            logger.error("未安装 ultralytics")
            raise
        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            raise
            
    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        执行车辆检测
        
        Args:
            frame: 输入图像
            
        Returns:
            检测结果列表
        """
        if self.model is None:
            return []
            
        try:
            results = self.model(
                frame,
                conf=self.conf_threshold,
                iou=self.iou_threshold,
                imgsz=self.img_size,
                device=self.device,
                verbose=False,
                classes=[2, 3, 5, 7]  # COCO: car, motorcycle, bus, truck
            )
            
            detections = []
            
            for result in results:
                if result.boxes is None:
                    continue
                    
                for box in result.boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    
                    # 映射到我们的类别名称
                    class_name = self._map_coco_class(cls_id)
                    if class_name is None:
                        continue
                        
                    detection = Detection(
                        bbox=(x1, y1, x2, y2),
                        class_id=cls_id,
                        class_name=class_name,
                        confidence=conf
                    )
                    
                    detections.append(detection)
                    
            # 更新计数
            self._update_count(detections)
            
            return detections
            
        except Exception as e:
            logger.error(f"检测失败: {e}")
            return []
            
    def _map_coco_class(self, coco_class_id: int) -> Optional[str]:
        """
        映射 COCO 类别到我们的类别
        
        COCO classes:
        2: car
        3: motorcycle
        5: bus
        7: truck
        """
        mapping = {
            2: 'car',
            3: 'motorcycle',
            5: 'bus',
            7: 'truck'
        }
        return mapping.get(coco_class_id)
        
    def _update_count(self, detections: List[Detection]):
        """更新车辆计数"""
        current_vehicles = set()
        
        for det in detections:
            # 使用边界框作为唯一标识（简化版）
            vehicle_id = f"{det.class_name}_{det.bbox}"
            current_vehicles.add(vehicle_id)
            
            if vehicle_id not in self.detected_vehicles:
                self.vehicle_count[det.class_name] += 1
                self.total_count += 1
                
        self.detected_vehicles = current_vehicles
        
    def check_violations(self, detections: List[Detection]) -> List[Dict]:
        """
        检查未授权车辆
        
        Returns:
            违规列表
        """
        violations = []
        
        for det in detections:
            if det.class_name in self.unauthorized_types:
                violations.append({
                    'type': 'unauthorized_vehicle',
                    'description': f'未授权车辆: {det.class_name}',
                    'severity': 'medium',
                    'vehicle_type': det.class_name,
                    'bbox': det.bbox
                })
                
        return violations
        
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取车辆统计信息
        
        Returns:
            统计字典
        """
        return {
            'total_vehicles': self.total_count,
            'current_count': len(self.detected_vehicles),
            'by_type': dict(self.vehicle_count),
            'unauthorized_detected': any(
                v in self.unauthorized_types 
                for v in self.vehicle_count.keys()
            )
        }
        
    def reset_count(self):
        """重置计数器"""
        self.vehicle_count.clear()
        self.total_count = 0
        self.detected_vehicles.clear()
        
    def draw_results(self, frame: np.ndarray, detections: List[Detection],
                     show_labels: bool = True, show_conf: bool = True) -> np.ndarray:
        """
        绘制检测结果
        """
        result = frame.copy()
        
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            color = self.class_colors.get(det.class_id, (128, 128, 128))
            
            # 未授权车辆用红色标记
            if det.class_name in self.unauthorized_types:
                color = (0, 0, 255)
                
            cv2.rectangle(result, (x1, y1), (x2, y2), color, 2)
            
            if show_labels:
                label = f"{det.class_name}"
                if show_conf:
                    label += f" {det.confidence:.2f}"
                    
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
                
        # 绘制统计信息
        stats = self.get_statistics()
        stats_text = f"Total: {stats['total_vehicles']}"
        cv2.putText(result, stats_text, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        return result
