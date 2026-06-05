"""
车辆清洗检测 V3 - 文件模式（无数据库）
基于 test_full_video.py 的副本
修改：使用本地视频文件，不写入数据库
"""

import sys
import cv2
import time
import threading
import queue
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np

log_file = open('test_video_file.log', 'w', encoding='utf-8')

def log(msg, end='\n'):
    timestamp = datetime.now().strftime('%H:%M:%S')
    line = f"[{timestamp}] {msg}"
    try:
        print(line, end=end, flush=True)
    except:
        print(line.encode('gbk', errors='ignore').decode('gbk'), end=end, flush=True)
    log_file.write(line + end)
    log_file.flush()

# ============================================================
# 进出场 + 清洗判定
# ============================================================

@dataclass
class VehicleRecord:
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


class EntryExitManager:
    """进出场 + 清洗判定管理器 (方案2: 强车牌合并)"""

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

        # 车牌变体映射: 变体 -> 主车牌
        self.plate_variants: Dict[str, str] = {}

    def set_db(self, db):
        self.db = db

    def _plate_similarity(self, p1: str, p2: str) -> float:
        """计算两个车牌的相似度 (使用统一缓存实现)"""
        from plate_utils import plate_similarity
        return plate_similarity(p1, p2)

    def _find_similar_record(self, plate: str) -> Optional[str]:
        """查找与给定车牌相似的已有记录"""
        # 先检查变体映射
        if plate in self.plate_variants:
            return self.plate_variants[plate]

        best_match = None
        best_sim = self.plate_merge_threshold

        # 与所有在场记录比较
        for existing_plate, record in self.records.items():
            if record.exit_time is not None:
                continue  # 已出场的不再合并
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

        # 方案2核心: 查找相似记录
        similar_plate = self._find_similar_record(plate)

        if similar_plate and similar_plate in self.records:
            # 合并到已有记录
            record = self.records[similar_plate]

            # 如果当前车牌更"标准"（长度更接近7位），更新主车牌
            if abs(len(plate) - 7) < abs(len(similar_plate) - 7):
                # 迁移记录到新车牌键
                old_plate = similar_plate
                self.records[plate] = record
                record.license_plate = plate
                del self.records[old_plate]

                # 更新变体映射
                self.plate_variants[old_plate] = plate
                self.plate_variants[plate] = plate

                log(f"车牌更新: {old_plate} -> {plate}")
                similar_plate = plate

            # 记录变体映射
            if plate != similar_plate:
                self.plate_variants[plate] = similar_plate
                log(f"车牌合并: {plate} -> {similar_plate} (similarity: {self._plate_similarity(plate, similar_plate):.2f})")

            # 更新位置信息
            record.last_bbox = bbox
            record.last_seen = current_time
            record.position_history.append((center_x, center_y))
            if len(record.position_history) > 60:
                record.position_history = record.position_history[-30:]

            # 清洗判定 - 修复重复重置问题
            if not record.is_washed:
                in_wash_zone = self._is_in_wash_zone(bbox, frame_width, frame_height)
                is_stopped = self._is_vehicle_stopped(similar_plate)

                if in_wash_zone and is_stopped:
                    if record.wash_start_time is None:
                        record.wash_start_time = current_time
                        log(f"车辆进入清洗区域并停止: 车牌={similar_plate}")
                    else:
                        stop_duration = (current_time - record.wash_start_time).total_seconds()
                        if stop_duration >= self.wash_stop_time:
                            record.is_washed = True
                            log(f"★ 车辆清洗完成: 车牌={similar_plate}, 停止时间={stop_duration:.0f}秒")
                else:
                    # 只有在真正离开区域或移动时才重置
                    if record.wash_start_time is not None:
                        if not in_wash_zone:
                            log(f"车辆离开清洗区域，计时重置: 车牌={similar_plate}")
                            record.wash_start_time = None
                        elif not is_stopped:
                            # 检查是否真的在移动（不是微小抖动）
                            if len(record.position_history) >= 10:
                                recent = record.position_history[-10:]
                                xs = [p[0] for p in recent]
                                ys = [p[1] for p in recent]
                                x_range = max(xs) - min(xs)
                                y_range = max(ys) - min(ys)
                                # 只有移动超过阈值才重置
                                if x_range > 50 or y_range > 50:
                                    log(f"车辆在清洗区域移动，计时重置: 车牌={similar_plate} (移动: {x_range:.0f}, {y_range:.0f})")
                                    record.wash_start_time = None

            # 出场检测
            if self._is_near_left_edge(bbox, frame_width):
                if similar_plate not in self.left_disappear_time:
                    self.left_disappear_time[similar_plate] = current_time
                    log(f"车辆到达画面左侧: 车牌={similar_plate}")
            else:
                if similar_plate in self.left_disappear_time:
                    del self.left_disappear_time[similar_plate]

            return record

        # 检查是否是二次进场
        if similar_plate and similar_plate in self.exited_plates:
            is_reentry = True
            del self.exited_plates[similar_plate]
            log(f"车辆二次进场: 车牌={plate} (匹配已出场记录: {similar_plate})")
            # 使用已出场的车牌作为主记录
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
        log(f"★ 车辆{entry_type}: ID={record.vehicle_id}, 车牌={plate}")

        return record

    def check_exits(self, frame_shape: Tuple):
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

                    updated.append(record)
                    log(f"★ 车辆出场: 车牌={plate}, 停留={record.dwell_time:.0f}秒, "
                        f"清洗={'是' if record.is_washed else '否'}")

                    del self.left_disappear_time[plate]

        return updated

    def check_missing_vehicles(self, confirmed_plates: List[str], frame_shape: Tuple):
        current_time = datetime.now()
        frame_height, frame_width = frame_shape[:2]

        for plate, record in self.records.items():
            if record.exit_time is not None:
                continue

            # 检查该记录的主车牌或其变体是否在当前帧被确认
            is_confirmed_this_frame = False
            for cp in confirmed_plates:
                if cp == plate or self.plate_variants.get(cp) == plate:
                    is_confirmed_this_frame = True
                    break
            if is_confirmed_this_frame:
                continue

            if record.last_bbox and self._is_near_left_edge(record.last_bbox, frame_width):
                if plate not in self.left_disappear_time:
                    self.left_disappear_time[plate] = current_time
                    log(f"车辆从左侧消失: 车牌={plate}")

    def _is_in_wash_zone(self, bbox, frame_width, frame_height):
        x1, y1, x2, y2 = bbox
        center_x = (x1 + x2) / 2 / frame_width
        center_y = (y1 + y2) / 2 / frame_height
        zone = self.wash_zone
        return (zone['x1'] <= center_x <= zone['x2'] and
                zone['y1'] <= center_y <= zone['y2'])

    def _is_vehicle_stopped(self, plate):
        record = self.records.get(plate)
        if not record or len(record.position_history) < 10:
            return False
        recent = record.position_history[-10:]
        xs = [p[0] for p in recent]
        ys = [p[1] for p in recent]
        return (max(xs) - min(xs)) < 30 and (max(ys) - min(ys)) < 30

    def _is_near_left_edge(self, bbox, frame_width):
        x1, y1, x2, y2 = bbox
        return x2 < frame_width * self.exit_left_threshold

    def get_active_records(self):
        return [r for r in self.records.values() if r.exit_time is None]

    def get_completed_records(self):
        return [r for r in self.records.values() if r.exit_time is not None]

    def get_statistics(self):
        return {
            'total_entries': self.total_entries,
            'total_exits': self.total_exits,
            'washed_count': self.washed_count,
            'active_vehicles': len(self.get_active_records()),
            'pending_exit': len(self.left_disappear_time),
            'wash_rate': self.washed_count / self.total_exits if self.total_exits > 0 else 0,
        }


