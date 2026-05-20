"""
多路视频流管理器
管理多个视频流处理器的生命周期
"""

import asyncio
import logging
from typing import Dict, List, Optional, Callable, Any
from pathlib import Path

from utils.config_loader import ConfigManager, CameraConfig, SiteConfig
from detectors import DetectorEngine
from .stream_processor import VideoStreamProcessor, StreamConfig

logger = logging.getLogger(__name__)


class MultiStreamManager:
    """
    多路视频流管理器
    
    功能：
    1. 管理多个视频流处理器
    2. 根据配置自动创建处理器
    3. 统一事件处理
    4. 全局状态监控
    """
    
    def __init__(self, config_manager: ConfigManager, detector_engine: DetectorEngine,
                 output_base_dir: str = "./output"):
        """
        初始化多路视频流管理器
        
        Args:
            config_manager: 配置管理器
            detector_engine: 检测引擎
            output_base_dir: 输出基础目录
        """
        self.config_manager = config_manager
        self.detector_engine = detector_engine
        self.output_base_dir = Path(output_base_dir)
        
        # 处理器字典
        self.processors: Dict[str, VideoStreamProcessor] = {}
        
        # 事件回调
        self.event_callbacks: List[Callable] = []
        
        # 运行状态
        self.running = False
        
    def add_event_callback(self, callback: Callable):
        """添加事件回调"""
        self.event_callbacks.append(callback)
        
    async def _event_handler(self, event: Dict[str, Any]):
        """事件处理器"""
        # 分发到所有回调
        for callback in self.event_callbacks:
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"事件回调异常: {e}")
                
    def initialize_from_config(self):
        """从配置初始化所有处理器"""
        enabled_cameras = self.config_manager.get_enabled_cameras()
        
        logger.info(f"从配置初始化 {len(enabled_cameras)} 个摄像头")
        
        for site, camera in enabled_cameras:
            self._create_processor(site, camera)
            
    def _create_processor(self, site: SiteConfig, camera: CameraConfig):
        """创建单个处理器"""
        camera_id = camera.id
        
        if camera_id in self.processors:
            logger.warning(f"摄像头 {camera_id} 已存在，跳过")
            return
            
        # 获取主模型（第一个）
        if not camera.models:
            logger.warning(f"摄像头 {camera_id} 未配置模型，跳过")
            return
            
        model_id = camera.models[0]
        detector = self.detector_engine.load_model(model_id)
        
        if detector is None:
            logger.error(f"无法加载模型 {model_id}，跳过摄像头 {camera_id}")
            return
            
        # 创建流配置
        stream_config = StreamConfig(
            camera_id=camera_id,
            name=camera.name,
            url=camera.url,
            stream_type=camera.type,
            enabled=camera.enabled,
            frame_skip=3  # 从全局配置读取
        )
        
        # 创建输出目录
        output_dir = self.output_base_dir / site.id / camera_id
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建处理器
        processor = VideoStreamProcessor(
            config=stream_config,
            detector=detector,
            output_dir=output_dir,
            event_callback=self._event_handler
        )
        
        self.processors[camera_id] = processor
        logger.info(f"创建处理器: {camera_id} ({camera.name})")
        
    async def start_all(self):
        """启动所有处理器"""
        logger.info("启动所有视频流处理器")
        self.running = True
        
        tasks = []
        for camera_id, processor in self.processors.items():
            if processor.config.enabled:
                task = asyncio.create_task(
                    processor.start(),
                    name=f"processor_{camera_id}"
                )
                tasks.append(task)
                
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
    async def stop_all(self):
        """停止所有处理器"""
        logger.info("停止所有视频流处理器")
        self.running = False
        
        for camera_id, processor in self.processors.items():
            await processor.stop()
            
    async def start_camera(self, camera_id: str):
        """启动指定摄像头"""
        if camera_id not in self.processors:
            logger.error(f"摄像头 {camera_id} 不存在")
            return False
            
        processor = self.processors[camera_id]
        await processor.start()
        return True
        
    async def stop_camera(self, camera_id: str):
        """停止指定摄像头"""
        if camera_id not in self.processors:
            logger.error(f"摄像头 {camera_id} 不存在")
            return False
            
        processor = self.processors[camera_id]
        await processor.stop()
        return True
        
    def pause_camera(self, camera_id: str):
        """暂停指定摄像头"""
        if camera_id in self.processors:
            self.processors[camera_id].pause()
            
    def resume_camera(self, camera_id: str):
        """恢复指定摄像头"""
        if camera_id in self.processors:
            self.processors[camera_id].resume()
            
    def get_camera_status(self, camera_id: str) -> Optional[Dict]:
        """获取摄像头状态"""
        if camera_id not in self.processors:
            return None
        return self.processors[camera_id].get_status()
        
    def get_all_status(self) -> List[Dict]:
        """获取所有摄像头状态"""
        return [p.get_status() for p in self.processors.values()]
        
    def get_summary(self) -> Dict[str, Any]:
        """获取汇总信息"""
        total_frames = sum(p.stats.frame_count for p in self.processors.values())
        total_violations = sum(p.stats.violation_count for p in self.processors.values())
        total_detections = sum(p.stats.detection_count for p in self.processors.values())
        
        active_count = sum(
            1 for p in self.processors.values()
            if p.status.value == "running"
        )
        
        return {
            "total_cameras": len(self.processors),
            "active_cameras": active_count,
            "total_frames": total_frames,
            "total_detections": total_detections,
            "total_violations": total_violations,
            "cameras": self.get_all_status()
        }
