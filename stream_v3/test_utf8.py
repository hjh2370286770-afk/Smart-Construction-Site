#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test with proper UTF-8 encoding for Windows
"""

import sys
import os

# Set environment variable for UTF-8
os.environ['PYTHONIOENCODING'] = 'utf-8'

# For Windows, set console code page to UTF-8
if sys.platform == 'win32':
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleCP(65001)  # UTF-8
    kernel32.SetConsoleOutputCP(65001)  # UTF-8

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, '.')

import cv2
import time
from pathlib import Path

print("=" * 60)
print("车辆清洗检测器 - UTF-8编码测试")
print("=" * 60)

VIDEO_PATH = r"D:\Users\Admini503\OneDrive\Desktop\文件\视觉识别\微信视频2026-04-23_090043_727.mp4"

print(f"\n视频路径: {VIDEO_PATH}")

# Check video exists
video_path = Path(VIDEO_PATH)
if not video_path.exists():
    print("错误: 视频文件不存在")
    sys.exit(1)

print(f"视频大小: {video_path.stat().st_size / 1024 / 1024:.1f} MB")

# Open video
print("\n正在打开视频...")
cap = cv2.VideoCapture(str(video_path))
if not cap.isOpened():
    print("错误: 无法打开视频")
    sys.exit(1)

fps = cap.get(cv2.CAP_PROP_FPS)
frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print(f"视频信息: {frame_count}帧, {fps:.1f}fps, {frame_count/fps:.1f}秒")

# Load detector
print("\n正在加载检测器...")
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
    print("检测器加载成功!")
    
except Exception as e:
    print(f"错误: 加载检测器失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Process first 100 frames
print("\n正在处理前100帧...")
print("-" * 60)

frame_idx = 0
max_frames = 100
start_time = time.time()

while frame_idx < max_frames:
    ret, frame = cap.read()
    if not ret:
        print("视频结束")
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
                    print(f"第{frame_idx}帧: 车牌={plate}, 状态={status}")
        except Exception as e:
            print(f"第{frame_idx}帧处理错误: {e}")
    
    # Print progress every 10 frames
    if frame_idx % 10 == 0:
        elapsed = time.time() - start_time
        fps_current = frame_idx / elapsed if elapsed > 0 else 0
        print(f"进度: {frame_idx}/{max_frames}帧, FPS: {fps_current:.1f}")

cap.release()

# Summary
elapsed = time.time() - start_time
print("\n" + "=" * 60)
print("测试完成!")
print("=" * 60)
print(f"处理帧数: {frame_idx}")
print(f"处理时间: {elapsed:.1f}秒")
print(f"平均FPS: {frame_idx/elapsed:.1f}")

stats = detector.get_statistics()
print(f"\n统计信息:")
print(f"  进场车辆: {stats['total_entries']}")
print(f"  出场车辆: {stats['total_exits']}")
print(f"  已清洗: {stats['washed_count']}")

print(f"\n在场车辆:")
for record in detector.get_active_records():
    print(f"  - {record.license_plate} (进场时间: {record.entry_time.strftime('%H:%M:%S')})")
