#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据集划分工具
将提取的帧划分为训练集和验证集
"""

import os
import json
import shutil
import random
from pathlib import Path
from datetime import datetime

# 配置
RAW_FRAMES_DIR = r"C:\Users\Admini503\.openclaw\workspace\dataset\wall_inspection\raw_frames"
TRAIN_DIR = r"C:\Users\Admini503\.openclaw\workspace\dataset\wall_inspection\train\images"
VAL_DIR = r"C:\Users\Admini503\.openclaw\workspace\dataset\wall_inspection\val\images"
METADATA_FILE = r"C:\Users\Admini503\.openclaw\workspace\dataset\wall_inspection\metadata.json"

# 划分比例
TRAIN_RATIO = 0.8
VAL_RATIO = 0.2

def split_dataset():
    """划分数据集"""
    # 获取所有帧文件
    frame_files = sorted([f for f in os.listdir(RAW_FRAMES_DIR) if f.endswith('.jpg')])
    
    print(f"总帧数: {len(frame_files)}")
    
    # 随机打乱
    random.seed(42)  # 固定随机种子，保证可重复
    random.shuffle(frame_files)
    
    # 划分
    train_size = int(len(frame_files) * TRAIN_RATIO)
    train_files = frame_files[:train_size]
    val_files = frame_files[train_size:]
    
    print(f"训练集: {len(train_files)} 帧")
    print(f"验证集: {len(val_files)} 帧")
    
    # 创建目录
    os.makedirs(TRAIN_DIR, exist_ok=True)
    os.makedirs(VAL_DIR, exist_ok=True)
    
    # 复制文件到训练集
    for f in train_files:
        src = os.path.join(RAW_FRAMES_DIR, f)
        dst = os.path.join(TRAIN_DIR, f)
        shutil.copy2(src, dst)
    
    # 复制文件到验证集
    for f in val_files:
        src = os.path.join(RAW_FRAMES_DIR, f)
        dst = os.path.join(VAL_DIR, f)
        shutil.copy2(src, dst)
    
    print(f"\n文件已复制到:")
    print(f"  训练集: {TRAIN_DIR}")
    print(f"  验证集: {VAL_DIR}")
    
    # 生成元数据模板
    metadata = {
        "created_at": datetime.now().isoformat(),
        "total_frames": len(frame_files),
        "train_frames": len(train_files),
        "val_frames": len(val_files),
        "train_files": train_files,
        "val_files": val_files,
        "annotations": {}
    }
    
    # 为每个文件创建空的标注模板
    for f in frame_files:
        metadata["annotations"][f] = {
            "phase": "",  # preparation/spraying/leveling/curing/inspection
            "wall_status": "",  # bare/meshed/coated/finished
            "equipment_status": "",  # idle/spraying/moving/cleaning
            "defects": [],  # crack, hollow, stain, uneven, etc.
            "quality_score": None,  # 0-100
            "bboxes": []  # YOLO format: [class_id, x_center, y_center, width, height]
        }
    
    # 保存元数据
    with open(METADATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    print(f"\n元数据模板已生成: {METADATA_FILE}")
    print("请使用 LabelImg 或 CVAT 进行标注，然后更新 metadata.json")

if __name__ == "__main__":
    split_dataset()
