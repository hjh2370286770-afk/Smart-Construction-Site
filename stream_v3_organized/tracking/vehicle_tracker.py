"""
车辆检测框跟踪器
基于IOU的简单跟踪，为每个检测到的车辆分配跟踪ID
不依赖车牌识别，只基于检测框位置
"""

import time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
import numpy as np


@dataclass
class TrackedObject:
    """跟踪对象"""
    track_id: int
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    class_name: str
    confidence: float
    frame_idx: int
    last_seen: float  # 时间戳
    miss_count: int = 0  # 连续未检测到的帧数
    
    # 车牌关联信息
    plate_text: Optional[str] = None
    plate_confidence: float = 0.0
    
    # 位置历史（用于出场检测）
    position_history: List[Tuple[float, float, float]] = field(default_factory=list)  # (cx, cy, timestamp)
    
    # 出场状态
    exit_detected: bool = False
    exit_time: Optional[float] = None
    
    def get_center(self) -> Tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2, (y1 + y2) / 2)
    
    def update(self, bbox: Tuple[int, int, int, int], frame_idx: int, 
               confidence: float, timestamp: float):
        """更新跟踪对象"""
        self.bbox = bbox
        self.frame_idx = frame_idx
        self.confidence = confidence
        self.last_seen = timestamp
        self.miss_count = 0
        
        center = self.get_center()
        self.position_history.append((center[0], center[1], timestamp))
        # 只保留最近100个位置
        if len(self.position_history) > 100:
            self.position_history = self.position_history[-50:]
    
    def mark_missed(self):
        """标记该帧未检测到"""
        self.miss_count += 1


