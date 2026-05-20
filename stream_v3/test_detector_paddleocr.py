#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试车辆清洗检测器 - 使用 PaddleOCR
"""

import sys
import io
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import cv2
from pathlib import Path

print("=" * 60)
print("车辆清洗检测器 - PaddleOCR 测试")
print("=" * 60)

# 加载车辆区域图片
vehicle_path = Path("storage/test_ocr/vehicle_region.jpg")
if not vehicle_path.exists():
    print("[FAIL] 找不到车辆区域图片")
    sys.exit(1)

print(f"[OK] 找到车辆区域图片: {vehicle_path}")

# 初始化检测器
print("\n[1] 初始化检测器（使用 PaddleOCR）...")
try:
    from detectors.vehicle_wash_detector import VehicleWashDetector
    
    detector_config = {
        'path': 'yolov8n.pt',
        'device': 'cpu',
        'conf_threshold': 0.5,
        'iou_threshold': 0.45,
        'img_size': 640,
        'ocr_engine': 'paddleocr',  # 使用 PaddleOCR
        'wash_time_min': 300,
        'wash_time_max': 1800,
        'entry_line_y': 300,
        'exit_line_y': 500,
        'save_images': False,
    }
    
    detector = VehicleWashDetector(detector_config)
    print("[OK] 检测器初始化成功\n")
    
except Exception as e:
    print(f"[FAIL] 检测器初始化失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试处理帧
print("[2] 测试处理帧...")
print("-" * 60)

# 加载图片
frame = cv2.imread(str(vehicle_path))
print(f"图片尺寸: {frame.shape[1]}x{frame.shape[0]}")

# 处理帧
print("\n开始处理...")
result_frame, updated_records = detector.process_frame(frame)

# 显示结果
print(f"\n处理完成!")
print(f"更新记录数: {len(updated_records)}")

if updated_records:
    for record in updated_records:
        print(f"\n  车牌: {record.license_plate}")
        print(f"  进场时间: {record.entry_time}")
        print(f"  是否清洗: {'是' if record.is_washed else '否'}")

# 显示统计
print("\n" + "-" * 60)
print("\n[3] 统计信息...")
stats = detector.get_statistics()
print(f"  总进场: {stats['total_entries']}")
print(f"  总出场: {stats['total_exits']}")
print(f"  已清洗: {stats['washed_count']}")
print(f"  清洗率: {stats['wash_rate']*100:.1f}%")

print("\n" + "=" * 60)
print("测试完成!")
print("=" * 60)
print("\n✅ PaddleOCR 集成成功！")