# ============================================================
# 主程序
# ============================================================

log("=" * 70)
log("车辆清洗检测 V3 - 文件模式（无数据库）")
log("=" * 70)

# 视频源配置：本地视频文件
VIDEO_PATH = r"C:\Users\Admini503\OneDrive\文档\xwechat_files\wxid_je5m1ms8edvj22_dcf2\msg\video\2026-05\3142ea242af10c9dbabe37d1dbafb51d_raw.mp4"

IS_STREAM = VIDEO_PATH.startswith(('rtmp://', 'rtsp://', 'http://', 'https://'))

log(f"\nVideo Source: {VIDEO_PATH}")
if not IS_STREAM:
    video_path = Path(VIDEO_PATH)
    if not video_path.exists():
        log(f"Error: Video file not found: {VIDEO_PATH}")
        log_file.close()
        sys.exit(1)
    log(f"Size: {video_path.stat().st_size / 1024 / 1024:.1f} MB")

cap = cv2.VideoCapture(VIDEO_PATH)
if not cap.isOpened():
    log("Error: Cannot open video source")
    log_file.close()
    sys.exit(1)

fps = cap.get(cv2.CAP_PROP_FPS)
frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

# 流模式下fps可能为0，使用默认值
if fps <= 0:
    fps = 25.0
    log("[Stream] FPS not provided by source, using default 25.0")

