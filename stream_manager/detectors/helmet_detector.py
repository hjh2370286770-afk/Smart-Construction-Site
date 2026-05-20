#!/usr/bin/env python3
"""
安全帽检测模块 - 基于YOLOv8的安全帽佩戴检测
支持安全帽/无安全帽分类，支持颜色识别
"""

import cv2
import numpy as np
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from pathlib import Path

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

logger = logging.getLogger(__name__)


@dataclass
class HelmetDetection:
    """安全帽检测结果"""
    bbox: List[float]          # [x1, y1, x2, y2]
    confidence: float
    has_helmet: bool           # True=戴安全帽, False=未戴
    helmet_color: Optional[str] = None  # 安全帽颜色（红/黄/蓝/白）
    person_bbox: Optional[List[float]] = None  # 关联的人体框


class HelmetDetector:
    """
    安全帽检测器
    
    功能：
    1. 检测人员是否佩戴安全帽
    2. 识别安全帽颜色（用于区分不同工种）
    3. 关联人体和头部区域
    """
    
    # 安全帽颜色定义 (BGR格式)
    HELMET_COLORS = {
        "red": ([0, 0, 100], [80, 80, 255]),      # 红色
        "yellow": ([0, 150, 150], [100, 255, 255]), # 黄色
        "blue": ([100, 50, 0], [255, 150, 100]),   # 蓝色
        "white": ([180, 180, 180], [255, 255, 255]), # 白色
    }
    
    def __init__(self, 
                 model_path: str = "yolov8n.pt",
                 conf_threshold: float = 0.5,
                 use_custom_model: bool = False):
        """
        初始化检测器
        
        Args:
            model_path: YOLO模型路径
            conf_threshold: 置信度阈值
            use_custom_model: 是否使用专门训练的安全帽检测模型
        """
        self.conf_threshold = conf_threshold
        self.use_custom_model = use_custom_model
        
        if YOLO is None:
            raise ImportError("ultralytics is required")
            
        # 加载模型
        self.model = YOLO(model_path)
        logger.info(f"HelmetDetector initialized with model: {model_path}")
        
        # 类别映射（如果使用通用模型）
        self.class_names = self.model.names
        
    def detect(self, frame: np.ndarray) -> List[HelmetDetection]:
        """
        检测安全帽
        
        Args:
            frame: 输入图像 (BGR格式)
            
        Returns:
            检测结果列表
        """
        results = self.model(frame, conf=self.conf_threshold, verbose=False)[0]
        
        detections = []
        persons = []
        heads = []
        
        # 第一步：分类检测结果
        for box in results.boxes:
            cls_id = int(box.cls)
            cls_name = self.class_names[cls_id].lower()
            conf = float(box.conf)
            bbox = box.xyxy[0].tolist()
            
            # 如果是自定义模型，直接解析类别
            if self.use_custom_model:
                if "helmet" in cls_name and "no" not in cls_name:
                    heads.append({"bbox": bbox, "conf": conf, "has_helmet": True})
                elif "no_helmet" in cls_name or "head" in cls_name:
                    heads.append({"bbox": bbox, "conf": conf, "has_helmet": False})
                elif "person" in cls_name:
                    persons.append({"bbox": bbox, "conf": conf})
            else:
                # 使用通用模型：检测person和head
                if "person" in cls_name:
                    persons.append({"bbox": bbox, "conf": conf})
                elif "head" in cls_name or "face" in cls_name:
                    heads.append({"bbox": bbox, "conf": conf, "has_helmet": None})
                    
        # 第二步：关联人体和头部，判断安全帽
        for head in heads:
            head_bbox = head["bbox"]
            has_helmet = head.get("has_helmet")
            
            # 如果通用模型，需要判断是否有安全帽
            if has_helmet is None:
                has_helmet = self._check_helmet(frame, head_bbox)
                
            # 识别人体关联
            person_bbox = self._find_associated_person(head_bbox, persons)
            
            # 识别安全帽颜色
            helmet_color = None
            if has_helmet:
                helmet_color = self._detect_helmet_color(frame, head_bbox)
                
            detection = HelmetDetection(
                bbox=head_bbox,
                confidence=head["conf"],
                has_helmet=has_helmet,
                helmet_color=helmet_color,
                person_bbox=person_bbox
            )
            detections.append(detection)
            
        # 第三步：检测只有人体但没有头部的情况（可能被遮挡）
        matched_persons = set()
        for det in detections:
            if det.person_bbox:
                for i, p in enumerate(persons):
                    if self._iou(det.person_bbox, p["bbox"]) > 0.5:
                        matched_persons.add(i)
                        
        # 未匹配的人体，尝试直接检测头部区域
        for i, person in enumerate(persons):
            if i not in matched_persons:
                head_region = self._estimate_head_region(person["bbox"])
                has_helmet = self._check_helmet(frame, head_region)
                helmet_color = self._detect_helmet_color(frame, head_region) if has_helmet else None
                
                detection = HelmetDetection(
                    bbox=head_region,
                    confidence=person["conf"] * 0.8,  # 置信度降低
                    has_helmet=has_helmet,
                    helmet_color=helmet_color,
                    person_bbox=person["bbox"]
                )
                detections.append(detection)
                
        return detections
        
    def _check_helmet(self, frame: np.ndarray, head_bbox: List[float]) -> bool:
        """
        检查头部区域是否有安全帽
        
        使用颜色特征和形状分析判断
        """
        x1, y1, x2, y2 = map(int, head_bbox)
        h, w = y2 - y1, x2 - x1
        
        # 扩展区域以包含安全帽
        y1_ext = max(0, y1 - int(h * 0.3))
        head_region = frame[y1_ext:y2, x1:x2]
        
        if head_region.size == 0:
            return False
            
        # 转换到HSV颜色空间进行颜色分析
        hsv = cv2.cvtColor(head_region, cv2.COLOR_BGR2HSV)
        
        # 检查是否有安全帽颜色特征
        for color_name, (lower, upper) in self.HELMET_COLORS.items():
            lower = np.array(lower)
            upper = np.array(upper)
            mask = cv2.inRange(head_region, lower, upper)
            
            # 如果颜色占比超过阈值，认为是安全帽
            color_ratio = np.sum(mask > 0) / mask.size
            if color_ratio > 0.15:  # 15%阈值
                return True
                
        return False
        
    def _detect_helmet_color(self, frame: np.ndarray, head_bbox: List[float]) -> Optional[str]:
        """识别安全帽颜色"""
        x1, y1, x2, y2 = map(int, head_bbox)
        h = y2 - y1
        y1_ext = max(0, y1 - int(h * 0.3))
        head_region = frame[y1_ext:y2, x1:x2]
        
        if head_region.size == 0:
            return None
            
        max_ratio = 0
        detected_color = None
        
        for color_name, (lower, upper) in self.HELMET_COLORS.items():
            lower = np.array(lower)
            upper = np.array(upper)
            mask = cv2.inRange(head_region, lower, upper)
            
            color_ratio = np.sum(mask > 0) / mask.size
            if color_ratio > max_ratio and color_ratio > 0.15:
                max_ratio = color_ratio
                detected_color = color_name
                
        return detected_color
        
    def _find_associated_person(self, 
                                 head_bbox: List[float], 
                                 persons: List[Dict]) -> Optional[List[float]]:
        """找到与头部关联的人体框"""
        head_center = [(head_bbox[0] + head_bbox[2]) / 2, (head_bbox[1] + head_bbox[3]) / 2]
        
        best_match = None
        best_iou = 0
        
        for person in persons:
            person_bbox = person["bbox"]
            # 检查头部是否在人体框上方
            if head_bbox[1] < person_bbox[1]:  # head y1 < person y1
                iou = self._iou(head_bbox, person_bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_match = person_bbox
                    
        return best_match
        
    def _estimate_head_region(self, person_bbox: List[float]) -> List[float]:
        """从人体框估计头部区域"""
        x1, y1, x2, y2 = person_bbox
        w, h = x2 - x1, y2 - y1
        
        # 头部约占人体上部15-20%
        head_h = h * 0.2
        head_w = w * 0.5
        
        head_x1 = x1 + (w - head_w) / 2
        head_x2 = head_x1 + head_w
        head_y1 = y1
        head_y2 = y1 + head_h
        
        return [head_x1, head_y1, head_x2, head_y2]
        
    def _iou(self, box1: List[float], box2: List[float]) -> float:
        """计算IOU"""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        
        inter_area = max(0, x2 - x1) * max(0, y2 - y1)
        box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
        box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])
        
        union_area = box1_area + box2_area - inter_area
        return inter_area / union_area if union_area > 0 else 0
        
    def draw_results(self, 
                     frame: np.ndarray, 
                     detections: List[HelmetDetection]) -> np.ndarray:
        """绘制检测结果"""
        result = frame.copy()
        
        for det in detections:
            x1, y1, x2, y2 = map(int, det.bbox)
            
            # 根据是否戴安全帽选择颜色
            if det.has_helmet:
                color = (0, 255, 0)  # 绿色
                status = f"Helmet"
                if det.helmet_color:
                    status += f"({det.helmet_color})"
            else:
                color = (0, 0, 255)  # 红色
                status = "NO Helmet!"
                
            # 绘制边界框
            cv2.rectangle(result, (x1, y1), (x2, y2), color, 2)
            
            # 绘制标签
            label = f"{status} {det.confidence:.2f}"
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
            cv2.rectangle(result, (x1, y1 - label_size[1] - 8), 
                         (x1 + label_size[0], y1), color, -1)
            cv2.putText(result, label, (x1, y1 - 4), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                       
            # 如果有关联人体，绘制人体框（虚线）
            if det.person_bbox:
                px1, py1, px2, py2 = map(int, det.person_bbox)
                cv2.rectangle(result, (px1, py1), (px2, py2), color, 1)
                
        # 添加统计信息
        total = len(detections)
        with_helmet = sum(1 for d in detections if d.has_helmet)
        without_helmet = total - with_helmet
        
        stats_text = f"Total: {total} | With Helmet: {with_helmet} | Without: {without_helmet}"
        cv2.putText(result, stats_text, (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                   
        return result
        
    def get_summary(self, detections: List[HelmetDetection]) -> Dict:
        """获取检测摘要"""
        total = len(detections)
        with_helmet = sum(1 for d in detections if d.has_helmet)
        without_helmet = total - with_helmet
        
        color_stats = {}
        for d in detections:
            if d.has_helmet and d.helmet_color:
                color_stats[d.helmet_color] = color_stats.get(d.helmet_color, 0) + 1
                
        return {
            "total_persons": total,
            "with_helmet": with_helmet,
            "without_helmet": without_helmet,
            "compliance_rate": with_helmet / total if total > 0 else 0,
            "helmet_colors": color_stats
        }


# ==================== 测试 ====================

def test():
    """测试安全帽检测"""
    import sys
    
    # 创建检测器
    detector = HelmetDetector(
        model_path="../yolov8n.pt",
        conf_threshold=0.5
    )
    
    # 测试图片或摄像头
    test_source = 0  # 默认摄像头，或改为图片路径
    
    if isinstance(test_source, str) and Path(test_source).exists():
        frame = cv2.imread(test_source)
        detections = detector.detect(frame)
        result = detector.draw_results(frame, detections)
        
        print("Detection Summary:")
        print(detector.get_summary(detections))
        
        cv2.imshow("Helmet Detection", result)
        cv2.waitKey(0)
    else:
        cap = cv2.VideoCapture(test_source)
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            detections = detector.detect(frame)
            result = detector.draw_results(frame, detections)
            
            cv2.imshow("Helmet Detection", result)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    test()
