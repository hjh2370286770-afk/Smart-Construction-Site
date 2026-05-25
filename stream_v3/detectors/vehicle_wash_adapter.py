"""
车辆清洗检测适配器 - 完整版

基于 test_full_video.py 的已验证架构，完整实现：
- 车辆检测 + 车牌识别
- V2/V1双重车牌验证
- SpatialPlateDeduplicator 空间聚类+投票确认
- 强车牌合并（相似度>0.60）
- 进出场管理 + 清洗判定
- 数据库持久化
"""

import logging
import time
import threading
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path
from dataclasses import dataclass, field

import numpy as np
import cv2

from .base_detector import BaseDetector
from .vehicle_wash_detector import VehicleWashDetector
from .vehicle_tracker import VehicleTracker
from .plate_validator_v2 import PlateValidatorV2, PlateColor, validate_plate_v2
from .spatial_plate_deduplicator import SpatialPlateDeduplicator
from .plate_utils import validate_and_filter_plate

logger = logging.getLogger(__name__)


@dataclass
class VehicleRecord:
    """车辆记录"""
    vehicle_id: str
    license_plate: str
    entry_time: datetime
    exit_time: Optional[datetime] = None
    is_washed: bool = False
    dwell_time: float = 0.0
    wash_start_time: Optional[datetime] = None
    is_reentry: bool = False
    last_bbox: Optional[Tuple[int, int, int, int]] = None
    last_seen: Optional[datetime] = None
    position_history: List[Tuple[float, float]] = field(default_factory=list)
    db_id: Optional[int] = None


class VehicleWashDetectionResult:
    """车辆清洗检测结果"""
    def __init__(self,
                 class_name: str,
                 confidence: float,
                 bbox: Tuple[int, int, int, int],
                 plate_text: Optional[str] = None,
                 plate_color: Optional[str] = None,
                 vehicle_id: Optional[str] = None,
                 event_type: Optional[str] = None):
        self.class_name = class_name
        self.confidence = confidence
        self.bbox = bbox
        self.plate_text = plate_text
        self.plate_color = plate_color
        self.vehicle_id = vehicle_id
        self.event_type = event_type

    def __repr__(self):
        return f"VehicleWashResult({self.class_name}, {self.plate_text or 'N/A'}, conf={self.confidence:.2f})"


