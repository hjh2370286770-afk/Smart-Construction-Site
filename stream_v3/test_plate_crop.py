#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
精确裁剪车牌区域并测试OCR
"""

import sys
import io
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import cv2
import numpy as np
from pathlib import Path

print("=" * 60)
print("精确裁剪车牌区域测试")
print("=" * 60)

# 加载测试图片
image_path = Path("storage/test_ocr/vehicle_region.jpg")
image = cv2.imread(str(image_path))
h, w = image.shape[:2]

print(f"原图尺寸: {w}x{h}")

# 根据图片分析，车牌位置（估算）
# 车牌在保险杠中央，大约在图片的横向25%-65%，纵向55%-70%
plate_crops = [
    ("车牌区域1", image[int(h*0.55):int(h*0.72), int(w*0.28):int(w*0.62)]),
    ("车牌区域2", image[int(h*0.58):int(h*0.70), int(w*0.30):int(w*0.60)]),
    ("车牌区域3", image[int(h*0.60):int(h*0.68), int(w*0.32):int(w*0.58)]),
    ("扩大区域", image[int(h*0.50):int(h*0.75), int(w*0.25):int(w*0.65)]),
]

# 保存裁剪区域
output_dir = Path("storage/test_ocr/crops")
output_dir.mkdir(exist_ok=True)

for name, crop in plate_crops:
    cv2.imwrite(str(output_dir / f"{name}.jpg"), crop)
    print(f"保存: {name}.jpg - 尺寸: {crop.shape[1]}x{crop.shape[0]}")

# 查看裁剪的图片
print("\n请查看裁剪的图片，确认哪个包含完整车牌:")
for i, (name, _) in enumerate(plate_crops, 1):
    print(f"  {i}. storage/test_ocr/crops/{name}.jpg")

print("\n查看后告诉我哪个裁剪最准确，我再进行OCR测试")
