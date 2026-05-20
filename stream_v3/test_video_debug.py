#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试车辆清洗检测器 - 带调试信息
"""

import sys
import io
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import cv2
import logging
from pathlib import Path

# 设置详细日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

print("=" * 60)
print("车辆清洗检测器 - 调试测试")
print("=" * 60)

# 视频路径
VIDEO_PATH = r"D:\Users\Admini503\OneDrive\Desktop\文件\视觉识别\微信视频2026-04-23_090043_727.mp4"

# 检查视频文件
video_path = Path(VIDEO_PATH)
if not video_path.exists():
    print(f"[FAIL] 视频文件不存在: {VIDEO_PATH}")
    sys.exit(1)

print(f"[OK] 找到视频文件: {video_path}")

# 导入检测器
print("\n[1] 加载检测器...")
try:
    from detectors.vehicle_wash_detector import VehicleWashDetector
    
    detector_config = {
        'path': 'yolov8n.pt',
        'device': 'cpu',
        'conf_threshold': 0.5,
        'iou_threshold': 0.45,
        'img_size': 640,
        'ocr_engine': 'paddleocr',
        'wash_time_min': 300,
        'wash_time_max': 1800,
        'entry_line_y': 300,
        'exit_line_y': 500,
        'save_images': True,
        'image_save_path': 'storage/test_video_debug',
    }
    
    detector = VehicleWashDetector(detector_config)
    print("[OK] 检测器加载成功")
    
except Exception as e:
    print(f"[FAIL] 检测器加载失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 打开视频
print("\n[2] 打开视频...")
cap = cv2.VideoCapture(str(video_path))
if not cap.isOpened():
    print("[FAIL] 无法打开视频")
    sys.exit(1)

fps = cap.get(cv2.CAP_PROP_FPS)
frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

print(f"[OK] 视频信息:")
print(f"   分辨率: {width}x{height}")
print(f"   FPS: {fps}")
print(f"   总帧数: {frame_count}")

# 只处理前30帧来调试
print("\n[3] 开始处理视频（前30帧调试）...")
print("-" * 60)

frame_idx = 0
max_frames = 30

while frame_idx < max_frames:
    ret, frame = cap.read()
    if not ret:
        print("[INFO] 视频读取完毕")
        break
    
    frame_idx += 1
    
    # 每3帧处理一次
    if frame_idx % 3 == 0:
        print(f"\n处理帧 {frame_idx}/{max_frames}...")
        result_frame, updated_records = detector.process_frame(frame)
        
        if updated_records:
            for record in updated_records:
                status = "已清洗" if record.is_washed else "未清洗"
                print(f"  [记录] 车牌:{record.license_plate} | "
                      f"停留:{record.dwell_time:.1f}秒 | {status}")
        else:
            print(f"  无更新记录")
    
    if frame_idx % 10 == 0:
        print(f"进度: {frame_idx}/{max_frames}")

# 释放资源
cap.release()

# 统计
print("\n" + "=" * 60)
print("调试完成")
print("=" * 60)
print(f"处理帧数: {frame_idx}")
print()
print("最终统计:")
stats = detector.get_statistics()
print(f"  总进场: {stats['total_entries']}")
print(f"  总出场: {stats['total_exits']}")
print(f"  已清洗: {stats['washed_count']}")
print()
print("在场车辆:")
for record in detector.get_active_records():
    print(f"  - {record.license_plate} (进场时间: {record.entry_time.strftime('%H:%M:%S')})")
print()
print("抓拍图片保存在: storage/test_video_debug/")