class EntryExitManager:
    """进出场 + 清洗判定管理器 (完整版，基于 test_full_video.py)"""

    def __init__(self, wash_stop_time=180, exit_wait_time=60,
                 exit_left_threshold=0.05, wash_zone=None,
                 plate_merge_threshold=0.60):
        self.wash_stop_time = wash_stop_time
        self.exit_wait_time = exit_wait_time
        self.exit_left_threshold = exit_left_threshold
        self.wash_zone = wash_zone or {'x1': 0.1, 'y1': 0.3, 'x2': 0.7, 'y2': 0.8}
        self.plate_merge_threshold = plate_merge_threshold

        self.records: Dict[str, VehicleRecord] = {}
        self.exited_plates: Dict[str, datetime] = {}
        self.left_disappear_time: Dict[str, datetime] = {}

        self.next_id = 0
        self.total_entries = 0
        self.total_exits = 0
        self.washed_count = 0

        self.db = None
        self.plate_variants: Dict[str, str] = {}

    def set_db(self, db):
        self.db = db

    def _plate_similarity(self, p1: str, p2: str) -> float:
        """计算两个车牌的相似度"""
        from .plate_utils import plate_similarity
        return plate_similarity(p1, p2)

    def _find_similar_record(self, plate: str) -> Optional[str]:
        """查找与给定车牌相似的已有记录"""
        if plate in self.plate_variants:
            return self.plate_variants[plate]

        best_match = None
        best_sim = self.plate_merge_threshold

        # 与所有在场记录比较
        for existing_plate, record in self.records.items():
            if record.exit_time is not None:
                continue
            sim = self._plate_similarity(plate, existing_plate)
            if sim > best_sim:
                best_sim = sim
                best_match = existing_plate

        # 也与已出场记录比较（用于二次进场识别）
        if best_match is None:
            for existing_plate in self.exited_plates:
                sim = self._plate_similarity(plate, existing_plate)
                if sim > best_sim:
                    best_sim = sim
                    best_match = existing_plate

        return best_match

    def on_plate_confirmed(self, plate: str, bbox: Tuple, frame_shape: Tuple):
        """车牌确认后的回调 - 方案2: 强合并"""
        current_time = datetime.now()
        frame_height, frame_width = frame_shape[:2]
        center_x = (bbox[0] + bbox[2]) / 2
        center_y = (bbox[1] + bbox[3]) / 2

        # 查找相似记录
        similar_plate = self._find_similar_record(plate)

        if similar_plate and similar_plate in self.records:
            # 合并到已有记录
            record = self.records[similar_plate]

            # 如果当前车牌更"标准"（长度更接近7位），更新主车牌
            if abs(len(plate) - 7) < abs(len(similar_plate) - 7):
                old_plate = similar_plate
                self.records[plate] = record
                record.license_plate = plate
                del self.records[old_plate]
                self.plate_variants[old_plate] = plate
                self.plate_variants[plate] = plate
                logger.info(f"车牌更新: {old_plate} -> {plate}")
                similar_plate = plate

            if plate != similar_plate:
                self.plate_variants[plate] = similar_plate
                logger.info(f"车牌合并: {plate} -> {similar_plate} (similarity: {self._plate_similarity(plate, similar_plate):.2f})")

            # 更新位置信息
            record.last_bbox = bbox
            record.last_seen = current_time
            record.position_history.append((center_x, center_y))
            if len(record.position_history) > 60:
                record.position_history = record.position_history[-30:]

            # 清洗判定
            if not record.is_washed:
                in_wash_zone = self._is_in_wash_zone(bbox, frame_width, frame_height)
                is_stopped = self._is_vehicle_stopped(similar_plate)

                if in_wash_zone and is_stopped:
                    if record.wash_start_time is None:
                        record.wash_start_time = current_time
                        logger.info(f"车辆进入清洗区域并停止: 车牌={similar_plate}")
                        if self.db:
                            try:
                                self.db.save_vehicle_record(record)
                            except Exception as e:
                                logger.error(f"数据库保存清洗开始失败: {e}")
                    else:
                        stop_duration = (current_time - record.wash_start_time).total_seconds()
                        if stop_duration >= self.wash_stop_time:
                            record.is_washed = True
                            logger.info(f"★ 车辆清洗完成: 车牌={similar_plate}, 停止时间={stop_duration:.0f}秒")
                            if self.db:
                                try:
                                    self.db.save_vehicle_record(record)
                                except Exception as e:
                                    logger.error(f"数据库保存清洗状态失败: {e}")
                else:
                    if record.wash_start_time is not None:
                        if not in_wash_zone:
                            logger.info(f"车辆离开清洗区域，计时重置: 车牌={similar_plate}")
                            record.wash_start_time = None
                        elif not is_stopped:
                            if len(record.position_history) >= 10:
                                recent = record.position_history[-10:]
                                xs = [p[0] for p in recent]
                                ys = [p[1] for p in recent]
                                x_range = max(xs) - min(xs)
                                y_range = max(ys) - min(ys)
                                if x_range > 50 or y_range > 50:
                                    logger.info(f"车辆在清洗区域移动，计时重置: 车牌={similar_plate} (移动: {x_range:.0f}, {y_range:.0f})")
                                    record.wash_start_time = None

            # 出场检测
            if self._is_near_left_edge(bbox, frame_width):
                if similar_plate not in self.left_disappear_time:
                    self.left_disappear_time[similar_plate] = current_time
                    logger.info(f"车辆到达画面左侧: 车牌={similar_plate}")
            else:
                if similar_plate in self.left_disappear_time:
                    del self.left_disappear_time[similar_plate]

            return record

        # 检查是否是二次进场
        if similar_plate and similar_plate in self.exited_plates:
            is_reentry = True
            del self.exited_plates[similar_plate]
            logger.info(f"车辆二次进场: 车牌={plate} (匹配已出场记录: {similar_plate})")
            plate = similar_plate
        else:
            is_reentry = False

        # 创建新记录
        record = VehicleRecord(
            vehicle_id=str(self.next_id),
            license_plate=plate,
            entry_time=current_time,
            is_reentry=is_reentry,
            last_bbox=bbox,
            last_seen=current_time,
            position_history=[(center_x, center_y)],
        )
        self.records[plate] = record
        self.next_id += 1
        self.total_entries += 1

        entry_type = "二次进场" if is_reentry else "进场"
        logger.info(f"★ 车辆{entry_type}: ID={record.vehicle_id}, 车牌={plate}")

        if self.db:
            try:
                db_id = self.db.save_vehicle_record(record)
                record.db_id = db_id
            except Exception as e:
                logger.error(f"数据库保存失败: {e}")

        return record

    def check_exits(self, frame_shape: Tuple):
        """检查并确认出场"""
        current_time = datetime.now()
        updated = []

        for plate, disappear_time in list(self.left_disappear_time.items()):
            wait_elapsed = (current_time - disappear_time).total_seconds()
            if wait_elapsed >= self.exit_wait_time:
                record = self.records.get(plate)
                if record and record.exit_time is None:
                    record.exit_time = current_time
                    record.dwell_time = (record.exit_time - record.entry_time).total_seconds()

                    self.total_exits += 1
                    if record.is_washed:
                        self.washed_count += 1

                    self.exited_plates[plate] = current_time

                    if self.db:
                        try:
                            self.db.save_vehicle_record(record)
                        except Exception as e:
                            logger.error(f"数据库保存失败: {e}")

                    updated.append(record)
                    logger.info(f"★ 车辆出场: 车牌={plate}, 停留={record.dwell_time:.0f}秒, "
                              f"清洗={'是' if record.is_washed else '否'}")

                    del self.left_disappear_time[plate]

        return updated

    def check_missing_vehicles(self, confirmed_plates: List[str], frame_shape: Tuple):
        """检查失踪车辆（未在当前帧确认但之前在场）"""
        current_time = datetime.now()
        frame_height, frame_width = frame_shape[:2]

        for plate, record in self.records.items():
            if record.exit_time is not None:
                continue

            is_confirmed_this_frame = False
            for cp in confirmed_plates:
                if cp == plate or self.plate_variants.get(cp) == plate:
                    is_confirmed_this_frame = True
                    break
            if is_confirmed_this_frame:
                # 车辆当前帧被确认，如果之前在left_disappear_time中，移除它
                if plate in self.left_disappear_time:
                    del self.left_disappear_time[plate]
                continue

            # 车辆未在当前帧确认，检查是否失踪
            if record.last_seen:
                missing_time = (current_time - record.last_seen).total_seconds()
                # 如果失踪超过3秒，且最后位置在左侧，标记为左侧消失
                if missing_time > 3.0:
                    if record.last_bbox and self._is_near_left_edge(record.last_bbox, frame_width):
                        if plate not in self.left_disappear_time:
                            self.left_disappear_time[plate] = current_time
                            logger.info(f"车辆从左侧消失: 车牌={plate}, 失踪时间={missing_time:.0f}秒, "
                                      f"最后位置={record.last_bbox}")
                    else:
                        # 车辆不在左侧消失，但已经失踪，输出警告
                        if missing_time > 10.0:
                            logger.warning(f"车辆失踪（非左侧）: 车牌={plate}, 失踪时间={missing_time:.0f}秒, "
                                         f"最后位置={record.last_bbox}")

    def _is_in_wash_zone(self, bbox, frame_width, frame_height):
        """检查是否在清洗区域"""
        x1, y1, x2, y2 = bbox
        center_x = (x1 + x2) / 2 / frame_width
        center_y = (y1 + y2) / 2 / frame_height
        zone = self.wash_zone
        return (zone['x1'] <= center_x <= zone['x2'] and
                zone['y1'] <= center_y <= zone['y2'])

    def _is_vehicle_stopped(self, plate):
        """检查车辆是否停止"""
        record = self.records.get(plate)
        if not record or len(record.position_history) < 10:
            return False
        recent = record.position_history[-10:]
        xs = [p[0] for p in recent]
        ys = [p[1] for p in recent]
        return (max(xs) - min(xs)) < 30 and (max(ys) - min(ys)) < 30

    def _is_near_left_edge(self, bbox, frame_width):
        """检查是否在画面左侧（出场区域）"""
        x1, y1, x2, y2 = bbox
        # 条件1：车辆完全在左侧阈值内
        is_fully_left = x2 < frame_width * self.exit_left_threshold
        # 条件2：车辆大部分在左侧（左边界已过阈值线）
        is_mostly_left = x1 < frame_width * self.exit_left_threshold and x2 < frame_width * self.exit_left_threshold * 3
        return is_fully_left or is_mostly_left

    def get_active_records(self):
        """获取在场记录"""
        return [r for r in self.records.values() if r.exit_time is None]

    def get_completed_records(self):
        """获取已完成记录"""
        return [r for r in self.records.values() if r.exit_time is not None]

    def get_statistics(self):
        """获取统计信息"""
        return {
            'total_entries': self.total_entries,
            'total_exits': self.total_exits,
            'washed_count': self.washed_count,
            'active_vehicles': len(self.get_active_records()),
            'pending_exit': len(self.left_disappear_time),
            'wash_rate': self.washed_count / self.total_exits if self.total_exits > 0 else 0,
        }


