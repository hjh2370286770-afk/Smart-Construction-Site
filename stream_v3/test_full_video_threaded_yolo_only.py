"""
车辆清洗检测器 - YOLO-only高性能版本
优化策略:
1. 只使用YOLOv8进行车辆和车牌检测（不使用OCR）
2. 检测时使用降低分辨率的图像
3. 4个核心线程并行处理
4. 车牌检测使用专用YOLO模型
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

# Open log file with UTF-8 encoding
log_file = open('full_video_test_yolo_only.log', 'w', encoding='utf-8')

def log(msg, end='\n'):
    """Write to both console and file"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    line = f"[{timestamp}] {msg}"
    try:
        print(line, end=end, flush=True)
    except:
        print(line.encode('gbk', errors='ignore').decode('gbk'), end=end, flush=True)
    log_file.write(line + end)
    log_file.flush()

log("=" * 70)
log("车辆清洗检测器 - YOLO-only高性能版本")
log("=" * 70)

# Video path
VIDEO_PATH = r"D:\Users\Admini503\OneDrive\Desktop\文件\视觉识别\微信视频2026-04-23_090043_727.mp4"

# Check video exists
video_path = Path(VIDEO_PATH)
if not video_path.exists():
    log(f"Error: Video file not found: {VIDEO_PATH}")
    log_file.close()
    sys.exit(1)

log(f"\nVideo: {VIDEO_PATH}")
log(f"Size: {video_path.stat().st_size / 1024 / 1024:.1f} MB")

# Open video
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

# 检测分辨率设置（降低以提高速度）
DETECT_WIDTH = 1280
DETECT_HEIGHT = int(height * DETECT_WIDTH / width)
detect_scale = width / DETECT_WIDTH

log(f"\nDetection Settings:")
log(f"  Detection resolution: {DETECT_WIDTH}x{DETECT_HEIGHT}")
log(f"  Scale factor: {detect_scale:.2f}x")

# Load detector
log("\nLoading detector...")
log("  Step 1/3: Import modules...", end=' ')
try:
    from ultralytics import YOLO
    log("OK")
    
    log("  Step 2/3: Load YOLOv8 vehicle model...", end=' ')
    vehicle_model = YOLO('yolov8n.pt')
    log("OK")
    
    log("  Step 3/3: Load YOLOv8 plate model...", end=' ')
    # 尝试加载车牌检测模型
    plate_model_path = 'detectors/plate_recognition/plate_detect.pt'
    plate_model = None
    try:
        plate_model = YOLO(plate_model_path)
        log("OK")
    except Exception as e:
        log(f"Not found ({e}), will use vehicle ROI only")
    
    log("Detector loaded successfully!")
    
except Exception as e:
    log(f"Error: Failed to load detector: {e}")
    import traceback
    traceback.print_exc()
    log_file.close()
    sys.exit(1)

# Create output directory
output_dir = Path("storage/full_video_test_yolo_only")
output_dir.mkdir(parents=True, exist_ok=True)
output_path = output_dir / "output.mp4"

# Multi-threading architecture
log("\nInitializing multi-threading architecture...")

# Thread-safe queues
frame_queue = queue.Queue(maxsize=5)
detect_queue = queue.Queue(maxsize=5)
result_queue = queue.Queue(maxsize=5)

# Control flags
stop_event = threading.Event()
frame_idx = 0
processed_frames = 0
lock = threading.Lock()

# Performance stats
stats = {
    'total_frames': 0,
    'processed_frames': 0,
    'detect_times': [],
    'plate_times': [],
    'start_time': time.time()
}

# Detection config
VEHICLE_CLASSES = [2, 3, 5, 7]  # car, motorcycle, bus, truck
CONF_THRESHOLD = 0.3
IOU_THRESHOLD = 0.45
IMG_SIZE = 640

