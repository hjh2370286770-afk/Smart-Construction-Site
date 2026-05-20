#!/usr/bin/env python3
"""
完整系统整合 - 多路视频流 + 场景路由 + PPE检测 + 关键帧提取 + 云端上传

更新说明:
- 新增 PPE 综合检测（安全帽+反光衣+口罩）
- 使用专用 YOLOv8 模型，检测精度更高
- 支持人员跟踪和合规性判断
"""

import asyncio
import logging
from typing import Dict
from pathlib import Path

# 添加项目根目录到路径
import sys
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "detectors"))

from stream_manager import StreamManager, StreamConfig
from scene_router import SceneRouter
from keyframe_extractor import KeyFrameExtractor, KeyFrameConfig
from cloud_uploader import CloudUploader, UploadConfig

# 使用 DetectorManager 进行高级检测
from detectors.detector_manager import DetectorManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ConstructionSiteMonitor:
    """
    工地监控系统（集成PPE检测）
    
    整合所有模块的完整系统，支持：
    - 多路视频流管理
    - PPE综合检测（安全帽+反光衣+口罩）
    - 场景路由
    - 关键帧提取
    - 云端上传
    """
    
    def __init__(self):
        # 初始化各个模块
        self.stream_manager = StreamManager()
        self.scene_router = SceneRouter(models_dir="..")
        self.detector_manager: DetectorManager = None  # 高级检测管理器
        self.keyframe_extractor: KeyFrameExtractor = None
        self.cloud_uploader: CloudUploader = None
        
        # PPE违规记录
        self.ppe_violations = []
        
    async def setup(self, 
                    use_detector_manager: bool = True,
                    keyframe_config: KeyFrameConfig = None,
                    upload_config: UploadConfig = None,
                    detector_configs: Dict = None):
        """
        系统初始化
        
        Args:
            use_detector_manager: 是否使用 DetectorManager（推荐）
            keyframe_config: 关键帧提取配置
            upload_config: 云端上传配置
            detector_configs: 检测器配置
        """
        
        # 初始化高级检测管理器（推荐）
        if use_detector_manager:
            self.detector_manager = DetectorManager(models_dir="..")
            detector_configs = detector_configs or {
                "helmet": {"conf_threshold": 0.5},
                "vest": {"conf_threshold": 0.5},
                "ppe": {"conf_threshold": 0.4},  # PPE专用模型
                "vehicle": {"conf_threshold": 0.5}
            }
            self.detector_manager.initialize(detector_configs)
            logger.info("DetectorManager initialized with PPE detection")
        
        # 初始化关键帧提取器
        if keyframe_config:
            self.keyframe_extractor = KeyFrameExtractor(keyframe_config)
            self.keyframe_extractor.on_capture(self._on_keyframe_captured)
            
        # 初始化云端上传器
        if upload_config:
            self.cloud_uploader = CloudUploader(upload_config)
            await self.cloud_uploader.start()
            
        # 注册全局帧回调
        self.stream_manager.on_frame(self._on_frame_received)
        self.stream_manager.on_status_change(self._on_stream_status_changed)
        
        logger.info("ConstructionSiteMonitor setup complete")
        
    async def shutdown(self):
        """系统关闭"""
        await self.stream_manager.stop_all()
        if self.cloud_uploader:
            await self.cloud_uploader.stop()
        logger.info("ConstructionSiteMonitor shutdown complete")
        
    def add_camera(self, config: StreamConfig):
        """添加摄像头"""
        self.stream_manager.add_stream(config)
        
        # 如果使用 DetectorManager，注册流到场景的映射
        if self.detector_manager:
            self.detector_manager.register_stream_scene(
                config.stream_id, 
                config.scene_type
            )
        
        logger.info(f"Camera added: {config.stream_id} -> {config.scene_type}")
        
    async def start(self):
        """启动所有摄像头"""
        await self.stream_manager.start_all()
        
    async def stop(self):
        """停止所有摄像头"""
        await self.stream_manager.stop_all()
        
    def _on_frame_received(self, frame_data):
        """帧接收回调 - 进行目标检测"""
        
        # 使用 DetectorManager 进行检测（推荐）
        if self.detector_manager:
            detection_result = self.detector_manager.detect(
                frame_data.frame,
                frame_data.scene_type,
                timestamp=frame_data.timestamp
            )
            
            # 特别处理 PPE 违规
            if frame_data.scene_type in ["ppe", "ppe_detection", "construction_safety"]:
                self._handle_ppe_violations(
                    frame_data.stream_id,
                    detection_result,
                    frame_data.timestamp
                )
        else:
            # 使用场景路由进行检测
            detection_result = self.scene_router.detect(
                frame_data.frame,
                frame_data.scene_type
            )
        
        if detection_result.get("success"):
            # 如果有关键帧提取器，尝试提取
            if self.keyframe_extractor:
                self.keyframe_extractor.extract(
                    frame=frame_data.frame,
                    stream_id=frame_data.stream_id,
                    detection_result=detection_result,
                    metadata={
                        "fps_actual": frame_data.metadata.get("fps_actual"),
                        "timestamp": frame_data.timestamp,
                        "scene_type": frame_data.scene_type
                    }
                )
                
    def _handle_ppe_violations(self, stream_id: str, result: Dict, timestamp: float):
        """处理 PPE 违规"""
        if not result.get("success"):
            return
            
        violation_count = result.get("violation_count", 0)
        if violation_count > 0:
            # 记录违规
            self.ppe_violations.append({
                "stream_id": stream_id,
                "timestamp": timestamp,
                "violation_count": violation_count,
                "compliance_rate": result.get("compliance_rate", 0),
                "detections": result.get("detections", [])
            })
            
            # 只保留最近100条记录
            if len(self.ppe_violations) > 100:
                self.ppe_violations = self.ppe_violations[-100:]
                
    def _on_keyframe_captured(self, keyframe_data):
        """关键帧捕获回调 - 上传到云端"""
        logger.info(f"Keyframe captured: {keyframe_data.frame_path}")
        
        # 如果有云端上传器，进行上传
        if self.cloud_uploader:
            asyncio.create_task(self._upload_keyframe(keyframe_data))
            
    async def _upload_keyframe(self, keyframe_data):
        """上传关键帧到云端"""
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
        logger.info(f"Stream status changed: {stream_id} -> {status.value}
        
    def get_status(self) -> Dict:
        """获取系统状态"""
        status = {
            "streams": self.stream_manager.get_status(),
        }
        
        if self.keyframe_extractor:
            status["keyframe_extractor"] = self.keyframe_extractor.get_stats()
            
        # PPE 违规统计
        if self.ppe_violations:
            recent_violations = [v for v in self.ppe_violations 
                               if v["timestamp"] > time.time() - 300]  # 最近5分钟
            status["ppe_violations_5min"] = len(recent_violations)
            
        return status


# ==================== 主程序 ====================

async def main():
    """主程序"""
    import time
    
    # 创建监控系统
    monitor = ConstructionSiteMonitor()
    
    # 配置关键帧提取
    keyframe_config = KeyFrameConfig(
        save_dir="./keyframes_output",
        min_interval=3.0,              # 最少3秒提取一次
        trigger_classes=["person"],    # 检测到人就触发
        trigger_min_confidence=0.6,
        save_with_annotation=True,     # 保存带标注的图片
        save_original=True             # 同时保存原图
    )
    
    # 配置云端上传（HTTP 模式示例）
    upload_config = UploadConfig(
        upload_mode="http",
        http_endpoint="http://your-api-server.com/api/keyframes",
        http_headers={
            "Authorization": "Bearer YOUR_TOKEN",
            "X-Project-ID": "construction_site_001"
        },
        concurrent_uploads=3,
        enabled=False  # 默认关闭，配置好服务器后改为 True
    )
    
    # 配置检测器
    detector_configs = {
        "helmet": {"conf_threshold": 0.5},
        "vest": {"conf_threshold": 0.5},
        "ppe": {
            "conf_threshold": 0.4,  # PPE专用模型阈值
            # "device": "cuda"  # 如果有GPU，启用CUDA加速
        },
        "vehicle": {"conf_threshold": 0.5}
    }
    
    # 系统初始化
    await monitor.setup(
        use_detector_manager=True,  # 使用 DetectorManager
        keyframe_config=keyframe_config,
        upload_config=upload_config,
        detector_configs=detector_configs
    )
    
    # 添加摄像头 - 使用 PPE 检测场景
    camera_configs = [
        StreamConfig(
            stream_id="cam_001_entrance",
            url="rtmp://49.235.101.158/live/JHMH2411005018",
            scene_type="ppe_detection",  # ⭐ 使用PPE综合检测
            fps=10,
            buffer_size=5,
            frame_skip=2
        ),
        StreamConfig(
            stream_id="cam_002_workarea",
            url="rtmp://49.235.101.158/live/JHMH2510001023",
            scene_type="construction_safety",  # ⭐ 工地安全检测
            fps=10,
            buffer_size=5,
            frame_skip=2
        ),
        StreamConfig(
            stream_id="cam_003_gate",
            url="rtmp://49.235.101.158/live/JHMH2410013005",
            scene_type="vehicle_count",  # 车辆计数
            fps=15,
            buffer_size=5,
            frame_skip=1
        )
    ]
    
    for config in camera_configs:
        monitor.add_camera(config)
    
    # 配置车辆计数线（用于 cam_003_gate）
    if monitor.detector_manager:
        monitor.detector_manager.configure_vehicle_line(
            "main_gate", (100, 300), (540, 300), "bottom"
        )
    
    # 启动所有摄像头
    await monitor.start()
    
    try:
        # 运行状态监控
        while True:
            await asyncio.sleep(10)
            
            status = monitor.get_status()
            logger.info("=" * 70)
            logger.info("System Status Report:")
            
            for stream_id, info in status["streams"].items():
                logger.info(f"  [{stream_id}] {info['status']:12} | "
                           f"Frames: {info['frame_number']:6} | "
                           f"FPS: {info['fps_actual']:5.1f} | "
                           f"Scene: {info['scene_type']}")
            
            if "keyframe_extractor" in status:
                kf_stats = status["keyframe_extractor"]
                logger.info(f"  KeyFrames today: {kf_stats['daily_capture_count']}/"
                           f"{kf_stats['max_daily_frames']}")
            
            if "ppe_violations_5min" in status:
                logger.info(f"  PPE Violations (5min): {status['ppe_violations_5min']}")
            
            logger.info("=" * 70)
            
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await monitor.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
