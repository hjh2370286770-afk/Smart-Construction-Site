#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stream_manager_v2 主程序
多工地安全监控系统 - 下一代版本

功能：
1. 多路视频流并发处理
2. 可配置的多模型检测
3. 向量记忆系统
4. Web API 接口（预留）

使用方法：
    python main.py --config ./config
    python main.py --duration 600  # 运行10分钟
"""

import sys
import io
import asyncio
import argparse
import logging
import signal
from pathlib import Path

# 修复 Windows 控制台编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 获取项目根目录（脚本所在目录）
PROJECT_ROOT = Path(__file__).parent.absolute()

# 添加项目路径
sys.path.insert(0, str(PROJECT_ROOT))

from utils.config_loader import get_config
from detectors import create_detector_engine
from core import MultiStreamManager


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SafetyMonitor:
    """安全监控主控类"""
    
    def __init__(self, config_dir: str = None, output_dir: str = None):
        # 默认使用项目目录下的 config 和 output
        self.config_dir = config_dir or str(PROJECT_ROOT / "config")
        self.output_dir = Path(output_dir) if output_dir else PROJECT_ROOT / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 组件
        self.config_manager = None
        self.detector_engine = None
        self.stream_manager = None
        
        # 运行状态
        self.running = False
        
    async def initialize(self, enable_web: bool = True):
        """初始化系统"""
        logger.info("=" * 70)
        logger.info("初始化 stream_manager_v2 安全监控系统")
        logger.info("=" * 70)
        
        # 1. 加载配置
        logger.info("[1/4] 加载配置...")
        self.config_manager = get_config(self.config_dir)
        logger.info(f"   - 站点: {len(self.config_manager.sites)}")
        logger.info(f"   - 模型: {len(self.config_manager.models)}")
        
        # 2. 初始化检测引擎
        logger.info("[2/4] 初始化检测引擎...")
        self.detector_engine = create_detector_engine(self.config_manager)
        logger.info(f"   - 注册模型: {list(self.detector_engine.model_configs.keys())}")
        
        # 3. 初始化视频流管理器
        logger.info("[3/4] 初始化视频流管理器...")
        self.stream_manager = MultiStreamManager(
            config_manager=self.config_manager,
            detector_engine=self.detector_engine,
            output_base_dir=self.output_dir
        )
        
        # 添加事件回调
        self.stream_manager.add_event_callback(self._on_event)
        
        # 从配置创建处理器
        self.stream_manager.initialize_from_config()
        logger.info(f"   - 创建处理器: {len(self.stream_manager.processors)}")
        
        # 4. 设置信号处理
        logger.info("[4/4] 设置信号处理...")
        self._setup_signal_handlers()
        
        # 5. 启动 Web 服务（如果启用）
        web_config = self.config_manager.global_config.web
        if enable_web and isinstance(web_config, dict) and web_config.get('enabled', False):
            await self._start_web_server()
        
        logger.info("=" * 70)
        logger.info("初始化完成")
        logger.info("=" * 70)
    
    async def _start_web_server(self):
        """启动 Web 服务"""
        try:
            from web.main import create_app
            from web.dependencies import set_stream_manager, set_config_manager
            from web.websocket.events import websocket_event_handler
            
            # 设置依赖
            set_stream_manager(self.stream_manager)
            set_config_manager(self.config_manager)
            
            # 添加 WebSocket 事件处理器到流管理器
            self.stream_manager.add_event_callback(websocket_event_handler)
            
            # 创建 FastAPI 应用
            web_config = self.config_manager.global_config.web
            host = web_config.get('host', '0.0.0.0')
            port = web_config.get('port', 8000)
            
            logger.info(f"[WEB] 启动 Web 服务: http://{host}:{port}")
            
            # 使用 uvicorn 启动
            import uvicorn
            
            app = create_app(self.stream_manager, self.config_manager)
            
            # 配置 uvicorn - 使用更简洁的日志
            config = uvicorn.Config(
                app,
                host=host,
                port=port,
                log_level="warning",
                access_log=False
            )
            self._web_server = uvicorn.Server(config)
            
            # 在后台运行 Web 服务器（使用单独的线程避免阻塞）
            import threading
            def run_server():
                asyncio.run(self._web_server.serve())
            
            self._web_thread = threading.Thread(target=run_server, daemon=True)
            self._web_thread.start()
            
            # 等待服务器启动
            await asyncio.sleep(2)
            
            logger.info(f"[WEB] Web 服务已启动: http://{host}:{port}")
            
        except Exception as e:
            logger.error(f"[WEB] 启动 Web 服务失败: {e}")
            import traceback
            traceback.print_exc()
        
    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(sig, frame):
            logger.info(f"收到信号 {sig}，正在关闭...")
            asyncio.create_task(self.shutdown())
            
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
    async def _on_event(self, event: dict):
        """事件处理器"""
        event_type = event.get("type")
        camera_id = event.get("camera_id")
        
        if event_type == "violation":
            logger.warning(f"[EVENT] 违规事件 - 摄像头: {camera_id}")
        elif event_type == "status":
            # 状态更新，可以发送到Web前端
            pass
            
    async def run(self, duration: int = None):
        """
        运行监控系统
        
        Args:
            duration: 运行时长（秒），None表示无限运行
        """
        if not self.stream_manager:
            logger.error("系统未初始化")
            return
            
        self.running = True
        
        logger.info("\n" + "=" * 70)
        logger.info("启动监控系统")
        logger.info("=" * 70)
        logger.info(f"运行时长: {'无限' if duration is None else f'{duration}秒'}")
        logger.info(f"输出目录: {self.output_dir}")
        logger.info("=" * 70 + "\n")
        
        try:
            # 启动所有视频流
            await self.stream_manager.start_all()
            
            # 如果指定了时长，等待指定时间
            if duration:
                logger.info(f"运行 {duration} 秒...")
                await asyncio.sleep(duration)
                logger.info("运行时长结束")
            else:
                # 无限运行，等待停止信号
                logger.info("无限运行中，按 Ctrl+C 停止...")
                while self.running:
                    await asyncio.sleep(1)
                    
        except asyncio.CancelledError:
            logger.info("运行被取消")
        except Exception as e:
            logger.error(f"运行异常: {e}")
        finally:
            await self.shutdown()
            
    async def shutdown(self):
        """关闭系统"""
        if not self.running:
            return
            
        logger.info("\n" + "=" * 70)
        logger.info("关闭系统")
        logger.info("=" * 70)
        
        self.running = False
        
        # 停止所有视频流
        if self.stream_manager:
            await self.stream_manager.stop_all()
            
        # 打印统计
        self._print_summary()
        
        logger.info("=" * 70)
        logger.info("系统已关闭")
        logger.info("=" * 70)
        
    def _print_summary(self):
        """打印统计摘要"""
        if not self.stream_manager:
            return
            
        summary = self.stream_manager.get_summary()
        
        logger.info("\n监控统计:")
        logger.info("-" * 70)
        logger.info(f"摄像头总数: {summary['total_cameras']}")
        logger.info(f"活跃摄像头: {summary['active_cameras']}")
        logger.info(f"总处理帧数: {summary['total_frames']}")
        logger.info(f"总检测次数: {summary['total_detections']}")
        logger.info(f"总违规次数: {summary['total_violations']}")
        logger.info("-" * 70)
        
        for camera in summary['cameras']:
            stats = camera['stats']
            logger.info(
                f"[{camera['camera_id']}] "
                f"帧: {stats['frame_count']}, "
                f"检测: {stats['detection_count']}, "
                f"违规: {stats['violation_count']}, "
                f"重连: {stats['reconnect_count']}"
            )


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='stream_manager_v2 安全监控系统')
    parser.add_argument('--config', '-c', default=None, help='配置目录 (默认: 项目目录/config)')
    parser.add_argument('--output', '-o', default=None, help='输出目录 (默认: 项目目录/output)')
    parser.add_argument('--duration', '-d', type=int, default=None, help='运行时长（秒）')
    parser.add_argument('--camera', '-cam', default=None, help='只运行指定摄像头')
    parser.add_argument('--web', '-w', action='store_true', help='启用 Web 服务')
    parser.add_argument('--no-web', action='store_true', help='禁用 Web 服务')
    
    args = parser.parse_args()
    
    # 创建并运行监控
    monitor = SafetyMonitor(
        config_dir=args.config,
        output_dir=args.output
    )
    
    # 确定是否启用 Web 服务
    enable_web = True
    if args.no_web:
        enable_web = False
    elif args.web:
        enable_web = True
    # 否则使用配置文件中的设置
    
    # 初始化
    asyncio.run(monitor.initialize(enable_web=enable_web))
    
    # 运行
    try:
        asyncio.run(monitor.run(duration=args.duration))
    except KeyboardInterrupt:
        logger.info("用户中断")
    

if __name__ == "__main__":
    main()