class VehicleTracker:
    """
    车辆检测框跟踪器
    
    核心功能：
    1. 为每个检测到的车辆分配唯一跟踪ID
    2. 基于IOU进行帧间匹配
    3. 检测车辆出场（从左侧或下方离开画面）
    4. 车牌关联（将识别到的车牌绑定到跟踪ID）
    """
    
    def __init__(self, 
                 iou_threshold: float = 0.3,
                 max_miss_frames: int = 5,
                 exit_left_threshold: float = 0.05,
                 exit_wait_time: float = 3.0,
                 exit_direction: str = 'left'):
        """
        Args:
            iou_threshold: IOU匹配阈值
            max_miss_frames: 最大允许连续未检测到的帧数
            exit_left_threshold: 出场阈值（画面宽度/高度的比例，根据 exit_direction）
            exit_wait_time: 出场确认等待时间（秒）
            exit_direction: 出场方向 ('left' 或 'bottom')
        """
        self.iou_threshold = iou_threshold
        self.max_miss_frames = max_miss_frames
        self.exit_left_threshold = exit_left_threshold
        self.exit_wait_time = exit_wait_time
        self.exit_direction = exit_direction.lower() if exit_direction else 'left'
        
        # 活跃跟踪
        self.active_tracks: Dict[int, TrackedObject] = {}
        
        # 已出场的跟踪（保留一段时间用于二次进场检测）
        self.exited_tracks: Dict[int, TrackedObject] = {}
        self.last_detection_map: Dict[int, int] = {}
        
        # ID计数器
        self.next_track_id = 1
        
        # 统计
        self.stats = {
            'total_tracks': 0,
            'active_count': 0,
            'exited_count': 0,
        }
    
    def update(self, detections: List, frame_idx: int, 
               frame_shape: Tuple[int, int]) -> List[TrackedObject]:
        """
        更新跟踪器
        
        Args:
            detections: 当前帧的检测结果列表
            frame_idx: 帧索引
            frame_shape: 画面尺寸 (height, width)
            
        Returns:
            当前活跃的跟踪对象列表
        """
        timestamp = time.time()
        frame_height, frame_width = frame_shape[:2]
        
        # 1. 计算所有活跃跟踪与当前检测的IOU
        matched_tracks = set()
        matched_detections = set()
        self.last_detection_map = {}
        
        if detections and self.active_tracks:
            # 构建IOU矩阵
            track_ids = list(self.active_tracks.keys())
            iou_matrix = np.zeros((len(track_ids), len(detections)))
            
            for i, track_id in enumerate(track_ids):
                track = self.active_tracks[track_id]
                for j, det in enumerate(detections):
                    iou_matrix[i, j] = self._compute_iou(track.bbox, det.bbox)
            
            # 贪心匹配：每次选择IOU最大的配对
            while True:
                if iou_matrix.size == 0:
                    break
                
                max_iou = np.max(iou_matrix)
                if max_iou < self.iou_threshold:
                    break
                
                max_idx = np.unravel_index(np.argmax(iou_matrix), iou_matrix.shape)
                track_idx, det_idx = max_idx
                
                # 匹配成功
                track_id = track_ids[track_idx]
                det = detections[det_idx]
                
                self.active_tracks[track_id].update(
                    det.bbox, frame_idx, det.confidence, timestamp
                )
                
                matched_tracks.add(track_id)
                matched_detections.add(det_idx)
                self.last_detection_map[det_idx] = track_id
                
                # 将已匹配的行和列置为-1
                iou_matrix[track_idx, :] = -1
                iou_matrix[:, det_idx] = -1
        
        # 2. 未匹配的跟踪标记为missed
        for track_id in self.active_tracks:
            if track_id not in matched_tracks:
                self.active_tracks[track_id].mark_missed()
        
        # 3. 未匹配的检测创建新跟踪
        for i, det in enumerate(detections):
            if i not in matched_detections:
                # 检查bbox格式
                bbox = det.bbox if hasattr(det, 'bbox') else (0, 0, 0, 0)
                if not isinstance(bbox, (tuple, list)) or len(bbox) != 4:
                    continue
                    
                track = TrackedObject(
                    track_id=self.next_track_id,
                    bbox=tuple(bbox),
                    class_name=det.class_name if hasattr(det, 'class_name') else 'vehicle',
                    confidence=det.confidence if hasattr(det, 'confidence') else 0.0,
                    frame_idx=frame_idx,
                    last_seen=timestamp,
                    position_history=[((bbox[0] + bbox[2]) / 2, 
                                      (bbox[1] + bbox[3]) / 2, timestamp)]
                )
                self.active_tracks[self.next_track_id] = track
                self.last_detection_map[i] = self.next_track_id
                self.next_track_id += 1
                self.stats['total_tracks'] += 1
        
        # 4. 检查出场（从左侧或下方离开）
        self._check_exits(frame_width, timestamp, frame_height)
        
        # 5. 清理长时间未检测到的跟踪
        self._cleanup_tracks()
        
        # 更新统计
        self.stats['active_count'] = len(self.active_tracks)
        self.stats['exited_count'] = len(self.exited_tracks)
        
        return list(self.active_tracks.values())
    
    def associate_plate(self, track_id: int, plate_text: str, 
                        plate_confidence: float = 1.0) -> bool:
        """
        将车牌关联到跟踪对象
        
        Returns:
            是否关联成功
        """
        if track_id in self.active_tracks:
            track = self.active_tracks[track_id]
            # 只更新置信度更高的车牌
            if plate_confidence >= track.plate_confidence:
                track.plate_text = plate_text
                track.plate_confidence = plate_confidence
                return True
        return False
    
    def get_track_by_plate(self, plate_text: str) -> Optional[TrackedObject]:
        """根据车牌查找跟踪对象"""
        for track in self.active_tracks.values():
            if track.plate_text == plate_text:
                return track
        return None
    
    def _check_exits(self, frame_width: int, timestamp: float, frame_height: int = None):
        """检查是否有车辆从指定方向出场"""
        tracks_to_exit = []
        if frame_height is None:
            frame_height = frame_width  # 兼容旧调用
        
        for track_id, track in self.active_tracks.items():
            if track.exit_detected:
                continue
            
            x1, y1, x2, y2 = track.bbox
            
            if self.exit_direction == 'bottom':
                # 从画面下方出场
                bottom_threshold = frame_height * (1 - self.exit_left_threshold)
                
                # 条件1：检测框完全在下方阈值内
                is_fully_bottom = y1 > bottom_threshold
                
                # 条件2：车辆大部分在下方
                is_mostly_bottom = y2 > bottom_threshold and y1 > bottom_threshold - frame_height * self.exit_left_threshold * 2
                
                # 条件3：或者车辆正在向下移动且接近边缘
                is_moving_bottom = False
                if len(track.position_history) >= 3:
                    recent = track.position_history[-3:]
                    y_positions = [p[1] for p in recent]
                    if y_positions[-1] > y_positions[0]:  # 向下移动
                        is_moving_bottom = True
                
                should_exit = is_fully_bottom or is_mostly_bottom or (is_moving_bottom and y2 > bottom_threshold - frame_height * self.exit_left_threshold)
            else:
                # 默认：从画面左侧出场
                left_threshold = frame_width * self.exit_left_threshold
                
                # 条件1：检测框完全在左侧阈值内
                is_fully_left = x2 < left_threshold
                
                # 条件2：车辆大部分在左侧（左边界已过阈值线）
                is_mostly_left = x1 < left_threshold and x2 < left_threshold * 3
                
                # 条件3：或者车辆正在向左移动且接近边缘
                is_moving_left = False
                if len(track.position_history) >= 3:
                    recent = track.position_history[-3:]
                    # 计算x方向移动趋势
                    x_positions = [p[0] for p in recent]
                    if x_positions[-1] < x_positions[0]:  # 向左移动
                        is_moving_left = True
                
                should_exit = is_fully_left or is_mostly_left or (is_moving_left and x1 < left_threshold * 2)
            
            if should_exit:
                track.exit_detected = True
                track.exit_time = timestamp
                tracks_to_exit.append(track_id)
        
        # 将标记出场的跟踪移到exited_tracks
        for track_id in tracks_to_exit:
            track = self.active_tracks.pop(track_id)
            self.exited_tracks[track_id] = track
    
    def _cleanup_tracks(self):
        """清理长时间未检测到的跟踪"""
        current_time = time.time()
        expired_ids = []
        
        for track_id, track in self.active_tracks.items():
            # 如果连续未检测到超过阈值，且不在左侧，则删除
            if track.miss_count > self.max_miss_frames:
                # 检查最后位置是否在左侧（可能是出场）
                x1, y1, x2, y2 = track.bbox
                # 如果最后位置在左侧，标记为出场
                expired_ids.append(track_id)
        
        for track_id in expired_ids:
            if track_id in self.active_tracks:
                del self.active_tracks[track_id]
        
        # 清理过久的出场记录
        old_exit_ids = []
        for track_id, track in self.exited_tracks.items():
            if track.exit_time and (current_time - track.exit_time) > 300:  # 5分钟后清理
                old_exit_ids.append(track_id)
        
        for track_id in old_exit_ids:
            del self.exited_tracks[track_id]
    
    def _compute_iou(self, bbox1: Tuple[int, int, int, int], 
                     bbox2: Tuple[int, int, int, int]) -> float:
        """计算两个bbox的IOU"""
        x1_1, y1_1, x2_1, y2_1 = bbox1
        x1_2, y1_2, x2_2, y2_2 = bbox2
        
        # 计算交集
        xi1 = max(x1_1, x1_2)
        yi1 = max(y1_1, y1_2)
        xi2 = min(x2_1, x2_2)
        yi2 = min(y2_1, y2_2)
        
        if xi2 <= xi1 or yi2 <= yi1:
            return 0.0
        
        intersection = (xi2 - xi1) * (yi2 - yi1)
        
        # 计算并集
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        union = area1 + area2 - intersection
        
        if union <= 0:
            return 0.0
        
        return intersection / union
    
    def get_active_tracks(self) -> List[TrackedObject]:
        """获取所有活跃跟踪"""
        return list(self.active_tracks.values())
    
    def get_exited_tracks(self) -> List[TrackedObject]:
        """获取已出场的跟踪"""
        return list(self.exited_tracks.values())

    def get_last_detection_mapping(self) -> Dict[int, int]:
        """获取最近一次 update 的 detection_index -> track_id 映射"""
        return dict(self.last_detection_map)
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        return {
            **self.stats,
            'total_active': len(self.active_tracks),
            'total_exited': len(self.exited_tracks),
        }
