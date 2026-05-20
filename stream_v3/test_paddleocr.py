#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试PaddleOCR车牌识别
"""

import sys
import io
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import cv2
from pathlib import Path

print("=" * 60)
print("PaddleOCR 车牌识别测试")
print("=" * 60)

# 加载车牌图片
plate_path = Path("storage/test_ocr/plate_correct.jpg")
plate = cv2.imread(str(plate_path))

if plate is None:
    print("[FAIL] 无法读取车牌图片")
    sys.exit(1)

print(f"[OK] 加载车牌图片: {plate.shape[1]}x{plate.shape[0]}")

# 初始化PaddleOCR
print("\n[1] 初始化PaddleOCR...")
try:
    from paddleocr import PaddleOCR
    
    # 初始化PaddleOCR（中文模型）
    ocr = PaddleOCR(lang='ch')
    print("[OK] PaddleOCR初始化成功")
    
except Exception as e:
    print(f"[FAIL] PaddleOCR初始化失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 测试识别
print("\n[2] 识别车牌...")
try:
    # PaddleOCR需要保存图片再识别
    temp_path = "storage/test_ocr/temp_plate.jpg"
    cv2.imwrite(temp_path, plate)
    
    # 识别
    result = ocr.ocr(temp_path, cls=True)
    
    if result and result[0]:
        print(f"[OK] 识别到 {len(result[0])} 个文本区域:")
        for line in result[0]:
            text = line[1][0]
            confidence = line[1][1]
            print(f"  文本: {text} | 置信度: {confidence:.2f}")
    else:
        print("[INFO] 未识别到文字")
        
except Exception as e:
    print(f"[FAIL] 识别失败: {e}")
    import traceback
    traceback.print_exc()

# 测试颜色反转后的图片
print("\n[3] 测试颜色反转后的图片...")
try:
    inverted_path = "storage/test_ocr/processed/3_inverted.jpg"
    inverted = cv2.imread(inverted_path)
    
    if inverted is not None:
        result = ocr.ocr(inverted_path, cls=True)
        
        if result and result[0]:
            print(f"[OK] 识别到 {len(result[0])} 个文本区域:")
            for line in result[0]:
                text = line[1][0]
                confidence = line[1][1]
                print(f"  文本: {text} | 置信度: {confidence:.2f}")
        else:
            print("[INFO] 未识别到文字")
    else:
        print("[WARN] 找不到反转后的图片")
        
except Exception as e:
    print(f"[FAIL] 识别失败: {e}")

# 测试二值化图片
print("\n[4] 测试二值化图片...")
try:
    binary_path = "storage/test_ocr/processed/5_otsu.jpg"
    binary = cv2.imread(binary_path)
    
    if binary is not None:
        result = ocr.ocr(binary_path, cls=True)
        
        if result and result[0]:
            print(f"[OK] 识别到 {len(result[0])} 个文本区域:")
            for line in result[0]:
                text = line[1][0]
                confidence = line[1][1]
                print(f"  文本: {text} | 置信度: {confidence:.2f}")
        else:
            print("[INFO] 未识别到文字")
    else:
        print("[WARN] 找不到二值化图片")
        
except Exception as e:
    print(f"[FAIL] 识别失败: {e}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