class VehicleWashDetectorAdapter(BaseDetector):
    """
    车辆清洗检测适配器 - 完整版

    基于 test_full_video.py 的已验证架构，完整实现所有功能：
    - 车辆检测 (YOLOv8n)
    - 车牌识别 (YOLOv8s + plate_rec_color)
    - V2/V1双重车牌验证
    - SpatialPlateDeduplicator 空间聚类+投票确认
    - 强车牌合并
    - 进出场管理 + 清洗判定
    - 数据库持久化
    """

    def __init__(self, config: Optional[Dict] = None):
        self.adapter_config = config or {}

        # 先初始化所有需要的属性（因为 BaseDetector.__init__ 会调用 _load_model）
        self.frame_count = 0
        self.tracker = None
        self.detector = None
        self.spatial_dedup = None
        self.entry_exit_mgr = None
        self.stats = {
            'total_frames': 0,
            'total_detections': 0,
            'valid_plates': 0,
            'invalid_plates': 0,
            'confirmed_vehicles': set(),
        }

        base_config = {
            'name': 'Vehicle Wash Detector',
            'type': 'vehicle_wash',
            'params': {
                'conf_threshold': self.adapter_config.get('conf_threshold', 0.35),
                'device': self.adapter_config.get('device', 'auto')
            },
            'classes': [
                {'id': 0, 'name': 'vehicle', 'color': [0, 255, 0]}
            ]
        }
        super().__init__(base_config)

        # 初始化空间去重器
        self.spatial_dedup = SpatialPlateDeduplicator(
            spatial_threshold=80.0,
            time_window=12.0,
            min_detections=10,
            min_plate_agreement=0.80,
            plate_similarity_threshold=0.90
        )

        # 初始化进出场管理器
        self.entry_exit_mgr = EntryExitManager(
            wash_stop_time=self.adapter_config.get('wash_stop_time', 180),
            exit_wait_time=60,
            exit_left_threshold=0.05,
            wash_zone=self.adapter_config.get('wash_zone', {'x1': 0.1, 'y1': 0.3, 'x2': 0.7, 'y2': 0.8}),
            plate_merge_threshold=0.60
        )

        # 初始化数据库
        db_config = self.adapter_config.get('db_config', {'enabled': False})
        if db_config.get('enabled', False):
            try:
                from .vehicle_wash_db import VehicleWashDB
                db = VehicleWashDB(db_config)
                self.entry_exit_mgr.set_db(db)
                logger.info("数据库已连接")
            except Exception as e:
                logger.error(f"数据库连接失败: {e}")

    def _load_model(self):
        """加载模型"""
        model_path = self.adapter_config.get('model_path', 'yolov8n.pt')
        device = self.adapter_config.get('device', 'auto')
        conf_threshold = self.adapter_config.get('conf_threshold', 0.35)

        logger.info(f"初始化车辆清洗检测适配器: model={model_path}, device={device}")

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
        self.tracker = VehicleTracker(
            iou_threshold=0.3,
            max_miss_frames=5,
            exit_left_threshold=0.05
        )

        logger.info("车辆清洗检测器模型已加载")

    def detect(self, frame: np.ndarray) -> List[VehicleWashDetectionResult]:
        """
        检测帧中的车辆并识别车牌 - 完整流程

        基于 test_full_video.py 的已验证架构：
        1. 车辆检测（降分辨率）
        2. 车辆跟踪
        3. 车牌识别（原始分辨率）
        4. V2/V1双重验证
        5. SpatialPlateDeduplicator 空间聚类+投票确认
        6. 强车牌合并
        7. 进出场管理 + 清洗判定
        """
        self.frame_count += 1
        self.stats['total_frames'] += 1
        results = []

        try:
            # === 步骤1: 车辆检测 ===
            vehicle_detections = self.detector.detect(frame)
            logger.info(f"[检测] 帧 {self.frame_count}: 检测到 {len(vehicle_detections)} 辆车")

            if not vehicle_detections:
                return results

            self.stats['total_detections'] += len(vehicle_detections)

            # === 步骤2: 更新车辆跟踪 ===
            frame_height, frame_width = frame.shape[:2]
            tracked_objects = self.tracker.update(vehicle_detections, self.frame_count, (frame_height, frame_width))
            logger.info(f"[跟踪] 活跃跟踪车辆: {len(tracked_objects)} 辆")

            # === 步骤3: 车牌识别（每个跟踪车辆）===
            confirmed_plates_this_frame = []
            valid_count = 0
            invalid_count = 0

            for track in tracked_objects:
                if track.exit_detected:
                    logger.info(f"[跟踪] 车辆 T{track.track_id} 已标记出场，跳过")
                    continue

                if not isinstance(track.bbox, (tuple, list)) or len(track.bbox) != 4:
                    logger.warning(f"[跟踪] 车辆 T{track.track_id} bbox格式错误: {track.bbox}")
                    continue

                x1, y1, x2, y2 = track.bbox
                in_wash_zone = self.entry_exit_mgr._is_in_wash_zone(track.bbox, frame_width, frame_height)
                logger.info(f"[跟踪] 车辆 T{track.track_id}: 位置=({x1},{y1},{x2},{y2}), 清洗区域={in_wash_zone}")

                # 检测车牌
                plate_result = self.detector.detect_license_plate(frame, (x1, y1, x2, y2))

                if plate_result and plate_result[0]:
                    plate_text, plate_bbox, plate_color, color_conf = plate_result
                    logger.info(f"[识别] 车辆 T{track.track_id}: 原始车牌={plate_text}, 颜色={plate_color}, 颜色置信度={color_conf:.2f}")

                    # === 步骤4: V2/V1双重验证 ===
                    is_valid, cleaned, reason = validate_plate_v2(plate_text, plate_color, color_conf)
                    logger.info(f"[验证] 车辆 T{track.track_id}: V2验证结果={is_valid}, 清理后={cleaned}, 原因={reason}")

                    if not is_valid:
                        # V2验证失败，尝试V1验证器作为后备
                        logger.info(f"[验证] 车辆 T{track.track_id}: V2验证失败，尝试V1后备验证")
                        is_valid_v1, reason_v1, cleaned_v1 = validate_and_filter_plate(plate_text)
                        if is_valid_v1 and cleaned_v1:
                            is_valid = True
                            cleaned = cleaned_v1
                            reason = reason_v1 + " (V1 fallback)"
                            logger.info(f"[验证] 车辆 T{track.track_id}: V1后备验证成功: {cleaned}")
                        else:
                            logger.warning(f"[验证] 车辆 T{track.track_id}: V1后备验证也失败: {reason_v1}")

                    if is_valid and cleaned:
                        # === 步骤5: SpatialPlateDeduplicator 空间聚类+投票确认 ===
                        logger.info(f"[去重] 车辆 T{track.track_id}: 提交空间去重: {cleaned}")
                        confirmed_vehicle = self.spatial_dedup.add_detection(
                            frame_idx=self.frame_count,
                            bbox=track.bbox,
                            plate_text=cleaned,
                            plate_bbox=plate_bbox,
                            confidence=track.confidence,
                            plate_color=plate_color,
                            color_conf=color_conf
                        )

                        if confirmed_vehicle:
                            valid_count += 1
                            confirmed_plates_this_frame.append(confirmed_vehicle['plate_number'])

                            if confirmed_vehicle['plate_number'] not in self.stats['confirmed_vehicles']:
                                self.stats['confirmed_vehicles'].add(confirmed_vehicle['plate_number'])
                                logger.info(f"[Vehicle ✓#{confirmed_vehicle['vehicle_id']}] Confirmed: {confirmed_vehicle['plate_number']} "
                                          f"(conf: {confirmed_vehicle['confidence']:.1%}, 颜色: {plate_color})")

                            # === 步骤6: 强车牌合并 + 进出场管理 ===
                            logger.info(f"[进场] 车辆 T{track.track_id}: 提交进出场管理: {confirmed_vehicle['plate_number']}")
                            record = self.entry_exit_mgr.on_plate_confirmed(
                                confirmed_vehicle['plate_number'], track.bbox, frame.shape
                            )

                            # 关联车牌到跟踪器
                            self.tracker.associate_plate(
                                track.track_id, confirmed_vehicle['plate_number'],
                                confirmed_vehicle['confidence']
                            )

                            # 创建结果
                            event = None
                            if record:
                                if record.is_washed:
                                    event = 'wash_complete'
                                    logger.info(f"[事件] 车辆 T{track.track_id}: 清洗完成事件: {confirmed_vehicle['plate_number']}")
                                elif record.wash_start_time:
                                    event = 'wash_start'
                                    logger.info(f"[事件] 车辆 T{track.track_id}: 清洗开始事件: {confirmed_vehicle['plate_number']}")
                                else:
                                    logger.info(f"[事件] 车辆 T{track.track_id}: 进场事件: {confirmed_vehicle['plate_number']}")

                            result = VehicleWashDetectionResult(
                                class_name="vehicle",
                                confidence=track.confidence,
                                bbox=track.bbox,
                                plate_text=confirmed_vehicle['plate_number'],
                                plate_color=plate_color,
                                vehicle_id=str(track.track_id),
                                event_type=event
                            )
                            results.append(result)
                        else:
                            # 空间去重尚未确认，记录但不生成事件
                            logger.info(f"[去重] 车辆 T{track.track_id}: 空间去重尚未确认: {cleaned}")
                            invalid_count += 1
                    else:
                        logger.warning(f"[验证] 车辆 T{track.track_id}: 车牌验证失败: {plate_text}, 原因: {reason}")
                        invalid_count += 1
                else:
                    # 无车牌，只返回车辆检测
                    if in_wash_zone:
                        logger.warning(f"[识别] 车辆 T{track.track_id}: 在清洗区域内未识别到车牌")
                    else:
                        logger.info(f"[识别] 车辆 T{track.track_id}: 在清洗区域外未识别到车牌")
                    result = VehicleWashDetectionResult(
                        class_name="vehicle",
                        confidence=track.confidence,
                        bbox=track.bbox,
                        vehicle_id=str(track.track_id)
                    )
                    results.append(result)

            self.stats['valid_plates'] += valid_count
            self.stats['invalid_plates'] += invalid_count
            logger.info(f"[统计] 帧 {self.frame_count}: 有效车牌={valid_count}, 无效={invalid_count}, 总确认={len(self.stats['confirmed_vehicles'])}")

            # === 步骤7: 检查出场 ===
            # 7a. 跟踪器检测到的出场（车辆从左侧离开画面）
            exited_tracks = self.tracker.get_exited_tracks()
            if exited_tracks:
                logger.info(f"[出场] 跟踪器检测到 {len(exited_tracks)} 辆车已出场")
                for track in exited_tracks:
                    logger.info(f"[出场] 已出场车辆: T{track.track_id}, 车牌={track.plate_text or '未识别'}, "
                              f"最后位置={track.bbox}, 出场时间={track.exit_time}")

            # 7b. 先检查失踪车辆（更新 left_disappear_time）
            logger.info(f"[出场] 检查失踪车辆，当前帧确认车牌: {confirmed_plates_this_frame}")
            self.entry_exit_mgr.check_missing_vehicles(confirmed_plates_this_frame, frame.shape)

            # 7c. 左侧消失确认出场（基于时间阈值）
            exited_records = self.entry_exit_mgr.check_exits(frame.shape)
            if exited_records:
                logger.info(f"[出场] EntryExitManager 确认 {len(exited_records)} 辆车出场")
                for record in exited_records:
                    logger.info(f"★ 车辆出场(确认): 车牌={record.license_plate}, 停留={record.dwell_time:.0f}秒, "
                              f"清洗={'是' if record.is_washed else '否'}")
                    result = VehicleWashDetectionResult(
                        class_name="vehicle",
                        confidence=1.0,
                        bbox=record.last_bbox or (0, 0, 0, 0),
                        plate_text=record.license_plate,
                        vehicle_id=record.vehicle_id,
                        event_type='exit'
                    )
                    results.append(result)
            else:
                # 输出当前 left_disappear_time 状态
                if self.entry_exit_mgr.left_disappear_time:
                    logger.info(f"[出场] 左侧消失等待中: {dict((k, f'{(datetime.now()-v).total_seconds():.0f}秒') for k,v in self.entry_exit_mgr.left_disappear_time.items())}")

            # === 步骤8: 定期输出完整统计（每30帧）===
            if self.frame_count % 30 == 0:
                self._log_statistics()

        except Exception as e:
            import traceback
            logger.error(f"车辆清洗检测异常: {e}")
            logger.error(f"异常详情: {traceback.format_exc()}")

        return results

    def draw_results(self, frame: np.ndarray, results: List[VehicleWashDetectionResult]) -> np.ndarray:
        """在帧上绘制检测结果"""
        output = frame.copy()

        for result in results:
            x1, y1, x2, y2 = result.bbox

            if result.event_type == 'entry':
                color = (0, 255, 0)
            elif result.event_type == 'exit':
                color = (0, 0, 255)
            elif result.event_type == 'wash_complete':
                color = (255, 165, 0)
            elif result.event_type == 'wash_start':
                color = (0, 255, 255)
            else:
                color = (255, 255, 0)

            cv2.rectangle(output, (x1, y1), (x2, y2), color, 2)

            labels = []
            if result.plate_text:
                labels.append(result.plate_text)
            if result.plate_color:
                labels.append(f"[{result.plate_color}]")
            if result.event_type:
                labels.append(f"({result.event_type})")

            label = " ".join(labels) if labels else f"Vehicle {result.vehicle_id}"

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
        stats = self.entry_exit_mgr.get_statistics()
        stats_text = (f"Entries: {stats['total_entries']} | "
                     f"Exits: {stats['total_exits']} | "
                     f"Washed: {stats['washed_count']} | "
                     f"Active: {stats['active_vehicles']}")
        cv2.putText(output, stats_text, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        return output

    def check_violations(self, results: List[VehicleWashDetectionResult]) -> List[Dict]:
        """检查违规（未清洗出场）"""
        violations = []

        for result in results:
            if result.event_type == 'exit' and result.plate_text:
                record = self.entry_exit_mgr.get_record(result.plate_text)
                if record and not record.is_washed:
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

        overlay = frame.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), (255, 200, 100), -1)
        cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)

        cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 150, 50), 2)
        cv2.putText(frame, "WASH ZONE", (x1 + 5, y1 + 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 150, 50), 2)

    def _log_statistics(self):
        """输出完整统计信息（每30帧调用一次）"""
        mgr_stats = self.entry_exit_mgr.get_statistics()
        tracker_stats = self.tracker.get_statistics() if hasattr(self.tracker, 'get_statistics') else {}

        logger.info("=" * 70)
        logger.info(f"[统计报告] 帧 {self.frame_count}")
        logger.info(f"  视频处理: 总帧数={self.stats['total_frames']}, 总检测数={self.stats['total_detections']}")
        logger.info(f"  车牌识别: 有效={self.stats['valid_plates']}, 无效={self.stats['invalid_plates']}, "
                   f"总确认车辆={len(self.stats['confirmed_vehicles'])}")
        logger.info(f"  进出场: 进场={mgr_stats['total_entries']}, 出场={mgr_stats['total_exits']}, "
                   f"清洗完成={mgr_stats['washed_count']}")
        logger.info(f"  当前状态: 在场={mgr_stats['active_vehicles']}, 待出场={mgr_stats['pending_exit']}, "
                   f"清洗率={mgr_stats['wash_rate']*100:.1f}%")

        # 输出在场车辆列表
        active_records = self.entry_exit_mgr.get_active_records()
        if active_records:
            logger.info(f"  在场车辆 ({len(active_records)}辆):")
            for r in active_records:
                wash_info = ""
                if r.is_washed:
                    wash_info = " [已清洗]"
                elif r.wash_start_time:
                    elapsed = (datetime.now() - r.wash_start_time).total_seconds()
                    wash_info = f" [清洗中 {elapsed:.0f}s/{self.entry_exit_mgr.wash_stop_time}s]"
                re_tag = " [二次进场]" if r.is_reentry else ""
                logger.info(f"    - {r.license_plate}{wash_info}{re_tag}")
        else:
            logger.info("  在场车辆: 无")

        # 输出已确认车牌列表
        if self.stats['confirmed_vehicles']:
            logger.info(f"  已确认车牌: {', '.join(sorted(self.stats['confirmed_vehicles']))}")
        logger.info("=" * 70)

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return self.entry_exit_mgr.get_statistics()

    def get_active_vehicles(self) -> List[Dict]:
        """获取在场车辆"""
        return self.entry_exit_mgr.get_active_records()