frame_interval = 1.0 / fps

log(f"Video Info:")
log(f"  Resolution: {width}x{height}")
log(f"  FPS: {fps:.1f}")
if not IS_STREAM and frame_count > 0:
    log(f"  Total frames: {frame_count}")
    log(f"  Duration: {frame_count/fps:.1f}s")
else:
    log(f"  Mode: Live stream")

DETECT_WIDTH = 1280
DETECT_HEIGHT = int(height * DETECT_WIDTH / width)
detect_scale = width / DETECT_WIDTH

log(f"\nDetection Settings:")
log(f"  Vehicle detection: {DETECT_WIDTH}x{DETECT_HEIGHT}")
log(f"  Plate detection: Original ({width}x{height})")

# ============================================================
# 加载检测器
# ============================================================

log("\nLoading detector...")
try:
    from vehicle_wash_detector import VehicleWashDetector
    from spatial_plate_deduplicator import SpatialPlateDeduplicator
    from plate_utils import validate_and_filter_plate
    from plate_validator_v2 import validate_plate_v2
    from vehicle_tracker import VehicleTracker
    log("  Import OK")

    detector_config = {
        'path': str(Path(__file__).parent.parent / 'models' / 'yolov8n.pt'),
        'device': 'cuda',
        'conf_threshold': 0.35,
        'iou_threshold': 0.45,
        'img_size': 640,
    }

    detector = VehicleWashDetector(detector_config)
    log("  Detector OK")

    if detector.plate_detector is not None:
        log("  YOLOv8 plate model loaded")
    else:
        log("  WARNING: Plate detector not loaded!")

    spatial_dedup = SpatialPlateDeduplicator(
        spatial_threshold=80.0,
        time_window=12.0,
        min_detections=10,
        min_plate_agreement=0.80,
        plate_similarity_threshold=0.90
    )
    log("  Spatial dedup: spatial=80px, min_detections=10, agreement=0.80, similarity=0.90")

    entry_exit_mgr = EntryExitManager(
        wash_stop_time=180,
        exit_wait_time=60,
        exit_left_threshold=0.05,
        wash_zone={'x1': 0.1, 'y1': 0.3, 'x2': 0.7, 'y2': 0.8},
        plate_merge_threshold=0.60
    )
    log("  Entry/Exit: exit_wait=60s, wash_stop=180s, plate_merge=0.60")

    vehicle_tracker = VehicleTracker(
        iou_threshold=0.3,
        max_miss_frames=5,
        exit_left_threshold=0.05
    )
    log("  Vehicle Tracker: IOU=0.3, max_miss=5 frames")

    # 禁用数据库
    log("  Database: DISABLED (no DB writes)")

except Exception as e:
    log(f"Error: {e}")
    import traceback
    traceback.print_exc()
    log_file.close()
    sys.exit(1)

# ============================================================
# 多线程架构
# ============================================================

frame_queue = queue.Queue(maxsize=30)
detect_queue = queue.Queue(maxsize=30)
result_queue = queue.Queue(maxsize=30)

stop_event = threading.Event()
frame_idx = 0
processed_frames = 0
lock = threading.Lock()

stats = {
    'total_frames': 0,
    'start_time': time.time(),
    'total_detections': 0,
    'valid_plates': 0,
    'invalid_plates': 0,
    'confirmed_vehicles': set(),
}

