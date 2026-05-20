"""
车辆清洗检测适配器

将车辆清洗检测功能包装为符合 BaseDetector 接口的适配器，
使其可以在 StreamProcessor 中作为可选检测器使用。
"""

import logging
import time
import threading
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path

import numpy as np
import cv2

from .base_detector import BaseDetector
from .vehicle_wash_detector import VehicleWashDetector
from .vehicle_tracker import VehicleTracker
from .plate_validator_v2 import PlateValidatorV2, PlateColor

logger = logging.getLogger(__name__)


class VehicleWashDetectionResult:
    """车辆清洗检测结果"""
    def __init__(self, 
                 class_name: str,
                 confidence: float,
                 bbox: Tuple[int, int, int, int],
                 plate_text: Optional[str] = None,
                 plate_color: Optional[str] = None,
                 vehicle_id: Optional[str] = None,
                 event_type: Optional[str] = None):  # entry, exit, wash_start, wash_complete
        self.class_name = class_name
        self.confidence = confidence
        self.bbox = bbox
        self.plate_text = plate_text
        self.plate_color = plate_color
        self.vehicle_id = vehicle_id
        self.event_type = event_type
        
    def __repr__(self):
        return f"VehicleWashResult({self.class_name}, {self.plate_text or 'N/A'}, conf={self.confidence:.2f})"


