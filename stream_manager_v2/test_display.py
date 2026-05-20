#!/usr/bin/env python3
"""
带显示的视频流测试
可以看到实时画面和检测结果
"""

import sys
import asyncio
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import logging
logging.basicConfig(level=logging.INFO)

from utils.config_loader import get_config
from detectors import create_detector_engine
from core import MultiStreamManager


async def test_with_display():
    """带显示窗口的测试"""
    print("\n" + "="*60)
    print("视频流测试 - 带显示窗口")
    print("="*60)
    print("按键: q=退出, p=暂停")
    print("="*60)
    
    # 初始化
    config = get_config("./config")
    engine = create_detector_engine(config)
    
    manager = MultiStreamManager(
        config_manager=config,
        detector_engine=engine,
        output_base_dir="./output"
    )
    
    # 从配置初始化
    manager.initialize_from_config()
    
    print(f"\n启动 {len(manager.processors)} 个视频流...")
    
    # 启动（带显示）
    for processor in manager.processors.values():
        processor.enable_display = True  # 启用显示
    
    await manager.start_all()
    
    # 运行30秒
    print("\n运行30秒...")
    await asyncio.sleep(30)
    
    # 停止
    print("\n停止...")
    await manager.stop_all()
    
    # 打印统计
    summary = manager.get_summary()
    print("\n" + "="*60)
    print("测试统计")
    print("="*60)
    print(f"处理帧数: {summary['total_frames']}")
    print(f"检测次数: {summary['total_detections']}")
    print(f"违规次数: {summary['total_violations']}")
    
    print("\n[OK] 测试完成!")


if __name__ == "__main__":
    try:
        asyncio.run(test_with_display())
    except KeyboardInterrupt:
        print("\n用户中断")