def video_reader_thread():
    global frame_idx
    log("[Video Reader] Started (FILE MODE)")
    next_frame_time = time.time()
    consecutive_failures = 0

    while not stop_event.is_set():
        ret, frame = cap.read()
        if not ret:
            consecutive_failures += 1
            if IS_STREAM and consecutive_failures < 10:
                log(f"[Video Reader] Frame read failed ({consecutive_failures}/10), retrying...")
                time.sleep(0.5)
                continue
            else:
                if IS_STREAM:
                    log("[Video Reader] Stream disconnected after 10 retries")
                else:
                    log("[Video Reader] Video ended")
                break
        
        consecutive_failures = 0

        try:
            frame_queue.put((frame_idx, frame), block=True, timeout=1.0)
        except queue.Full:
            log("[Video Reader] Frame queue full, dropping frame")
            continue

        with lock:
            frame_idx += 1
            stats['total_frames'] = frame_idx

        next_frame_time += frame_interval
        sleep_time = next_frame_time - time.time()
        if sleep_time > 0:
            time.sleep(sleep_time)

    log("[Video Reader] Stopped")

def vehicle_detection_thread():
    log("[Vehicle Detector] Started")

    while not stop_event.is_set():
        if stop_event.is_set():
            break
            
        try:
            idx, original_frame = frame_queue.get(timeout=0.2)
        except queue.Empty:
            if stop_event.is_set():
                break
            continue

        start_time = time.time()

        detect_frame = cv2.resize(
            original_frame, (DETECT_WIDTH, DETECT_HEIGHT),
            interpolation=cv2.INTER_LINEAR
        )

        detections = detector.detect(detect_frame)
        detect_time = time.time() - start_time

        for det in detections:
            x1, y1, x2, y2 = det.bbox
            det.bbox = (
                int(x1 * detect_scale),
                int(y1 * detect_scale),
                int(x2 * detect_scale),
                int(y2 * detect_scale)
            )

        with lock:
            stats['total_detections'] += len(detections)

        detect_queue.put(
            (idx, original_frame, detections, detect_time),
            block=True
        )

    log("[Vehicle Detector] Stopped")

def plate_detection_worker(args):
    original_frame, detection, idx = args
    x1, y1, x2, y2 = detection.bbox
    vehicle_roi = original_frame[y1:y2, x1:x2]

    if vehicle_roi.size == 0 or vehicle_roi.shape[0] < 20 or vehicle_roi.shape[1] < 50:
        return None

    plate_result = detector.detect_license_plate(original_frame, detection.bbox)

    if plate_result and plate_result[0]:
        plate_text, plate_bbox, plate_color, color_conf = plate_result
        
        # 使用V2验证器（基于颜色）
        is_valid, cleaned, reason = validate_plate_v2(plate_text, plate_color, color_conf)
        
        if not is_valid:
            # V2验证失败，尝试V1验证器作为后备
            is_valid_v1, reason_v1, cleaned_v1 = validate_and_filter_plate(plate_text)
            if is_valid_v1 and cleaned_v1:
                is_valid = True
                cleaned = cleaned_v1
                reason = reason_v1 + " (V1 fallback)"
        
        if is_valid and cleaned:
            confirmed_vehicle = spatial_dedup.add_detection(
                frame_idx=idx,
                bbox=detection.bbox,
                plate_text=cleaned,
                plate_bbox=plate_bbox,
                confidence=detection.confidence,
                plate_color=plate_color,
                color_conf=color_conf
            )

            if confirmed_vehicle:
                return {
                    'detection': detection,
                    'plate_text': confirmed_vehicle['plate_number'],
                    'plate_bbox': plate_bbox,
                    'vehicle_id': confirmed_vehicle['vehicle_id'],
                    'confidence': confirmed_vehicle['confidence'],
                    'is_confirmed': True,
                    'plate_color': plate_color,
                    'color_conf': color_conf
                }
            else:
                return {
                    'detection': detection,
                    'plate_text': cleaned,
                    'plate_bbox': plate_bbox,
                    'vehicle_id': None,
                    'confidence': 0,
                    'is_confirmed': False,
                    'plate_color': plate_color,
                    'color_conf': color_conf
                }

    return None

