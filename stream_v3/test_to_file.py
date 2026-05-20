#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test with output to file to avoid encoding issues
"""

import sys
sys.path.insert(0, '.')

import cv2
import time
from pathlib import Path
from datetime import datetime

# Open log file with UTF-8 encoding
log_file = open('test_output.log', 'w', encoding='utf-8')

def log(msg):
    """Write to both console and file"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    line = f"[{timestamp}] {msg}"
    print(line)
    log_file.write(line + '\n')
    log_file.flush()

log("=" * 60)
log("车辆清洗检测器 - 测试")
log("=" * 60)

VIDEO_PATH = r"D:\Users\Admini503\OneDrive\Desktop\文件\视觉识别\微信视频2026-04-23_090043_727.mp4"

log(f"\n视频路径: {VIDEO_PATH}")

# Check video exists
video_path = Path(VIDEO_PATH)
if not video_path.exists():
    log("错误: 视频文件不存在")
    log_file.close()
    sys.exit(1)

log(f"视频大小: {video_path.stat().st_size / 1024 / 1024:.1f} MB")

# Open video
log("\n正在打开视频...")
cap = cv2.VideoCapture(str(video_path))
if not cap.isOpened():
    log("错误: 无法打开视频")
    log_file.close()
    sys.exit(1)

fps = cap.get(cv2.CAP_PROP_FPS)
frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
log(f"视频信息: {frame_count}帧, {fps:.1f}fps, {frame_count/fps:.1f}秒")

# Load detector
log("\n正在加载检测器...")
try:
    from detectors.vehicle_wash_detector import VehicleWashDetector
    
    detector_config = {
        'path': 'yolov8n.pt',
        'device': 'cpu',
        'conf_threshold': 0.3,
        'iou_threshold': 0.45,
        'img_size': 640,
        'ocr_engine': 'paddleocr',
        'wash_time_min': 300,
        'wash_time_max': 1800,
        'entry_line_y': 300,
        'exit_line_y': 500,
        'save_images': False,
    }
    
    detector = VehicleWashDetector(detector_config)
    log("检测器加载成功!")
    
except Exception as e:
    log(f"错误: 加载检测器失败: {e}")
    import traceback
    traceback.print_exc()
    log_file.close()
    sys.exit(1)

# Process first 100 frames
log("\n正在处理前100帧...")
log("-" * 60)

frame_idx = 0
max_frames = 100
start_time = time.time()

while frame_idx < max_frames:
    ret, frame = cap.read()
    if not ret:
        log("视频结束")
        break
    
    frame_idx += 1
    
    # Process every 3rd frame
    if frame_idx % 3 == 0:
        try:
            result_frame, updated_records = detector.process_frame(frame)
            
            if updated_records:
                for record in updated_records:
                    plate = record.license_plate
                    status = "已清洗" if record.is_washed else "未清洗"
                    log(f"第{frame_idx}帧: 车牌={plate}, 状态={status}")
        except Exception as e:
            log(f"第{frame_idx}帧处理错误: {e}")
    
    # Print progress every 10 frames
    if frame_idx % 10 == 0:
        elapsed = time.time() - start_time
        fps_current = frame_idx / elapsed if elapsed > 0 else 0
        log(f"进度: {frame_idx}/{max_frames}帧, FPS: {fps_current:.1f}")

cap.release()

# Summary
elapsed = time.time() - start_time
log("\n" + "=" * 60)
log("测试完成!")
log("=" * 60)
log(f"处理帧数: {frame_idx}")
log(f"处理时间: {elapsed:.1f}秒")
log(f"平均FPS: {frame_idx/elapsed:.1f}")

stats = detector.get_statistics()
log(f"\n统计信息:")
log(f"  进场车辆: {stats['total_entries']}")
log(f"  出场车辆: {stats['total_exits']}")
log(f"  已清洗: {stats['washed_count']}")

log(f"\n在场车辆:")
for record in detector.get_active_records():
    log(f"  - {record.license_plate} (进场时间: {record.entry_time.strftime('%H:%M:%S')})")

log(f"\n已完成记录:")
for record in detector.get_completed_records():
    status = "已清洗" if record.is_washed else "未清洗"
    log(f"  - {record.license_plate} | {record.dwell_time:.1f}秒 | {status}")

log("\n日志已保存到: test_output.log")
log_file.close()
