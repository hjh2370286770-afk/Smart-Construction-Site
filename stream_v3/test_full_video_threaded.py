"""
车辆清洗检测器 - 多线程版本
实现完全并行的检测流程
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
log_file = open('full_video_test_threaded.log', 'w', encoding='utf-8')

def log(msg, end='\n'):
    """Write to both console and file"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    line = f"[{timestamp}] {msg}"
    print(line, end=end, flush=True)
    log_file.write(line + end)
    log_file.flush()

log("=" * 70)
log("车辆清洗检测器 - 多线程版本")
log("=" * 70)

# Video path
VIDEO_PATH = r"D:\Users\Admini503\OneDrive\Desktop\文件\视觉识别\微信视频2026-04-23_090043_727.mp4"

# Check video exists
video_path = Path(VIDEO_PATH)
if not video_path.exists():
    log(f"错误: 视频文件不存在: {VIDEO_PATH}")
    log_file.close()
    sys.exit(1)

log(f"\n视频路径: {VIDEO_PATH}")
log(f"视频大小: {video_path.stat().st_size / 1024 / 1024:.1f} MB")

# Open video
cap = cv2.VideoCapture(str(video_path))
if not cap.isOpened():
    log("错误: 无法打开视频")
    log_file.close()
    sys.exit(1)

fps = cap.get(cv2.CAP_PROP_FPS)
frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

log(f"视频信息:")
log(f"  分辨率: {width}x{height}")
log(f"  帧率: {fps:.1f} fps")
log(f"  总帧数: {frame_count}")
log(f"  时长: {frame_count/fps:.1f}秒")

# Load detector
log("\n正在加载检测器...")
log("  步骤1/3: 导入模块...", end=' ')
try:
    from detectors.vehicle_wash_detector import VehicleWashDetector
    log("[OK]")
    
    log("  步骤2/3: 配置检测器...", end=' ')
    detector_config = {
        'path': 'yolov8n.pt',
        'device': 'cuda',
        'conf_threshold': 0.3,
        'iou_threshold': 0.45,
        'img_size': 640,
        'ocr_engine': 'paddleocr',
        'wash_time_min': 300,
        'wash_time_max': 1800,
        'entry_line_y': 300,
        'exit_line_y': 500,
        'save_images': True,
        'image_save_path': 'storage/full_video_test_threaded',
    }
    log("[OK]")
    
    log("  步骤3/3: 初始化YOLOv8和OCR引擎...")
    log("    - 加载YOLOv8模型...", end=' ')
    detector = VehicleWashDetector(detector_config)
    log("[OK]")
    log("检测器加载成功!")
    log(f"  OCR引擎: PaddleOCR")
    log(f"  置信度阈值: 0.3")
    
except Exception as e:
    log(f"错误: 加载检测器失败: {e}")
    import traceback
    traceback.print_exc()
    log_file.close()
    sys.exit(1)

# Create output video
output_path = "storage/full_video_test_threaded/output.mp4"
Path("storage/full_video_test_threaded").mkdir(parents=True, exist_ok=True)

# 尝试多种编码器
fourcc_options = ['mp4v', 'XVID', 'MJPG']
fourcc = None
for codec in fourcc_options:
    try:
        test_fourcc = cv2.VideoWriter_fourcc(*codec)
        test_out = cv2.VideoWriter("test.mp4", test_fourcc, fps, (width, height))
        if test_out.isOpened():
            fourcc = test_fourcc
            test_out.release()
            Path("test.mp4").unlink(missing_ok=True)
            log(f"使用视频编码: {codec}")
            break
    except:
        continue

if fourcc is None:
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    log("使用默认视频编码: mp4v")

out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

# 多线程架构
log("\n初始化多线程架构...")

# 线程安全的队列
frame_queue = queue.Queue(maxsize=5)  # 原始帧队列
detect_queue = queue.Queue(maxsize=5)  # 检测结果队列
display_queue = queue.Queue(maxsize=2)  # 显示帧队列

# 控制标志
stop_event = threading.Event()
frame_idx = 0
processed_frames = 0
lock = threading.Lock()

# 统计信息
stats = {
    'total_entries': 0,
    'total_exits': 0,
    'washed_count': 0,
    'fps': 0,
    'start_time': time.time()
}

def video_reader_thread():
    """视频读取线程 - 持续读取视频帧"""
    global frame_idx
    log("[视频读取线程] 启动")
    
    while not stop_event.is_set():
        ret, frame = cap.read()
        if not ret:
            log("[视频读取线程] 视频结束")
            break
        
        # 放入队列，如果队列满则丢弃最旧的帧
        try:
            frame_queue.put((frame_idx, frame), block=False)
        except queue.Full:
            try:
                frame_queue.get_nowait()  # 丢弃旧帧
                frame_queue.put((frame_idx, frame), block=False)
            except:
                pass
        
        with lock:
            frame_idx += 1
    
    log("[视频读取线程] 结束")

