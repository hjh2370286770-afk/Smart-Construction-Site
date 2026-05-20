#!/usr/bin/env python3
"""
动态场景配置系统 - 支持多路视频流，每路可配置不同检测场景
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional
from dataclasses import dataclass

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "detectors"))

from stream_manager import StreamManager, StreamConfig
from keyframe_extractor import KeyFrameExtractor, KeyFrameConfig
from cloud_uploader import CloudUploader, UploadConfig
from detector_manager import DetectorManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class CameraConfig:
    """摄像头配置"""
    stream_id: str
    url: str
    scene_type: str           # 检测场景类型
    name: str = ""            # 摄像头名称（可选）
    location: str = ""        # 位置描述（可选）
    fps: int = 10
    frame_skip: int = 2
    enabled: bool = True


class DynamicSceneMonitor:
    """
    动态场景监控系统
    
    支持：
    - 多路视频流动态管理
    - 每路视频流独立配置检测场景
    - 运行时添加/删除/修改摄像头
    - 场景切换
    """
    
    # 支持的检测场景
    SUPPORTED_SCENES = {
        "safety_helmet": "安全帽检测",
        "reflective_vest": "反光衣检测",
        "safety_equipment": "安全帽+反光衣综合检测",
        "vehicle_count": "车辆进出计数",
        "person_count": "人员计数",
        "danger_zone": "危险区域入侵",
        "fire_smoke": "烟火检测",
    }
    
    def __init__(self):
        self.stream_manager = StreamManager()
        self.detector_manager = DetectorManager(models_dir="..")
        self.keyframe_extractor: Optional[KeyFrameExtractor] = None
        self.cloud_uploader: Optional[CloudUploader] = None
        
        # 摄像头配置存储
        self.camera_configs: Dict[str, CameraConfig] = {}
        
    async def setup(self,
                    detector_configs: Dict = None,
                    keyframe_config: KeyFrameConfig = None,
                    upload_config: UploadConfig = None):
        """系统初始化"""
        
        # 初始化检测器
        self.detector_manager.initialize(detector_configs)
        
        # 初始化关键帧提取器
        if keyframe_config:
            self.keyframe_extractor = KeyFrameExtractor(keyframe_config)
            self.keyframe_extractor.on_capture(self._on_keyframe_captured)
            
        # 初始化云端上传器
        if upload_config:
            self.cloud_uploader = CloudUploader(upload_config)
            await self.cloud_uploader.start()
        
        # 注册流回调
        self.stream_manager.on_frame(self._on_frame_received)
        self.stream_manager.on_status_change(self._on_stream_status_changed)
        
        logger.info("DynamicSceneMonitor setup complete")
        
    async def shutdown(self):
        """系统关闭"""
        await self.stream_manager.stop_all()
        if self.cloud_uploader:
            await self.cloud_uploader.stop()
        logger.info("DynamicSceneMonitor shutdown complete")
        
    def add_camera(self, config: CameraConfig) -> bool:
        """
        添加摄像头
        
        Args:
            config: 摄像头配置
            
        Returns:
            是否成功添加
        """
        if config.scene_type not in self.SUPPORTED_SCENES:
            logger.error(f"Unsupported scene type: {config.scene_type}")
            logger.info(f"Supported scenes: {list(self.SUPPORTED_SCENES.keys())}")
            return False
            
        # 保存配置
        self.camera_configs[config.stream_id] = config
        
        # 注册到检测器管理器
        self.detector_manager.register_stream_scene(config.stream_id, config.scene_type)
        
        # 创建流配置
        stream_config = StreamConfig(
            stream_id=config.stream_id,
            url=config.url,
            scene_type=config.scene_type,
            fps=config.fps,
            buffer_size=10,
            frame_skip=config.frame_skip
        )
        
        # 添加到流管理器
        self.stream_manager.add_stream(stream_config)
        
        logger.info(f"Camera added: {config.stream_id} -> {config.scene_type} ({self.SUPPORTED_SCENES[config.scene_type]})")
        return True
        
    async def remove_camera(self, stream_id: str):
        """移除摄像头"""
        if stream_id in self.camera_configs:
            del self.camera_configs[stream_id]
            await self.stream_manager.remove_stream(stream_id)
            logger.info(f"Camera removed: {stream_id}")
            
    async def update_camera_scene(self, stream_id: str, new_scene_type: str):
        """
        更新摄像头的检测场景
        
        不需要重启流，动态切换检测模型
        """
        if stream_id not in self.camera_configs:
            logger.error(f"Camera not found: {stream_id}")
            return False
            
        if new_scene_type not in self.SUPPORTED_SCENES:
            logger.error(f"Unsupported scene type: {new_scene_type}")
            return False
            
        # 更新配置
        self.camera_configs[stream_id].scene_type = new_scene_type
        self.detector_manager.register_stream_scene(stream_id, new_scene_type)
        
        # 更新流配置
        stream = self.stream_manager.get_stream(stream_id)
        if stream:
            stream.config.scene_type = new_scene_type
            
        logger.info(f"Camera {stream_id} scene updated: {new_scene_type}")
        return True
        
    async def start_camera(self, stream_id: str):
        """启动指定摄像头"""
        await self.stream_manager.start_stream(stream_id)
        
    async def stop_camera(self, stream_id: str):
        """停止指定摄像头"""
        await self.stream_manager.stop_stream(stream_id)
        
    async def start_all(self):
        """启动所有摄像头"""
        await self.stream_manager.start_all()
        
    async def stop_all(self):
        """停止所有摄像头"""
        await self.stream_manager.stop_all()
        
    def list_cameras(self) -> List[Dict]:
        """列出所有摄像头"""
        return [
            {
                "stream_id": cfg.stream_id,
                "name": cfg.name,
                "url": cfg.url,
                "scene_type": cfg.scene_type,
                "scene_name": self.SUPPORTED_SCENES.get(cfg.scene_type, "Unknown"),
                "location": cfg.location,
                "enabled": cfg.enabled
            }
            for cfg in self.camera_configs.values()
        ]
        
    def _on_frame_received(self, frame_data):
        """帧接收回调"""
        stream_id = frame_data.stream_id
        
        # 获取该流的场景类型
        scene_type = self.detector_manager.get_stream_scene(stream_id)
        if not scene_type:
            scene_type = frame_data.scene_type
            
        # 执行检测
        detection_result = self.detector_manager.detect(
            frame_data.frame,
            scene_type,
            timestamp=frame_data.timestamp
        )
        
        if detection_result.get("success"):
            # 检查是否提取关键帧
            if self._should_extract_keyframe(detection_result):
                if self.keyframe_extractor:
                    # 绘制检测结果
                    annotated_frame = self.detector_manager.draw_results(
                        frame_data.frame.copy(),
                        scene_type,
                        detection_result
                    )
                    
                    self.keyframe_extractor.extract(
                        frame=annotated_frame,
                        stream_id=stream_id,
                        detection_result=detection_result,
                        metadata={
                            "fps_actual": frame_data.metadata.get("fps_actual"),
                            "timestamp": frame_data.timestamp,
                            "scene_type": scene_type
                        }
                    )
                    
    def _should_extract_keyframe(self, detection_result: Dict) -> bool:
        """判断是否应该提取关键帧"""
        scene_type = detection_result.get("scene_type")
        
        # 安全相关场景：有违规时触发
        if scene_type in ["safety_helmet", "reflective_vest", "safety_equipment"]:
            violation_count = detection_result.get("violation_count", 0)
            return violation_count > 0
            
        # 车辆场景：有车辆时触发
        elif scene_type == "vehicle_count":
            return detection_result.get("count", 0) > 0
            
        # 其他场景：有目标时触发
        return detection_result.get("count", 0) > 0
        
    def _on_keyframe_captured(self, keyframe_data):
        """关键帧捕获回调"""
        logger.info(f"Keyframe captured: {keyframe_data.frame_path}")
        
        if self.cloud_uploader:
            asyncio.create_task(self._upload_keyframe(keyframe_data))
            
    async def _upload_keyframe(self, keyframe_data):
        """上传关键帧"""
        result = await self.cloud_uploader.upload(
            file_path=keyframe_data.frame_path,
            stream_id=keyframe_data.stream_id,
            detection_result=keyframe_data.detection_result,
            metadata={
                "timestamp": keyframe_data.timestamp,
                "datetime": keyframe_data.datetime_str
            }
        )
        
        if result.success:
            logger.info(f"Upload queued: {keyframe_data.stream_id}")
        else:
            logger.error(f"Upload failed: {result.error}")
            
    def _on_stream_status_changed(self, stream_id: str, status):
        """流状态变更回调"""
        logger.info(f"Stream {stream_id} status: {status.value}")
        
    def get_status(self) -> Dict:
        """获取系统状态"""
        return {
            "cameras": self.list_cameras(),
            "streams": self.stream_manager.get_status(),
            "detectors": self.detector_manager.list_detectors(),
            "keyframe_stats": self.keyframe_extractor.get_stats() if self.keyframe_extractor else None
        }


# ==================== 配置示例 ====================

# 示例摄像头配置（可以根据需要添加更多）
EXAMPLE_CAMERAS = [
    CameraConfig(
        stream_id="gate_001",
        url="rtmp://49.235.101.158/live/JHMH2411005018",
        scene_type="safety_equipment",  # 综合安全检测
        name="大门入口",
        location="工地主入口",
        fps=10,
        frame_skip=2
    ),
    CameraConfig(
        stream_id="gate_002",
        url="rtmp://49.235.101.158/live/JHMH2510001023",
        scene_type="vehicle_count",  # 车辆计数
        name="车辆通道",
        location="工地车辆出入口",
        fps=15,
        frame_skip=1
    ),
    CameraConfig(
        stream_id="work_area_001",
        url="rtmp://49.235.101.158/live/JHMH2410013005",
        scene_type="safety_equipment",  # 综合安全检测
        name="施工区域A",
        location="一号施工区",
        fps=10,
        frame_skip=2
    ),
    # 可以动态添加更多...
]


# ==================== 主程序 ====================

async def main():
    """主程序"""
    
    monitor = DynamicSceneMonitor()
    
    # 配置检测器
    detector_configs = {
        "helmet": {"conf_threshold": 0.5},
        "vest": {"conf_threshold": 0.5},
        "safety_equipment": {
            "model": "yolov8n.pt",
            "conf_threshold": 0.5,
            "use_custom_model": False  # 使用颜色分析
        },
        "vehicle": {"conf_threshold": 0.5}
    }
    
    # 配置关键帧提取
    keyframe_config = KeyFrameConfig(
        save_dir="./keyframes_output",
        min_interval=5.0,
        trigger_classes=["person_no_helmet", "person_no_vest", "no_helmet_no_vest"],
        trigger_min_confidence=0.6,
        save_with_annotation=True,
        save_original=True
    )
    
    # 配置云端上传
    upload_config = UploadConfig(
        upload_mode="http",
        http_endpoint="http://your-api-server.com/api/keyframes",
        enabled=False  # 配置好后设为 True
    )
    
    # 初始化
    await monitor.setup(detector_configs, keyframe_config, upload_config)
    
    # 添加示例摄像头
    for cam_config in EXAMPLE_CAMERAS:
        monitor.add_camera(cam_config)
    
    # 启动所有
    await monitor.start_all()
    
    logger.info("\n" + "="*60)
    logger.info("Dynamic Scene Monitor Started")
    logger.info(f"Cameras: {len(monitor.list_cameras())}")
    logger.info("Supported scenes:")
    for scene, name in monitor.SUPPORTED_SCENES.items():
        logger.info(f"  - {scene}: {name}")
    logger.info("="*60 + "\n")
    
    try:
        while True:
            await asyncio.sleep(10)
            
            status = monitor.get_status()
            logger.info("\n" + "="*60)
            logger.info("System Status:")
            
            for cam in status["cameras"]:
                stream_status = status["streams"].get(cam["stream_id"], {})
                logger.info(f"  [{cam['stream_id']}] {cam['scene_name']:15} | "
                           f"{stream_status.get('status', 'unknown'):10} | "
                           f"Frames: {stream_status.get('frame_number', 0)}")
            
            if status["keyframe_stats"]:
                kf = status["keyframe_stats"]
                logger.info(f"  KeyFrames today: {kf['daily_capture_count']}/{kf['max_daily_frames']}")
                
            logger.info("="*60)
            
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await monitor.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
