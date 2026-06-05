#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试EasyOCR是否能正常识别车牌
"""

import sys
import io
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import cv2
import numpy as np
from pathlib import Path

print("=" * 60)
print("EasyOCR 车牌识别测试")
print("=" * 60)

# 测试图片路径
VIDEO_PATH = r"D:\Users\Admini503\OneDrive\Desktop\文件\视觉识别\微信视频2026-04-23_090043_727.mp4"

# 打开视频
print("\n[1] 打开视频...")
cap = cv2.VideoCapture(VIDEO_PATH)
if not cap.isOpened():
    print("[FAIL] 无法打开视频")
    sys.exit(1)

# 读取一帧
ret, frame = cap.read()
cap.release()

if not ret:
    print("[FAIL] 无法读取视频帧")
    sys.exit(1)

print(f"[OK] 读取帧成功，尺寸: {frame.shape}")

# 初始化EasyOCR
print("\n[2] 初始化EasyOCR...")
try:
    from plate_ocr import PlateOCR
    
    ocr = PlateOCR(engine='easyocr')
    ocr.init()
    print("[OK] EasyOCR初始化成功")
except Exception as e:
    print(f"[FAIL] EasyOCR初始化失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试识别车辆区域
print("\n[3] 测试识别车辆区域...")

# 模拟一个车辆区域（取画面中间偏下部分，假设有车辆）
h, w = frame.shape[:2]
vehicle_region = frame[int(h*0.4):int(h*0.8), int(w*0.3):int(w*0.7)]

print(f"车辆区域尺寸: {vehicle_region.shape}")

# 保存测试图片
output_dir = Path("storage/test_ocr")
output_dir.mkdir(parents=True, exist_ok=True)
cv2.imwrite(str(output_dir / "vehicle_region.jpg"), vehicle_region)
print(f"车辆区域已保存到: {output_dir / 'vehicle_region.jpg'}")

# 尝试识别
print("\n[4] 尝试OCR识别...")
result = ocr.recognize(vehicle_region)

if result:
    print(f"[OK] 识别结果: {result}")
else:
    print("[INFO] 未识别到文字")

# 测试车牌格式验证
print("\n[5] 测试车牌格式验证...")
from plate_ocr import validate_plate_number

test_plates = [
    "京A12345",
    "京AD12345",
    "使123456",
    "京A1234警",
    "ABC123",
    "12345",
]

for plate in test_plates:
    valid = validate_plate_number(plate)
    print(f"  {plate}: {'✓' if valid else '✗'}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
