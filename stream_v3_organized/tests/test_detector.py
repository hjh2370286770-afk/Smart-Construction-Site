#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试车辆清洗检测器加载
"""

import sys
import io
sys.path.insert(0, '.')

# 设置UTF-8编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print('=== 测试车辆清洗检测器加载 ===')
print()

# 测试导入
try:
    from vehicle_wash_detector import VehicleWashDetector, VehicleRecord
    print('[OK] 成功导入 VehicleWashDetector')
except Exception as e:
    print(f'[FAIL] 导入失败: {e}')
    sys.exit(1)

# 测试配置加载
try:
    import yaml
    with open('config/vehicle_wash_config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    print('[OK] 成功加载配置文件')
except Exception as e:
    print(f'[FAIL] 配置文件加载失败: {e}')
    sys.exit(1)

# 测试检测器初始化
try:
    detector_config = {
        'path': str(Path(__file__).parent.parent / 'models' / 'yolov8n.pt'),
        'device': 'cpu',
        'conf_threshold': 0.5,
        'iou_threshold': 0.45,
        'img_size': 640,
        'ocr_engine': 'easyocr',
        'wash_time_min': 300,
        'wash_time_max': 1800,
        'entry_line_y': 300,
        'exit_line_y': 500,
        'save_images': False,
    }

    print('正在初始化检测器...')
    print('（首次运行会自动下载YOLOv8n模型，约6MB）')
    detector = VehicleWashDetector(detector_config)
    print('[OK] 检测器初始化成功')

    # 测试统计信息
    stats = detector.get_statistics()
    print(f'   - 总进场数: {stats["total_entries"]}')
    print(f'   - 总出场数: {stats["total_exits"]}')
    print(f'   - 清洗数量: {stats["washed_count"]}')
    print(f'   - 清洗时间范围: {stats["wash_time_threshold"]["min"]}-{stats["wash_time_threshold"]["max"]}秒')

except Exception as e:
    print(f'[FAIL] 检测器初始化失败: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print('=== 所有测试通过 ===')
