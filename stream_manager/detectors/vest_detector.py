#!/usr/bin/env python3
"""
反光衣检测模块 - 基于YOLOv8和颜色识别的反光衣穿戴检测
支持反光衣/普通衣服分类，支持颜色识别（橙/黄/红）
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
class VestDetection:
    """反光衣检测结果"""
    bbox: List[float]          # [x1, y1, x2, y2]
    confidence: float
    has_vest: bool             # True=穿反光衣, False=未穿
    vest_color: Optional[str] = None  # 反光衣颜色（orange/yellow/red）
    person_bbox: Optional[List[float]] = None  # 关联的人体框
    reflective_score: float = 0.0  # 反光特征分数


class ReflectiveVestDetector:
    """
    反光衣检测器
    
    功能：
    1. 检测人员是否穿着反光衣
    2. 识别反光衣颜色（橙色/黄色/红色）
    3. 分析反光条纹特征
    4. 关联人体和反光衣区域
    """
    
    # 反光衣颜色范围 (BGR格式)
    VEST_COLORS = {
        "orange": ([0, 80, 160], [80, 160, 255]),      # 橙色
        "yellow": ([0, 180, 180], [100, 255, 255]),     # 黄色
        "red": ([0, 0, 160], [80, 80, 255]),           # 红色
    }
    
    # 反光条纹颜色范围 (高亮度)
    REFLECTIVE_RANGE = ([200, 200, 200], [255, 255, 255])
    
    def __init__(self, 
                 model_path: str = "yolov8n.pt",
                 conf_threshold: float = 0.5,
                 reflective_threshold: float = 0.3):
        """
        初始化检测器
        
        Args:
            model_path: YOLO模型路径
            conf_threshold: 置信度阈值
            reflective_threshold: 反光特征阈值
        """
        self.conf_threshold = conf_threshold
        self.reflective_threshold = reflective_threshold
        
        if YOLO is None:
            raise ImportError("ultralytics is required")
            
        self.model = YOLO(model_path)
        self.class_names = self.model.names
        
        logger.info(f"ReflectiveVestDetector initialized")
        
    def detect(self, frame: np.ndarray) -> List[VestDetection]:
        """
        检测反光衣
        
        Args:
            frame: 输入图像 (BGR格式)
            
        Returns:
            检测结果列表
        """
        results = self.model(frame, conf=self.conf_threshold, verbose=False)[0]
        
        detections = []
        persons = []
        
        # 收集人体检测结果
        for box in results.boxes:
            cls_id = int(box.cls)
            cls_name = self.class_names[cls_id].lower()
            conf = float(box.conf)
            bbox = box.xyxy[0].tolist()
            
            if "person" in cls_name:
                persons.append({"bbox": bbox, "conf": conf})
                
        # 对每个检测的人体，分析是否穿反光衣
        for person in persons:
            person_bbox = person["bbox"]
            
            # 提取上半身区域（反光衣通常在上半身）
            upper_body = self._extract_upper_body(frame, person_bbox)
            
            if upper_body is None:
                continue
                
            # 检测反光衣特征
            has_vest, vest_color, reflective_score = self._analyze_vest_features(
                frame, person_bbox, upper_body
            )
            
            detection = VestDetection(
                bbox=upper_body["bbox"],
                confidence=person["conf"],
                has_vest=has_vest,
                vest_color=vest_color,
                person_bbox=person_bbox,
                reflective_score=reflective_score
            )
            detections.append(detection)
            
        return detections
        
    def _extract_upper_body(self, 
                           frame: np.ndarray, 
                           person_bbox: List[float]) -> Optional[Dict]:
        """提取人体上半身区域"""
        x1, y1, x2, y2 = map(int, person_bbox)
        h, w = y2 - y1, x2 - x1
        
        # 上半身约占人体的40%（从肩膀到腰部）
        upper_h = int(h * 0.45)
        
        # 稍微缩小宽度，聚焦躯干
        margin = int(w * 0.15)
        
        ux1 = max(0, x1 + margin)
        uy1 = max(0, y1)
        ux2 = min(frame.shape[1], x2 - margin)
        uy2 = min(frame.shape[0], y1 + upper_h)
        
        if ux2 <= ux1 or uy2 <= uy1:
            return None
            
        upper_region = frame[uy1:uy2, ux1:ux2]
        
        return {
            "bbox": [ux1, uy1, ux2, uy2],
            "region": upper_region
        }
        
    def _analyze_vest_features(self, 
                               frame: np.ndarray,
                               person_bbox: List[float],
                               upper_body: Dict) -> Tuple[bool, Optional[str], float]:
        """
        分析反光衣特征
        
        Returns:
            (是否穿反光衣, 颜色, 反光分数)
        """
        region = upper_body["region"]
        
        # 1. 检测反光衣颜色
        vest_color = self._detect_vest_color(region)
        
        # 2. 检测反光条纹
        reflective_score = self._detect_reflective_stripes(region)
        
        # 3. 综合判断
        has_vest = False
        
        # 如果有明显的反光条纹，认为是反光衣
        if reflective_score > self.reflective_threshold:
            has_vest = True
        # 或者有明显的安全背心颜色 + 一定反光特征
        elif vest_color is not None and reflective_score > 0.1:
            has_vest = True
            
        return has_vest, vest_color, reflective_score
        
    def _detect_vest_color(self, region: np.ndarray) -> Optional[str]:
        """检测反光衣颜色"""
        max_ratio = 0
        detected_color = None
        
        for color_name, (lower, upper) in self.VEST_COLORS.items():
            lower = np.array(lower)
            upper = np.array(upper)
            mask = cv2.inRange(region, lower, upper)
            
            color_ratio = np.sum(mask > 0) / mask.size
            if color_ratio > max_ratio and color_ratio > 0.2:  # 20%阈值
                max_ratio = color_ratio
                detected_color = color_name
                
        return detected_color
        
    def _detect_reflective_stripes(self, region: np.ndarray) -> float:
        """
        检测反光条纹特征
        
        反光条纹特点：
        1. 高亮度
        2. 水平条纹状分布
        3. 与背景对比明显
        """
        if region.size == 0:
            return 0.0
            
        # 转换为灰度图
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        
        # 1. 高亮度区域检测
        _, bright_mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        bright_ratio = np.sum(bright_mask > 0) / bright_mask.size
        
        # 2. 水平条纹检测（使用水平边缘）
        sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        sobel_y = np.abs(sobel_y)
        
        # 水平条纹会有明显的水平梯度
        _, edge_mask = cv2.threshold(sobel_y.astype(np.uint8), 50, 255, cv2.THRESH_BINARY)
        
        # 3. 检测水平线（使用形态学操作）
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (region.shape[1] // 4, 3))
        horizontal_lines = cv2.morphologyEx(edge_mask, cv2.MORPH_OPEN, kernel)
        
        # 计算水平线占比
        line_ratio = np.sum(horizontal_lines > 0) / horizontal_lines.size
        
        # 综合评分
        # 高亮度 + 水平条纹特征
        score = bright_ratio * 0.4 + line_ratio * 0.6
        
        return min(score, 1.0)
        
    def _calculate_brightness(self, region: np.ndarray) -> float:
        """计算区域平均亮度"""
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        return np.mean(gray) / 255.0
        
    def draw_results(self, 
                     frame: np.ndarray, 
                     detections: List[VestDetection]) -> np.ndarray:
        """绘制检测结果"""
        result = frame.copy()
        
        for det in detections:
            x1, y1, x2, y2 = map(int, det.bbox)
            
            # 根据是否穿反光衣选择颜色
            if det.has_vest:
                color = (0, 255, 0)  # 绿色
                status = f"Vest"
                if det.vest_color:
                    status += f"({det.vest_color})"
            else:
                color = (0, 0, 255)  # 红色
                status = "NO Vest!"
                
            # 绘制边界框
            cv2.rectangle(result, (x1, y1), (x2, y2), color, 2)
            
            # 绘制标签
            label = f"{status} {det.confidence:.2f}"
            if det.has_vest:
                label += f" R:{det.reflective_score:.2f}"
                
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
            cv2.rectangle(result, (x1, y1 - label_size[1] - 8), 
                         (x1 + label_size[0], y1), color, -1)
            cv2.putText(result, label, (x1, y1 - 4), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                       
            # 绘制人体框（虚线效果）
            if det.person_bbox:
                px1, py1, px2, py2 = map(int, det.person_bbox)
                # 绘制虚线框
                self._draw_dashed_rect(result, (px1, py1), (px2, py2), color, 1)
                
        # 添加统计信息
        total = len(detections)
        with_vest = sum(1 for d in detections if d.has_vest)
        without_vest = total - with_vest
        
        stats_text = f"Total: {total} | With Vest: {with_vest} | Without: {without_vest}"
        cv2.putText(result, stats_text, (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                   
        return result
        
    def _draw_dashed_rect(self, img, pt1, pt2, color, thickness=1, dash_length=10):
        """绘制虚线矩形"""
        x1, y1 = pt1
        x2, y2 = pt2
        
        # 上边
        for x in range(x1, x2, dash_length * 2):
            cv2.line(img, (x, y1), (min(x + dash_length, x2), y1), color, thickness)
        # 下边
        for x in range(x1, x2, dash_length * 2):
            cv2.line(img, (x, y2), (min(x + dash_length, x2), y2), color, thickness)
        # 左边
        for y in range(y1, y2, dash_length * 2):
            cv2.line(img, (x1, y), (x1, min(y + dash_length, y2)), color, thickness)
        # 右边
        for y in range(y1, y2, dash_length * 2):
            cv2.line(img, (x2, y), (x2, min(y + dash_length, y2)), color, thickness)
            
    def get_summary(self, detections: List[VestDetection]) -> Dict:
        """获取检测摘要"""
        total = len(detections)
        with_vest = sum(1 for d in detections if d.has_vest)
        without_vest = total - with_vest
        
        color_stats = {}
        for d in detections:
            if d.has_vest and d.vest_color:
                color_stats[d.vest_color] = color_stats.get(d.vest_color, 0) + 1
                
        avg_reflective = np.mean([d.reflective_score for d in detections]) if detections else 0
        
        return {
            "total_persons": total,
            "with_vest": with_vest,
            "without_vest": without_vest,
            "compliance_rate": with_vest / total if total > 0 else 0,
            "vest_colors": color_stats,
            "avg_reflective_score": float(avg_reflective)
        }


# ==================== 测试 ====================

def test():
    """测试反光衣检测"""
    detector = ReflectiveVestDetector(
        model_path="../yolov8n.pt",
        conf_threshold=0.5
    )
    
    cap = cv2.VideoCapture(0)
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        detections = detector.detect(frame)
        result = detector.draw_results(frame, detections)
        
        # 打印统计
        if cv2.waitKey(1) & 0xFF == ord('s'):
            print(detector.get_summary(detections))
            
        cv2.imshow("Reflective Vest Detection", result)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
            
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    test()
