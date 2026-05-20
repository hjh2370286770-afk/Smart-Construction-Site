#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试前后端连接
"""

import asyncio
import sys
import io
from pathlib import Path
import urllib.request
import json

# 修复 Windows 控制台编码
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from utils.config_loader import get_config
from detectors import create_detector_engine
from core import MultiStreamManager

async def test_full_stack():
    """测试完整堆栈"""
    print("=" * 60)
    print("启动后端服务...")
    print("=" * 60)
    
    # 加载配置
    config_manager = get_config("./config")
    
    # 初始化检测引擎
    detector_engine = create_detector_engine(config_manager)
    
    # 初始化视频流管理器
    stream_manager = MultiStreamManager(
        config_manager=config_manager,
        detector_engine=detector_engine,
        output_base_dir="./output"
    )
    stream_manager.initialize_from_config()
    
    # 启动 Web 服务
    from web.main import create_app
    from web.dependencies import set_stream_manager, set_config_manager
    from web.websocket.events import websocket_event_handler
    
    set_stream_manager(stream_manager)
    set_config_manager(config_manager)
    stream_manager.add_event_callback(websocket_event_handler)
    
    import uvicorn
    
    app = create_app(stream_manager, config_manager)
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="warning",  # 减少日志输出
        access_log=False
    )
    server = uvicorn.Server(config)
    
    # 在后台启动服务器
    server_task = asyncio.create_task(server.serve())
    
    # 等待服务器启动
    print("等待服务器启动...")
    await asyncio.sleep(3)
    
    # 测试 API
    print("\n" + "=" * 60)
    print("测试 API 连接...")
    print("=" * 60)
    
    try:
        # Health check
        res = urllib.request.urlopen('http://localhost:8000/api/health', timeout=5)
        print(f"✓ Health: {res.read().decode()}")
    except Exception as e:
        print(f"✗ Health check failed: {e}")
    
    try:
        # Cameras
        res = urllib.request.urlopen('http://localhost:8000/api/cameras', timeout=5)
        data = json.loads(res.read().decode())
        print(f"✓ Cameras: Found {len(data)} cameras")
        for cam in data:
            print(f"  - {cam['id']}: {cam['name']} ({cam['status'] or 'stopped'})")
    except Exception as e:
        print(f"✗ Cameras API failed: {e}")
    
    try:
        # Sites
        res = urllib.request.urlopen('http://localhost:8000/api/sites', timeout=5)
        data = json.loads(res.read().decode())
        print(f"✓ Sites: Found {len(data)} sites")
        for site in data:
            print(f"  - {site['id']}: {site['name']}")
    except Exception as e:
        print(f"✗ Sites API failed: {e}")
    
    try:
        # Stats
        res = urllib.request.urlopen('http://localhost:8000/api/stats/realtime', timeout=5)
        data = json.loads(res.read().decode())
        print(f"✓ Stats: {data}")
    except Exception as e:
        print(f"✗ Stats API failed: {e}")
    
    print("\n" + "=" * 60)
    print("后端服务运行中...")
    print("前端可以通过以下地址连接:")
    print("  - API: http://localhost:8000/api")
    print("  - WebSocket: ws://localhost:8000/ws/events")
    print("=" * 60)
    print("\n按 Ctrl+C 停止服务")
    
    try:
        await server_task
    except asyncio.CancelledError:
        print("\n服务已停止")

if __name__ == "__main__":
    try:
        asyncio.run(test_full_stack())
    except KeyboardInterrupt:
        print("\n\n停止")