def detect_vehicles(frame):
    """Detect vehicles using YOLOv8"""
    results = vehicle_model(
        frame,
        conf=CONF_THRESHOLD,
        iou=IOU_THRESHOLD,
        imgsz=IMG_SIZE,
        device='cuda',
        verbose=False,
        classes=VEHICLE_CLASSES
    )
    
    detections = []
    for result in results:
        if result.boxes is None:
            continue
        for box in result.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            
            class_names = {2: 'car', 3: 'motorcycle', 5: 'bus', 7: 'truck'}
            class_name = class_names.get(cls_id, 'unknown')
            
            detections.append({
                'bbox': (x1, y1, x2, y2),
                'class_id': cls_id,
                'class_name': class_name,
                'confidence': conf
            })
    
    return detections

def detect_plate_in_vehicle(vehicle_roi):
    """Detect license plate in vehicle ROI using YOLO"""
    if plate_model is None:
        return None
    
    try:
        results = plate_model(vehicle_roi, verbose=False)
        
        for result in results:
            if result.boxes is None or len(result.boxes) == 0:
                continue
            
            # Get best plate detection
            best_box = None
            best_conf = 0
            for box in result.boxes:
                conf = float(box.conf[0])
                if conf > best_conf:
                    best_conf = conf
                    best_box = box
            
            if best_box is not None:
                px1, py1, px2, py2 = map(int, best_box.xyxy[0])
                return (px1, py1, px2, py2)
        
        return None
    except Exception as e:
        return None

def video_reader_thread():
    """Video reader thread"""
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
            except:
                pass
        
        with lock:
            frame_idx += 1
            stats['total_frames'] = frame_idx
    
    log("[Video Reader] Stopped")

def vehicle_detection_thread():
    """Vehicle detection thread"""
    log("[Vehicle Detector] Started")
    
    while not stop_event.is_set():
        try:
            idx, original_frame = frame_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        
        # Resize for faster detection
        detect_frame = cv2.resize(original_frame, (DETECT_WIDTH, DETECT_HEIGHT), interpolation=cv2.INTER_LINEAR)
        
        # Detect vehicles
        start_time = time.time()
        detections = detect_vehicles(detect_frame)
        detect_time = time.time() - start_time
        
        # Scale boxes back to original resolution
        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            det['bbox'] = (
                int(x1 * detect_scale),
                int(y1 * detect_scale),
                int(x2 * detect_scale),
                int(y2 * detect_scale)
            )
        
        with lock:
            stats['detect_times'].append(detect_time)
            if len(stats['detect_times']) > 100:
                stats['detect_times'].pop(0)
        
        try:
            detect_queue.put((idx, original_frame, detections, detect_time), block=False)
        except queue.Full:
            try:
                detect_queue.get_nowait()
                detect_queue.put((idx, original_frame, detections, detect_time), block=False)
            except:
                pass
    
    log("[Vehicle Detector] Stopped")

def plate_detection_worker(args):
    """Plate detection worker"""
    frame, det = args
    x1, y1, x2, y2 = det['bbox']
    vehicle_roi = frame[y1:y2, x1:x2]
    
    if vehicle_roi.size == 0:
        return det, None
    
    plate_bbox = detect_plate_in_vehicle(vehicle_roi)
    
    if plate_bbox:
        px1, py1, px2, py2 = plate_bbox
        abs_bbox = (x1 + px1, y1 + py1, x1 + px2, y1 + py2)
        return det, abs_bbox
    
    return det, None

def plate_detection_thread():
    """Plate detection thread with thread pool"""
    log("[Plate Detector] Started")
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        while not stop_event.is_set():
            try:
                idx, frame, detections, detect_time = detect_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            
            start_time = time.time()
            
            plate_results = []
            if detections:
                futures = []
                for det in detections:
                    future = executor.submit(plate_detection_worker, (frame, det))
                    futures.append(future)
                
                for future in as_completed(futures):
                    try:
                        det, plate_bbox = future.result(timeout=5.0)
                        plate_results.append((det, plate_bbox))
                    except Exception as e:
                        log(f"[Plate Detection] Error: {e}")
            
            plate_time = time.time() - start_time
            
            with lock:
                stats['plate_times'].append(plate_time)
                if len(stats['plate_times']) > 100:
                    stats['plate_times'].pop(0)
            
            try:
                result_queue.put((idx, frame, plate_results, detect_time, plate_time), block=False)
            except queue.Full:
                try:
                    result_queue.get_nowait()
                    result_queue.put((idx, frame, plate_results, detect_time, plate_time), block=False)
                except:
                    pass
    
    log("[Plate Detector] Stopped")