def plate_detection_thread():
    log("[Plate Detector] Started (with tracking + spatial deduplication)")

    with ThreadPoolExecutor(max_workers=4) as executor:
        while not stop_event.is_set():
            if stop_event.is_set():
                break

            try:
                idx, frame, detections, detect_time = detect_queue.get(timeout=0.2)
            except queue.Empty:
                if stop_event.is_set():
                    break
                continue

            start_time = time.time()

            # === 步骤1: 更新车辆跟踪（所有检测到的车辆，不依赖车牌）===
            tracked_objects = []
            if detections:
                tracked_objects = vehicle_tracker.update(detections, idx, frame.shape)

            # === 步骤2: 车牌识别（只处理有车牌的）===
            plate_results = []
            confirmed_plates_this_frame = []
            valid_count = 0
            invalid_count = 0

            # 建立检测到跟踪的映射
            det_to_track = {}
            for track in tracked_objects:
                # 找到对应的检测（通过bbox匹配）
                for i, det in enumerate(detections):
                    if track.bbox == det.bbox:
                        det_to_track[i] = track.track_id
                        break

            if detections:
                futures = []
                det_indices = []
                for i, det in enumerate(detections):
                    future = executor.submit(plate_detection_worker, (frame, det, idx))
                    futures.append(future)
                    det_indices.append(i)

                for future, det_idx in zip(futures, det_indices):
                    try:
                        result = future.result(timeout=10.0)

                        if result:
                            # 关联车牌到跟踪ID
                            track_id = det_to_track.get(det_idx)
                            if track_id and result.get('plate_text'):
                                vehicle_tracker.associate_plate(
                                    track_id, result['plate_text'],
                                    result.get('confidence', 0)
                                )

                            if result['is_confirmed']:
                                plate_results.append(result)
                                valid_count += 1
                                confirmed_plates_this_frame.append(result['plate_text'])

                                with lock:
                                    if result['plate_text'] not in stats['confirmed_vehicles']:
                                        stats['confirmed_vehicles'].add(result['plate_text'])
                                        color_info = f""
                                        if result.get('plate_color'):
                                            color_info = f", 颜色:{result['plate_color']}"
                                        log(f"[Vehicle ✓#{result['vehicle_id']}] Confirmed: {result['plate_text']} "
                                            f"(conf: {result['confidence']:.1%}{color_info})")

                                entry_exit_mgr.on_plate_confirmed(
                                    result['plate_text'], result['detection'].bbox, frame.shape
                                )
                            else:
                                invalid_count += 1

                    except Exception as e:
                        log(f"[Plate Detection] Error: {e}")

                with lock:
                    stats['valid_plates'] += valid_count
                    stats['invalid_plates'] += invalid_count

            # === 步骤3: 检查出场（基于跟踪器）===
            exited_tracks = vehicle_tracker.get_exited_tracks()
            for track in exited_tracks:
                if track.plate_text and track.plate_text in entry_exit_mgr.records:
                    record = entry_exit_mgr.records[track.plate_text]
                    if record.exit_time is None:
                        # 标记出场
                        from datetime import datetime
                        record.exit_time = datetime.now()
                        record.dwell_time = (record.exit_time - record.entry_time).total_seconds()
                        entry_exit_mgr.total_exits += 1
                        if record.is_washed:
                            entry_exit_mgr.washed_count += 1
                        entry_exit_mgr.exited_plates[track.plate_text] = record.exit_time
                        log(f"★ 车辆出场(跟踪): 车牌={track.plate_text}, 跟踪ID={track.track_id}")

            entry_exit_mgr.check_missing_vehicles(confirmed_plates_this_frame, frame.shape)
            entry_exit_mgr.check_exits(frame.shape)

            plate_time = time.time() - start_time

            # === 传递所有跟踪对象到显示线程 ===
            result_queue.put(
                (idx, frame, plate_results, detect_time, plate_time, tracked_objects),
                block=True
            )

    log("[Plate Detector] Stopped")

# 显示队列 - 用于线程间传递显示帧
display_queue = queue.Queue(maxsize=2)

