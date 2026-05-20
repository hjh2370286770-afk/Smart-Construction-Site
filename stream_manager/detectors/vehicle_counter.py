#!/usr/bin/env python3
"""
车辆进出检测模块 - 基于YOLOv8和轨迹跟踪的车辆进出统计
支持车辆类型识别、方向判断、进出计数
"""

import cv2
import numpy as np
import logging
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict, deque
from pathlib import Path

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

logger = logging.getLogger(__name__)


@dataclass
class Vehicle:
    """车辆跟踪对象"""
    track_id: int
    vehicle_type: str          # car, truck, bus, motorcycle
    bbox: List[float]
    confidence: float
    center: Tuple[float, float]
    trajectory: deque = field(default_factory=lambda: deque(maxlen=30))
    first_seen: float = 0
    last_seen: float = 0
    entered: bool = False
    exited: bool = False
    direction: Optional[str] = None  # in/out


@dataclass
class CountLine:
    """计数线配置"""
    name: str
    line: Tuple[Tuple[int, int], Tuple[int, int]]  # ((x1,y1), (x2,y2))
    direction_in: str = "in"   # 从哪侧算进入
    direction_out: str = "out"


class VehicleCounter:
    """
    车辆进出计数器
    
    功能：
    1. 车辆检测和类型识别（轿车/卡车/巴士/摩托车）
    2. 车辆跟踪和轨迹分析
    3. 进出方向判断
    4. 跨线计数
    """
    
    VEHICLE_CLASSES = ["car", "truck", "bus", "motorcycle"]
    
    def __init__(self, 
                 model_path: str = "yolov8n.pt",
                 conf_threshold: float = 0.5,
                 track_max_age: int = 30,
                 track_min_hits: int = 3):
        """
        初始化计数器
        
        Args:
            model_path: YOLO模型路径
            conf_threshold: 置信度阈值
            track_max_age: 跟踪最大丢失帧数
            track_min_hits: 最小确认帧数
        """
        self.conf_threshold = conf_threshold
        self.track_max_age = track_max_age
        self.track_min_hits = track_min_hits
        
        if YOLO is None:
            raise ImportError("ultralytics is required")
            
        self.model = YOLO(model_path)
        self.class_names = self.model.names
        
        # 跟踪状态
        self.next_track_id = 1
        self.tracks: Dict[int, Vehicle] = {}
        self.count_lines: List[CountLine] = []
        
        # 计数统计
        self.counts = {
            "in": defaultdict(int),   # 进入计数
            "out": defaultdict(int),  # 出去计数
        }
        self.counted_ids: Set[int] = set()  # 已计数的track_id
        
        logger.info(f"VehicleCounter initialized")
        
    def add_count_line(self, 
                       name: str, 
                       start_point: Tuple[int, int], 
                       end_point: Tuple[int, int],
                       in_direction: str = "bottom"):
        """
        添加计数线
        
        Args:
            name: 线的名称
            start_point: 起点 (x, y)
            end_point: 终点 (x, y)
            in_direction: 哪个方向算进入 (top/bottom/left/right)
        """
        line = CountLine(
            name=name,
            line=(start_point, end_point),
            direction_in=in_direction
        )
        self.count_lines.append(line)
        logger.info(f"Added count line: {name} from {start_point} to {end_point}")
        
    def detect_and_track(self, frame: np.ndarray, timestamp: float) -> List[Vehicle]:
        """
        检测并跟踪车辆
        
        Args:
            frame: 输入图像
            timestamp: 当前时间戳
            
        Returns:
            跟踪的车辆列表
        """
        # 1. 目标检测
        detections = self._detect_vehicles(frame)
        
        # 2. 更新跟踪
        self._update_tracks(detections, timestamp)
        
        # 3. 检查跨线计数
        self._check_line_crossing(timestamp)
        
        # 4. 清理过期跟踪
        self._clean_tracks(timestamp)
        
        return list(self.tracks.values())
        
    def _detect_vehicles(self, frame: np.ndarray) -> List[Dict]:
        """检测车辆"""
        results = self.model(frame, conf=self.conf_threshold, verbose=False)[0]
        
        detections = []
        for box in results.boxes:
            cls_id = int(box.cls)
            cls_name = self.class_names[cls_id].lower()
            
            if cls_name in self.VEHICLE_CLASSES:
                bbox = box.xyxy[0].tolist()
                center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
                
                detections.append({
                    "vehicle_type": cls_name,
                    "bbox": bbox,
                    "confidence": float(box.conf),
                    "center": center
                })
                
        return detections
        
    def _update_tracks(self, detections: List[Dict], timestamp: float):
        """更新跟踪器"""
        # 简单的IOU匹配（实际可用DeepSORT等）
        matched_tracks = set()
        matched_dets = set()
        
        # 计算所有匹配对的IOU
        matches = []
        for track_id, track in self.tracks.items():
            for det_idx, det in enumerate(detections):
                iou = self._iou(track.bbox, det["bbox"])
                if iou > 0.3:  # IOU阈值
                    matches.append((track_id, det_idx, iou))
                    
        # 按IOU排序，优先匹配高IOU
        matches.sort(key=lambda x: x[2], reverse=True)
        
        for track_id, det_idx, iou in matches:
            if track_id in matched_tracks or det_idx in matched_dets:
                continue
                
            # 更新已有跟踪
            det = detections[det_idx]
            track = self.tracks[track_id]
            track.bbox = det["bbox"]
            track.center = det["center"]
            track.confidence = det["confidence"]
            track.trajectory.append(det["center"])
            track.last_seen = timestamp
            
            matched_tracks.add(track_id)
            matched_dets.add(det_idx)
            
        # 未匹配的检测创建新跟踪
        for det_idx, det in enumerate(detections):
            if det_idx not in matched_dets:
                vehicle = Vehicle(
                    track_id=self.next_track_id,
                    vehicle_type=det["vehicle_type"],
                    bbox=det["bbox"],
                    confidence=det["confidence"],
                    center=det["center"],
                    first_seen=timestamp,
                    last_seen=timestamp
                )
                vehicle.trajectory.append(det["center"])
                self.tracks[self.next_track_id] = vehicle
                self.next_track_id += 1
                
    def _check_line_crossing(self, timestamp: float):
        """检查跨线事件"""
        for track_id, track in self.tracks.items():
            if track_id in self.counted_ids:
                continue
                
            if len(track.trajectory) < 5:
                continue
                
            # 获取轨迹的前点和后点
            prev_center = list(track.trajectory)[-5]
            curr_center = track.center
            
            for line in self.count_lines:
                # 检查是否跨越线段
                crossed, direction = self._check_cross_line(
                    prev_center, curr_center, line.line
                )
                
                if crossed and direction:
                    # 确定进出方向
                    if direction == line.direction_in:
                        track.direction = "in"
                        self.counts["in"][track.vehicle_type] += 1
                    else:
                        track.direction = "out"
                        self.counts["out"][track.vehicle_type] += 1
                        
                    track.entered = track.direction == "in"
                    track.exited = track.direction == "out"
                    self.counted_ids.add(track_id)
                    
                    logger.info(f"Vehicle {track_id} ({track.vehicle_type}) {track.direction}")
                    break
                    
    def _check_cross_line(self, 
                          prev_point: Tuple[float, float],
                          curr_point: Tuple[float, float],
                          line: Tuple[Tuple[int, int], Tuple[int, int]]) -> Tuple[bool, Optional[str]]:
        """
        检查线段是否被跨越
        
        Returns:
            (是否跨越, 方向)
        """
        # 使用叉积判断线段相交
        x1, y1 = prev_point
        x2, y2 = curr_point
        x3, y3 = line[0]
        x4, y4 = line[1]
        
        # 计算方向
        def direction(ax, ay, bx, by, cx, cy):
            return (cx - ax) * (by - ay) - (cy - ay) * (bx - ax)
            
        d1 = direction(x3, y3, x4, y4, x1, y1)
        d2 = direction(x3, y3, x4, y4, x2, y2)
        d3 = direction(x1, y1, x2, y2, x3, y3)
        d4 = direction(x1, y1, x2, y2, x4, y4)
        
        # 检查是否相交
        if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
           ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
            # 确定方向（基于运动方向）
            dy = y2 - y1
            dx = x2 - x1
            
            # 根据线段方向判断
            line_dy = y4 - y3
            line_dx = x4 - x3
            
            if abs(line_dy) > abs(line_dx):  # 垂直线
                direction = "bottom" if dy > 0 else "top"
            else:  # 水平线
                direction = "right" if dx > 0 else "left"
                
            return True, direction
            
        return False, None
        
    def _clean_tracks(self, timestamp: float):
        """清理过期跟踪"""
        expired = []
        for track_id, track in self.tracks.items():
            if timestamp - track.last_seen > self.track_max_age:
                expired.append(track_id)
                
        for track_id in expired:
            del self.tracks[track_id]
            
        # 清理已计数集合（防止无限增长）
        if len(self.counted_ids) > 10000:
            self.counted_ids.clear()
            
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
        
    def draw_results(self, frame: np.ndarray, tracks: List[Vehicle]) -> np.ndarray:
        """绘制结果"""
        result = frame.copy()
        h, w = frame.shape[:2]
        
        # 绘制计数线
        for line in self.count_lines:
            (x1, y1), (x2, y2) = line.line
            cv2.line(result, (x1, y1), (x2, y2), (0, 255, 255), 2)
            # 线名称
            mid_x, mid_y = (x1 + x2) // 2, (y1 + y2) // 2
            cv2.putText(result, line.name, (mid_x, mid_y - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                       
        # 绘制跟踪的车辆
        for track in tracks:
            x1, y1, x2, y2 = map(int, track.bbox)
            
            # 根据方向选择颜色
            if track.direction == "in":
                color = (0, 255, 0)  # 绿色-进入
            elif track.direction == "out":
                color = (0, 0, 255)  # 红色-出去
            else:
                color = (255, 255, 0)  # 青色-未计数
                
            cv2.rectangle(result, (x1, y1), (x2, y2), color, 2)
            
            # 标签
            label = f"ID:{track.track_id} {track.vehicle_type}"
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
            cv2.rectangle(result, (x1, y1 - label_size[1] - 4),
                         (x1 + label_size[0], y1), color, -1)
            cv2.putText(result, label, (x1, y1 - 4),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
                       
            # 绘制轨迹
            points = list(track.trajectory)
            for i in range(1, len(points)):
                pt1 = tuple(map(int, points[i-1]))
                pt2 = tuple(map(int, points[i]))
                cv2.line(result, pt1, pt2, color, 1)
                
        # 绘制统计面板
        self._draw_stats_panel(result)
        
        return result
        
    def _draw_stats_panel(self, frame: np.ndarray):
        """绘制统计面板"""
        h, w = frame.shape[:2]
        panel_w = 250
        panel_h = 150
        x = w - panel_w - 10
        y = 10
        
        # 背景
        overlay = frame.copy()
        cv2.rectangle(overlay, (x, y), (x + panel_w, y + panel_h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        # 标题
        cv2.putText(frame, "Vehicle Count", (x + 10, y + 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                   
        # 进入统计
        y_offset = y + 50
        cv2.putText(frame, "IN:", (x + 10, y_offset),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
        in_total = sum(self.counts["in"].values())
        cv2.putText(frame, str(in_total), (x + 60, y_offset),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
                   
        # 出去统计
        y_offset += 25
        cv2.putText(frame, "OUT:", (x + 10, y_offset),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)
        out_total = sum(self.counts["out"].values())
        cv2.putText(frame, str(out_total), (x + 60, y_offset),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)
                   
        # 各类型统计
        y_offset += 30
        all_types = set(list(self.counts["in"].keys()) + list(self.counts["out"].keys()))
        for vtype in sorted(all_types):
            in_count = self.counts["in"].get(vtype, 0)
            out_count = self.counts["out"].get(vtype, 0)
            text = f"{vtype}: {in_count}/{out_count}"
            cv2.putText(frame, text, (x + 10, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            y_offset += 20
            
    def get_summary(self) -> Dict:
        """获取统计摘要"""
        in_total = sum(self.counts["in"].values())
        out_total = sum(self.counts["out"].values())
        
        return {
            "total_in": in_total,
            "total_out": out_total,
            "current_tracks": len(self.tracks),
            "by_type": {
                "in": dict(self.counts["in"]),
                "out": dict(self.counts["out"])
            }
        }
        
    def reset_counts(self):
        """重置计数"""
        self.counts = {"in": defaultdict(int), "out": defaultdict(int)}
        self.counted_ids.clear()
        logger.info("Vehicle counts reset")


# ==================== 测试 ====================

def test():
    """测试车辆计数"""
    detector = VehicleCounter(
        model_path="../yolov8n.pt",
        conf_threshold=0.5
    )
    
    # 添加计数线（假设摄像头俯视门口）
    # 水平线，从上到下进入
    detector.add_count_line("gate", (100, 300), (540, 300), "bottom")
    
    cap = cv2.VideoCapture(0)
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        timestamp = cv2.getTickCount() / cv2.getTickFrequency()
        tracks = detector.detect_and_track(frame, timestamp)
        result = detector.draw_results(frame, tracks)
        
        # 按r重置计数
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('r'):
            detector.reset_counts()
        elif key == ord('s'):
            print(detector.get_summary())
            
        cv2.imshow("Vehicle Counter", result)
        
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    test()