def vehicle_detection_thread():
    """车辆检测线程 - 持续检测车辆"""
    log("[车辆检测线程] 启动")
    
    while not stop_event.is_set():
        try:
            idx, frame = frame_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        
        # 检测车辆（只检测，不识别车牌）
        start_time = time.time()
        detections = detector.detect(frame)
        detect_time = time.time() - start_time
        
        # 放入检测队列
        try:
            detect_queue.put((idx, frame, detections, detect_time), block=False)
        except queue.Full:
            try:
                detect_queue.get_nowait()
                detect_queue.put((idx, frame, detections, detect_time), block=False)
            except:
                pass
    
    log("[车辆检测线程] 结束")

def plate_detection_worker(args):
    """车牌检测工作函数 - 在线程池中执行"""
    frame, detection = args
    
    # 检测车牌
    plate_result = detector.detect_license_plate(frame, detection.bbox)
    
    return detection, plate_result

def plate_detection_thread():
    """车牌检测线程 - 使用线程池并行处理多个车辆"""
    log("[车牌检测线程] 启动")
    
    # 创建线程池
    with ThreadPoolExecutor(max_workers=4) as executor:
        while not stop_event.is_set():
            try:
                idx, frame, detections, detect_time = detect_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            
            # 提交所有车辆的车牌检测任务
            if detections:
                futures = []
                for det in detections:
                    future = executor.submit(plate_detection_worker, (frame, det))
                    futures.append(future)
                
                # 收集结果
                plate_results = []
                for future in as_completed(futures):
                    try:
                        det, plate_result = future.result(timeout=5.0)
                        plate_results.append((det, plate_result))
                    except Exception as e:
                        log(f"[车牌检测] 错误: {e}")
                
                # 放入显示队列
                try:
                    display_queue.put((idx, frame, plate_results, detect_time), block=False)
                except queue.Full:
                    try:
                        display_queue.get_nowait()
                        display_queue.put((idx, frame, plate_results, detect_time), block=False)
                    except:
                        pass
            else:
                # 没有检测到车辆
                try:
                    display_queue.put((idx, frame, [], detect_time), block=False)
                except queue.Full:
                    pass
    
    log("[车牌检测线程] 结束")

def display_thread():
    """显示线程 - 处理显示和保存"""
    global processed_frames
    log("[显示线程] 启动")
    
    while not stop_event.is_set():
        try:
            idx, frame, plate_results, detect_time = display_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        
        # 绘制结果
        result_frame = frame.copy()
        
        # 绘制检测框和车牌
        for det, plate_result in plate_results:
            x1, y1, x2, y2 = det.bbox
            
            if plate_result:
                plate_text, plate_bbox = plate_result
                # 绘制车辆框（绿色）
                cv2.rectangle(result_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                # 绘制车牌框（红色）
                if plate_bbox:
                    px1, py1, px2, py2 = plate_bbox
                    cv2.rectangle(result_frame, (px1, py1), (px2, py2), (0, 0, 255), 2)
                # 显示车牌
                label = f"{det.class_name} | {plate_text}"
                cv2.putText(result_frame, label, (x1, y1 - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            else:
                # 未检测到车牌（黄色）
                cv2.rectangle(result_frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
                label = f"{det.class_name} (No Plate)"
                cv2.putText(result_frame, label, (x1, y1 - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
        
        # 显示统计信息
        elapsed = time.time() - stats['start_time']
        current_fps = processed_frames / elapsed if elapsed > 0 else 0
        
        info_text = [
            f"Frame: {idx}",
            f"FPS: {current_fps:.1f}",
            f"Detect: {detect_time*1000:.0f}ms",
            f"Vehicles: {len(plate_results)}",
            f"Entries: {stats['total_entries']}",
            f"Exits: {stats['total_exits']}"
        ]
        
        y_offset = 30
        for text in info_text:
            cv2.putText(result_frame, text, (width - 350, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            y_offset += 30
        
        # 保存视频
        out.write(result_frame)
        
        # 实时显示
        display_frame = cv2.resize(result_frame, (1280, 720))
        cv2.imshow("Vehicle Detection (Threaded)", display_frame)
        
        # 键盘控制
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            log("[显示线程] 用户按Q退出")
            stop_event.set()
            break
        elif key == ord('p'):
            log("[显示线程] 暂停，按任意键继续...")
            cv2.waitKey(0)
        
        with lock:
            processed_frames += 1
    
    log("[显示线程] 结束")

# 启动所有线程
log("\n启动多线程...")
threads = []

t1 = threading.Thread(target=video_reader_thread, name="VideoReader")
t2 = threading.Thread(target=vehicle_detection_thread, name="VehicleDetector")
t3 = threading.Thread(target=plate_detection_thread, name="PlateDetector")
t4 = threading.Thread(target=display_thread, name="Display")

threads = [t1, t2, t3, t4]

for t in threads:
    t.daemon = True
    t.start()

log("所有线程已启动")
log("-" * 70)

# 等待所有线程结束
try:
    for t in threads:
        t.join()
except KeyboardInterrupt:
    log("\n用户中断")
    stop_event.set()

# Summary
log("\n" + "=" * 70)
log("处理完成!")
log(f"总帧数: {frame_idx}")
log(f"处理帧数: {processed_frames}")
log(f"输出视频: {output_path}")
log("=" * 70)

# Release resources
cap.release()
out.release()
cv2.destroyAllWindows()
log_file.close()
