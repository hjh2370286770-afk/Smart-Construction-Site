#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查GPU环境并提供安装指南
"""

import sys
import subprocess

print("=" * 60)
print("GPU环境检查")
print("=" * 60)

# 检查PyTorch
print("\n1. 检查PyTorch安装...")
try:
    import torch
    print(f"   PyTorch版本: {torch.__version__}")
    print(f"   CUDA可用: {torch.cuda.is_available()}")
    
    if torch.cuda.is_available():
        print(f"   CUDA版本: {torch.version.cuda}")
        print(f"   GPU数量: {torch.cuda.device_count()}")
        for i in range(torch.cuda.device_count()):
            print(f"   GPU {i}: {torch.cuda.get_device_name(i)}")
        print("\n✅ GPU环境已就绪！")
    else:
        print("\n❌ 当前是CPU版PyTorch，需要安装GPU版本")
        print("\n" + "=" * 60)
        print("安装GPU版PyTorch命令：")
        print("=" * 60)
        print("\n# 方法1：使用conda（推荐）")
        print("conda install pytorch torchvision torchaudio pytorch-cuda=11.8 -c pytorch -c nvidia")
        print("\n# 方法2：使用pip")
        print("pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118")
        print("\n# 方法3：使用清华镜像（国内）")
        print("pip install torch torchvision torchaudio -i https://pypi.tuna.tsinghua.edu.cn/simple")
        print("\n注意：")
        print("- 需要先安装NVIDIA显卡驱动")
        print("- 建议安装CUDA 11.8或12.1")
        print("- 安装后重启终端")
        
except ImportError:
    print("   PyTorch未安装")
    print("\n安装命令：")
    print("pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118")

# 检查ultralytics GPU支持
print("\n2. 检查Ultralytics GPU支持...")
try:
    import ultralytics
    print(f"   Ultralytics版本: {ultralytics.__version__}")
    
    # 尝试检测GPU
    from ultralytics import YOLO
    import torch
    
    if torch.cuda.is_available():
        print("   ✅ Ultralytics将使用GPU加速")
    else:
        print("   ⚠️  Ultralytics将使用CPU运行")
        
except ImportError:
    print("   Ultralytics未安装")

# 检查EasyOCR GPU支持
print("\n3. 检查EasyOCR GPU支持...")
try:
    import easyocr
    print(f"   EasyOCR版本: {easyocr.__version__}")
    
    import torch
    if torch.cuda.is_available():
        print("   ✅ EasyOCR可以使用GPU")
        print("   使用方式: easyocr.Reader(['ch_sim', 'en'], gpu=True)")
    else:
        print("   ⚠️  EasyOCR将使用CPU")
        
except ImportError:
    print("   EasyOCR未安装")

print("\n" + "=" * 60)
print("配置建议")
print("=" * 60)
print("""
在 vehicle_wash_config.yaml 中设置：

detector:
  model:
    device: "cuda"  # 使用GPU，或设为 "auto" 自动检测
    
  ocr:
    engine: "easyocr"
    # EasyOCR会自动使用GPU（如果PyTorch支持）
""")
