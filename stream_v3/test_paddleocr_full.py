#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 PaddleOCR 识别车辆区域原图
"""

import sys
import io
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import cv2
from pathlib import Path

print("=" * 60)
print("PaddleOCR 车辆区域识别测试")
print("=" * 60)

# 加载车辆区域图片
vehicle_path = Path("storage/test_ocr/vehicle_region.jpg")
if not vehicle_path.exists():
    print("[FAIL] 找不到车辆区域图片")
    sys.exit(1)

print(f"[OK] 找到车辆区域图片: {vehicle_path}")

# 初始化 PaddleOCR
print("\n[1] 初始化 PaddleOCR...")
try:
    from paddleocr import PaddleOCR
    
    # 初始化（使用中文模型）
    ocr = PaddleOCR(
        use_angle_cls=True,
        lang='ch',
        show_log=False
    )
    print("[OK] PaddleOCR 初始化成功\n")
    
except Exception as e:
    print(f"[FAIL] PaddleOCR 初始化失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试识别
print("[2] 识别车辆区域...")
print("-" * 60)

# 加载图片
image = cv2.imread(str(vehicle_path))
print(f"图片尺寸: {image.shape[1]}x{image.shape[0]}")

# 识别
print("\n开始识别...")
result = ocr.ocr(str(vehicle_path), cls=True)

if result and result[0]:
    print(f"\n[OK] 识别到 {len(result[0])} 个文本区域:")
    for i, line in enumerate(result[0], 1):
        text = line[1][0]
        confidence = line[1][1]
        box = line[0]
        print(f"\n  区域 {i}:")
        print(f"    文本: {text}")
        print(f"    置信度: {confidence:.4f}")
        print(f"    位置: {box}")
else:
    print("\n[INFO] 未识别到文字")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
