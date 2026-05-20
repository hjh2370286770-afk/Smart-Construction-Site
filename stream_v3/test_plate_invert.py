#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
颜色反转处理 - 让EasyOCR能识别黄色车牌
黄底黑字 -> 白底黑字（类似蓝底白字车牌的对比度）
"""

import sys
import io
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import cv2
import numpy as np
from pathlib import Path

print("=" * 60)
print("颜色反转处理测试")
print("=" * 60)

# 加载车牌图片
plate_path = Path("storage/test_ocr/plate_correct.jpg")
plate = cv2.imread(str(plate_path))

if plate is None:
    print("[FAIL] 无法读取车牌图片")
    sys.exit(1)

print(f"[OK] 加载车牌图片: {plate.shape[1]}x{plate.shape[0]}")

# 保存各种处理后的图片
output_dir = Path("storage/test_ocr/processed")
output_dir.mkdir(exist_ok=True)

# 1. 原图
cv2.imwrite(str(output_dir / "1_original.jpg"), plate)

# 2. 灰度图
gray = cv2.cvtColor(plate, cv2.COLOR_BGR2GRAY)
cv2.imwrite(str(output_dir / "2_gray.jpg"), gray)

# 3. 颜色反转（黄底黑字 -> 蓝底白字效果）
# 黄色在BGR中大约是 (0, 255, 255)，反转后变成 (255, 0, 0) 蓝色
inverted = cv2.bitwise_not(plate)
cv2.imwrite(str(output_dir / "3_inverted.jpg"), inverted)

# 4. 自适应阈值（自动二值化）
adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                  cv2.THRESH_BINARY, 11, 2)
cv2.imwrite(str(output_dir / "4_adaptive.jpg"), adaptive)

# 5. OTSU自动阈值
_, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
cv2.imwrite(str(output_dir / "5_otsu.jpg"), otsu)

# 6. 颜色范围提取（提取黄色区域）
hsv = cv2.cvtColor(plate, cv2.COLOR_BGR2HSV)
# 黄色的HSV范围
lower_yellow = np.array([20, 100, 100])
upper_yellow = np.array([40, 255, 255])
yellow_mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
cv2.imwrite(str(output_dir / "6_yellow_mask.jpg"), yellow_mask)

# 7. 黄色区域反转（变成白底黑字）
yellow_inverted = cv2.bitwise_not(yellow_mask)
cv2.imwrite(str(output_dir / "7_yellow_inverted.jpg"), yellow_inverted)

# 8. 增强对比度
lab = cv2.cvtColor(plate, cv2.COLOR_BGR2LAB)
l, a, b = cv2.split(lab)
clache = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
l_enhanced = clache.apply(l)
enhanced = cv2.merge([l_enhanced, a, b])
enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
cv2.imwrite(str(output_dir / "8_enhanced.jpg"), enhanced)

print(f"\n[OK] 已保存8种处理后的图片到: {output_dir}")

# 测试OCR识别
print("\n" + "=" * 60)
print("OCR识别测试")
print("=" * 60)

try:
    from detectors.plate_ocr import PlateOCR, validate_plate_number
    
    print("\n初始化EasyOCR...")
    ocr = PlateOCR(engine='easyocr')
    ocr.init()
    print("[OK] EasyOCR初始化成功\n")
    
    # 测试每种处理方法
    methods = [
        ("原图", plate),
        ("灰度图", gray),
        ("颜色反转", inverted),
        ("自适应阈值", adaptive),
        ("OTSU阈值", otsu),
        ("黄色掩码", yellow_mask),
        ("黄色反转", yellow_inverted),
        ("对比度增强", enhanced),
    ]
    
    for name, img in methods:
        result = ocr.recognize(img)
        if result:
            valid = validate_plate_number(result)
            status = "✓" if valid else "✗"
            print(f"{name:12s}: {result:20s} [{status}]")
        else:
            print(f"{name:12s}: 未识别到文字")
            
except Exception as e:
    print(f"[FAIL] 错误: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
print("\n请查看处理后的图片，找出效果最好的处理方法")
