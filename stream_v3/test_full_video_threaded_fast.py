"""
车辆清洗检测器 - 高性能多线程版本
优化策略:
1. 检测时使用降低分辨率的图像
2. 检测框坐标映射回原始分辨率
3. 车牌检测在原始分辨率上进行（保证清晰度）
4. 4个核心线程并行处理
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
log_file = open('full_video_test_fast.log', 'w', encoding='utf-8')

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
log("车辆清洗检测器 - 高性能多线程版本")
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
DETECT_WIDTH = 1280  # 检测时使用的宽度
DETECT_HEIGHT = int(height * DETECT_WIDTH / width)
detect_scale = width / DETECT_WIDTH

log(f"\nDetection Settings:")
log(f"  Detection resolution: {DETECT_WIDTH}x{DETECT_HEIGHT}")
log(f"  Scale factor: {detect_scale:.2f}x")

# Load detector
log("\nLoading detector...")
log("  Step 1/3: Import modules...", end=' ')
try:
    from detectors.vehicle_wash_detector import VehicleWashDetector
    log("OK")
    
    log("  Step 2/3: Configure detector...", end=' ')
    detector_config = {
        'path': 'yolov8n.pt',
        'device': 'cuda',
        'conf_threshold': 0.3,
        'iou_threshold': 0.45,
        'img_size': 640,
        'ocr_engine': 'paddleocr',
        'wash_time_min': 300,
        'wash_time_max': 1800,
        'entry_line_y': int(300 / detect_scale),
        'exit_line_y': int(500 / detect_scale),
        'save_images': True,
        'image_save_path': 'storage/full_video_test_fast',
    }
    log("OK")
    
    log("  Step 3/3: Initialize YOLOv8 and OCR...")
    log("    - Loading YOLOv8 model...", end=' ')
    detector = VehicleWashDetector(detector_config)
    log("OK")
    log("Detector loaded successfully!")
    log(f"  OCR Engine: PaddleOCR")
    log(f"  Confidence threshold: 0.3")
    
except Exception as e:
    log(f"Error: Failed to load detector: {e}")
    import traceback
    traceback.print_exc()
    log_file.close()
    sys.exit(1)

# Create output directory
output_dir = Path("storage/full_video_test_fast")
output_dir.mkdir(parents=True, exist_ok=True)
output_path = output_dir / "output.mp4"

# Multi-threading architecture
log("\nInitializing multi-threading architecture...")

# Thread-safe queues
frame_queue = queue.Queue(maxsize=5)           # Original frame queue
detect_queue = queue.Queue(maxsize=5)          # Detection results queue
plate_queue = queue.Queue(maxsize=5)           # License plate detection queue
result_queue = queue.Queue(maxsize=5)          # Final results queue

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

def video_reader_thread():
    """Video reader thread - continuously reads video frames"""
    global frame_idx
    log("[Video Reader] Started")
    
    while not stop_event.is_set():
        ret, frame = cap.read()
        if not ret:
            log("[Video Reader] Video ended")
            break
        
        # Put in queue, drop oldest if full
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
    """Vehicle detection thread - GPU inference on scaled image"""
    log("[Vehicle Detector] Started")
    
    while not stop_event.is_set():
        try:
            idx, original_frame = frame_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        
        # Resize frame for faster detection
        detect_frame = cv2.resize(original_frame, (DETECT_WIDTH, DETECT_HEIGHT), interpolation=cv2.INTER_LINEAR)
        
        # Detect vehicles
        start_time = time.time()
        detections = detector.detect(detect_frame)
        detect_time = time.time() - start_time
        
        # Scale detection boxes back to original resolution
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
        
        # Put in detection queue
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
    """License plate detection worker - runs in thread pool"""
    frame, detection = args
    plate_result = detector.detect_license_plate(frame, detection.bbox)
    return detection, plate_result

def plate_detection_thread():
    """License plate detection thread - uses thread pool for parallel processing"""
    log("[Plate Detector] Started")
    
    # Create thread pool
    with ThreadPoolExecutor(max_workers=4) as executor:
        while not stop_event.is_set():
            try:
                idx, frame, detections, detect_time = detect_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            
            start_time = time.time()
            
            # Submit all vehicle plate detection tasks
            plate_results = []
            if detections:
                futures = []
                for det in detections:
                    future = executor.submit(plate_detection_worker, (frame, det))
                    futures.append(future)
                
                # Collect results
                for future in as_completed(futures):
                    try:
                        det, plate_result = future.result(timeout=5.0)
                        plate_results.append((det, plate_result))
                    except Exception as e:
                        log(f"[Plate Detection] Error: {e}")
            
            plate_time = time.time() - start_time
            
            with lock:
                stats['plate_times'].append(plate_time)
                if len(stats['plate_times']) > 100:
                    stats['plate_times'].pop(0)
            
            # Put in result queue
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
    """Result processing thread - rendering, saving, display"""
    global processed_frames
    log("[Result Processor] Started")
    
    # Initialize video writer
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
        
        # Draw detection boxes and license plates
        for det, plate_result in plate_results:
            x1, y1, x2, y2 = det.bbox
            
            if plate_result:
                plate_text, plate_bbox = plate_result
                # Draw vehicle box (green)
                cv2.rectangle(result_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                # Draw plate box (red)
                if plate_bbox:
                    px1, py1, px2, py2 = plate_bbox
                    cv2.rectangle(result_frame, (px1, py1), (px2, py2), (0, 0, 255), 2)
                # Show plate text
                label = f"{det.class_name} | {plate_text}"
                cv2.putText(result_frame, label, (x1, y1 - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            else:
                # No plate detected (yellow)
                cv2.rectangle(result_frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
                label = f"{det.class_name} (No Plate)"
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
        
        # Real-time display (every 3 frames to reduce overhead)
        if frame_count % 3 == 0:
            display_frame = cv2.resize(result_frame, (1280, 720))
            cv2.imshow("Vehicle Detection (Fast)", display_frame)
            
            # Keyboard control
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
