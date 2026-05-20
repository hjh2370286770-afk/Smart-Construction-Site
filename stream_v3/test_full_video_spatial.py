"""
车辆清洗检测器 V3 - 多线程测试
- 进场：首次检测到车牌号
- 出场：车辆从画面左侧完整离开超过1分钟
- 二次进场：出场后再次出现，创建新记录
- 清洗：在清洗区域停止超过3分钟（离开或移动则重置计时）
- MySQL数据库持久化存储
"""

import sys
import cv2
import time
import threading
import queue
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np

log_file = open('full_video_test_v3.log', 'w', encoding='utf-8')

def log(msg, end='\n'):
    timestamp = datetime.now().strftime('%H:%M:%S')
    line = f"[{timestamp}] {msg}"
    try:
        print(line, end=end, flush=True)
    except Exception:
        print(line.encode('gbk', errors='ignore').decode('gbk'), end=end, flush=True)
    log_file.write(line + end)
    log_file.flush()

log("=" * 70)
log("车辆清洗检测器 V3 - 多线程测试")
log("进场: 首次检测到车牌 | 出场: 左侧离开1分钟 | 清洗: 停止3分钟")
log("=" * 70)

VIDEO_PATH = r"D:\Users\Admini503\OneDrive\Desktop\文件\视觉识别\微信视频2026-04-23_090043_727.mp4"

video_path = Path(VIDEO_PATH)
if not video_path.exists():
    log(f"Error: Video file not found: {VIDEO_PATH}")
    log_file.close()
    sys.exit(1)

log(f"\nVideo: {VIDEO_PATH}")
log(f"Size: {video_path.stat().st_size / 1024 / 1024:.1f} MB")

cap = cv2.VideoCapture(str(video_path))
if not cap.isOpened():
    log("Error: Cannot open video")
    log_file.close()
    sys.exit(1)

fps = cap.get(cv2.CAP_PROP_FPS)
frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

log(f"Video Info:")
log(f"  Resolution: {width}x{height}")
log(f"  FPS: {fps:.1f}")
log(f"  Total frames: {frame_count}")
log(f"  Duration: {frame_count/fps:.1f}s")

DETECT_WIDTH = 1280
DETECT_HEIGHT = int(height * DETECT_WIDTH / width)
detect_scale = width / DETECT_WIDTH

log(f"\nDetection Settings:")
log(f"  Vehicle detection resolution: {DETECT_WIDTH}x{DETECT_HEIGHT}")
log(f"  Scale factor: {detect_scale:.2f}x")
log(f"  Plate detection: Original resolution ({width}x{height})")

log("\nLoading detector...")
log("  Step 1/2: Import modules...", end=' ')
try:
    from detectors.vehicle_wash_detector import VehicleWashDetector, VehicleRecord
    from detectors.plate_utils import validate_and_filter_plate
    log("OK")

    log("  Step 2/2: Initialize detector...", end=' ')
    detector_config = {
        'path': 'yolov8n.pt',
        'device': 'cuda',
        'conf_threshold': 0.35,
        'iou_threshold': 0.45,
        'img_size': 640,

        'wash_stop_time': 180,
        'wash_zone': {
            'x1': 0.1, 'y1': 0.3,
            'x2': 0.7, 'y2': 0.8
        },

        'exit_left_threshold': 0.05,
        'exit_wait_time': 60,

        'track_iou_threshold': 0.5,
        'max_lost_frames': 30,

        'save_images': True,
        'image_save_path': 'storage/full_video_test_v3',

        'database': {
            'enabled': False,
            'host': 'localhost',
            'port': 3306,
            'user': 'root',
            'password': 'password',
            'database': 'vehicle_wash_db',
            'table_name': 'vehicle_wash_records',
        }
    }

    detector = VehicleWashDetector(detector_config)
    log("OK")

    if detector.plate_detector is not None:
        log("    - YOLOv8 plate model loaded")
    else:
        log("    - WARNING: Plate detector not loaded!")

    log("\nDetector V3 initialized:")
    log(f"  Wash stop time: {detector.wash_stop_time}s")
    log(f"  Exit wait time: {detector.exit_wait_time}s")
    log(f"  Wash zone: {detector.wash_zone}")
    log(f"  Exit left threshold: {detector.exit_left_threshold}")

except Exception as e:
    log(f"Error: Failed to load detector: {e}")
    import traceback
    traceback.print_exc()
    log_file.close()
    sys.exit(1)

