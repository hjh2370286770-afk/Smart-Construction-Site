#!/usr/bin/env python3
"""
下载 Hugging Face 上的 YOLOv8 裂缝检测预训练模型
"""

import urllib.request
import os

# 模型保存路径
MODELS_DIR = r"C:\Users\Admini503\.openclaw\workspace\models\pretrained"
os.makedirs(MODELS_DIR, exist_ok=True)

# Hugging Face 模型列表
MODELS = {
    # OpenSistemas 的裂缝分割模型 (推荐 - 有多个尺寸)
    "yolov8n-crack-seg.pt": "https://huggingface.co/OpenSistemas/YOLOv8-crack-seg/resolve/main/yolov8n/weights/best.pt",
    "yolov8s-crack-seg.pt": "https://huggingface.co/OpenSistemas/YOLOv8-crack-seg/resolve/main/yolov8s/weights/best.pt",
    "yolov8m-crack-seg.pt": "https://huggingface.co/OpenSistemas/YOLOv8-crack-seg/resolve/main/yolov8m/weights/best.pt",
    
    # hyunon 的裂缝检测模型
    "crack-yolov8.pt": "https://huggingface.co/hyunon/crack-yolov8/resolve/main/crack.pt",
}

def download_file(url, dest_path):
    """下载文件"""
    try:
        print(f"Downloading: {url}")
        print(f"Save to: {dest_path}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        req = urllib.request.Request(url, headers=headers)
        
        with urllib.request.urlopen(req, timeout=120) as response:
            total_size = int(response.headers.get('Content-Length', 0))
            downloaded = 0
            chunk_size = 8192
            
            with open(dest_path, 'wb') as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\rProgress: {percent:.1f}% ({downloaded}/{total_size} bytes)", end='')
        
        print(f"\n✓ Downloaded: {os.path.basename(dest_path)}")
        return True
        
    except Exception as e:
        print(f"\n✗ Failed: {e}")
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return False

def main():
    print("=" * 60)
    print("Download YOLOv8 Crack Detection Pretrained Models")
    print("=" * 60)
    print()
    
    success_count = 0
    fail_count = 0
    
    # 优先下载轻量级模型 (yolov8n)
    priority_models = ["yolov8n-crack-seg.pt", "crack-yolov8.pt"]
    
    for model_name in priority_models:
        if model_name not in MODELS:
            continue
            
        url = MODELS[model_name]
        dest_path = os.path.join(MODELS_DIR, model_name)
        
        # 检查是否已存在
        if os.path.exists(dest_path):
            size_mb = os.path.getsize(dest_path) / (1024 * 1024)
            print(f"Skip (exists): {model_name} ({size_mb:.2f} MB)")
            success_count += 1
            continue
        
        print(f"\n[{success_count + fail_count + 1}] Downloading {model_name}...")
        if download_file(url, dest_path):
            success_count += 1
        else:
            fail_count += 1
        print()
    
    # 总结
    print("\n" + "=" * 60)
    print("Download Summary")
    print("=" * 60)
    print(f"Success: {success_count}")
    print(f"Failed: {fail_count}")
    print(f"Save location: {MODELS_DIR}")
    
    # 列出已下载的模型
    print("\nDownloaded models:")
    for f in os.listdir(MODELS_DIR):
        if f.endswith('.pt'):
            size_mb = os.path.getsize(os.path.join(MODELS_DIR, f)) / (1024 * 1024)
            print(f"  - {f} ({size_mb:.2f} MB)")

if __name__ == "__main__":
    main()
