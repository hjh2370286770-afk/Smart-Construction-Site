#!/usr/bin/env python3
"""
更新后的主程序 - 整合所有检测器
"""

import asyncio
import logging
import time
from typing import Dict

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


class ConstructionSiteMonitor:
    """
    工地监控系统 - 完整版
    
    整合所有模块：
    - 多路视频流管理
    - 多场景检测（安全帽/反光衣/车辆）
    - 关键帧提取
    - 云端上传
    """
    
    def __init__(self):
        self.stream_manager = StreamManager()
        self.detector_manager = DetectorManager(models_dir="..")
        self.keyframe_extractor: KeyFrameExtractor = None
        self.cloud_uploader: CloudUploader = None
        
    async def setup(self, 
                    detector_configs: Dict = None,
                    keyframe_config: KeyFrameConfig = None,
                    upload_config: UploadConfig = None):
        """系统初始化"""
        
        # 1. 初始化检测器
        self.detector_manager.initialize(detector_configs)
        
        # 2. 配置车辆计数线（根据实际摄像头位置调整）
        # 这里使用示例坐标，实际使用时需要根据摄像头画面调整
        self.detector_manager.configure_vehicle_line(
            "main_gate", (200, 300), (600, 300), "bottom"
        )
        
        # 3. 初始化关键帧提取器
        if keyframe_config:
            self.keyframe_extractor = KeyFrameExtractor(keyframe_config)
            self.keyframe_extractor.on_capture(self._on_keyframe_captured)
            
        # 4. 初始化云端上传器
        if upload_config:
            self.cloud_uploader = CloudUploader(upload_config)
            await self.cloud_uploader.start()
            
        # 5. 注册流回调
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
        logger.info(f"Camera added: {config.stream_id} -> {config.scene_type}")
        
    async def start(self):
        """启动所有摄像头"""
        await self.stream_manager.start_all()
        
    async def stop(self):
        """停止所有摄像头"""
        await self.stream_manager.stop_all()
        
    def _on_frame_received(self, frame_data):
        """帧接收回调 - 进行检测"""
        # 使用检测器管理器进行检测
        detection_result = self.detector_manager.detect(
            frame_data.frame,
            frame_data.scene_type,
            timestamp=frame_data.timestamp
        )
        
        if detection_result.get("success"):
            # 检查是否需要提取关键帧
            if self._should_extract_keyframe(frame_data, detection_result):
                if self.keyframe_extractor:
                    # 绘制检测结果后再提取
                    annotated_frame = self.detector_manager.draw_results(
                        frame_data.frame.copy(),
                        frame_data.scene_type,
                        detection_result
                    )
                    
                    self.keyframe_extractor.extract(
                        frame=annotated_frame,
                        stream_id=frame_data.stream_id,
                        detection_result=detection_result,
                        metadata={
                            "fps_actual": frame_data.metadata.get("fps_actual"),
                            "timestamp": frame_data.timestamp,
                            "scene_type": frame_data.scene_type
                        }
                    )
                    
    def _should_extract_keyframe(self, 
                                  frame_data, 
                                  detection_result: Dict) -> bool:
        """判断是否应该提取关键帧"""
        # 场景特定的触发条件
        scene_type = frame_data.scene_type
        
        if scene_type in ["safety_helmet", "helmet"]:
            # 安全帽场景：有违规（未戴安全帽）时触发
            violation_count = detection_result.get("violation_count", 0)
            return violation_count > 0
            
        elif scene_type in ["reflective_vest", "vest"]:
            # 反光衣场景：有违规（未穿反光衣）时触发
            violation_count = detection_result.get("violation_count", 0)
            return violation_count > 0
            
        elif scene_type in ["vehicle_count", "vehicle"]:
            # 车辆场景：有进出事件时触发
            summary = detection_result.get("summary", {})
            total_in = summary.get("total_in", 0)
            total_out = summary.get("total_out", 0)
            # 这里需要更复杂的逻辑来判断是否有新事件
            # 简化处理：只要有车辆就触发
            return detection_result.get("count", 0) > 0
            
        return detection_result.get("count", 0) > 0
        
    def _on_keyframe_captured(self, keyframe_data):
        """关键帧捕获回调 - 上传到云端"""
        logger.info(f"Keyframe captured: {keyframe_data.stream_path}")
        
        # 构建上传数据
        upload_data = {
            "stream_id": keyframe_data.stream_id,
            "timestamp": keyframe_data.timestamp,
            "datetime": keyframe_data.datetime_str,
            "scene_type": keyframe_data.metadata.get("scene_type", "unknown"),
            "detection_summary": self._summarize_detection(
                keyframe_data.detection_result
            )
        }
        
        # 如果有云端上传器，进行上传
        if self.cloud_uploader:
            asyncio.create_task(self._upload_keyframe(keyframe_data, upload_data))
            
    def _summarize_detection(self, detection_result: Dict) -> Dict:
        """汇总检测结果用于上传"""
        summary = {
            "scene_type": detection_result.get("scene_type"),
            "total_count": detection_result.get("count", 0),
        }
        
        scene_type = detection_result.get("scene_type")
        
        if scene_type in ["safety_helmet", "helmet"]:
            det_summary = detection_result.get("summary", {})
            summary.update({
                "with_helmet": det_summary.get("with_helmet", 0),
                "without_helmet": det_summary.get("without_helmet", 0),
                "compliance_rate": det_summary.get("compliance_rate", 0),
                "helmet_colors": det_summary.get("helmet_colors", {})
            })
            
        elif scene_type in ["reflective_vest", "vest"]:
            det_summary = detection_result.get("summary", {})
            summary.update({
                "with_vest": det_summary.get("with_vest", 0),
                "without_vest": det_summary.get("without_vest", 0),
                "compliance_rate": det_summary.get("compliance_rate", 0),
                "vest_colors": det_summary.get("vest_colors", {})
            })
            
        elif scene_type in ["vehicle_count", "vehicle"]:
            det_summary = detection_result.get("summary", {})
            summary.update({
                "total_in": det_summary.get("total_in", 0),
                "total_out": det_summary.get("total_out", 0),
                "by_type": det_summary.get("by_type", {})
            })
            
        return summary
        
    async def _upload_keyframe(self, keyframe_data, upload_data: Dict):
        """上传关键帧到云端"""
        result = await self.cloud_uploader.upload(
            file_path=keyframe_data.frame_path,
            stream_id=keyframe_data.stream_id,
            detection_result=upload_data,
            metadata={
                "timestamp": keyframe_data.timestamp,
                "datetime": keyframe_data.datetime_str,
                "original_path": keyframe_data.frame_path,
                "annotated_path": keyframe_data.annotated_path
            }
        )
        
        if result.success:
            logger.info(f"Upload queued: {keyframe_data.stream_id}")
        else:
            logger.error(f"Upload failed: {result.error}")
            
    def _on_stream_status_changed(self, stream_id: str, status):
        """流状态变更回调"""
        logger.info(f"Stream status changed: {stream_id} -> {status.value}")
        
    def get_status(self) -> Dict:
        """获取系统状态"""
        status = {
            "streams": self.stream_manager.get_status(),
            "detectors": self.detector_manager.list_detectors(),
        }
        
        if self.keyframe_extractor:
            status["keyframe_extractor"] = self.keyframe_extractor.get_stats()
            
        return status