def display_thread():
    """独立显示线程 - 不阻塞主处理流水线"""
    log("[Display] Started")
    window_name = "Vehicle Wash V3 (FILE MODE)"
    
    while not stop_event.is_set():
        # 先检查stop_event，避免不必要的队列等待
        if stop_event.is_set():
            break
            
        try:
            display_frame = display_queue.get(timeout=0.05)
        except queue.Empty:
            # 队列为空时仍然处理waitKey，让OpenCV有机会处理窗口事件
            if stop_event.is_set():
                break
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                log("[Display] User pressed Q")
                stop_event.set()
                break
            continue

        # 再次检查stop_event，避免在显示已停止的帧
        if stop_event.is_set():
            break
            
        cv2.imshow(window_name, display_frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            log("[Display] User pressed Q")
            stop_event.set()
            break
        elif key == ord('p'):
            cv2.waitKey(0)

    # 确保窗口关闭
    try:
        cv2.destroyWindow(window_name)
    except:
        pass
    cv2.destroyAllWindows()
    for _ in range(10):
        cv2.waitKey(1)
    log("[Display] Stopped")


def result_processing_thread():
    global processed_frames
    log("[Result Processor] Started (display separated)")

    frame_count = 0
    last_log_time = time.time()
    tracked_confirmed = {}
    skipped_frames = 0

    while not stop_event.is_set():
        # 快速检查stop_event
        if stop_event.is_set():
            break

        try:
            item = result_queue.get(timeout=0.2)
            # 兼容旧格式和新格式
            if len(item) == 5:
                idx, frame, plate_results, detect_time, plate_time = item
                tracked_objects = []
            else:
                idx, frame, plate_results, detect_time, plate_time, tracked_objects = item
        except queue.Empty:
            # 如果stop_event已设置且队列为空，退出循环
            if stop_event.is_set():
                break
            continue

        # 队列积压检测 - 如果显示队列满，跳过绘制直接处理
        skip_drawing = display_queue.full()
        if skip_drawing:
            skipped_frames += 1
            result_frame = frame  # 不复制，直接使用原帧
        else:
            result_frame = frame.copy()

        h, w = result_frame.shape[:2]

        # 只在需要显示时才绘制
        if not skip_drawing:
            zone = entry_exit_mgr.wash_zone
            zx1, zy1 = int(zone['x1'] * w), int(zone['y1'] * h)
            zx2, zy2 = int(zone['x2'] * w), int(zone['y2'] * h)
            cv2.rectangle(result_frame, (zx1, zy1), (zx2, zy2), (255, 255, 0), 2)
            cv2.putText(result_frame, "WASH ZONE", (zx1 + 5, zy1 + 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

            exit_x = int(w * entry_exit_mgr.exit_left_threshold)
            cv2.line(result_frame, (exit_x, 0), (exit_x, h), (0, 0, 255), 2)
            cv2.putText(result_frame, "EXIT", (5, h - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

            # === 绘制所有跟踪的车辆检测框 ===
            for track in tracked_objects:
                x1, y1, x2, y2 = track.bbox

                # 根据状态选择颜色
                if track.exit_detected:
                    color = (128, 128, 128)  # 灰色: 已出场
                    label = f"T{track.track_id}: EXITED"
                elif track.plate_text:
                    # 有车牌确认的车辆
                    if track.plate_text not in tracked_confirmed:
                        hash_val = hash(track.plate_text) % 0xFFFFFF
                        r = (hash_val >> 16) & 0xFF
                        g = (hash_val >> 8) & 0xFF
                        b = hash_val & 0xFF
                        color = (max(r, 80), max(g, 80), max(b, 80))
                        tracked_confirmed[track.plate_text] = color
                    else:
                        color = tracked_confirmed[track.plate_text]

                    record = entry_exit_mgr.records.get(track.plate_text)
                    if record:
                        if record.is_washed:
                            color = (0, 200, 255)
                        elif record.wash_start_time:
                            color = (0, 255, 255)

                    label = f"T{track.track_id}: {track.plate_text}"
                    if record and record.is_washed:
                        label += " WASHED"
                    elif record and record.wash_start_time:
                        elapsed = (datetime.now() - record.wash_start_time).total_seconds()
                        label += f" Wash:{elapsed:.0f}s"
                else:
                    # 未识别到车牌的车辆 - 使用青色显示
                    color = (0, 255, 255)
                    label = f"T{track.track_id}: {track.class_name}"

                cv2.rectangle(result_frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(result_frame, label, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            # === 绘制车牌识别结果（在车辆框内显示车牌框）===
            for result in plate_results:
                det = result['detection']
                if result.get('plate_bbox'):
                    px1, py1, px2, py2 = result['plate_bbox']
                    cv2.rectangle(result_frame, (px1, py1), (px2, py2), (0, 0, 255), 2)

            mgr_stats = entry_exit_mgr.get_statistics()
            tracker_stats = vehicle_tracker.get_statistics()
            video_elapsed = idx / fps
            video_min = int(video_elapsed // 60)
            video_sec = video_elapsed % 60

            with lock:
                unique_vehicles = len(stats['confirmed_vehicles'])

            info_text = [
                f"Video: {video_min:02d}:{video_sec:05.2f}",
                f"FPS: {processed_frames / max(1, time.time() - stats['start_time']):.1f}",
                f"Tracks: {tracker_stats['total_active']}",
                f"Confirmed: {unique_vehicles}",
                f"Entries: {mgr_stats['total_entries']}",
                f"Exits: {mgr_stats['total_exits']}",
                f"Washed: {mgr_stats['washed_count']}",
                f"Active: {mgr_stats['active_vehicles']}",
            ]
            y_offset = 30
            for text in info_text:
                cv2.putText(result_frame, text, (w - 300, y_offset),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                y_offset += 25

            # 每3帧发送一次到显示队列
            if frame_count % 3 == 0:
                try:
                    display_frame = cv2.resize(result_frame, (1280, 720))
                    display_queue.put(display_frame, block=False)
                except queue.Full:
                    pass  # 显示队列满，丢弃此帧

        frame_count += 1
        with lock:
            processed_frames += 1

        current_time = time.time()
        if current_time - last_log_time >= 5.0:
            with lock:
                total = stats['total_frames']
                proc = processed_frames
                elapsed = current_time - stats['start_time']
                avg_fps = proc / elapsed if elapsed > 0 else 0
                total_det = stats['total_detections']
                valid = stats['valid_plates']
                invalid = stats['invalid_plates']
                unique = len(stats['confirmed_vehicles'])
                mgr_stats = entry_exit_mgr.get_statistics()
                tracker_stats = vehicle_tracker.get_statistics()

            log(f"[Stats] Frames: {proc}/{total} ({proc/total*100:.1f}%), "
                f"FPS: {avg_fps:.1f}, "
                f"Video: {video_min:02d}:{video_sec:05.2f}, "
                f"Detections: {total_det}, Valid: {valid}, Invalid: {invalid}, "
                f"Tracks: {tracker_stats['total_active']}, "
                f"Confirmed: {unique}, "
                f"Entries: {mgr_stats['total_entries']}, "
                f"Exits: {mgr_stats['total_exits']}, "
                f"Washed: {mgr_stats['washed_count']}")
            if skip_drawing and skipped_frames > 0:
                log(f"[Warning] Skipped {skipped_frames} frames due to display backlog")
                skipped_frames = 0
            if stats['confirmed_vehicles']:
                log(f"[Plates] {', '.join(sorted(stats['confirmed_vehicles']))}")
            for r in entry_exit_mgr.get_active_records():
                wash_info = ""
                if r.is_washed:
                    wash_info = " WASHED"
                elif r.wash_start_time:
                    elapsed_w = (datetime.now() - r.wash_start_time).total_seconds()
                    wash_info = f" Wash:{elapsed_w:.0f}s/{entry_exit_mgr.wash_stop_time}s"
                re_tag = " [RE]" if r.is_reentry else ""
                log(f"  Active: {r.license_plate}{wash_info}{re_tag}")
            last_log_time = current_time

    log("[Result Processor] Stopped")

# ============================================================
# 启动
# ============================================================

log("\nStarting threads (FILE MODE)...")
log(f"  Frame interval: {frame_interval*1000:.1f}ms ({fps:.1f}fps)")

threads = [
    threading.Thread(target=video_reader_thread, name="VideoReader"),
    threading.Thread(target=vehicle_detection_thread, name="VehicleDetector"),
    threading.Thread(target=plate_detection_thread, name="PlateDetector"),
    threading.Thread(target=result_processing_thread, name="ResultProcessor"),
    threading.Thread(target=display_thread, name="Display"),
]

for t in threads:
    t.daemon = True
    t.start()

log("All threads started (5 threads)")
log("-" * 70)

try:
    if IS_STREAM:
        # 流模式：持续运行，等待用户中断
        log("[Main] Stream mode - running continuously. Press Ctrl+C to stop.")
        while True:
            time.sleep(1)
            if stop_event.is_set():
                break
    else:
        # 文件模式：等视频播放完
        threads[0].join(timeout=300.0)
        if threads[0].is_alive():
            log("[Main] VideoReader did not exit in time")
        
        if not stop_event.is_set():
            log("[Main] Video ended, signaling all threads to stop...")
            stop_event.set()
        
        for t in threads[1:]:
            t.join(timeout=5.0)
            if t.is_alive():
                log(f"[Main] Thread {t.name} did not exit in time")
            
except KeyboardInterrupt:
    log("\nUser interrupted")
    stop_event.set()

# 给所有线程一点时间处理停止信号
time.sleep(0.5)

# 强制关闭所有OpenCV窗口
cv2.destroyAllWindows()
for i in range(10):
    cv2.waitKey(1)

log("[Main] All windows closed")

# ============================================================
# 最终统计
# ============================================================

log("\n" + "=" * 70)
log("PROCESSING COMPLETED!")
log("=" * 70)

with lock:
    total_frames = frame_idx
    processed = processed_frames
    elapsed = time.time() - stats['start_time']
    total_det = stats['total_detections']
    valid = stats['valid_plates']
    invalid = stats['invalid_plates']
    confirmed_list = stats['confirmed_vehicles']

dedup_stats = spatial_dedup.get_statistics()
confirmed_vehicles_detail = spatial_dedup.get_confirmed_vehicles()
mgr_stats = entry_exit_mgr.get_statistics()

log(f"\nPerformance:")
log(f"  Total frames: {total_frames}")
if total_frames > 0:
    log(f"  Processed: {processed} ({processed/total_frames*100:.1f}%)")
if elapsed > 0:
    log(f"  Average FPS: {processed/elapsed:.1f}")
log(f"  Video duration: {total_frames/fps:.1f}s")
log(f"  Processing time: {elapsed:.1f}s")

log(f"\nDetection Results:")
log(f"  Total vehicle detections: {total_det}")
log(f"  Valid plates detected: {valid}")
log(f"  Invalid plates filtered: {invalid}")

log(f"\nSpatial Deduplication Statistics:")
log(f"  Tracks created: {dedup_stats['tracks_created']}")
log(f"  Active tracks: {dedup_stats['active_tracks']}")
log(f"  Vehicles confirmed: {len(confirmed_vehicles_detail)}")
log(f"  Plates merged: {dedup_stats['plates_merged']}")

log(f"\nFinal Confirmed Vehicles ({len(confirmed_vehicles_detail)}):")
if confirmed_vehicles_detail:
    for i, vehicle in enumerate(confirmed_vehicles_detail, 1):
        plate_num = vehicle['plate_number']
        # 获取车牌颜色和类型信息
        from plate_validator_v2 import PlateValidatorV2
        plate_info = PlateValidatorV2.get_plate_info(plate_num)
        color_str = plate_info.get('plate_color', '未知')
        type_str = plate_info.get('plate_type', '未知')
        
        log(f"  {i}. [ID:{vehicle['vehicle_id']}] {plate_num}")
        log(f"     颜色: {color_str}, 类型: {type_str}, 长度: {len(plate_num)}位")
        log(f"     Detections: {vehicle['detection_count']}, "
            f"Confidence: {vehicle['confidence']:.1%}")
        if vehicle.get('merged'):
            log(f"     Candidates: {vehicle.get('candidate_plates', {})}")
else:
    log("  No vehicles confirmed")

log(f"\nEntry/Exit Statistics:")
log(f"  Total entries: {mgr_stats['total_entries']}")
log(f"  Total exits: {mgr_stats['total_exits']}")