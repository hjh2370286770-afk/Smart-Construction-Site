#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试单张图片的车牌识别
"""

import sys
sys.path.insert(0, '.')

import cv2
from pathlib import Path

print("=" * 60)
print("测试3分10秒图片的车牌识别")
print("=" * 60)

# 加载图片
image_path = Path("storage/frame_at_3m10s.jpg")
if not image_path.exists():
    print("错误: 图片不存在")
    sys.exit(1)

print(f"\n加载图片: {image_path}")
image = cv2.imread(str(image_path))
print(f"图片尺寸: {image.shape[1]}x{image.shape[0]}")

# 初始化检测器
print("\n初始化检测器...")
try:
    from detectors.vehicle_wash_detector import VehicleWashDetector
    
    detector_config = {
        'path': 'yolov8n.pt',
        'device': 'cpu',
        'conf_threshold': 0.3,
        'iou_threshold': 0.45,
        'img_size': 640,
        'ocr_engine': 'paddleocr',
        'wash_time_min': 300,
        'wash_time_max': 1800,
        'entry_line_y': 300,
        'exit_line_y': 500,
        'save_images': False,
    }
    
    detector = VehicleWashDetector(detector_config)
    print("检测器加载成功!")
    
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 处理帧
print("\n处理图片...")
print("-" * 60)

try:
    result_frame, updated_records = detector.process_frame(image)
    
    if updated_records:
        for record in updated_records:
            status = "已清洗" if record.is_washed else "未清洗"
            print(f"\n识别结果:")
            print(f"  车牌: {record.license_plate}")
            print(f"  进场时间: {record.entry_time}")
            print(f"  状态: {status}")
    else:
        print("未检测到车辆或未能识别车牌")
        
    # 保存结果图片
    output_path = "storage/frame_at_3m10s_result.jpg"
    cv2.imwrite(output_path, result_frame)
    print(f"\n结果图片已保存: {output_path}")
    
except Exception as e:
    print(f"处理错误: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)
print("\n实际车牌应该是: 沪AZ50584 (新能源车牌)")