# ==================== 主程序 ====================

async def main():
    """主程序"""
    
    # 创建监控系统
    monitor = ConstructionSiteMonitor()
    
    # 配置检测器
    detector_configs = {
        "helmet": {
            "model": "yolov8n.pt",
            "conf_threshold": 0.5
        },
        "vest": {
            "model": "yolov8n.pt",
            "conf_threshold": 0.5
        },
        "vehicle": {
            "model": "yolov8n.pt",
            "conf_threshold": 0.5
        }
    }
    
    # 配置关键帧提取
    keyframe_config = KeyFrameConfig(
        save_dir="./keyframes_output",
        min_interval=5.0,              # 最少5秒提取一次
        trigger_classes=["person_no_helmet", "person_no_vest"],  # 违规时触发
        trigger_min_confidence=0.6,
        save_with_annotation=True,
        save_original=True
    )
    
    # 配置云端上传
    upload_config = UploadConfig(
        upload_mode="http",
        http_endpoint="http://your-api-server.com/api/keyframes",
        http_headers={
            "Authorization": "Bearer YOUR_TOKEN",
            "X-Project-ID": "construction_site_001"
        },
        concurrent_uploads=3,
        enabled=False  # 配置好服务器后改为 True
    )
    
    # 系统初始化
    await monitor.setup(detector_configs, keyframe_config, upload_config)
    
    # 添加三个摄像头（对应三个场景）
    camera_configs = [
        StreamConfig(
            stream_id="cam_helmet",
            url="rtmp://49.235.101.158/live/JHMH2411005018",
            scene_type="safety_helmet",  # 安全帽检测
            fps=10,
            buffer_size=5,
            frame_skip=2
        ),
        StreamConfig(
            stream_id="cam_vest",
            url="rtmp://49.235.101.158/live/JHMH2510001023",
            scene_type="reflective_vest",  # 反光衣检测
            fps=10,
            buffer_size=5,
            frame_skip=2
        ),
        StreamConfig(
            stream_id="cam_vehicle",
            url="rtmp://49.235.101.158/live/JHMH2410013005",
            scene_type="vehicle_count",  # 车辆进出计数
            fps=15,
            buffer_size=5,
            frame_skip=1
        )
    ]
    
    for config in camera_configs:
        monitor.add_camera(config)
    
    # 启动所有摄像头
    await monitor.start()
    
    try:
        # 运行状态监控
        while True:
            await asyncio.sleep(10)
            
            status = monitor.get_status()
            logger.info("=" * 70)
            logger.info("Construction Site Monitor - Status Report")
            logger.info("=" * 70)
            
            for stream_id, info in status["streams"].items():
                logger.info(f"[{stream_id}] {info['status']:12} | "
                           f"Frames: {info['frame_number']:6} | "
                           f"FPS: {info['fps_actual']:5.1f} | "
                           f"Scene: {info['scene_type']}")
            
            if "keyframe_extractor" in status:
                kf_stats = status["keyframe_extractor"]
                logger.info(f"KeyFrames today: {kf_stats['daily_capture_count']}/"
                           f"{kf_stats['max_daily_frames']}")
            
            logger.info(f"Active detectors: {', '.join(status['detectors'])}")
            logger.info("=" * 70)
            
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await monitor.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