def result_processing_thread():
    """Result processing thread"""
    global processed_frames
    log("[Result Processor] Started")
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
    
    frame_count = 0
    last_log_time = time.time()
    
    while not stop_event.is_set():
        try:
            idx, frame, plate_results, detect_time, plate_time = result_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        
        # Draw results
        result_frame = frame.copy()
        
        for det, plate_bbox in plate_results:
            x1, y1, x2, y2 = det['bbox']
            
            if plate_bbox:
                px1, py1, px2, py2 = plate_bbox
                cv2.rectangle(result_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.rectangle(result_frame, (px1, py1), (px2, py2), (0, 0, 255), 2)
                label = f"{det['class_name']} | Plate"
                cv2.putText(result_frame, label, (x1, y1 - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            else:
                cv2.rectangle(result_frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
                label = f"{det['class_name']} (No Plate)"
                cv2.putText(result_frame, label, (x1, y1 - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
        
        # Show statistics
        with lock:
            elapsed = time.time() - stats['start_time']
            current_fps = processed_frames / elapsed if elapsed > 0 else 0
            avg_detect = np.mean(stats['detect_times']) * 1000 if stats['detect_times'] else 0
            avg_plate = np.mean(stats['plate_times']) * 1000 if stats['plate_times'] else 0
        
        info_text = [
            f"Frame: {idx}",
            f"FPS: {current_fps:.1f}",
            f"Detect: {detect_time*1000:.0f}ms",
            f"Plate: {plate_time*1000:.0f}ms",
            f"Vehicles: {len(plate_results)}",
        ]
        
        y_offset = 30
        for text in info_text:
            cv2.putText(result_frame, text, (width - 350, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            y_offset += 25
        
        # Save video
        out.write(result_frame)
        
        # Display every 3 frames
        if frame_count % 3 == 0:
            display_frame = cv2.resize(result_frame, (1280, 720))
            cv2.imshow("Vehicle Detection (YOLO-only)", display_frame)
            
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
        
        # Log stats every 2 seconds
        current_time = time.time()
        if current_time - last_log_time >= 2.0:
            with lock:
                total = stats['total_frames']
                proc = processed_frames
                avg_fps = proc / (current_time - stats['start_time']) if current_time > stats['start_time'] else 0
            log(f"[Stats] Total: {total}, Processed: {proc}, Avg FPS: {avg_fps:.1f}")
            last_log_time = current_time
    
    out.release()
    cv2.destroyAllWindows()
    log("[Result Processor] Stopped")

# Start all threads
log("\nStarting threads...")
threads = []

t1 = threading.Thread(target=video_reader_thread, name="VideoReader")
t2 = threading.Thread(target=vehicle_detection_thread, name="VehicleDetector")
t3 = threading.Thread(target=plate_detection_thread, name="PlateDetector")
t4 = threading.Thread(target=result_processing_thread, name="ResultProcessor")

threads = [t1, t2, t3, t4]

for t in threads:
    t.daemon = True
    t.start()

log("All threads started (4 core threads)")
log("-" * 70)

# Wait for all threads to finish
try:
    for t in threads:
        t.join()
except KeyboardInterrupt:
    log("\nUser interrupted")
    stop_event.set()

# Summary
log("\n" + "=" * 70)
log("Processing completed!")
log(f"Total frames: {frame_idx}")
log(f"Processed frames: {processed_frames}")
log(f"Output video: {output_path}")
log("=" * 70)

# Release resources
cap.release()
log_file.close()
