#!/usr/bin/env python3
"""
测试下载的 YOLOv8 裂缝检测预训练模型
"""

import os
import sys

# 添加 ultralytics 到路径
try:
    from ultralytics import YOLO
except ImportError:
    print("Error: ultralytics not installed")
    print("Install: pip install ultralytics")
    sys.exit(1)

# 模型路径
MODEL_PATH = r"C:\Users\Admini503\.openclaw\workspace\models\pretrained\yolov8n-crack-seg.pt"

# 测试图像路径 - 使用数据集中的图像
TEST_IMAGE = r"C:\Users\Admini503\.openclaw\workspace\dataset\wall_inspection\raw_frames\JHMH2405004008_20260331_132219_t02s.jpg"

print("=" * 60)
print("Testing YOLOv8 Crack Detection Pretrained Model")
print("=" * 60)
print()

# 检查模型文件
if not os.path.exists(MODEL_PATH):
    print(f"Error: Model not found at {MODEL_PATH}")
    sys.exit(1)

print(f"Model: {MODEL_PATH}")
print(f"Size: {os.path.getsize(MODEL_PATH) / (1024*1024):.2f} MB")
print()

# 加载模型
print("Loading model...")
try:
    model = YOLO(MODEL_PATH)
    print("Model loaded successfully!")
    print(f"Task: {model.task}")
    print()
except Exception as e:
    print(f"Error loading model: {e}")
    sys.exit(1)

# 检查测试图像
if not os.path.exists(TEST_IMAGE):
    print(f"Warning: Test image not found at {TEST_IMAGE}")
    print("Please provide a valid image path")
    sys.exit(1)

print(f"Test image: {TEST_IMAGE}")
print()

# 进行预测
print("Running prediction...")
try:
    results = model.predict(TEST_IMAGE, conf=0.25, save=False)
    
    # 分析结果
    for result in results:
        boxes = result.boxes
        masks = result.masks
        
        print(f"\nResults:")
        print(f"  Detected cracks: {len(boxes)}")
        
        if len(boxes) > 0:
            for i, box in enumerate(boxes):
                conf = box.conf.item()
                cls = int(box.cls.item())
                print(f"  Crack #{i+1}: confidence={conf:.3f}, class={cls}")
        else:
            print("  No cracks detected in this image")
        
        # 如果有分割掩码
        if masks is not None:
            print(f"  Segmentation masks: {len(masks)}")
    
    print("\nPrediction completed successfully!")
    
except Exception as e:
    print(f"Error during prediction: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("Model is ready to use!")
print("=" * 60)
