"""
车辆清洗检测器 - 完全多线程版本 V2
所有可分离功能都独立线程:
- 视频读取线程
- 图像预处理线程
- 车辆检测线程
- 车牌检测线程（线程池）
- 跟踪与逻辑处理线程
- 可视化渲染线程
- 视频保存线程
- 统计信息线程
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
log_file = open('full_video_test_threaded_v2.log', 'w', encoding='utf-8')

def log(msg, end='\n'):
    """Write to both console and file"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    line = f"[{timestamp}] {msg}"
    print(line, end=end, flush=True)
    log_file.write(line + end)
    log_file.flush()

log("=" * 70)
log("车辆清洗检测器 - 完全多线程版本 V2")
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
        'image_save_path': 'storage/full_video_test_threaded_v2',
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

# Create output directory
output_dir = Path("storage/full_video_test_threaded_v2")
output_dir.mkdir(parents=True, exist_ok=True)
output_path = output_dir / "output.mp4"

# 多线程架构 - 完全分离所有功能
log("\n初始化完全多线程架构...")

# 线程安全的队列（每个功能独立队列）
raw_frame_queue = queue.Queue(maxsize=10)           # 原始帧队列
preprocessed_queue = queue.Queue(maxsize=10)        # 预处理后帧队列
detection_queue = queue.Queue(maxsize=10)           # 车辆检测结果队列
plate_queue = queue.Queue(maxsize=10)               # 车牌检测任务队列
plate_result_queue = queue.Queue(maxsize=10)        # 车牌检测结果队列
tracking_queue = queue.Queue(maxsize=10)            # 跟踪处理队列
render_queue = queue.Queue(maxsize=5)               # 渲染队列
save_queue = queue.Queue(maxsize=10)                # 保存队列
display_queue = queue.Queue(maxsize=3)              # 显示队列

# 控制标志
stop_event = threading.Event()
pause_event = threading.Event()
frame_idx = 0
processed_frames = 0
lock = threading.Lock()

# 统计信息
stats = {
    'total_entries': 0,
    'total_exits': 0,
    'washed_count': 0,
    'fps': 0,
    'start_time': time.time(),
    'frame_times': [],
    'detect_times': [],
    'plate_times': [],
    'render_times': []
}

def video_reader_thread():
    """视频读取线程 - 持续读取视频帧"""
    global frame_idx
    log("[视频读取线程] 启动")
    
    while not stop_event.is_set():
        if pause_event.is_set():
            time.sleep(0.01)
            continue
            
        ret, frame = cap.read()
        if not ret:
            log("[视频读取线程] 视频结束")
            break
        
        # 放入队列，如果队列满则丢弃最旧的帧
        try:
            raw_frame_queue.put((frame_idx, frame), block=False)
        except queue.Full:
            try:
                raw_frame_queue.get_nowait()
                raw_frame_queue.put((frame_idx, frame), block=False)
            except:
                pass
        
        with lock:
            frame_idx += 1
    
    log("[视频读取线程] 结束")

