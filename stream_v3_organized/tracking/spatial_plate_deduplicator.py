"""
基于位置的车牌智能去重系统
结合车辆空间位置和车牌文本进行精确去重
"""

import time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict
import numpy as np

from plate_utils import PlateValidator, validate_and_filter_plate, plate_similarity
from plate_validator_v2 import PlateValidatorV2, PlateColor
import sys
from pathlib import Path


@dataclass
class VehicleDetection:
    """车辆检测结果"""
    frame_idx: int
    bbox: tuple  # (x1, y1, x2, y2)
    center: tuple  # (cx, cy)
    plate_text: Optional[str]
    plate_bbox: Optional[tuple]
    confidence: float
    timestamp: float
    
    def get_center(self) -> tuple:
        """获取中心点"""
        if self.center:
            return self.center
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2, (y1 + y2) / 2)


@dataclass 
class TrackedVehicle:
    """跟踪的车辆"""
    vehicle_id: int
    plate_candidates: Dict[str, List[VehicleDetection]] = field(default_factory=dict)
    position_history: List[Tuple[float, float, float]] = field(default_factory=list)  # (x, y, timestamp)
    first_seen: float = 0
    last_seen: float = 0
    confirmed_plate: Optional[str] = None
    plate_confidence: float = 0
    detection_count: int = 0