class VehicleWashDetectorAdapter(BaseDetector):
    """
    车辆清洗检测适配器
    
    包装车辆清洗检测功能，提供与 BaseDetector 兼容的接口：
    - detect(frame) -> 返回检测结果列表
    - draw_results(frame, results) -> 绘制检测框
    - check_violations(results) -> 检查违规（此处为清洗状态）
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初始化适配器
        
        Args:
            config: 配置字典，可包含:
                - model_path: 模型路径
                - device: 计算设备
                - conf_threshold: 置信度阈值
                - wash_zone: 清洗区域 {x1, y1, x2, y2}
                - wash_stop_time: 清洗判定时间(秒)
        """
        # 先保存配置，供 _load_model 使用
        self.adapter_config = config or {}
        
        # 调用父类初始化（会自动调用 _load_model 和 _init_classes）
        # 但 BaseDetector.__init__ 需要 config 参数，我们传一个兼容的
        base_config = {
            'name': 'Vehicle Wash Detector',
            'type': 'vehicle_wash',
            'params': {
                'conf_threshold': self.adapter_config.get('conf_threshold', 0.5),
                'device': self.adapter_config.get('device', 'auto')
            },
            'classes': [
                {'id': 0, 'name': 'vehicle', 'color': [0, 255, 0]}
            ]
        }
        super().__init__(base_config)
        
        # 进出场管理
        self.entry_exit_mgr = EntryExitManager(
            wash_zone=self.adapter_config.get('wash_zone', {'x1': 0.1, 'y1': 0.3, 'x2': 0.7, 'y2': 0.8}),
            wash_stop_time=self.adapter_config.get('wash_stop_time', 180)
        )
        
        # 状态
        self.frame_count = 0
        self.last_plate_result = None
    
    def _load_model(self):
        """加载模型 - 实现抽象方法"""
        # 初始化核心检测器
        model_path = self.adapter_config.get('model_path', 'yolov8n.pt')
        device = self.adapter_config.get('device', 'auto')
        conf_threshold = self.adapter_config.get('conf_threshold', 0.5)
        
        logger.info(f"初始化车辆清洗检测适配器: model={model_path}, device={device}")
        
        # VehicleWashDetector 需要 config 字典格式
        detector_config = {
            'path': model_path,
            'device': device,
            'conf_threshold': conf_threshold,
            'params': {
                'conf_threshold': conf_threshold,
                'device': device
            }
        }
        
        self.detector = VehicleWashDetector(detector_config)
        
        # 初始化车辆跟踪器
        self.tracker = VehicleTracker()
        
        logger.info("车辆清洗检测器模型已加载")
        
    def detect(self, frame: np.ndarray) -> List[VehicleWashDetectionResult]:
        """
        检测帧中的车辆并识别车牌
        
        Args:
            frame: BGR格式的视频帧
            
        Returns:
            VehicleWashDetectionResult 列表
        """
        self.frame_count += 1
        results = []
        
        try:
            # 1. 检测车辆 (VehicleWashDetector 使用 detect 方法)
            vehicle_detections = self.detector.detect(frame)
            
            if not vehicle_detections:
                return results
            
            # 2. 更新跟踪器
            frame_height, frame_width = frame.shape[:2]
            tracks = self.tracker.update(vehicle_detections, self.frame_count, (frame_height, frame_width))
            
            # 3. 对每个跟踪车辆检测车牌
            for track in tracks:
                # 跳过已标记出场的跟踪对象
                if track.exit_detected:
                    continue
                
                # 检查bbox类型
                if not isinstance(track.bbox, (tuple, list)) or len(track.bbox) != 4:
                    logger.warning(f"跟踪对象 {track.track_id} 的bbox格式错误: {track.bbox} (类型: {type(track.bbox)})")
                    continue
                    
                x1, y1, x2, y2 = track.bbox
                
                # 检查是否在清洗区域
                in_wash_zone = self.entry_exit_mgr._is_in_wash_zone(track.bbox, frame.shape)
                
                # 检测车牌
                plate_result = self.detector.detect_license_plate(frame, (x1, y1, x2, y2))
                
                # 调试：记录车牌检测器状态
                if self.frame_count % 30 == 0:  # 每30帧记录一次
                    has_plate_detector = self.detector.plate_detector is not None if hasattr(self.detector, 'plate_detector') else False
                    logger.debug(f"车牌检测器状态: {'可用' if has_plate_detector else '不可用'}, "
                               f"车辆区域大小: {x2-x1}x{y2-y1}, 帧: {self.frame_count}")
                
                if plate_result and plate_result[0]:
                    plate_text, plate_bbox, plate_color, color_conf = plate_result
                    logger.info(f"车辆 T{track.track_id}: 识别到车牌 {plate_text}, 颜色={plate_color}, 清洗区域={in_wash_zone}")
                else:
                    if in_wash_zone:
                        logger.warning(f"车辆 T{track.track_id}: 在清洗区域内未识别到车牌 "
                                     f"(plate_result={plate_result}, detector={'可用' if self.detector.plate_detector else '不可用'})")
                    else:
                        logger.info(f"车辆 T{track.track_id}: 在清洗区域外未识别到车牌")
                
                if plate_result and plate_result[0]:
                    plate_text, plate_bbox, plate_color, color_conf = plate_result
                    
                    # 验证车牌
                    is_valid, cleaned, reason = PlateValidatorV2.validate(plate_text, plate_color, color_conf)
                    
                    if is_valid and cleaned:
                        # 更新进出场状态
                        event = self.entry_exit_mgr.update_vehicle(
                            track_id=track.track_id,
                            plate_text=cleaned,
                            bbox=track.bbox,
                            frame_shape=frame.shape
                        )
                        
                        # 创建结果
                        result = VehicleWashDetectionResult(
                            class_name="vehicle",
                            confidence=track.confidence,
                            bbox=track.bbox,
                            plate_text=cleaned,
                            plate_color=plate_color,
                            vehicle_id=str(track.track_id),
                            event_type=event
                        )
                        results.append(result)
                        
                        # 记录事件
                        if event:
                            logger.info(f"车辆事件 [{event}]: {cleaned} (T{track.track_id})")
                else:
                    # 无车牌，只返回车辆检测
                    result = VehicleWashDetectionResult(
                        class_name="vehicle",
                        confidence=track.confidence,
                        bbox=track.bbox,
                        vehicle_id=str(track.track_id)
                    )
                    results.append(result)
            
            # 4. 检查出场
            exited_tracks = self.tracker.get_exited_tracks()
            for track in exited_tracks:
                if track.plate_text:
                    event = self.entry_exit_mgr.handle_exit(track.plate_text)
                    if event:
                        result = VehicleWashDetectionResult(
                            class_name="vehicle",
                            confidence=track.confidence,
                            bbox=track.bbox,
                            plate_text=track.plate_text,
                            vehicle_id=str(track.track_id),
                            event_type='exit'
                        )
                        results.append(result)
                        
        except Exception as e:
            import traceback
            logger.error(f"车辆清洗检测异常: {e}")
            logger.error(f"异常详情: {traceback.format_exc()}")
            
        return results
    
    def draw_results(self, frame: np.ndarray, results: List[VehicleWashDetectionResult]) -> np.ndarray:
        """
        在帧上绘制检测结果
        
        Args:
            frame: 原始帧
            results: 检测结果列表
            
        Returns:
            绘制后的帧
        """
        output = frame.copy()
        
        for result in results:
            x1, y1, x2, y2 = result.bbox
            
            # 根据事件类型选择颜色
            if result.event_type == 'entry':
                color = (0, 255, 0)  # 绿色-进场
            elif result.event_type == 'exit':
                color = (0, 0, 255)  # 红色-出场
            elif result.event_type == 'wash_complete':
                color = (255, 165, 0)  # 橙色-清洗完成
            else:
                color = (255, 255, 0)  # 黄色-普通
            
            # 画车辆框
            cv2.rectangle(output, (x1, y1), (x2, y2), color, 2)
            
            # 构建标签
            labels = []
            if result.plate_text:
                labels.append(result.plate_text)
            if result.plate_color:
                labels.append(f"[{result.plate_color}]")
            if result.event_type:
                labels.append(f"({result.event_type})")
            
            label = " ".join(labels) if labels else f"Vehicle {result.vehicle_id}"
            
            # 画标签背景
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
            cv2.rectangle(output, 
                         (x1, y1 - label_size[1] - 10),
                         (x1 + label_size[0], y1),
                         color, -1)
            cv2.putText(output, label, (x1, y1 - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # 画清洗区域
        self._draw_wash_zone(output)
        
        # 画统计信息
        stats = self.entry_exit_mgr.get_stats()
        stats_text = f"Entries: {stats['entries']} | Exits: {stats['exits']} | Washed: {stats['washed']} | Active: {stats['active']}"
        cv2.putText(output, stats_text, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        return output
    
    def check_violations(self, results: List[VehicleWashDetectionResult]) -> List[Dict]:
        """
        检查违规（未清洗出场）
        
        Args:
            results: 检测结果
            
        Returns:
            违规列表
        """
        violations = []
        
        for result in results:
            if result.event_type == 'exit' and result.plate_text:
                # 检查是否已清洗
                record = self.entry_exit_mgr.get_record(result.plate_text)
                if record and not record.get('is_washed', False):
                    violations.append({
                        'type': 'vehicle_not_washed',
                        'severity': 'high',
                        'plate': result.plate_text,
                        'description': f'车辆 {result.plate_text} 未清洗出场',
                        'vehicle_id': result.vehicle_id
                    })
        
        return violations
    
    def _draw_wash_zone(self, frame: np.ndarray):
        """绘制清洗区域"""
        h, w = frame.shape[:2]
        zone = self.entry_exit_mgr.wash_zone
        
        x1 = int(zone['x1'] * w)
        y1 = int(zone['y1'] * h)
        x2 = int(zone['x2'] * w)
        y2 = int(zone['y2'] * h)
        
        # 半透明填充
        overlay = frame.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (255, 200, 100), -1)
        cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)
        
        # 边框
        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 150, 50), 2)
        cv2.putText(frame, "WASH ZONE", (x1 + 5, y1 + 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 150, 50), 2)
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return self.entry_exit_mgr.get_stats()
    
    def get_active_vehicles(self) -> List[Dict]:
        """获取在场车辆"""
        return self.entry_exit_mgr.get_active_vehicles()


