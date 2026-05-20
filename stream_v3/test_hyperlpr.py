#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 HyperLPR3 车牌识别
"""

import sys
import io
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import cv2
from pathlib import Path

print("=" * 60)
print("HyperLPR3 车牌识别测试")
print("=" * 60)

# 加载测试图片
plate_path = Path("storage/test_ocr/plate_correct.jpg")
if not plate_path.exists():
    print("[FAIL] 找不到车牌图片")
    sys.exit(1)

print(f"[OK] 找到车牌图片: {plate_path}")

# 初始化 HyperLPR3
print("\n[1] 初始化 HyperLPR3...")
try:
    import hyperlpr3 as lpr3
    
    # 创建识别器
    catcher = lpr3.LicensePlateCatcher()
    print("[OK] HyperLPR3 初始化成功\n")
    
except Exception as e:
    print(f"[FAIL] HyperLPR3 初始化失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试识别
print("[2] 测试识别...")
print("-" * 60)

# 加载图片
image = cv2.imread(str(plate_path))
print(f"图片尺寸: {image.shape[1]}x{image.shape[0]}")

# 识别
print("\n开始识别...")
results = catcher(image)

if results:
    print(f"\n[OK] 识别到 {len(results)} 个车牌:")
    for i, result in enumerate(results, 1):
        print(f"\n  车牌 {i}:")
        print(f"    车牌号: {result[0]}")
        print(f"    置信度: {result[1]:.4f}")
        print(f"    类型: {result[2]}")
        print(f"    位置: {result[3]}")
else:
    print("\n[INFO] 未识别到车牌")

# 测试原图（车辆区域）
print("\n" + "-" * 60)
print("\n[3] 测试车辆区域原图...")

vehicle_path = Path("storage/test_ocr/vehicle_region.jpg")
if vehicle_path.exists():
    vehicle = cv2.imread(str(vehicle_path))
    print(f"车辆区域尺寸: {vehicle.shape[1]}x{vehicle.shape[0]}")
    
    results = catcher(vehicle)
    
    if results:
        print(f"\n[OK] 识别到 {len(results)} 个车牌:")
        for i, result in enumerate(results, 1):
            print(f"\n  车牌 {i}:")
            print(f"    车牌号: {result[0]}")
            print(f"    置信度: {result[1]:.4f}")
            print(f"    类型: {result[2]}")
    else:
        print("\n[INFO] 未识别到车牌")
else:
    print("[WARN] 找不到车辆区域图片")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
