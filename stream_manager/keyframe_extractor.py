#!/usr/bin/env python3
"""
关键帧提取器 - 根据检测结果智能提取关键帧
"""

import cv2
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
import json
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class KeyFrameConfig:
    """关键帧提取配置"""
    save_dir: str = "./keyframes"           # 保存目录
    min_interval: float = 2.0               # 最小提取间隔（秒）
    max_daily_frames: int = 1000            # 每日最大提取数量
    quality: int = 85                       # JPEG质量
    save_format: str = "jpg"                # 保存格式
    save_with_annotation: bool = True       # 是否保存带标注的图片
    save_original: bool = True              # 是否保存原图
    upload_enabled: bool = False            # 是否自动上传
    
    # 触发条件
    trigger_classes: List[str] = field(default_factory=list)  # 触发提取的类别
    trigger_min_confidence: float = 0.6     # 触发最小置信度
    trigger_on_count_change: bool = True    # 数量变化时触发
    trigger_on_new_class: bool = True       # 出现新类别时触发


@dataclass
class KeyFrameData:
    """关键帧数据"""
    stream_id: str
    timestamp: float
    datetime_str: str
    frame_path: str
    annotated_path: Optional[str]
    detection_result: Dict
    metadata: Dict[str, Any] = field(default_factory=dict)