class EntryExitManager:
    """进出场管理器（简化版，用于适配器）"""
    
    def __init__(self, wash_zone: Dict, wash_stop_time: int = 180):
        self.wash_zone = wash_zone
        self.wash_stop_time = wash_stop_time
        self.records = {}
        self.active_vehicles = {}
        self.stats = {'entries': 0, 'exits': 0, 'washed': 0, 'active': 0}
        
    def update_vehicle(self, track_id: int, plate_text: str, bbox: Tuple, frame_shape: Tuple) -> Optional[str]:
        """更新车辆状态，返回事件类型"""
        current_time = time.time()
        
        # 检查是否在清洗区域
        in_wash_zone = self._is_in_wash_zone(bbox, frame_shape)
        
        # 检查是否停止
        is_stopped = self._is_stopped(track_id, bbox)
        
        # 获取或创建记录
        if plate_text not in self.records:
            self.records[plate_text] = {
                'entry_time': current_time,
                'exit_time': None,
                'is_washed': False,
                'wash_start_time': None,
                'wash_duration': 0,
                'positions': []
            }
            self.stats['entries'] += 1
            self.stats['active'] += 1
            return 'entry'
        
        record = self.records[plate_text]
        
        # 更新位置历史
        record['positions'].append(bbox)
        if len(record['positions']) > 30:
            record['positions'].pop(0)
        
        # 检查清洗状态
        if in_wash_zone and is_stopped:
            if record['wash_start_time'] is None:
                record['wash_start_time'] = current_time
            else:
                wash_duration = current_time - record['wash_start_time']
                if wash_duration >= self.wash_stop_time and not record['is_washed']:
                    record['is_washed'] = True
                    record['wash_duration'] = wash_duration
                    self.stats['washed'] += 1
                    return 'wash_complete'
        else:
            record['wash_start_time'] = None
        
        return None
    
    def handle_exit(self, plate_text: str) -> Optional[str]:
        """处理车辆出场"""
        if plate_text in self.records:
            record = self.records[plate_text]
            if record['exit_time'] is None:
                record['exit_time'] = time.time()
                self.stats['exits'] += 1
                self.stats['active'] -= 1
                return 'exit'
        return None
    
    def _is_in_wash_zone(self, bbox: Tuple, frame_shape: Tuple) -> bool:
        """检查是否在清洗区域"""
        h, w = frame_shape[:2]
        cx = (bbox[0] + bbox[2]) / 2 / w
        cy = (bbox[1] + bbox[3]) / 2 / h
        
        return (self.wash_zone['x1'] <= cx <= self.wash_zone['x2'] and
                self.wash_zone['y1'] <= cy <= self.wash_zone['y2'])
    
    def _is_stopped(self, track_id: int, bbox: Tuple, threshold: int = 10) -> bool:
        """检查车辆是否停止"""
        # 简化实现：检查位置变化
        if not hasattr(self, '_last_positions'):
            self._last_positions = {}
        
        if track_id not in self._last_positions:
            self._last_positions[track_id] = []
        
        self._last_positions[track_id].append(bbox)
        if len(self._last_positions[track_id]) > 10:
            self._last_positions[track_id].pop(0)
        
        if len(self._last_positions[track_id]) < 5:
            return False
        
        # 计算平均移动距离
        positions = self._last_positions[track_id]
        total_movement = 0
        for i in range(1, len(positions)):
            dx = abs(positions[i][0] - positions[i-1][0])
            dy = abs(positions[i][1] - positions[i-1][1])
            total_movement += (dx + dy) / 2
        
        avg_movement = total_movement / (len(positions) - 1)
        return avg_movement < threshold
    
    def get_stats(self) -> Dict:
        """获取统计"""
        return self.stats
    
    def get_active_vehicles(self) -> List[Dict]:
        """获取在场车辆"""
        active = []
        for plate, record in self.records.items():
            if record['exit_time'] is None:
                active.append({
                    'plate': plate,
                    'entry_time': record['entry_time'],
                    'is_washed': record['is_washed']
                })
        return active
    
    def get_record(self, plate_text: str) -> Optional[Dict]:
        """获取记录"""
        return self.records.get(plate_text)