class SpatialPlateDeduplicator:
    """
    基于空间位置的车牌去重器
    
    核心思想：
    1. 使用车辆位置（bbox中心）进行空间聚类
    2. 同一位置的多次检测聚合为同一辆车
    3. 对同一辆车的多个候选车牌进行投票/验证
    4. 只有高置信度且一致的车牌才被确认
    """
    
    def __init__(self, 
                 spatial_threshold: float = 150.0,  # 像素距离阈值
                 time_window: float = 10.0,          # 时间窗口（秒）
                 min_detections: int = 5,            # 最少检测次数
                 min_plate_agreement: float = 0.6,   # 车牌一致性阈值
                 plate_similarity_threshold: float = 0.8):  # 文本相似度阈值
        """
        Args:
            spatial_threshold: 空间距离阈值（像素），小于此值视为同一位置
            time_window: 时间窗口，超过此时间的记录会被清理
            min_detections: 最少需要多少次检测才确认一辆车
            min_plate_agreement: 车牌一致性比例，超过此值才确认车牌
            plate_similarity_threshold: 车牌文本相似度阈值
        """
        self.spatial_threshold = spatial_threshold
        self.time_window = time_window
        self.min_detections = min_detections
        self.min_plate_agreement = min_plate_agreement
        self.plate_similarity_threshold = plate_similarity_threshold
        
        # 当前跟踪的车辆
        self.active_tracks: Dict[int, TrackedVehicle] = {}
        
        # 已确认的车辆（输出结果）
        self.confirmed_vehicles: List[Dict] = []
        
        # ID计数器
        self.next_vehicle_id = 1
        
        # 统计信息
        self.stats = {
            'total_detections': 0,
            'valid_plates': 0,
            'invalid_plates': 0,
            'tracks_created': 0,
            'vehicles_confirmed': 0,
            'plates_merged': 0
        }
    
    def add_detection(self, 
                     frame_idx: int,
                     bbox: tuple,
                     plate_text: Optional[str],
                     plate_bbox: Optional[tuple],
                     confidence: float = 1.0,
                     plate_color: Optional[str] = None,
                     color_conf: float = 0.0) -> Optional[Dict]:
        """
        添加一次检测结果
        
        Args:
            frame_idx: 帧索引
            bbox: 车辆边界框 (x1, y1, x2, y2)
            plate_text: 检测到的车牌文字
            plate_bbox: 车牌边界框
            confidence: 置信度
            
        Returns:
            如果确认了新车牌，返回车辆信息字典；否则返回None
        """
        timestamp = time.time()
        self.stats['total_detections'] += 1
        
        # 计算中心点
        x1, y1, x2, y2 = bbox
        center = ((x1 + x2) / 2, (y1 + y2) / 2)
        
        # 创建检测对象
        detection = VehicleDetection(
            frame_idx=frame_idx,
            bbox=bbox,
            center=center,
            plate_text=plate_text,
            plate_bbox=plate_bbox,
            confidence=confidence,
            timestamp=timestamp
        )
        
        # 验证车牌格式 - 优先使用V2验证器（基于颜色）
        is_valid = False
        cleaned_plate = None
        validation_reason = ""
        if plate_text:
            # 首先尝试V2验证器（更严格，基于颜色）
            v2_result = PlateValidatorV2.validate(plate_text, plate_color, color_conf)
            if v2_result.is_valid and v2_result.cleaned_plate:
                is_valid = True
                cleaned_plate = v2_result.cleaned_plate
                validation_reason = v2_result.reason
            else:
                # V2验证失败，尝试V1作为后备（但更严格）
                is_valid_v1, _, cleaned_v1 = validate_and_filter_plate(plate_text)
                # V1通过后，再用V2的长度规则严格检查
                if is_valid_v1 and cleaned_v1:
                    if len(cleaned_v1) in [7, 8]:
                        is_valid = True
                        cleaned_plate = cleaned_v1
                        validation_reason = "V1 fallback (length ok)"
                    else:
                        is_valid = False
                        validation_reason = f"V1 passed but length {len(cleaned_v1)} invalid"
            
        if is_valid and cleaned_plate:
            self.stats['valid_plates'] += 1
        elif plate_text:
            self.stats['invalid_plates'] += 1
            return None  # 无效车牌直接忽略
        else:
            return None  # 没有车牌
        
        # 尝试匹配到现有跟踪
        matched_track_id = self._find_matching_track(center, cleaned_plate, timestamp)
        
        if matched_track_id is not None:
            # 添加到现有跟踪
            track = self.active_tracks[matched_track_id]
            self._add_to_track(track, detection, cleaned_plate)
        else:
            # 创建新跟踪
            track = self._create_new_track(detection, cleaned_plate)
            self.active_tracks[track.vehicle_id] = track
            self.stats['tracks_created'] += 1
        
        # 清理过期跟踪
        self._cleanup_expired_tracks(timestamp)
        
        # 检查是否可以确认某个跟踪
        confirmed = self._check_and_confirm(track, timestamp)
        
        return confirmed
    
    def _find_matching_track(self, 
                            center: tuple, 
                            plate_text: str,
                            timestamp: float) -> Optional[int]:
        """查找匹配的现有跟踪 - 修复：降低阈值，增加长度容错"""
        best_match_id = None
        best_score = -1
        
        for track_id, track in self.active_tracks.items():
            # 计算空间距离
            if track.position_history:
                last_pos = track.position_history[-1][:2]
                distance = np.sqrt((center[0] - last_pos[0])**2 + 
                                 (center[1] - last_pos[1])**2)
                
                if distance > self.spatial_threshold:
                    continue
                    
                spatial_score = max(0, 1 - distance / self.spatial_threshold)
            else:
                spatial_score = 0.3
            
            # 计算车牌相似度 - 修复：也检查已确认的车牌
            plate_score = 0
            
            # 首先检查已确认的车牌（如果有）
            if track.confirmed_plate:
                similarity = self._calculate_plate_similarity(plate_text, track.confirmed_plate)
                if similarity > plate_score:
                    plate_score = similarity
            
            # 然后检查候选车牌
            if track.plate_candidates:
                for existing_plate in track.plate_candidates.keys():
                    similarity = self._calculate_plate_similarity(plate_text, existing_plate)
                    if similarity > plate_score:
                        plate_score = similarity
            
            # 修复：降低车牌相似度阈值到0.5，增加容错
            if plate_score < 0.5:
                continue
            
            # 修复：降低综合得分阈值到0.5
            combined_score = 0.3 * spatial_score + 0.7 * plate_score
            
            if combined_score > best_score and combined_score > 0.5:
                best_score = combined_score
                best_match_id = track_id
        
        return best_match_id
    
    def _create_new_track(self, 
                         detection: VehicleDetection, 
                         plate_text: str) -> TrackedVehicle:
        """创建新的车辆跟踪"""
        track = TrackedVehicle(
            vehicle_id=self.next_vehicle_id,
            first_seen=detection.timestamp,
            last_seen=detection.timestamp
        )
        self.next_vehicle_id += 1
        
        self._add_to_track(track, detection, plate_text)
        
        return track
    
    def _add_to_track(self, 
                    track: TrackedVehicle, 
                    detection: VehicleDetection,
                    plate_text: str):
        """添加检测到跟踪"""
        # 更新位置历史
        center = detection.get_center()
        track.position_history.append((center[0], center[1], detection.timestamp))
        
        # 只保留最近的位置（限制内存）
        if len(track.position_history) > 100:
            track.position_history = track.position_history[-50:]
        
        # 添加车牌候选
        if plate_text not in track.plate_candidates:
            track.plate_candidates[plate_text] = []
        track.plate_candidates[plate_text].append(detection)
        
        # 更新统计
        track.last_seen = detection.timestamp
        track.detection_count += 1
    
    def _cleanup_expired_tracks(self, current_time: float):
        """清理过期的跟踪"""
        expired_ids = []
        
        for track_id, track in self.active_tracks.items():
            if current_time - track.last_seen > self.time_window * 2:
                # 这个跟踪已经过期太久了
                expired_ids.append(track_id)
            elif (current_time - track.first_seen > self.time_window and 
                  track.detection_count < self.min_detections // 2):
                # 时间够长但检测次数太少，可能是误检
                expired_ids.append(track_id)
        
        for track_id in expired_ids:
            del self.active_tracks[track_id]
    
    def _check_and_confirm(self, 
                          track: TrackedVehicle, 
                          timestamp: float) -> Optional[Dict]:
        """检查是否可以确认这个跟踪 - 修复：已确认车辆保留在active_tracks中"""
        # 检查检测次数是否足够
        if track.detection_count < self.min_detections:
            return None
        
        # 如果已经确认过，不再重复确认，但返回已确认信息用于匹配
        if track.confirmed_plate:
            return {
                'vehicle_id': track.vehicle_id,
                'plate_number': track.confirmed_plate,
                'confidence': track.plate_confidence,
                'detection_count': track.detection_count,
                'first_seen': track.first_seen,
                'last_seen': track.last_seen,
                'avg_position': [0, 0],
                'already_confirmed': True
            }
        
        # 分析车牌候选
        if not track.plate_candidates:
            return None
        
        # 找出最频繁出现的车牌
        plate_counts = [(plate, len(dets)) for plate, dets in track.plate_candidates.items()]
        plate_counts.sort(key=lambda x: x[1], reverse=True)
        
        total_detections_with_plate = sum(count for _, count in plate_counts)
        
        if total_detections_with_plate == 0:
            return None
        
        best_plate, best_count = plate_counts[0]
        agreement_ratio = best_count / total_detections_with_plate
        
        # === 修复：优先选择格式正确的车牌 ===
        # 检查所有候选中是否有格式更正确的车牌（7位或8位）
        valid_length_candidates = [(p, c) for p, c in plate_counts if len(p) in [7, 8]]
        invalid_length_candidates = [(p, c) for p, c in plate_counts if len(p) not in [7, 8]]
        
        # 如果有格式正确的候选，优先使用
        if valid_length_candidates:
            # 在格式正确的候选中，选择票数最多的
            valid_best_plate, valid_best_count = valid_length_candidates[0]
            
            # 如果格式正确的候选票数足够（超过总票数的40%），优先使用它
            valid_ratio = valid_best_count / total_detections_with_plate
            if valid_ratio >= 0.4:
                best_plate = valid_best_plate
                best_count = valid_best_count
                agreement_ratio = valid_ratio
        
        # 检查一致性 - 必须有足够高的比例
        if agreement_ratio >= self.min_plate_agreement:
            # 一致性足够高，确认这个车牌
            track.confirmed_plate = best_plate
            track.plate_confidence = agreement_ratio
            
            # 计算平均位置
            if track.position_history:
                positions = np.array([(p[0], p[1]) for p in track.position_history])
                avg_position = positions.mean(axis=0).tolist()
            else:
                avg_position = [0, 0]
            
            # 创建确认的车辆记录
            confirmed_vehicle = {
                'vehicle_id': track.vehicle_id,
                'plate_number': best_plate,
                'confidence': agreement_ratio,
                'detection_count': track.detection_count,
                'first_seen': track.first_seen,
                'last_seen': track.last_seen,
                'avg_position': avg_position,
                'candidate_plates': dict(plate_counts)
            }
            
            self.confirmed_vehicles.append(confirmed_vehicle)
            self.stats['vehicles_confirmed'] += 1
            
            return confirmed_vehicle
        
        # 尝试合并相似车牌
        merged_plate = self._try_merge_similar_plates(plate_counts)
        if merged_plate and len(merged_plate) >= self.min_detections * self.min_plate_agreement:
            track.confirmed_plate = merged_plate
            track.plate_confidence = sum(count for plate, count in plate_counts 
                                        if self._calculate_plate_similarity(plate, merged_plate) > 0.7) / total_detections_with_plate
            
            confirmed_vehicle = {
                'vehicle_id': track.vehicle_id,
                'plate_number': merged_plate,
                'confidence': track.plate_confidence,
                'detection_count': track.detection_count,
                'first_seen': track.first_seen,
                'last_seen': track.last_seen,
                'avg_position': [0, 0],
                'candidate_plates': dict(plate_counts),
                'merged': True
            }
            
            self.confirmed_vehicles.append(confirmed_vehicle)
            self.stats['vehicles_confirmed'] += 1
            self.stats['plates_merged'] += 1
            
            return confirmed_vehicle
        
        return None
    
    def _try_merge_similar_plates(self, 
                                plate_counts: List[Tuple[str, int]]) -> Optional[str]:
        """尝试合并相似的车牌 - 保守策略：只合并几乎相同的车牌"""
        if len(plate_counts) < 2:
            return None
        
        sorted_plates = sorted(plate_counts, key=lambda x: x[1], reverse=True)
        base_plate, base_count = sorted_plates[0]
        
        # 只合并编辑距离<=1的车牌（最多差1个字符）
        similar_plates = [base_plate]
        total_count = base_count
        
        for plate, count in sorted_plates[1:]:
            distance = self._levenshtein_distance(base_plate, plate)
            # 只有编辑距离<=1才合并（非常保守）
            if distance <= 1:
                similar_plates.append(plate)
                total_count += count
        
        # 合并后返回出现次数最多的那个（不是最长的！）
        if total_count >= sum(count for _, count in plate_counts) * 0.8:
            # 返回出现次数最多的车牌（最可靠）
            return sorted_plates[0][0]  # base_plate
        
        return None
    
    def _calculate_plate_similarity(self, plate1: str, plate2: str) -> float:
        """统一复用带缓存的车牌相似度实现"""
        return plate_similarity(plate1, plate2)
    
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """计算编辑距离"""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            
            previous_row = current_row
        
        return previous_row[-1]
    
    def get_confirmed_vehicles(self) -> List[Dict]:
        """获取所有已确认的车辆"""
        return self.confirmed_vehicles.copy()
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        return {
            **self.stats,
            'active_tracks': len(self.active_tracks),
            'confirmed_vehicles': len(self.confirmed_vehicles),
            'valid_rate': (self.stats['valid_plates'] / max(1, self.stats['total_detections'])) * 100,
            'confirmation_rate': (self.stats['vehicles_confirmed'] / max(1, self.stats['tracks_created'])) * 100
        }


def create_spatial_deduplicator(**kwargs) -> SpatialPlateDeduplicator:
    """创建空间去重器实例"""
    return SpatialPlateDeduplicator(**kwargs)
