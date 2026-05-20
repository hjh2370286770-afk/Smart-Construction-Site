#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
正确裁剪车牌区域并测试OCR
根据网格图精确定位
"""

import sys
import io
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import cv2
from pathlib import Path

print("=" * 60)
print("正确车牌裁剪和OCR测试")
print("=" * 60)

# 加载测试图片
image_path = Path("storage/test_ocr/vehicle_region.jpg")
image = cv2.imread(str(image_path))
h, w = image.shape[:2]

print(f"原图尺寸: {w}x{h}")

# 根据网格图，车牌在：横向45%-58%，纵向38%-48%
# 精确裁剪车牌区域
plate_x1 = int(w * 0.45)
plate_y1 = int(h * 0.38)
plate_x2 = int(w * 0.58)
plate_y2 = int(h * 0.48)

plate_crop = image[plate_y1:plate_y2, plate_x1:plate_x2]

print(f"\n车牌区域坐标: ({plate_x1}, {plate_y1}) - ({plate_x2}, {plate_y2})")
print(f"车牌区域尺寸: {plate_crop.shape[1]}x{plate_crop.shape[0]}")

# 保存车牌图片
output_path = Path("storage/test_ocr/plate_correct.jpg")
cv2.imwrite(str(output_path), plate_crop)
print(f"\n已保存车牌图片: {output_path}")

# 初始化OCR并测试
print("\n" + "=" * 60)
print("OCR识别测试")
print("=" * 60)

try:
    from detectors.plate_ocr import PlateOCR, validate_plate_number
    
    print("\n[1] 初始化EasyOCR...")
    ocr = PlateOCR(engine='easyocr')
    ocr.init()
    print("[OK] EasyOCR初始化成功")
    
    print("\n[2] 识别车牌...")
    result = ocr.recognize(plate_crop)
    
    if result:
        print(f"[OK] 识别结果: {result}")
        
        # 验证车牌格式
        valid = validate_plate_number(result)
        print(f"车牌格式验证: {'✓ 通过' if valid else '✗ 不通过'}")
        
        if valid:
            print(f"\n✅ 成功识别车牌: {result}")
        else:
            # 尝试清理
            import re
            cleaned = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', result)
            cleaned = cleaned.upper()
            print(f"清理后: {cleaned}")
            if validate_plate_number(cleaned):
                print(f"✅ 清理后识别成功: {cleaned}")
    else:
        print("[INFO] 未识别到文字")
        
        # 尝试图像增强
        print("\n[3] 尝试图像增强后识别...")
        
        # 转换为灰度图
        gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
        
        # 自适应阈值二值化
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                       cv2.THRESH_BINARY, 11, 2)
        
        # 保存增强后的图片
        cv2.imwrite("storage/test_ocr/plate_gray.jpg", gray)
        cv2.imwrite("storage/test_ocr/plate_binary.jpg", binary)
        
        # 尝试识别增强后的图片
        result_gray = ocr.recognize(gray)
        result_binary = ocr.recognize(binary)
        
        print(f"  灰度图识别: {result_gray if result_gray else '无'}")
        print(f"  二值图识别: {result_binary if result_binary else '无'}")
        
except Exception as e:
    print(f"[FAIL] 错误: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
print("\n生成的图片:")
print("  - storage/test_ocr/plate_correct.jpg (车牌区域)")
print("  - storage/test_ocr/plate_gray.jpg (灰度图)")
print("  - storage/test_ocr/plate_binary.jpg (二值图)")