output_dir = Path("storage/full_video_test_v3")
output_dir.mkdir(parents=True, exist_ok=True)
output_path = output_dir / "output.mp4"

log("\nInitializing multi-threading architecture...")

frame_queue = queue.Queue(maxsize=5)
detect_queue = queue.Queue(maxsize=5)
result_queue = queue.Queue(maxsize=5)

stop_event = threading.Event()
frame_idx = 0
processed_frames = 0
lock = threading.Lock()

stats = {
    'total_frames': 0,
    'processed_frames': 0,
    'detect_times': [],
    'plate_times': [],
    'start_time': time.time(),
    'total_detections': 0,
    'entries': 0,
    'exits': 0,
    'washed': 0,
    'reentries': 0,
}

def video_reader_thread():
    global frame_idx
    log("[Video Reader] Started")

    while not stop_event.is_set():
        ret, frame = cap.read()
        if not ret:
            log("[Video Reader] Video ended")
            break

        try:
            frame_queue.put((frame_idx, frame), block=False)
        except queue.Full:
            try:
                frame_queue.get_nowait()
                frame_queue.put((frame_idx, frame), block=False)
            except Exception:
                pass

        with lock:
            frame_idx += 1
            stats['total_frames'] = frame_idx

    log("[Video Reader] Stopped")

def vehicle_detection_thread():
    log("[Vehicle Detector] Started")

    while not stop_event.is_set():
        try:
            idx, original_frame = frame_queue.get(timeout=0.1)
        except queue.Empty:
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
            stats['detect_times'].append(detect_time)
            if len(stats['detect_times']) > 100:
                stats['detect_times'].pop(0)
            stats['total_detections'] += len(detections)

        try:
            detect_queue.put(
                (idx, original_frame, detections, detect_time),
                block=False
            )
        except queue.Full:
            try:
                detect_queue.get_nowait()
                detect_queue.put(
                    (idx, original_frame, detections, detect_time),
                    block=False
                )
            except Exception:
                pass

    log("[Vehicle Detector] Stopped")

def tracking_and_plate_thread():
    log("[Tracking & Plate] Started")

    while not stop_event.is_set():
        try:
            idx, frame, detections, detect_time = detect_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        start_time = time.time()

        updated_records = detector.track_and_update(frame, detections)
        plate_time = time.time() - start_time

        with lock:
            stats['plate_times'].append(plate_time)
            if len(stats['plate_times']) > 100:
                stats['plate_times'].pop(0)

            for record in updated_records:
                if record.exit_time is not None:
                    stats['exits'] += 1
                    if record.is_washed:
                        stats['washed'] += 1
                    reentry_tag = " [二次进场]" if record.is_reentry else ""
                    log(f"[EXIT] 车牌={record.license_plate}, "
                        f"停留={record.dwell_time:.0f}s, "
                        f"清洗={'是' if record.is_washed else '否'}"
                        f"{reentry_tag}")

        try:
            result_queue.put(
                (idx, frame, detections, updated_records, detect_time, plate_time),
                block=False
            )
        except queue.Full:
            try:
                result_queue.get_nowait()
                result_queue.put(
                    (idx, frame, detections, updated_records, detect_time, plate_time),
                    block=False
                )
            except Exception:
                pass

    log("[Tracking & Plate] Stopped")