class KeyFrameExtractor:
    """
    关键帧提取器
    
    根据检测结果智能提取关键帧，支持多种触发策略
    """
    
    def __init__(self, config: KeyFrameConfig):
        self.config = config
        self.save_dir = Path(config.save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        
        # 状态追踪
        self.last_capture_time: Dict[str, float] = {}
        self.last_detection_count: Dict[str, int] = {}
        self.last_detection_classes: Dict[str, set] = {}
        self.daily_capture_count = 0
        self.last_date = datetime.now().date()
        
        # 回调
        self._capture_callbacks: List[Callable[[KeyFrameData], None]] = []
        
    def on_capture(self, callback: Callable[[KeyFrameData], None]):
        """注册关键帧捕获回调"""
        self._capture_callbacks.append(callback)
        
    def should_capture(self, stream_id: str, detection_result: Dict) -> bool:
        """
        判断是否应提取关键帧
        
        Args:
            stream_id: 流ID
            detection_result: 检测结果
            
        Returns:
            是否应该提取
        """
        # 检查每日限额
        current_date = datetime.now().date()
        if current_date != self.last_date:
            self.daily_capture_count = 0
            self.last_date = current_date
            
        if self.daily_capture_count >= self.config.max_daily_frames:
            return False
            
        # 检查时间间隔
        current_time = time.time()
        last_time = self.last_capture_time.get(stream_id, 0)
        if current_time - last_time < self.config.min_interval:
            return False
            
        detections = detection_result.get("detections", [])
        if not detections:
            return False
            
        # 检查置信度
        high_conf_detections = [
            d for d in detections 
            if d.get("confidence", 0) >= self.config.trigger_min_confidence
        ]
        if not high_conf_detections:
            return False
            
        # 检查触发类别
        if self.config.trigger_classes:
            has_trigger_class = any(
                d.get("class_name") in self.config.trigger_classes
                for d in high_conf_detections
            )
            if not has_trigger_class:
                return False
                
        # 检查数量变化
        current_count = len(high_conf_detections)
        last_count = self.last_detection_count.get(stream_id, 0)
        if self.config.trigger_on_count_change and current_count != last_count:
            return True
            
        # 检查新类别出现
        current_classes = set(d.get("class_name") for d in high_conf_detections)
        last_classes = self.last_detection_classes.get(stream_id, set())
        if self.config.trigger_on_new_class and current_classes - last_classes:
            return True
            
        # 默认：有检测结果就触发（但受时间间隔限制）
        return True
        
    def extract(self, 
                frame: np.ndarray, 
                stream_id: str, 
                detection_result: Dict,
                metadata: Optional[Dict] = None) -> Optional[KeyFrameData]:
        """
        提取关键帧
        
        Args:
            frame: 原始帧
            stream_id: 流ID
            detection_result: 检测结果
            metadata: 额外元数据
            
        Returns:
            KeyFrameData 或 None
        """
        if not self.should_capture(stream_id, detection_result):
            return None
            
        current_time = time.time()
        dt = datetime.fromtimestamp(current_time)
        dt_str = dt.strftime("%Y%m%d_%H%M%S_%f")[:-3]
        
        # 创建保存路径
        date_dir = self.save_dir / dt.strftime("%Y%m%d") / stream_id
        date_dir.mkdir(parents=True, exist_ok=True)
        
        base_filename = f"{stream_id}_{dt_str}"
        
        # 保存原图
        original_path = None
        if self.config.save_original:
            original_path = date_dir / f"{base_filename}_orig.{self.config.save_format}"
            cv2.imwrite(
                str(original_path), 
                frame, 
                [cv2.IMWRITE_JPEG_QUALITY, self.config.quality]
            )
            
        # 保存带标注的图
        annotated_path = None
        if self.config.save_with_annotation:
            annotated_frame = self._draw_annotations(frame, detection_result)
            annotated_path = date_dir / f"{base_filename}_annotated.{self.config.save_format}"
            cv2.imwrite(
                str(annotated_path), 
                annotated_frame,
                [cv2.IMWRITE_JPEG_QUALITY, self.config.quality]
            )
            
        # 保存元数据
        meta_path = date_dir / f"{base_filename}.json"
        meta_data = {
            "stream_id": stream_id,
            "timestamp": current_time,
            "datetime": dt_str,
            "detection_result": detection_result,
            "original_path": str(original_path) if original_path else None,
            "annotated_path": str(annotated_path) if annotated_path else None,
            "metadata": metadata or {}
        }
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta_data, f, ensure_ascii=False, indent=2)
            
        # 更新状态
        self.last_capture_time[stream_id] = current_time
        self.last_detection_count[stream_id] = len(detection_result.get("detections", []))
        self.last_detection_classes[stream_id] = set(
            d.get("class_name") for d in detection_result.get("detections", [])
        )
        self.daily_capture_count += 1
        
        # 创建返回数据
        keyframe_data = KeyFrameData(
            stream_id=stream_id,
            timestamp=current_time,
            datetime_str=dt_str,
            frame_path=str(original_path or annotated_path),
            annotated_path=str(annotated_path) if annotated_path else None,
            detection_result=detection_result,
            metadata=metadata or {}
        )
        
        logger.info(f"KeyFrame captured: {stream_id} at {dt_str}, "
                   f"detections: {len(detection_result.get('detections', []))}")
        
        # 触发回调
        for cb in self._capture_callbacks:
            try:
                cb(keyframe_data)
            except Exception as e:
                logger.error(f"Capture callback error: {e}")
                
        return keyframe_data
        
    def _draw_annotations(self, frame: np.ndarray, detection_result: Dict) -> np.ndarray:
        """在帧上绘制检测结果"""
        annotated = frame.copy()
        detections = detection_result.get("detections", [])
        
        # 颜色映射
        colors = {
            "person": (0, 255, 0),
            "helmet": (0, 255, 255),
            "no_helmet": (0, 0, 255),
            "car": (255, 0, 0),
            "truck": (255, 128, 0),
        }
        default_color = (128, 128, 128)
        
        for det in detections:
            class_name = det.get("class_name", "unknown")
            confidence = det.get("confidence", 0)
            bbox = det.get("bbox", [0, 0, 0, 0])
            
            x1, y1, x2, y2 = map(int, bbox)
            color = colors.get(class_name, default_color)
            
            # 绘制边界框
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            
            # 绘制标签
            label = f"{class_name}: {confidence:.2f}"
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
            cv2.rectangle(
                annotated, 
                (x1, y1 - label_size[1] - 4), 
                (x1 + label_size[0], y1), 
                color, 
                -1
            )
            cv2.putText(
                annotated, 
                label, 
                (x1, y1 - 4), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.5, 
                (255, 255, 255), 
                1
            )
            
        # 添加时间戳
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(
            annotated,
            timestamp,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2
        )
        
        return annotated
        
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "daily_capture_count": self.daily_capture_count,
            "max_daily_frames": self.config.max_daily_frames,
            "save_dir": str(self.save_dir),
            "stream_stats": {
                stream_id: {
                    "last_capture": self.last_capture_time.get(stream_id, 0),
                    "last_count": self.last_detection_count.get(stream_id, 0)
                }
                for stream_id in self.last_capture_time.keys()
            }
        }


# ==================== 使用示例 ====================

def demo():
    """演示用法"""
    import numpy as np
    
    # 创建配置
    config = KeyFrameConfig(
        save_dir="./demo_keyframes",
        min_interval=1.0,  # 1秒间隔
        trigger_classes=["person", "no_helmet"],  # 只关注人和未戴安全帽
        trigger_min_confidence=0.6
    )
    
    # 创建提取器
    extractor = KeyFrameExtractor(config)
    
    # 模拟检测结果
    mock_detection = {
        "detections": [
            {"class_name": "person", "confidence": 0.85, "bbox": [100, 100, 200, 300]},
            {"class_name": "no_helmet", "confidence": 0.75, "bbox": [120, 120, 180, 180]}
        ]
    }
    
    # 模拟帧
    mock_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    
    # 测试提取
    for i in range(5):
        result = extractor.extract(mock_frame, "test_cam", mock_detection)
        if result:
            print(f"Captured: {result.frame_path}")
        else:
            print("Skipped (interval limit)")
        time.sleep(0.5)
        
    print(f"\nStats: {extractor.get_stats()}")


if __name__ == "__main__":
    demo()
