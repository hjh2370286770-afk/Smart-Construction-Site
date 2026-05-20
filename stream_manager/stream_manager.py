#!/usr/bin/env python3
"""
多路视频流管理器 - asyncio 版本
支持 RTMP/RTSP 多路并发拉流，帧队列管理，场景路由
"""

import asyncio
import cv2
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable, List, Any
from collections import deque
from enum import Enum
import numpy as np

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StreamStatus(Enum):
    """流状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    RECONNECTING = "reconnecting"


@dataclass
class StreamConfig:
    """视频流配置"""
    stream_id: str                    # 流唯一标识
    url: str                          # 流地址
    scene_type: str = "default"       # 场景类型（决定使用哪个模型）
    fps: int = 25                     # 目标帧率
    buffer_size: int = 30             # 帧缓冲区大小
    reconnect_interval: float = 5.0   # 重连间隔（秒）
    max_reconnect_attempts: int = 10  # 最大重连次数
    frame_skip: int = 0               # 跳帧数（0表示不跳帧）
    enable_save: bool = False         # 是否保存视频
    save_path: Optional[str] = None   # 保存路径


@dataclass
class FrameData:
    """帧数据封装"""
    stream_id: str
    frame: np.ndarray
    timestamp: float
    frame_number: int
    scene_type: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class VideoStream:
    """单路视频流处理器"""
    
    def __init__(self, config: StreamConfig):
        self.config = config
        self.status = StreamStatus.DISCONNECTED
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame_queue: deque = deque(maxlen=config.buffer_size)
        self.frame_number = 0
        self.reconnect_attempts = 0
        self.last_frame_time = 0
        self.fps_actual = 0
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self._frame_callbacks: List[Callable[[FrameData], None]] = []
        self._status_callbacks: List[Callable[[str, StreamStatus], None]] = []
        
    def on_frame(self, callback: Callable[[FrameData], None]):
        """注册帧回调"""
        self._frame_callbacks.append(callback)
        
    def on_status_change(self, callback: Callable[[str, StreamStatus], None]):
        """注册状态变更回调"""
        self._status_callbacks.append(callback)
        
    def _set_status(self, status: StreamStatus):
        """设置状态并触发回调"""
        old_status = self.status
        self.status = status
        if old_status != status:
            logger.info(f"Stream {self.config.stream_id}: {old_status.value} -> {status.value}")
            for cb in self._status_callbacks:
                try:
                    cb(self.config.stream_id, status)
                except Exception as e:
                    logger.error(f"Status callback error: {e}")
    
    async def start(self):
        """启动流处理"""
        self._stop_event.clear()
        self._task = asyncio.create_task(self._stream_loop())
        logger.info(f"Stream {self.config.stream_id} started")
        
    async def stop(self):
        """停止流处理"""
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._release_cap()
        self._set_status(StreamStatus.DISCONNECTED)
        logger.info(f"Stream {self.config.stream_id} stopped")
        
    def _release_cap(self):
        """释放视频捕获资源"""
        if self.cap:
            self.cap.release()
            self.cap = None
            
    async def _stream_loop(self):
        """主拉流循环"""
        while not self._stop_event.is_set():
            try:
                await self._connect_and_stream()
            except Exception as e:
                logger.error(f"Stream {self.config.stream_id} error: {e}")
                self._set_status(StreamStatus.ERROR)
                
            # 重连逻辑
            if not self._stop_event.is_set():
                self.reconnect_attempts += 1
                if self.reconnect_attempts > self.config.max_reconnect_attempts:
                    logger.error(f"Stream {self.config.stream_id} max reconnect attempts reached")
                    break
                    
                self._set_status(StreamStatus.RECONNECTING)
                logger.info(f"Stream {self.config.stream_id} reconnecting in {self.config.reconnect_interval}s "
                          f"(attempt {self.reconnect_attempts}/{self.config.max_reconnect_attempts})")
                await asyncio.sleep(self.config.reconnect_interval)
                
    async def _connect_and_stream(self):
        """连接并读取流"""
        self._set_status(StreamStatus.CONNECTING)
        self._release_cap()
        
        # 使用 OpenCV 打开 RTMP 流
        # 设置缓冲区大小为1，降低延迟
        self.cap = cv2.VideoCapture(self.config.url)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        # 设置超时（某些后端支持）
        self.cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000)
        self.cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)
        
        if not self.cap.isOpened():
            raise ConnectionError(f"Failed to open stream: {self.config.url}")
            
        self._set_status(StreamStatus.CONNECTED)
        self.reconnect_attempts = 0
        
        # 获取流信息
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        logger.info(f"Stream {self.config.stream_id} connected: {width}x{height} @ {fps}fps")
        
        frame_interval = 1.0 / self.config.fps if self.config.fps > 0 else 0.04
        frame_skip_counter = 0
        
        while not self._stop_event.is_set():
            loop_start = time.time()
            
            # 异步读取帧
            ret, frame = await asyncio.get_event_loop().run_in_executor(
                None, self._read_frame
            )
            
            if not ret or frame is None:
                logger.warning(f"Stream {self.config.stream_id} frame read failed")
                break
                
            self.frame_number += 1
            current_time = time.time()
            
            # 计算实际 FPS
            if self.last_frame_time > 0:
                self.fps_actual = 1.0 / (current_time - self.last_frame_time)
            self.last_frame_time = current_time
            
            # 跳帧处理
            if self.config.frame_skip > 0:
                frame_skip_counter += 1
                if frame_skip_counter <= self.config.frame_skip:
                    continue
                frame_skip_counter = 0
            
            # 创建帧数据对象
            frame_data = FrameData(
                stream_id=self.config.stream_id,
                frame=frame,
                timestamp=current_time,
                frame_number=self.frame_number,
                scene_type=self.config.scene_type,
                metadata={
                    "fps_actual": self.fps_actual,
                    "resolution": f"{width}x{height}"
                }
            )
            
            # 加入队列
            self.frame_queue.append(frame_data)
            
            # 触发回调
            for cb in self._frame_callbacks:
                try:
                    cb(frame_data)
                except Exception as e:
                    logger.error(f"Frame callback error: {e}")
                    
            # 帧率控制
            elapsed = time.time() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
                
    def _read_frame(self):
        """同步读取帧（在线程池中执行）"""
        if self.cap and self.cap.isOpened():
            return self.cap.read()
        return False, None
        
    def get_latest_frame(self) -> Optional[FrameData]:
        """获取最新帧"""
        if self.frame_queue:
            return self.frame_queue[-1]
        return None
        
    def get_frame_batch(self, count: int) -> List[FrameData]:
        """获取批量帧"""
        frames = []
        for _ in range(min(count, len(self.frame_queue))):
            frames.append(self.frame_queue.popleft())
        return frames


class StreamManager:
    """多路视频流管理器"""
    
    def __init__(self):
        self.streams: Dict[str, VideoStream] = {}
        self._global_frame_callbacks: List[Callable[[FrameData], None]] = []
        self._global_status_callbacks: List[Callable[[str, StreamStatus], None]] = []
        self._running = False
        
    def on_frame(self, callback: Callable[[FrameData], None]):
        """注册全局帧回调"""
        self._global_frame_callbacks.append(callback)
        
    def on_status_change(self, callback: Callable[[str, StreamStatus], None]):
        """注册全局状态回调"""
        self._global_status_callbacks.append(callback)
        
    def add_stream(self, config: StreamConfig) -> VideoStream:
        """添加视频流"""
        if config.stream_id in self.streams:
            logger.warning(f"Stream {config.stream_id} already exists, removing old one")
            asyncio.create_task(self.remove_stream(config.stream_id))
            
        stream = VideoStream(config)
        
        # 注册全局回调
        for cb in self._global_frame_callbacks:
            stream.on_frame(cb)
        for cb in self._global_status_callbacks:
            stream.on_status_change(cb)
            
        self.streams[config.stream_id] = stream
        logger.info(f"Stream {config.stream_id} added")
        return stream
        
    async def remove_stream(self, stream_id: str):
        """移除视频流"""
        if stream_id in self.streams:
            stream = self.streams.pop(stream_id)
            await stream.stop()
            logger.info(f"Stream {stream_id} removed")
            
    async def start_stream(self, stream_id: str):
        """启动指定流"""
        if stream_id in self.streams:
            await self.streams[stream_id].start()
            
    async def stop_stream(self, stream_id: str):
        """停止指定流"""
        if stream_id in self.streams:
            await self.streams[stream_id].stop()
            
    async def start_all(self):
        """启动所有流"""
        self._running = True
        tasks = [stream.start() for stream in self.streams.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("All streams started")
        
    async def stop_all(self):
        """停止所有流"""
        self._running = False
        tasks = [stream.stop() for stream in self.streams.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("All streams stopped")
        
    def get_stream(self, stream_id: str) -> Optional[VideoStream]:
        """获取指定流"""
        return self.streams.get(stream_id)
        
    def get_all_streams(self) -> Dict[str, VideoStream]:
        """获取所有流"""
        return self.streams.copy()
        
    def get_status(self) -> Dict[str, Dict]:
        """获取所有流状态"""
        return {
            stream_id: {
                "status": stream.status.value,
                "frame_number": stream.frame_number,
                "fps_actual": stream.fps_actual,
                "queue_size": len(stream.frame_queue),
                "url": stream.config.url,
                "scene_type": stream.config.scene_type
            }
            for stream_id, stream in self.streams.items()
        }


# ==================== 使用示例 ====================

async def main():
    """主函数 - 演示用法"""
    
    # 创建管理器
    manager = StreamManager()
    
    # 定义帧处理回调
    def on_frame_received(frame_data: FrameData):
        """处理收到的帧"""
        # 这里可以进行：
        # 1. 模型推理
        # 2. 关键帧提取
        # 3. 上传到云端
        # 4. 本地显示等
        
        if frame_data.frame_number % 100 == 0:  # 每100帧打印一次
            logger.info(f"[{frame_data.stream_id}] Frame #{frame_data.frame_number}, "
                       f"FPS: {frame_data.metadata.get('fps_actual', 0):.1f}, "
                       f"Scene: {frame_data.scene_type}")
    
    def on_status_changed(stream_id: str, status: StreamStatus):
        """处理状态变更"""
        logger.info(f"Stream {stream_id} status changed to: {status.value}")
    
    # 注册全局回调
    manager.on_frame(on_frame_received)
    manager.on_status_change(on_status_changed)
    
    # 配置三个视频流
    stream_configs = [
        StreamConfig(
            stream_id="cam_001",
            url="rtmp://49.235.101.158/live/JHMH2411005018",
            scene_type="safety_helmet",  # 安全帽检测场景
            fps=15,
            buffer_size=10,
            frame_skip=1  # 隔帧处理，降低负载
        ),
        StreamConfig(
            stream_id="cam_002",
            url="rtmp://49.235.101.158/live/JHMH2510001023",
            scene_type="person_count",   # 人员计数场景
            fps=15,
            buffer_size=10,
            frame_skip=1
        ),
        StreamConfig(
            stream_id="cam_003",
            url="rtmp://49.235.101.158/live/JHMH2410013005",
            scene_type="danger_zone",    # 危险区域检测场景
            fps=15,
            buffer_size=10,
            frame_skip=1
        )
    ]
    
    # 添加所有流到管理器
    for config in stream_configs:
        manager.add_stream(config)
    
    # 启动所有流
    await manager.start_all()
    
    try:
        # 运行状态监控循环
        while True:
            await asyncio.sleep(5)
            
            # 打印所有流状态
            status = manager.get_status()
            logger.info("=" * 60)
            logger.info("Stream Status Report:")
            for stream_id, info in status.items():
                logger.info(f"  {stream_id}: {info['status']} | "
                           f"Frames: {info['frame_number']} | "
                           f"FPS: {info['fps_actual']:.1f} | "
                           f"Queue: {info['queue_size']} | "
                           f"Scene: {info['scene_type']}")
            logger.info("=" * 60)
            
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await manager.stop_all()


if __name__ == "__main__":
    asyncio.run(main())
