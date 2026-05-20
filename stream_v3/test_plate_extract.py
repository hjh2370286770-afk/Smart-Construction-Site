#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试车牌提取逻辑
"""

import sys
import io
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from detectors.plate_ocr import validate_plate_number

# 测试数据
test_cases = [
    "EE7028",
    "320685总质量31000KG沪EE7028",
    "沪EE7028",
    "云台TJET瑞江车GENLVON上海鑫签遣物有限公司685恋狮MSOO320685总质量31000KGEE7028",
]

print("=" * 60)
print("车牌提取测试")
print("=" * 60)

for text in test_cases:
    print(f"\n原始文本: {text}")
    
    # 测试验证
    valid = validate_plate_number(text)
    print(f"直接验证: {'OK' if valid else 'FAIL'}")
    
    # 测试清理提取
    from detectors.plate_ocr import PlateOCR
    ocr = PlateOCR(engine='paddleocr')
    cleaned = ocr._clean_plate_text(text)
    print(f"清理后: {cleaned}")
    
    valid_cleaned = validate_plate_number(cleaned)
    print(f"清理后验证: {'OK' if valid_cleaned else 'FAIL'}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
