#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试单张图片的车牌识别 - 确认实际识别结果
"""

import sys
import io
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import cv2
from pathlib import Path

print("=" * 60)
print("单张图片车牌识别测试")
print("=" * 60)

# 测试保存的图片
test_images = [
    "storage/test_video/entry_0_20260423_091045.jpg",
    "storage/test_video/entry_1_20260423_091047.jpg",
    "storage/test_video_long/entry_1_20260423_111132.jpg",
]

# 初始化检测器
print("\n[1] 初始化检测器...")
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
    print("[OK] 检测器加载成功\n")
    
except Exception as e:
    print(f"[FAIL] 检测器加载失败: {e}")
    sys.exit(1)

# 测试每张图片
print("[2] 测试图片识别...")
print("-" * 60)

for img_path_str in test_images:
    img_path = Path(img_path_str)
    if not img_path.exists():
        print(f"\n图片不存在: {img_path}")
        continue
    
    print(f"\n测试: {img_path.name}")
    
    # 加载图片
    image = cv2.imread(str(img_path))
    if image is None:
        print(f"  [FAIL] 无法读取图片")
        continue
    
    h, w = image.shape[:2]
    print(f"  图片尺寸: {w}x{h}")
    
    # 调用车牌识别
    try:
        vehicle_bbox = (0, 0, w, h)
        plate = detector.detect_license_plate(image, vehicle_bbox)
        
        if plate:
            print(f"  ✅ 识别结果: {plate}")
        else:
            print(f"  ❌ 未识别到车牌")
            
    except Exception as e:
        print(f"  [ERROR] {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
print("\n实际车牌应该是: 沪EE7028")
print("请对比识别结果是否正确")
