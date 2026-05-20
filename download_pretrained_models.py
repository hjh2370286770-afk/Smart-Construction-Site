#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 GitHub 下载墙面缺陷检测预训练模型
"""

import os
import urllib.request
import ssl
from pathlib import Path

# 禁用 SSL 验证（如果需要）
ssl._create_default_https_context = ssl._create_unverified_context

# 模型保存路径
MODELS_DIR = Path(r"C:\Users\Admini503\.openclaw\workspace\models\pretrained")
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# 预训练模型列表 - 知名的裂缝/缺陷检测模型
MODELS = {
    # YOLOv8 官方模型（作为基础）
    "yolov8n.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt",
    "yolov8s.pt": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s.pt",
    
    # 裂缝检测专用模型（如果有公开链接）
    # 注意：这些需要根据实际找到的模型更新
}

def download_file(url: str, dest_path: Path, chunk_size: int = 8192) -> bool:
    """
    下载文件并显示进度
    
    Args:
        url: 文件 URL
        dest_path: 保存路径
        chunk_size: 下载块大小
    
    Returns:
        是否成功
    """
    try:
        print(f"下载: {url}")
        print(f"保存到: {dest_path}")
        
        # 创建请求
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        req = urllib.request.Request(url, headers=headers)
        
        # 下载文件
        with urllib.request.urlopen(req, timeout=60) as response:
            total_size = int(response.headers.get('Content-Length', 0))
            downloaded = 0
            
            with open(dest_path, 'wb') as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    # 显示进度
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\r进度: {percent:.1f}% ({downloaded}/{total_size} bytes)", end='')
        
        print(f"\n✓ 下载完成: {dest_path.name}")
        return True
        
    except Exception as e:
        print(f"\n✗ 下载失败: {e}")
        if dest_path.exists():
            dest_path.unlink()
        return False


def download_from_github_raw(repo: str, path: str, filename: str) -> bool:
    """
    从 GitHub raw 下载文件
    
    Args:
        repo: 仓库名 (如 "username/repo")
        path: 文件路径
        filename: 保存的文件名
    """
    url = f"https://raw.githubusercontent.com/{repo}/main/{path}"
    dest = MODELS_DIR / filename
    return download_file(url, dest)


def main():
    """主函数"""
    print("=" * 60)
    print("墙面缺陷检测预训练模型下载工具")
    print("=" * 60)
    print()
    
    success_count = 0
    fail_count = 0
    
    # 1. 下载 YOLOv8 基础模型
    print("【1/2】下载 YOLOv8 基础模型...")
    print("-" * 40)
    
    for model_name, url in MODELS.items():
        dest_path = MODELS_DIR / model_name
        
        # 检查是否已存在
        if dest_path.exists():
            print(f"跳过（已存在）: {model_name}")
            success_count += 1
            continue
        
        if download_file(url, dest_path):
            success_count += 1
        else:
            fail_count += 1
        print()
    
    # 2. 尝试搜索并下载裂缝检测专用模型
    print("\n【2/2】搜索裂缝检测专用模型...")
    print("-" * 40)
    
    # 这里可以尝试从 Hugging Face 或 GitHub Releases 下载
    # 一些知名的裂缝检测模型：
    
    # 示例：尝试下载 CrackForest 相关模型（如果有公开链接）
    crack_models = [
        # 格式: (名称, URL)
        # 需要根据实际找到的模型填写
    ]
    
    if crack_models:
        for model_name, url in crack_models:
            dest_path = MODELS_DIR / model_name
            if dest_path.exists():
                print(f"跳过（已存在）: {model_name}")
                success_count += 1
                continue
            
            if download_file(url, dest_path):
                success_count += 1
            else:
                fail_count += 1
            print()
    else:
        print("暂无预配置的裂缝检测专用模型链接")
        print("建议手动搜索以下资源：")
        print("  - Hugging Face: https://huggingface.co/models?search=crack+detection")
        print("  - GitHub: 搜索 'crack detection yolov8' 或 'wall defect detection'")
    
    # 总结
    print("\n" + "=" * 60)
    print("下载总结")
    print("=" * 60)
    print(f"成功: {success_count}")
    print(f"失败: {fail_count}")
    print(f"保存位置: {MODELS_DIR}")
    
    # 列出已下载的模型
    print("\n已下载的模型:")
    for f in MODELS_DIR.iterdir():
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  - {f.name} ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
