#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动下载并安装GPU版PyTorch
支持CUDA 11.8
"""

import os
import sys
import subprocess
import urllib.request
import tempfile
import shutil
from pathlib import Path

# 设置UTF-8编码
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 配置
CUDA_VERSION = "cu118"  # CUDA 11.8
TORCH_VERSION = "2.0.1"
TORCHVISION_VERSION = "0.15.2"
TORCHAUDIO_VERSION = "2.0.2"

# 下载地址
BASE_URL = "https://download.pytorch.org/whl/cu118"
PACKAGES = {
    "torch": f"{BASE_URL}/torch-{TORCH_VERSION}%2B{CUDA_VERSION}-cp38-cp38-win_amd64.whl",
    "torchvision": f"{BASE_URL}/torchvision-{TORCHVISION_VERSION}%2B{CUDA_VERSION}-cp38-cp38-win_amd64.whl",
    "torchaudio": f"{BASE_URL}/torchaudio-{TORCHAUDIO_VERSION}%2B{CUDA_VERSION}-cp38-cp38-win_amd64.whl",
}

def print_header(text):
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)

def print_step(step_num, text):
    print(f"\n[步骤 {step_num}] {text}")

def run_command(cmd, description):
    """运行命令并返回结果"""
    print(f"  执行: {description}")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            print(f"  [OK] {description}")
            return True
        else:
            print(f"  [FAIL] {description}")
            print(f"  错误: {result.stderr}")
            return False
    except Exception as e:
        print(f"  [FAIL] {description}: {e}")
        return False

def check_current_pytorch():
    """检查当前PyTorch版本"""
    try:
        import torch
        version = torch.__version__
        cuda_available = torch.cuda.is_available()
        print(f"  当前PyTorch版本: {version}")
        print(f"  CUDA可用: {cuda_available}")
        
        if cuda_available:
            print(f"  CUDA版本: {torch.version.cuda}")
            print(f"  GPU: {torch.cuda.get_device_name(0)}")
            return True
        else:
            return False
    except ImportError:
        print("  PyTorch未安装")
        return None

def uninstall_cpu_pytorch():
    """卸载CPU版PyTorch"""
    print_step(1, "卸载现有PyTorch...")
    
    packages = ["torch", "torchvision", "torchaudio"]
    for pkg in packages:
        run_command(f"pip uninstall {pkg} -y", f"卸载 {pkg}")
    
    # 清理缓存
    run_command("pip cache purge", "清理pip缓存")
    print("  [OK] 卸载完成")

def download_file(url, dest_path, description):
    """下载文件并显示进度"""
    print(f"  下载: {description}")
    print(f"  URL: {url}")
    
    def progress_hook(count, block_size, total_size):
        percent = int(count * block_size * 100 / total_size)
        percent = min(percent, 100)
        sys.stdout.write(f"\r  进度: {percent}%")
        sys.stdout.flush()
    
    try:
        urllib.request.urlretrieve(url, dest_path, reporthook=progress_hook)
        print()  # 换行
        print(f"  [OK] 下载完成: {dest_path}")
        return True
    except Exception as e:
        print(f"\n  [FAIL] 下载失败: {e}")
        return False

def install_from_whl(whl_path, description):
    """从whl文件安装"""
    print(f"  安装: {description}")
    cmd = f"pip install {whl_path} --user"
    return run_command(cmd, f"安装 {description}")

def install_pytorch_offline():
    """离线安装PyTorch GPU版"""
    print_step(2, "下载并安装GPU版PyTorch...")
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp(prefix="pytorch_gpu_")
    print(f"  临时目录: {temp_dir}")
    
    try:
        # 下载并安装每个包
        for pkg_name, url in PACKAGES.items():
            whl_filename = f"{pkg_name}.whl"
            whl_path = os.path.join(temp_dir, whl_filename)
            
            # 下载
            if not download_file(url, whl_path, pkg_name):
                print(f"  [FAIL] 下载 {pkg_name} 失败，尝试在线安装...")
                return False
            
            # 安装
            if not install_from_whl(whl_path, pkg_name):
                return False
        
        print("  [OK] 所有包安装完成")
        return True
        
    finally:
        # 清理临时目录
        print(f"  清理临时目录: {temp_dir}")
        shutil.rmtree(temp_dir, ignore_errors=True)

def install_pytorch_online():
    """在线安装PyTorch GPU版"""
    print_step(2, "在线安装GPU版PyTorch...")
    
    # 使用清华镜像
    cmd = f"pip install torch=={TORCH_VERSION}+cu118 torchvision=={TORCHVISION_VERSION}+cu118 torchaudio=={TORCHAUDIO_VERSION}+cu118 -f https://download.pytorch.org/whl/torch_stable.html --user"
    
    return run_command(cmd, "在线安装PyTorch GPU版")

def install_cuda_toolkit():
    """检查/提示安装CUDA Toolkit"""
    print_step(3, "检查CUDA Toolkit...")
    
    cuda_path = os.environ.get("CUDA_PATH", "")
    if cuda_path and os.path.exists(cuda_path):
        print(f"  [OK] 找到CUDA Toolkit: {cuda_path}")
        return True
    else:
        print("  [WARN] 未找到CUDA Toolkit")
        print("  CUDA Toolkit是可选的，PyTorch已经包含CUDA运行时")
        print("  如果需要开发CUDA程序，可以从以下地址下载：")
        print("  https://developer.nvidia.com/cuda-downloads")
        return True

def verify_installation():
    """验证安装"""
    print_step(4, "验证安装...")
    
    # 重新加载模块
    if 'torch' in sys.modules:
        del sys.modules['torch']
    
    try:
        import torch
        print(f"  PyTorch版本: {torch.__version__}")
        print(f"  CUDA可用: {torch.cuda.is_available()}")
        
        if torch.cuda.is_available():
            print(f"  CUDA版本: {torch.version.cuda}")
            print(f"  GPU数量: {torch.cuda.device_count()}")
            for i in range(torch.cuda.device_count()):
                print(f"  GPU {i}: {torch.cuda.get_device_name(i)}")
            print("\n  [OK] GPU版PyTorch安装成功！")
            return True
        else:
            print("\n  [FAIL] 安装后CUDA仍不可用")
            return False
            
    except Exception as e:
        print(f"  [FAIL] 验证失败: {e}")
        return False

def update_detector_config():
    """更新检测器配置使用GPU"""
    print_step(5, "更新检测器配置...")
    
    config_path = Path("config/vehicle_wash_config.yaml")
    if not config_path.exists():
        print(f"  [WARN] 配置文件不存在: {config_path}")
        return
    
    try:
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # 更新device为cuda
        if 'detector' in config and 'model' in config['detector']:
            config['detector']['model']['device'] = 'cuda'
            
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
            
            print(f"  [OK] 已更新配置文件，使用GPU: cuda")
        else:
            print(f"  [WARN] 配置文件结构不符")
            
    except Exception as e:
        print(f"  [WARN] 更新配置失败: {e}")

def main():
    print_header("PyTorch GPU版自动安装脚本")
    
    # 检查当前环境
    print_step(0, "检查当前环境...")
    current_status = check_current_pytorch()
    
    if current_status is True:
        print("\n  [INFO] GPU版PyTorch已安装，无需重复安装")
        update_detector_config()
        return 0
    
    # 卸载CPU版
    uninstall_cpu_pytorch()
    
    # 尝试离线安装
    success = install_pytorch_offline()
    
    # 如果离线失败，尝试在线安装
    if not success:
        print("\n  离线安装失败，尝试在线安装...")
        success = install_pytorch_online()
    
    if not success:
        print("\n  [FAIL] 安装失败")
        return 1
    
    # 检查CUDA Toolkit
    install_cuda_toolkit()
    
    # 验证安装
    if not verify_installation():
        print("\n  [FAIL] 安装验证失败")
        print("  可能的解决方案：")
        print("  1. 检查NVIDIA驱动是否安装")
        print("  2. 重启终端后重试")
        print("  3. 手动下载安装: https://pytorch.org/get-started/locally/")
        return 1
    
    # 更新配置
    update_detector_config()
    
    print_header("安装完成")
    print("""
  现在可以运行检测器使用GPU加速了！
  
  测试命令:
    python test_detector.py
    
  注意:
    - 首次运行会下载模型文件
    - GPU模式比CPU快3-5倍
    - RTX 3060 12GB可同时处理多路视频
    """)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
