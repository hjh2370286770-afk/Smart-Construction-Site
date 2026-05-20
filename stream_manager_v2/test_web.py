#!/usr/bin/env python3
"""
测试 Web 服务
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from utils.config_loader import get_config
from detectors import create_detector_engine
from core import MultiStreamManager

async def test_web():
    """测试 Web 服务"""
    print("加载配置...")
    config_manager = get_config("./config")
    
    print("初始化检测引擎...")
    detector_engine = create_detector_engine(config_manager)
    
    print("初始化视频流管理器...")
    stream_manager = MultiStreamManager(
        config_manager=config_manager,
        detector_engine=detector_engine,
        output_base_dir="./output"
    )
    stream_manager.initialize_from_config()
    
    print("启动 Web 服务...")
    from web.main import create_app
    from web.dependencies import set_stream_manager, set_config_manager
    from web.websocket.events import websocket_event_handler
    
    set_stream_manager(stream_manager)
    set_config_manager(config_manager)
    stream_manager.add_event_callback(websocket_event_handler)
    
    import uvicorn
    config = uvicorn.Config(
        create_app(stream_manager, config_manager),
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
    server = uvicorn.Server(config)
    
    print("Web 服务启动在 http://0.0.0.0:8000")
    print("按 Ctrl+C 停止")
    
    await server.serve()

if __name__ == "__main__":
    try:
        asyncio.run(test_web())
    except KeyboardInterrupt:
        print("\n停止")
