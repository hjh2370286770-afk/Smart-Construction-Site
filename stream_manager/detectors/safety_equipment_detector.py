#!/usr/bin/env python3
"""
安全帽+反光衣整合检测模块 - 统一的人员安全装备检测
同时检测安全帽和反光衣，输出完整的安全合规报告
"""

import cv2
import numpy as np
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from pathlib import Path

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

logger = logging.getLogger(__name__)


@dataclass
class PersonSafety:
    """人员安全装备检测结果"""
    track_id: int
    person_bbox: List[float]       # [x1, y1, x2, y2]
    confidence: float
    
    # 安全帽检测
    has_helmet: bool = False
    helmet_bbox: Optional[List[float]] = None
    helmet_color: Optional[str] = None
    helmet_confidence: float = 0.0
    
    # 反光衣检测
    has_vest: bool = False
    vest_bbox: Optional[List[float]] = None
    vest_color: Optional[str] = None
    vest_confidence: float = 0.0
    reflective_score: float = 0.0
    
    # 综合状态
    @property
    def is_compliant(self) -> bool:
        """是否完全合规（戴安全帽且穿反光衣）"""
        return self.has_helmet and self.has_vest
    
    @property
    def violation_type(self) -> Optional[str]:
        """违规类型"""
        if not self.has_helmet and not self.has_vest:
            return "no_helmet_no_vest"
        elif not self.has_helmet:
            return "no_helmet"
        elif not self.has_vest:
            return "no_vest"
        return None


