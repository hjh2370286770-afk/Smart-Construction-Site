#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试正则表达式匹配
"""

import sys
import io
import re
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 测试文本
text = "云台TJET瑞江车GENLVON上海鑫签遣物有限公司685恋狮MSOO320685总质量31000KGEE7028"

print("原始文本:")
print(text)
print()

# 测试正则
pattern = r'([京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z][A-Z0-9]{5,7})'

print(f"正则: {pattern}")
print()

matches = re.findall(pattern, text)
print(f"匹配结果: {matches}")
print()

# 检查文本中是否有"沪"
if '沪' in text:
    print("文本中包含 '沪'")
    idx = text.index('沪')
    print(f"'沪'的位置: {idx}")
    print(f"'沪'后面的字符: {text[idx:idx+10]}")
else:
    print("文本中不包含 '沪'")
    print("可能OCR识别成了其他字符")
    
    # 检查是否有类似字符
    for char in text:
        if char in '沪沪沪':
            print(f"找到类似字符: {char}")
