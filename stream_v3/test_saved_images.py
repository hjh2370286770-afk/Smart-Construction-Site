#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试保存的车辆区域图片的车牌识别
"""

import sys
import io
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import cv2
from pathlib import Path

print("=" * 60)
print("测试保存图片的车牌识别")
print("=" * 60)

# 初始化检测器
print("\n[1] 初始化检测器...")
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
        'save_images': False,
    }
    
    detector = VehicleWashDetector(detector_config)
    print("[OK] 检测器加载成功\n")
    
except Exception as e:
    print(f"[FAIL] 检测器加载失败: {e}")
    sys.exit(1)

# 测试保存的图片
image_dir = Path("storage/test_video")
image_files = list(image_dir.glob("entry_*.jpg"))[:5]  # 测试前5张

print(f"[2] 测试 {len(image_files)} 张图片...")
print("-" * 60)

for img_path in image_files:
    print(f"\n测试: {img_path.name}")
    
    # 加载图片
    image = cv2.imread(str(img_path))
    if image is None:
        print(f"  [FAIL] 无法读取图片")
        continue
    
    print(f"  图片尺寸: {image.shape[1]}x{image.shape[0]}")
    
    # 尝试识别车牌
    try:
        # 模拟车辆边界框（整张图片）
        h, w = image.shape[:2]
        vehicle_bbox = (0, 0, w, h)
        
        # 调用车牌识别
        plate = detector.detect_license_plate(image, vehicle_bbox)
        
        if plate:
            print(f"  ✅ 识别到车牌: {plate}")
        else:
            print(f"  ❌ 未识别到车牌")
            
    except Exception as e:
        print(f"  [ERROR] {e}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