class SafetyEquipmentDetector:
    """
    安全装备检测器（安全帽 + 反光衣）
    
    功能：
    1. 人员检测和跟踪
    2. 同时检测安全帽和反光衣
    3. 人员与安全装备关联
    4. 输出完整合规报告
    """
    
    # 颜色定义
    HELMET_COLORS = {
        "red": ([0, 0, 100], [80, 80, 255]),
        "yellow": ([0, 150, 150], [100, 255, 255]),
        "blue": ([100, 50, 0], [255, 150, 100]),
        "white": ([180, 180, 180], [255, 255, 255]),
    }
    
    VEST_COLORS = {
        "orange": ([0, 80, 160], [80, 160, 255]),
        "yellow": ([0, 180, 180], [100, 255, 255]),
        "red": ([0, 0, 160], [80, 80, 255]),
    }
    
    REFLECTIVE_RANGE = ([200, 200, 200], [255, 255, 255])
    
    def __init__(self, 
                 model_path: str = "yolov8n.pt",
                 conf_threshold: float = 0.5,
                 use_custom_model: bool = False,
                 track_max_age: int = 30):
        """
        初始化检测器
        
        Args:
            model_path: YOLO模型路径（通用或专用）
            conf_threshold: 置信度阈值
            use_custom_model: 是否使用专用模型
            track_max_age: 跟踪最大丢失帧数
        """
        self.conf_threshold = conf_threshold
        self.use_custom_model = use_custom_model
        self.track_max_age = track_max_age
        
        if YOLO is None:
            raise ImportError("ultralytics is required")
            
        self.model = YOLO(model_path)
        self.class_names = self.model.names
        
        # 跟踪状态
        self.next_track_id = 1
        self.tracks: Dict[int, Dict] = {}
        
        logger.info(f"SafetyEquipmentDetector initialized with {model_path}")
        
    def detect(self, frame: np.ndarray, timestamp: float = None) -> List[PersonSafety]:
        """
        检测人员安全装备
        
        Args:
            frame: 输入图像
            timestamp: 时间戳（用于跟踪）
            
        Returns:
            人员安全装备检测结果列表
        """
        # 1. 目标检测
        results = self.model(frame, conf=self.conf_threshold, verbose=False)[0]
        
        # 2. 解析检测结果
        persons = []
        helmets = []
        heads = []
        vests = []
        
        for box in results.boxes:
            cls_id = int(box.cls)
            cls_name = self.class_names[cls_id].lower()
            conf = float(box.conf)
            bbox = box.xyxy[0].tolist()
            
            if self.use_custom_model:
                # 专用模型类别映射
                if cls_name in ["person", "worker"]:
                    persons.append({"bbox": bbox, "conf": conf, "cls": cls_name})
                elif cls_name in ["helmet", "safety_helmet"]:
                    helmets.append({"bbox": bbox, "conf": conf, "color": None})
                elif cls_name in ["no_helmet", "head"]:
                    heads.append({"bbox": bbox, "conf": conf})
                elif cls_name in ["vest", "safety_vest", "reflective_vest"]:
                    vests.append({"bbox": bbox, "conf": conf, "color": None})
                elif cls_name in ["no_vest"]:
                    pass  # 记录未穿背心区域
            else:
                # 通用模型
                if "person" in cls_name:
                    persons.append({"bbox": bbox, "conf": conf, "cls": cls_name})
                elif "head" in cls_name or "face" in cls_name:
                    heads.append({"bbox": bbox, "conf": conf})
                    
        # 3. 如果没有专用模型，使用颜色分析检测安全帽和反光衣
        if not self.use_custom_model:
            helmets, vests = self._analyze_safety_equipment(frame, persons)
            
        # 4. 人员跟踪和装备关联
        person_safety_list = self._associate_and_track(
            frame, persons, helmets, heads, vests, timestamp
        )
        
        return person_safety_list
        
    def _analyze_safety_equipment(self, 
                                   frame: np.ndarray, 
                                   persons: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        分析安全装备（颜色分析方式）
        
        Returns:
            (安全帽列表, 反光衣列表)
        """
        helmets = []
        vests = []
        
        for person in persons:
            p_bbox = person["bbox"]
            
            # 分析头部区域（安全帽）
            head_region = self._extract_head_region(frame, p_bbox)
            if head_region is not None:
                has_helmet, color = self._detect_helmet_in_region(head_region)
                if has_helmet:
                    helmets.append({
                        "bbox": head_region["bbox"],
                        "conf": 0.7,
                        "color": color
                    })
                    
            # 分析躯干区域（反光衣）
            torso_region = self._extract_torso_region(frame, p_bbox)
            if torso_region is not None:
                has_vest, color, reflective = self._detect_vest_in_region(torso_region)
                if has_vest:
                    vests.append({
                        "bbox": torso_region["bbox"],
                        "conf": 0.7,
                        "color": color,
                        "reflective_score": reflective
                    })
                    
        return helmets, vests
        
    def _extract_head_region(self, frame: np.ndarray, person_bbox: List[float]) -> Optional[Dict]:
        """提取头部区域"""
        x1, y1, x2, y2 = map(int, person_bbox)
        h, w = y2 - y1, x2 - x1
        
        # 头部约占人体上部20%
        head_h = int(h * 0.25)
        margin = int(w * 0.2)
        
        hx1 = max(0, x1 + margin)
        hy1 = max(0, y1)
        hx2 = min(frame.shape[1], x2 - margin)
        hy2 = min(frame.shape[0], y1 + head_h)
        
        if hx2 <= hx1 or hy2 <= hy1:
            return None
            
        return {
            "bbox": [hx1, hy1, hx2, hy2],
            "region": frame[hy1:hy2, hx1:hx2]
        }
        
    def _extract_torso_region(self, frame: np.ndarray, person_bbox: List[float]) -> Optional[Dict]:
        """提取躯干区域"""
        x1, y1, x2, y2 = map(int, person_bbox)
        h, w = y2 - y1, x2 - x1
        
        # 躯干约占人体中部35%
        torso_y1 = int(y1 + h * 0.2)
        torso_y2 = int(y1 + h * 0.55)
        margin = int(w * 0.15)
        
        tx1 = max(0, x1 + margin)
        ty1 = max(0, torso_y1)
        tx2 = min(frame.shape[1], x2 - margin)
        ty2 = min(frame.shape[0], torso_y2)
        
        if tx2 <= tx1 or ty2 <= ty1:
            return None
            
        return {
            "bbox": [tx1, ty1, tx2, ty2],
            "region": frame[ty1:ty2, tx1:tx2]
        }
        
    def _detect_helmet_in_region(self, region_dict: Dict) -> Tuple[bool, Optional[str]]:
        """检测区域内的安全帽"""
        region = region_dict["region"]
        
        for color_name, (lower, upper) in self.HELMET_COLORS.items():
            lower = np.array(lower)
            upper = np.array(upper)
            mask = cv2.inRange(region, lower, upper)
            
            color_ratio = np.sum(mask > 0) / mask.size
            if color_ratio > 0.15:
                return True, color_name
                
        return False, None
        
    def _detect_vest_in_region(self, region_dict: Dict) -> Tuple[bool, Optional[str], float]:
        """检测区域内的反光衣"""
        region = region_dict["region"]
        
        # 检测颜色
        vest_color = None
        max_ratio = 0
        
        for color_name, (lower, upper) in self.VEST_COLORS.items():
            lower = np.array(lower)
            upper = np.array(upper)
            mask = cv2.inRange(region, lower, upper)
            
            color_ratio = np.sum(mask > 0) / mask.size
            if color_ratio > max_ratio and color_ratio > 0.2:
                max_ratio = color_ratio
                vest_color = color_name
                
        # 检测反光特征
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        _, bright_mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        reflective_score = np.sum(bright_mask > 0) / bright_mask.size
        
        has_vest = vest_color is not None and reflective_score > 0.1
        
        return has_vest, vest_color, reflective_score
        
    def _associate_and_track(self,
                             frame: np.ndarray,
                             persons: List[Dict],
                             helmets: List[Dict],
                             heads: List[Dict],
                             vests: List[Dict],
                             timestamp: float) -> List[PersonSafety]:
        """关联人员和安全装备，并更新跟踪"""
        person_safety_list = []
        
        for person in persons:
            p_bbox = person["bbox"]
            p_center = self._get_center(p_bbox)
            
            # 查找最佳匹配的跟踪ID
            track_id = self._find_best_track(p_center)
            
            if track_id is None:
                track_id = self.next_track_id
                self.next_track_id += 1
                
            # 更新跟踪
            self.tracks[track_id] = {
                "center": p_center,
                "bbox": p_bbox,
                "last_seen": timestamp or 0
            }
            
            # 创建安全装备对象
            ps = PersonSafety(
                track_id=track_id,
                person_bbox=p_bbox,
                confidence=person["conf"]
            )
            
            # 关联安全帽
            best_helmet = self._find_best_match(p_bbox, helmets, iou_threshold=0.3)
            if best_helmet:
                ps.has_helmet = True
                ps.helmet_bbox = best_helmet["bbox"]
                ps.helmet_color = best_helmet.get("color")
                ps.helmet_confidence = best_helmet["conf"]
            else:
                # 检查是否是裸头
                best_head = self._find_best_match(p_bbox, heads, iou_threshold=0.3)
                if best_head:
                    ps.has_helmet = False
                    
            # 关联反光衣
            best_vest = self._find_best_match(p_bbox, vests, iou_threshold=0.3)
            if best_vest:
                ps.has_vest = True
                ps.vest_bbox = best_vest["bbox"]
                ps.vest_color = best_vest.get("color")
                ps.vest_confidence = best_vest["conf"]
                ps.reflective_score = best_vest.get("reflective_score", 0)
                
            person_safety_list.append(ps)
            
        # 清理过期跟踪
        self._clean_tracks(timestamp)
        
        return person_safety_list
        
    def _find_best_track(self, center: Tuple[float, float]) -> Optional[int]:
        """找到最佳匹配的跟踪ID"""
        best_id = None
        best_dist = float('inf')
        
        for track_id, track in self.tracks.items():
            dist = np.sqrt(
                (center[0] - track["center"][0])**2 + 
                (center[1] - track["center"][1])**2
            )
            if dist < best_dist and dist < 100:  # 100像素阈值
                best_dist = dist
                best_id = track_id
                
        return best_id
        
    def _find_best_match(self, 
                         person_bbox: List[float], 
                         items: List[Dict],
                         iou_threshold: float = 0.3) -> Optional[Dict]:
        """找到最佳匹配的装备"""
        best_match = None
        best_iou = iou_threshold
        
        for item in items:
            iou = self._iou(person_bbox, item["bbox"])
            if iou > best_iou:
                best_iou = iou
                best_match = item
                
        return best_match
        
    def _clean_tracks(self, timestamp: Optional[float]):
        """清理过期跟踪"""
        if timestamp is None:
            return
            
        expired = []
        for track_id, track in self.tracks.items():
            if timestamp - track["last_seen"] > self.track_max_age:
                expired.append(track_id)
                
        for track_id in expired:
            del self.tracks[track_id]
            
    def _get_center(self, bbox: List[float]) -> Tuple[float, float]:
        """计算边界框中心"""
        return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
        
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
                     detections: List[PersonSafety]) -> np.ndarray:
        """绘制检测结果"""
        result = frame.copy()
        
        for det in detections:
            x1, y1, x2, y2 = map(int, det.person_bbox)
            
            # 根据合规状态选择颜色
            if det.is_compliant:
                color = (0, 255, 0)  # 绿色 - 完全合规
                status = "OK"
            elif det.violation_type == "no_helmet_no_vest":
                color = (0, 0, 255)  # 红色 - 严重违规
                status = "NO Helmet+Vest!"
            elif det.violation_type == "no_helmet":
                color = (0, 100, 255)  # 橙色 - 未戴安全帽
                status = "NO Helmet!"
            elif det.violation_type == "no_vest":
                color = (0, 255, 255)  # 黄色 - 未穿反光衣
                status = "NO Vest!"
            else:
                color = (128, 128, 128)
                status = "Unknown"
                
            # 绘制人体框
            cv2.rectangle(result, (x1, y1), (x2, y2), color, 2)
            
            # 绘制标签
            label = f"ID:{det.track_id} {status}"
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
            cv2.rectangle(result, (x1, y1 - label_size[1] - 4),
                         (x1 + label_size[0], y1), color, -1)
            cv2.putText(result, label, (x1, y1 - 4),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                       
            # 绘制安全帽区域（小框）
            if det.helmet_bbox:
                hx1, hy1, hx2, hy2 = map(int, det.helmet_bbox)
                helmet_color = (0, 255, 0) if det.has_helmet else (0, 0, 255)
                cv2.rectangle(result, (hx1, hy1), (hx2, hy2), helmet_color, 1)
                if det.helmet_color:
                    cv2.putText(result, f"H:{det.helmet_color}", (hx1, hy1 - 2),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, helmet_color, 1)
                               
            # 绘制反光衣区域（小框）
            if det.vest_bbox:
                vx1, vy1, vx2, vy2 = map(int, det.vest_bbox)
                vest_color = (0, 255, 0) if det.has_vest else (0, 0, 255)
                cv2.rectangle(result, (vx1, vy1), (vx2, vy2), vest_color, 1)
                if det.vest_color:
                    cv2.putText(result, f"V:{det.vest_color}", (vx1, vy2 + 10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.4, vest_color, 1)
                               
        # 绘制统计面板
        self._draw_stats_panel(result, detections)
        
        return result
        
    def _draw_stats_panel(self, frame: np.ndarray, detections: List[PersonSafety]):
        """绘制统计面板"""
        h, w = frame.shape[:2]
        panel_w = 300
        panel_h = 180
        x = w - panel_w - 10
        y = 10
        
        # 背景
        overlay = frame.copy()
        cv2.rectangle(overlay, (x, y), (x + panel_w, y + panel_h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        # 统计
        total = len(detections)
        compliant = sum(1 for d in detections if d.is_compliant)
        no_helmet = sum(1 for d in detections if not d.has_helmet)
        no_vest = sum(1 for d in detections if not d.has_vest)
        both_missing = sum(1 for d in detections if not d.has_helmet and not d.has_vest)
        
        # 标题
        cv2.putText(frame, "Safety Check", (x + 10, y + 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                   
        # 统计信息
        compliance_pct = compliant/total*100 if total > 0 else 0
        lines = [
            f"Total: {total}",
            f"Compliant: {compliant} ({compliance_pct:.0f}%)",
            f"No Helmet: {no_helmet}",
            f"No Vest: {no_vest}",
            f"Both Missing: {both_missing}"
        ]
        
        y_offset = y + 50
        for line in lines:
            cv2.putText(frame, line, (x + 10, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            y_offset += 22
            
    def get_summary(self, detections: List[PersonSafety]) -> Dict:
        """获取检测摘要"""
        total = len(detections)
        if total == 0:
            return {
                "total_persons": 0,
                "compliant": 0,
                "compliance_rate": 0,
                "violations": {}
            }
            
        compliant = sum(1 for d in detections if d.is_compliant)
        
        violations = {
            "no_helmet": sum(1 for d in detections if not d.has_helmet and d.has_vest),
            "no_vest": sum(1 for d in detections if d.has_helmet and not d.has_vest),
            "no_helmet_no_vest": sum(1 for d in detections if not d.has_helmet and not d.has_vest)
        }
        
        helmet_colors = {}
        vest_colors = {}
        for d in detections:
            if d.has_helmet and d.helmet_color:
                helmet_colors[d.helmet_color] = helmet_colors.get(d.helmet_color, 0) + 1
            if d.has_vest and d.vest_color:
                vest_colors[d.vest_color] = vest_colors.get(d.vest_color, 0) + 1
                
        return {
            "total_persons": total,
            "compliant": compliant,
            "compliance_rate": compliant / total,
            "violations": violations,
            "helmet_colors": helmet_colors,
            "vest_colors": vest_colors
        }


# ==================== 测试 ====================

def test():
    """测试安全装备检测"""
    import time
    
    detector = SafetyEquipmentDetector(
        model_path="../yolov8n.pt",
        conf_threshold=0.5
    )
    
    cap = cv2.VideoCapture(0)
    
    print("按键说明：")
    print("  q - 退出")
    print("  s - 打印统计")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        timestamp = time.time()
        detections = detector.detect(frame, timestamp)
        result = detector.draw_results(frame, detections)
        
        cv2.imshow("Safety Equipment Detection", result)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            summary = detector.get_summary(detections)
            print("\n" + "="*50)
            print("Detection Summary:")
            print(f"  Total persons: {summary['total_persons']}")
            print(f"  Compliant: {summary['compliant']}")
            print(f"  Compliance rate: {summary['compliance_rate']:.1%}")
            print(f"  Violations: {summary['violations']}")
            print("="*50 + "\n")
            
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    test()
