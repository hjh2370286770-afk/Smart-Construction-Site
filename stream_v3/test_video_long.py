#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试车辆清洗检测器 - 长时间视频测试（实时检测优化）
处理更多帧，优化检测参数
"""

import sys
import io
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import cv2
import time
from pathlib import Path
from datetime import datetime

print("=" * 60)
print("车辆清洗检测器 - 长时间视频测试（实时检测）")
print("=" * 60)

# 视频路径
VIDEO_PATH = r"D:\Users\Admini503\OneDrive\Desktop\文件\视觉识别\微信视频2026-04-23_090043_727.mp4"

# 检查视频文件是否存在
video_path = Path(VIDEO_PATH)
if not video_path.exists():
    print(f"[FAIL] 视频文件不存在: {VIDEO_PATH}")
    sys.exit(1)

print(f"[OK] 找到视频文件: {video_path}")
print(f"   文件大小: {video_path.stat().st_size / 1024 / 1024:.2f} MB")

# 导入检测器
print("\n[1] 加载检测器（优化参数）...")
try:
    from detectors.vehicle_wash_detector import VehicleWashDetector
    
    detector_config = {
        'path': 'yolov8n.pt',
        'device': 'cpu',
        'conf_threshold': 0.3,  # 降低置信度阈值，提高检测灵敏度
        'iou_threshold': 0.45,
        'img_size': 640,
        'ocr_engine': 'paddleocr',
        'wash_time_min': 300,
        'wash_time_max': 1800,
        'entry_line_y': 300,
        'exit_line_y': 500,
        'save_images': True,
        'image_save_path': 'storage/test_video_long',
    }
    
    detector = VehicleWashDetector(detector_config)
    print("[OK] 检测器加载成功")
    print("   置信度阈值: 0.3 (提高检测灵敏度)")
    
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
print(f"   FPS: {fps:.1f}")
print(f"   总帧数: {frame_count}")
print(f"   时长: {frame_count/fps:.1f}秒")

# 创建输出视频
output_path = "storage/test_video_long/output.mp4"
Path("storage/test_video_long").mkdir(parents=True, exist_ok=True)
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

# 处理视频
print("\n[3] 开始处理视频（实时检测模式）...")
print("-" * 60)

frame_idx = 0
process_every_n_frames = 2  # 每2帧处理一次，平衡速度和精度
start_time = time.time()
max_frames = min(frame_count, 900)  # 处理前900帧（约60秒视频）

print(f"将处理前 {max_frames} 帧（约 {max_frames/fps:.1f} 秒）")
print(f"处理频率: 每{process_every_n_frames}帧处理1次")
print(f"结果视频将保存到: {output_path}")
print()

# 统计识别到的车牌
recognized_plates = {}

while frame_idx < max_frames:
    ret, frame = cap.read()
    if not ret:
        print("[INFO] 视频读取完毕")
        break
    
    frame_idx += 1
    
    # 每N帧处理一次
    if frame_idx % process_every_n_frames == 0:
        # 处理帧
        result_frame, updated_records = detector.process_frame(frame)
        
        # 显示统计信息
        stats = detector.get_statistics()
        info_text = [
            f"Frame: {frame_idx}/{max_frames}",
            f"Entries: {stats['total_entries']}",
            f"Exits: {stats['total_exits']}",
            f"Washed: {stats['washed_count']}",
        ]
        
        y_offset = 30
        for text in info_text:
            cv2.putText(result_frame, text, (width - 350, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            y_offset += 30
        
        # 写入输出视频
        out.write(result_frame)
        
        # 打印记录并统计车牌
        if updated_records:
            for record in updated_records:
                status = "已清洗" if record.is_washed else "未清洗"
                plate = record.license_plate
                print(f"[记录] 车牌:{plate} | 停留:{record.dwell_time:.1f}秒 | {status}")
                
                # 统计识别到的车牌（排除UNKNOWN）
                if not plate.startswith("UNKNOWN"):
                    if plate not in recognized_plates:
                        recognized_plates[plate] = 0
                    recognized_plates[plate] += 1
    else:
        # 不处理的帧直接写入原帧
        out.write(frame)
    
    # 每30帧打印进度
    if frame_idx % 30 == 0:
        elapsed = time.time() - start_time
        progress = frame_idx / max_frames * 100
        fps_current = frame_idx / elapsed
        eta = (max_frames - frame_idx) / fps_current
        print(f"进度: {progress:.1f}% | 帧:{frame_idx}/{max_frames} | "
              f"FPS:{fps_current:.1f} | 剩余时间:{eta:.0f}秒")

# 释放资源
cap.release()
out.release()

# 统计
elapsed = time.time() - start_time
print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
print(f"处理帧数: {frame_idx}")
print(f"处理时间: {elapsed:.1f}秒")
print(f"平均FPS: {frame_idx/elapsed:.1f}")
print(f"结果视频: {output_path}")
print()
print("最终统计:")
stats = detector.get_statistics()
print(f"  总进场: {stats['total_entries']}")
print(f"  总出场: {stats['total_exits']}")
print(f"  已清洗: {stats['washed_count']}")
print(f"  清洗率: {stats['wash_rate']*100:.1f}%")
print()
print("识别到的车牌统计:")
if recognized_plates:
    for plate, count in sorted(recognized_plates.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {plate}: {count}次")
else:
    print("  无")
print()
print("在场车辆:")
active = detector.get_active_records()
if active:
    for record in active:
        print(f"  - {record.license_plate} (进场时间: {record.entry_time.strftime('%H:%M:%S')})")
else:
    print("  无")
print()
print("已完成记录:")
completed = detector.get_completed_records()
if completed:
    for record in completed[-5:]:
        status = "已清洗" if record.is_washed else "未清洗"
        print(f"  - {record.license_plate} | {record.dwell_time:.1f}秒 | {status}")
else:
    print("  无")
