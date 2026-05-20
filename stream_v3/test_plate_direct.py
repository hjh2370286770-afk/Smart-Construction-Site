#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接测试车牌图片OCR识别
"""

import sys
import io
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import cv2
from pathlib import Path

print("=" * 60)
print("车牌图片OCR识别测试")
print("=" * 60)

# 加载测试图片
image_path = Path("storage/test_ocr/vehicle_region.jpg")
if not image_path.exists():
    print(f"[FAIL] 图片不存在: {image_path}")
    sys.exit(1)

print(f"\n[1] 加载图片: {image_path}")
image = cv2.imread(str(image_path))
if image is None:
    print("[FAIL] 无法读取图片")
    sys.exit(1)

h, w = image.shape[:2]
print(f"[OK] 图片尺寸: {w}x{h}")

# 初始化EasyOCR
print("\n[2] 初始化EasyOCR...")
try:
    from detectors.plate_ocr import PlateOCR, validate_plate_number
    
    ocr = PlateOCR(engine='easyocr')
    ocr.init()
    print("[OK] EasyOCR初始化成功")
except Exception as e:
    print(f"[FAIL] EasyOCR初始化失败: {e}")
    sys.exit(1)

# 测试不同区域
print("\n[3] 测试不同区域识别...")

regions = [
    ("底部30%", image[int(h*0.7):, :]),
    ("底部40%", image[int(h*0.6):, :]),
    ("中间偏下", image[int(h*0.5):int(h*0.9), :]),
    ("全图", image),
]

for region_name, region_img in regions:
    print(f"\n  测试区域: {region_name} (尺寸: {region_img.shape[1]}x{region_img.shape[0]})")
    
    # 保存区域图片以便查看
    region_path = f"storage/test_ocr/region_{region_name.replace('%', '').replace('/', '_')}.jpg"
    cv2.imwrite(region_path, region_img)
    
    # OCR识别
    result = ocr.recognize(region_img)
    
    if result:
        print(f"    识别结果: {result}")
        
        # 验证车牌格式
        valid = validate_plate_number(result)
        print(f"    车牌格式验证: {'✓' if valid else '✗'}")
        
        if valid:
            print(f"    [OK] 成功识别车牌: {result}")
    else:
        print(f"    未识别到文字")

# 尝试裁剪车牌区域（根据图片手动定位）
print("\n[4] 尝试手动定位车牌区域...")
# 从图片看，车牌在底部中央位置
plate_region = image[int(h*0.55):int(h*0.75), int(w*0.25):int(w*0.65)]
print(f"  车牌区域尺寸: {plate_region.shape[1]}x{plate_region.shape[0]}")

cv2.imwrite("storage/test_ocr/plate_manual.jpg", plate_region)

result = ocr.recognize(plate_region)
if result:
    print(f"  识别结果: {result}")
    valid = validate_plate_number(result)
    print(f"  车牌格式验证: {'✓' if valid else '✗'}")
else:
    print("  未识别到文字")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
print("\n保存的区域图片:")
print("  - storage/test_ocr/region_底部30.jpg")
print("  - storage/test_ocr/region_底部40.jpg")
print("  - storage/test_ocr/region_中间偏下.jpg")
print("  - storage/test_ocr/region_全图.jpg")
print("  - storage/test_ocr/plate_manual.jpg (手动定位)")