def image_preprocessing_thread():
    """图像预处理线程 - 调整大小、格式转换等"""
    log("[图像预处理线程] 启动")
    
    while not stop_event.is_set():
        try:
            idx, frame = raw_frame_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        
        start_time = time.time()
        
        # 预处理：调整大小以提高检测速度
        # 保持宽高比，最大边不超过1280
        h, w = frame.shape[:2]
        max_size = 1280
        if max(h, w) > max_size:
            scale = max_size / max(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            processed_frame = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        else:
            processed_frame = frame
            scale = 1.0
            new_w, new_h = w, h
        
        preprocess_time = time.time() - start_time
        
        # 放入预处理队列
        try:
            preprocessed_queue.put((idx, frame, processed_frame, scale, (new_w, new_h)), block=False)
        except queue.Full:
            try:
                preprocessed_queue.get_nowait()
                preprocessed_queue.put((idx, frame, processed_frame, scale, (new_w, new_h)), block=False)
            except:
                pass
    
    log("[图像预处理线程] 结束")

def vehicle_detection_thread():
    """车辆检测线程 - 持续检测车辆"""
    log("[车辆检测线程] 启动")
    
    while not stop_event.is_set():
        try:
            idx, original_frame, processed_frame, scale, new_size = preprocessed_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        
        # 检测车辆（只检测，不识别车牌）
        start_time = time.time()
        detections = detector.detect(processed_frame)
        detect_time = time.time() - start_time
        
        # 调整检测框坐标（如果进行了缩放）
        if scale != 1.0:
            for det in detections:
                x1, y1, x2, y2 = det.bbox
                det.bbox = (
                    int(x1 / scale),
                    int(y1 / scale),
                    int(x2 / scale),
                    int(y2 / scale)
                )
        
        # 放入检测队列
        try:
            detection_queue.put((idx, original_frame, detections, detect_time), block=False)
        except queue.Full:
            try:
                detection_queue.get_nowait()
                detection_queue.put((idx, original_frame, detections, detect_time), block=False)
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
                idx, frame, detections, detect_time = detection_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            
            start_time = time.time()
            
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
                
                plate_time = time.time() - start_time
                
                # 放入车牌结果队列
                try:
                    plate_result_queue.put((idx, frame, plate_results, detect_time, plate_time), block=False)
                except queue.Full:
                    try:
                        plate_result_queue.get_nowait()
                        plate_result_queue.put((idx, frame, plate_results, detect_time, plate_time), block=False)
                    except:
                        pass
            else:
                # 没有检测到车辆
                try:
                    plate_result_queue.put((idx, frame, [], detect_time, 0), block=False)
                except queue.Full:
                    pass
    
    log("[车牌检测线程] 结束")

def tracking_logic_thread():
    """跟踪与逻辑处理线程 - 处理车辆跟踪和业务逻辑"""
    log("[跟踪逻辑线程] 启动")
    
    while not stop_event.is_set():
        try:
            idx, frame, plate_results, detect_time, plate_time = plate_result_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        
        start_time = time.time()
        
        # 提取检测信息用于跟踪
        detections = [det for det, _ in plate_results]
        
        # 调用跟踪更新（这里简化处理，实际应该调用完整的跟踪逻辑）
        # 更新统计信息
        for det, plate_result in plate_results:
            if plate_result:
                plate_text, _ = plate_result
                if plate_text and not plate_text.startswith("UNKNOWN"):
                    with lock:
                        stats['total_entries'] += 1
        
        track_time = time.time() - start_time
        
        # 放入跟踪队列
        try:
            tracking_queue.put((idx, frame, plate_results, detect_time, plate_time, track_time), block=False)
        except queue.Full:
            try:
                tracking_queue.get_nowait()
                tracking_queue.put((idx, frame, plate_results, detect_time, plate_time, track_time), block=False)
            except:
                pass
    
    log("[跟踪逻辑线程] 结束")

def visualization_thread():
    """可视化渲染线程 - 处理图像绘制"""
    log("[可视化线程] 启动")
    
    while not stop_event.is_set():
        try:
            idx, frame, plate_results, detect_time, plate_time, track_time = tracking_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        
        start_time = time.time()
        
        # 绘制结果
        result_frame = frame.copy()
        h, w = result_frame.shape[:2]
        
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
        with lock:
            elapsed = time.time() - stats['start_time']
            current_fps = processed_frames / elapsed if elapsed > 0 else 0
        
        info_text = [
            f"Frame: {idx}",
            f"FPS: {current_fps:.1f}",
            f"Detect: {detect_time*1000:.0f}ms",
            f"Plate: {plate_time*1000:.0f}ms",
            f"Track: {track_time*1000:.0f}ms",
            f"Vehicles: {len(plate_results)}",
        ]
        
        y_offset = 30
        for text in info_text:
            cv2.putText(result_frame, text, (w - 400, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            y_offset += 25
        
        render_time = time.time() - start_time
        
        # 放入渲染队列
        try:
            render_queue.put((idx, result_frame, render_time), block=False)
        except queue.Full:
            try:
                render_queue.get_nowait()
                render_queue.put((idx, result_frame, render_time), block=False)
            except:
                pass
    
    log("[可视化线程] 结束")

def video_save_thread():
    """视频保存线程 - 处理视频编码和保存"""
    log("[视频保存线程] 启动")
    
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
                log(f"[视频保存线程] 使用编码: {codec}")
                break
        except:
            continue
    
    if fourcc is None:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    
    out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
    
    while not stop_event.is_set():
        try:
            idx, frame, render_time = render_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        
        # 保存视频帧
        out.write(frame)
        
        # 放入显示队列
        try:
            display_queue.put((idx, frame), block=False)
        except queue.Full:
            try:
                display_queue.get_nowait()
                display_queue.put((idx, frame), block=False)
            except:
                pass
    
    out.release()
    log("[视频保存线程] 结束")

def display_thread():
    """显示线程 - 处理实时显示和用户交互"""
    global processed_frames
    log("[显示线程] 启动")
    
    while not stop_event.is_set():
        try:
            idx, frame = display_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        
        # 实时显示
        display_frame = cv2.resize(frame, (1280, 720))
        cv2.imshow("Vehicle Detection (Multi-Threaded V2)", display_frame)
        
        # 键盘控制
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            log("[显示线程] 用户按Q退出")
            stop_event.set()
            break
        elif key == ord('p'):
            log("[显示线程] 暂停，按任意键继续...")
            cv2.waitKey(0)
        elif key == ord(' '):
            pause_event.set() if not pause_event.is_set() else pause_event.clear()
            log("[显示线程] " + ("暂停" if pause_event.is_set() else "继续"))
        
        with lock:
            processed_frames += 1
    
    cv2.destroyAllWindows()
    log("[显示线程] 结束")

def statistics_thread():
    """统计信息线程 - 定期输出性能统计"""
    log("[统计线程] 启动")
    
    last_frame_count = 0
    last_time = time.time()
    
    while not stop_event.is_set():
        time.sleep(2.0)  # 每2秒输出一次统计
        
        if stop_event.is_set():
            break
        
        with lock:
            current_frames = processed_frames
            elapsed = time.time() - stats['start_time']
            current_fps = current_frames / elapsed if elapsed > 0 else 0
            instant_fps = (current_frames - last_frame_count) / 2.0
        
        log(f"[统计] 总帧数: {current_frames}, 平均FPS: {current_fps:.1f}, 瞬时FPS: {instant_fps:.1f}")
        
        last_frame_count = current_frames
        last_time = time.time()
    
    log("[统计线程] 结束")

# 启动所有线程
log("\n启动所有线程...")
threads = []

t1 = threading.Thread(target=video_reader_thread, name="VideoReader")
t2 = threading.Thread(target=image_preprocessing_thread, name="ImagePreprocessor")
t3 = threading.Thread(target=vehicle_detection_thread, name="VehicleDetector")
t4 = threading.Thread(target=plate_detection_thread, name="PlateDetector")
t5 = threading.Thread(target=tracking_logic_thread, name="TrackingLogic")
t6 = threading.Thread(target=visualization_thread, name="Visualizer")
t7 = threading.Thread(target=video_save_thread, name="VideoSaver")
t8 = threading.Thread(target=display_thread, name="Display")
t9 = threading.Thread(target=statistics_thread, name="Statistics")

threads = [t1, t2, t3, t4, t5, t6, t7, t8, t9]

for t in threads:
    t.daemon = True
    t.start()

log("所有线程已启动 (共9个线程)")
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
log_file.close()
