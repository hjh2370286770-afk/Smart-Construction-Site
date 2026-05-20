"""
视频流处理器测试
测试多路视频流处理功能
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


async def test_stream_processor():
    """测试视频流处理器"""
    print("\n" + "=" * 60)
    print("测试: 视频流处理器")
    print("=" * 60)
    
    try:
        # 初始化
        config = get_config("./config")
        engine = create_detector_engine(config)
        
        manager = MultiStreamManager(
            config_manager=config,
            detector_engine=engine,
            output_base_dir="./test_output"
        )
        
        # 从配置初始化
        manager.initialize_from_config()
        
        print(f"[OK] 创建 {len(manager.processors)} 个处理器")
        
        # 显示状态
        for camera_id, processor in manager.processors.items():
            status = processor.get_status()
            print(f"\n  摄像头: {status['name']} ({camera_id})")
            print(f"  - URL: {processor.config.url[:50]}...")
            print(f"  - 状态: {status['status']}")
            print(f"  - 模型: {processor.detector.get_model_info()['name']}")
        
        # 测试事件回调
        events = []
        async def on_event(event):
            events.append(event)
            
        manager.add_event_callback(on_event)
        print("\n[OK] 事件回调已注册")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_main_program():
    """测试主程序初始化"""
    print("\n" + "=" * 60)
    print("测试: 主程序初始化")
    print("=" * 60)
    
    try:
        from main import SafetyMonitor
        
        monitor = SafetyMonitor(
            config_dir="./config",
            output_dir="./test_output"
        )
        
        await monitor.initialize()
        
        print("\n[OK] 主程序初始化成功")
        print(f"  - 处理器数量: {len(monitor.stream_manager.processors)}")
        
        # 获取汇总
        summary = monitor.stream_manager.get_summary()
        print(f"  - 摄像头总数: {summary['total_cameras']}")
        
        return True
        
    except Exception as e:
        print(f"[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("视频流处理器测试")
    print("=" * 60)
    
    results = {
        "视频流处理器": await test_stream_processor(),
        "主程序初始化": await test_main_program(),
    }
    
    # 汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "[OK] 通过" if result else "[FAIL] 失败"
        print(f"  {status}: {name}")
    
    print(f"\n总计: {passed}/{total} 通过")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
