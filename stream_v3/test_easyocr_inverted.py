#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试EasyOCR识别颜色反转后的车牌
黄底黑字 -> 蓝底白字
"""

import sys
import io
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import cv2
from pathlib import Path

print("=" * 60)
print("EasyOCR 颜色反转车牌识别测试")
print("=" * 60)

# 加载原图和反转图
original_path = Path("storage/test_ocr/plate_correct.jpg")
inverted_path = Path("storage/test_ocr/processed/3_inverted.jpg")

if not original_path.exists():
    print("[FAIL] 找不到原图")
    sys.exit(1)

print(f"[OK] 找到原图: {original_path}")
print(f"[OK] 找到反转图: {inverted_path}")

# 初始化EasyOCR
print("\n[1] 初始化EasyOCR...")
try:
    from detectors.plate_ocr import PlateOCR, validate_plate_number
    
    ocr = PlateOCR(engine='easyocr')
    ocr.init()
    print("[OK] EasyOCR初始化成功\n")
    
except Exception as e:
    print(f"[FAIL] EasyOCR初始化失败: {e}")
    sys.exit(1)

# 测试不同图片
images = [
    ("原图（黄底黑字）", str(original_path)),
    ("颜色反转（蓝底白字）", str(inverted_path)),
]

# 额外处理：放大图片
original = cv2.imread(str(original_path))
inverted = cv2.imread(str(inverted_path))

# 放大2倍
original_large = cv2.resize(original, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
inverted_large = cv2.resize(inverted, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

# 保存放大后的图片
cv2.imwrite("storage/test_ocr/original_2x.jpg", original_large)
cv2.imwrite("storage/test_ocr/inverted_2x.jpg", inverted_large)

images.extend([
    ("原图放大2倍", "storage/test_ocr/original_2x.jpg"),
    ("反转图放大2倍", "storage/test_ocr/inverted_2x.jpg"),
])

# 测试识别
print("[2] 测试识别...")
print("-" * 60)

for name, img_path in images:
    print(f"\n测试: {name}")
    
    img = cv2.imread(img_path)
    if img is None:
        print(f"  [FAIL] 无法读取图片")
        continue
    
    print(f"  图片尺寸: {img.shape[1]}x{img.shape[0]}")
    
    # 识别
    result = ocr.recognize(img)
    
    if result:
        print(f"  识别结果: {result}")
        
        # 验证车牌格式
        valid = validate_plate_number(result)
        print(f"  车牌格式验证: {'✓ 通过' if valid else '✗ 不通过'}")
        
        if valid:
            print(f"  ✅ 成功识别车牌: {result}")
    else:
        print(f"  [INFO] 未识别到文字")

# 额外测试：灰度图
print("\n" + "-" * 60)
print("\n[3] 测试灰度图...")

gray_original = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
gray_inverted = cv2.cvtColor(inverted, cv2.COLOR_BGR2GRAY)

# 放大灰度图
gray_original_large = cv2.resize(gray_original, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
gray_inverted_large = cv2.resize(gray_inverted, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

cv2.imwrite("storage/test_ocr/gray_original_2x.jpg", gray_original_large)
cv2.imwrite("storage/test_ocr/gray_inverted_2x.jpg", gray_inverted_large)

gray_images = [
    ("原图灰度放大2倍", gray_original_large),
    ("反转图灰度放大2倍", gray_inverted_large),
]

for name, img in gray_images:
    print(f"\n测试: {name}")
    print(f"  图片尺寸: {img.shape[1]}x{img.shape[0]}")
    
    result = ocr.recognize(img)
    
    if result:
        print(f"  识别结果: {result}")
        valid = validate_plate_number(result)
        print(f"  车牌格式验证: {'✓ 通过' if valid else '✗ 不通过'}")
    else:
        print(f"  [INFO] 未识别到文字")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
