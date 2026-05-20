#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最终车牌裁剪和OCR测试
在原图上标记车牌位置并精确裁剪
"""

import sys
import io
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import cv2
import numpy as np
from pathlib import Path

print("=" * 60)
print("最终车牌裁剪测试")
print("=" * 60)

# 加载测试图片
image_path = Path("storage/test_ocr/vehicle_region.jpg")
image = cv2.imread(str(image_path))
h, w = image.shape[:2]

print(f"原图尺寸: {w}x{h}")

# 在原图上画网格，帮助定位
grid_image = image.copy()

# 画水平线（每10%一条）
for i in range(1, 10):
    y = int(h * i / 10)
    cv2.line(grid_image, (0, y), (w, y), (0, 255, 0), 1)
    cv2.putText(grid_image, f"{i*10}%", (10, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

# 画垂直线（每10%一条）
for i in range(1, 10):
    x = int(w * i / 10)
    cv2.line(grid_image, (x, 0), (x, h), (0, 255, 0), 1)
    cv2.putText(grid_image, f"{i*10}%", (x+5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

# 保存带网格的图片
cv2.imwrite("storage/test_ocr/grid_image.jpg", grid_image)
print("已保存带网格的图片: storage/test_ocr/grid_image.jpg")

# 根据观察，车牌大约在横向30%-60%，纵向60%-72%
# 尝试更精确的裁剪
plate_crops = [
    ("plate_exact", image[int(h*0.62):int(h*0.72), int(w*0.35):int(w*0.58)]),
    ("plate_wide", image[int(h*0.60):int(h*0.74), int(w*0.30):int(w*0.65)]),
    ("plate_tight", image[int(h*0.64):int(h*0.70), int(w*0.38):int(w*0.55)]),
]

output_dir = Path("storage/test_ocr/plates")
output_dir.mkdir(exist_ok=True)

print("\n保存裁剪区域:")
for name, crop in plate_crops:
    path = output_dir / f"{name}.jpg"
    cv2.imwrite(str(path), crop)
    print(f"  {name}.jpg - 尺寸: {crop.shape[1]}x{crop.shape[0]}")

print("\n请查看以下图片，确认哪个包含完整清晰的车牌:")
print("  1. storage/test_ocr/grid_image.jpg (带网格的原图)")
print("  2. storage/test_ocr/plates/plate_exact.jpg")
print("  3. storage/test_ocr/plates/plate_wide.jpg")
print("  4. storage/test_ocr/plates/plate_tight.jpg")