def result_processing_thread():
    global processed_frames
    log("[Result Processor] Started")

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    frame_count = 0
    last_log_time = time.time()

    while not stop_event.is_set():
        try:
            (idx, frame, detections, updated_records,
             detect_time, plate_time) = result_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        result_frame = detector.draw_results(frame, detections, updated_records)

        det_stats = detector.get_statistics()

        info_text = [
            f"Frame: {idx}",
            f"FPS: {processed_frames / max(1, time.time() - stats['start_time']):.1f}",
            f"Detect: {detect_time*1000:.0f}ms",
            f"Track+Plate: {plate_time*1000:.0f}ms",
            f"Entries: {det_stats['total_entries']}",
            f"Exits: {det_stats['total_exits']}",
            f"Washed: {det_stats['washed_count']}",
            f"Active: {det_stats['active_vehicles']}",
            f"Pending Exit: {det_stats['pending_exit']}",
        ]

        y_offset = 30
        for text in info_text:
            cv2.putText(result_frame, text, (width - 350, y_offset),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            y_offset += 25

        active_records = detector.get_active_records()
        if active_records:
            y_offset = height - 30 * len(active_records) - 10
            for record in active_records[-5:]:
                status = "WASHED" if record.is_washed else (
                    f"Wash:{(datetime.now() - record.wash_start_time).total_seconds():.0f}s"
                    if record.wash_start_time else "ACTIVE"
                )
                reentry_tag = " [RE]" if record.is_reentry else ""
                info = f"{record.license_plate} {status}{reentry_tag}"
                color = (0, 200, 255) if record.is_washed else (
                    (0, 255, 255) if record.wash_start_time else (0, 255, 0)
                )
                cv2.putText(result_frame, info, (10, y_offset),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                y_offset += 25

        out.write(result_frame)

        if frame_count % 3 == 0:
            display_frame = cv2.resize(result_frame, (1280, 720))
            cv2.imshow("Vehicle Wash Detection V3", display_frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                log("[Result Processor] User pressed Q to exit")
                stop_event.set()
                break
            elif key == ord('p'):
                log("[Result Processor] Paused, press any key to continue...")
                cv2.waitKey(0)

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
                det_stats = detector.get_statistics()

            log(f"[Stats] Frames: {proc}/{total}, FPS: {avg_fps:.1f}, "
                f"Entries: {det_stats['total_entries']}, "
                f"Exits: {det_stats['total_exits']}, "
                f"Washed: {det_stats['washed_count']}, "
                f"Active: {det_stats['active_vehicles']}, "
                f"Pending: {det_stats['pending_exit']}")
            last_log_time = current_time

    out.release()
    cv2.destroyAllWindows()
    log("[Result Processor] Stopped")

log("\nStarting threads...")
threads = []

t1 = threading.Thread(target=video_reader_thread, name="VideoReader")
t2 = threading.Thread(target=vehicle_detection_thread, name="VehicleDetector")
t3 = threading.Thread(target=tracking_and_plate_thread, name="TrackingPlate")
t4 = threading.Thread(target=result_processing_thread, name="ResultProcessor")

threads = [t1, t2, t3, t4]

for t in threads:
    t.daemon = True
    t.start()

log("All threads started (4 core threads)")
log("-" * 70)

try:
    for t in threads:
        t.join()
except KeyboardInterrupt:
    log("\nUser interrupted")
    stop_event.set()

log("\n" + "=" * 70)
log("PROCESSING COMPLETED!")
log("=" * 70)

det_stats = detector.get_statistics()
active_records = detector.get_active_records()
completed_records = detector.get_completed_records()

with lock:
    total_frames = frame_idx
    processed = processed_frames
    elapsed = time.time() - stats['start_time']
    final_fps = processed / elapsed if elapsed > 0 else 0

log(f"\nPerformance:")
log(f"  Total frames: {total_frames}")
log(f"  Processed frames: {processed} ({processed/total_frames*100:.1f}%)")
log(f"  Average FPS: {final_fps:.1f}")

log(f"\nDetection Results:")
log(f"  Total entries: {det_stats['total_entries']}")
log(f"  Total exits: {det_stats['total_exits']}")
log(f"  Washed: {det_stats['washed_count']}")
log(f"  Wash rate: {det_stats['wash_rate']:.1%}")
log(f"  Active vehicles: {det_stats['active_vehicles']}")

if completed_records:
    log(f"\nCompleted Records ({len(completed_records)}):")
    for i, record in enumerate(completed_records, 1):
        reentry_tag = " [二次进场]" if record.is_reentry else ""
        log(f"  {i}. 车牌={record.license_plate}, "
            f"停留={record.dwell_time:.0f}s, "
            f"清洗={'是' if record.is_washed else '否'}"
            f"{reentry_tag}")

if active_records:
    log(f"\nActive Records ({len(active_records)}):")
    for i, record in enumerate(active_records, 1):
        dwell = (datetime.now() - record.entry_time).total_seconds()
        wash_info = ""
        if record.is_washed:
            wash_info = ", 已清洗"
        elif record.wash_start_time:
            wash_elapsed = (datetime.now() - record.wash_start_time).total_seconds()
            wash_info = f", 清洗中:{wash_elapsed:.0f}s/{detector.wash_stop_time}s"
        reentry_tag = " [二次进场]" if record.is_reentry else ""
        log(f"  {i}. 车牌={record.license_plate}, "
            f"在场={dwell:.0f}s{wash_info}{reentry_tag}")

log(f"\nOutput video: {output_path}")
log("=" * 70)

cap.release()
log_file.close()
