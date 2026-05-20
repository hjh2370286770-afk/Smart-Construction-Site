"""
视频流处理器 - Stream Processor
支持多路视频流的实时处理和检测
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

import cv2
import numpy as np

from detectors import BaseDetector

logger = logging.getLogger(__name__)


class StreamStatus(Enum):
    """流状态"""
    STOPPED = "stopped"
    CONNECTING = "connecting"
    RUNNING = "running"
    RECONNECTING = "reconnecting"
    ERROR = "error"
    PAUSED = "paused"


@dataclass
class StreamStats:
    """流统计信息"""
    frame_count: int = 0
    detection_count: int = 0
    violation_count: int = 0
    fps: float = 0.0
    start_time: Optional[float] = None
    last_frame_time: Optional[float] = None
    reconnect_count: int = 0
    error_count: int = 0


@dataclass
class StreamConfig:
    """流配置"""
    camera_id: str
    name: str
    url: str
    stream_type: str = "rtmp"  # rtmp, rtsp, http
    enabled: bool = True
    fps: int = 25
    resolution: tuple = (960, 540)  # 处理分辨率
    buffer_size: int = 1
    reconnect_interval: int = 3
    max_reconnects: int = 10
    frame_skip: int = 3  # 每N帧检测一次


class VideoStreamProcessor:
    """
    视频流处理器
    
    功能：
    1. 单路视频流的读取和处理
    2. 自动重连机制
    3. 帧率控制和跳帧
    4. 检测器调用
    5. 违规截图保存
    6. 实时状态上报
    """
    
    def __init__(self, config: StreamConfig, detector: BaseDetector,
                 output_dir: Path, event_callback: Optional[Callable] = None,
                 enable_display: bool = True):
        """
        初始化视频流处理器
        
        Args:
            config: 流配置
            detector: 检测器实例
            output_dir: 输出目录
            event_callback: 事件回调函数
            enable_display: 是否启用显示窗口
        """
        self.config = config
        self.detector = detector
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.event_callback = event_callback
        self.enable_display = enable_display
        
        # 状态
        self.status = StreamStatus.STOPPED
        self.running = False
        self.paused = False
        
        # 统计
        self.stats = StreamStats()
        
        # 检测相关
        self.last_detection = []
        self.last_save_time = 0
        self.save_interval = 3  # 违规截图间隔（秒）
        
        # 日志
        self.violation_log: List[Dict] = []
        
    async def start(self):
        """启动处理"""
        if self.running:
            logger.warning(f"[{self.config.camera_id}] 已经在运行")
            return
            
        self.running = True
        self.status = StreamStatus.CONNECTING
        self.stats.start_time = time.time()
        
        logger.info(f"[{self.config.camera_id}] 启动视频流处理")
        
        # 在后台运行处理循环
        asyncio.create_task(self._process_loop())
        
    async def stop(self):
        """停止处理"""
        logger.info(f"[{self.config.camera_id}] 停止视频流处理")
        self.running = False
        self.status = StreamStatus.STOPPED
        
        # 关闭显示窗口
        if self.enable_display:
            cv2.destroyWindow(f"Monitor - {self.config.camera_id}")
        
        await self._save_log()
        
    def pause(self):
        """暂停"""
        self.paused = True
        self.status = StreamStatus.PAUSED
        logger.info(f"[{self.config.camera_id}] 暂停")
        
    def resume(self):
        """恢复"""
        self.paused = False
        self.status = StreamStatus.RUNNING
        logger.info(f"[{self.config.camera_id}] 恢复")
        
    async def _process_loop(self):
        """处理主循环"""
        reconnect_count = 0
        
        while self.running:
            try:
                # 连接并处理视频流
                should_reconnect = await self._process_stream()
                
                if not self.running:
                    break
                    
                # 需要重连
                if should_reconnect and reconnect_count < self.config.max_reconnects:
                    reconnect_count += 1
                    self.stats.reconnect_count = reconnect_count
                    self.status = StreamStatus.RECONNECTING
                    
                    logger.warning(
                        f"[{self.config.camera_id}] 第 {reconnect_count} 次重连，"
                        f"{self.config.reconnect_interval}秒后重试..."
                    )
                    await asyncio.sleep(self.config.reconnect_interval)
                else:
                    break
                    
            except Exception as e:
                logger.error(f"[{self.config.camera_id}] 处理循环异常: {e}")
                self.stats.error_count += 1
                await asyncio.sleep(1)
                
        self.status = StreamStatus.STOPPED
        logger.info(f"[{self.config.camera_id}] 处理循环结束")
        
    async def _process_stream(self) -> bool:
        """
        处理视频流
        
        Returns:
            bool: True=需要重连, False=正常结束
        """
        # 打开视频流
        logger.info(f"[{self.config.camera_id}] 连接视频流: {self.config.url[:50]}...")
        
        cap = cv2.VideoCapture(self.config.url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, self.config.buffer_size)
        
        if not cap.isOpened():
            logger.error(f"[{self.config.camera_id}] 无法打开视频流")
            return True  # 需要重连
            
        self.status = StreamStatus.RUNNING
        logger.info(f"[{self.config.camera_id}] 视频流已连接")
        
        # 获取视频信息
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info(f"[{self.config.camera_id}] 流信息: {width}x{height} @ {fps:.1f}fps")
        
        # 处理循环
        empty_count = 0
        max_empty = 30
        last_status_time = time.time()
        
        try:
            while self.running:
                # 暂停检查
                if self.paused:
                    await asyncio.sleep(0.1)
                    continue
                
                # 读取帧
                ret, frame = cap.read()
                
                if not ret:
                    empty_count += 1
                    if empty_count > max_empty:
                        logger.error(f"[{self.config.camera_id}] 视频流断开")
                        return True  # 需要重连
                    continue
                else:
                    empty_count = 0
                
                # 更新统计
                self.stats.frame_count += 1
                self.stats.last_frame_time = time.time()
                
                # 计算FPS
                if self.stats.start_time:
                    elapsed = time.time() - self.stats.start_time
                    self.stats.fps = self.stats.frame_count / elapsed if elapsed > 0 else 0
                
                # 调整分辨率
                if frame.shape[1] != self.config.resolution[0] or \
                   frame.shape[0] != self.config.resolution[1]:
                    frame = cv2.resize(frame, self.config.resolution)
                
                # 跳帧检测 - 使用 self.last_detection 保持检测结果，避免闪烁
                if self.stats.frame_count % self.config.frame_skip == 0:
                    try:
                        # 执行检测
                        self.last_detection = self.detector.detect(frame)
                        self.stats.detection_count += len(self.last_detection)
                        
                        # 检查违规
                        violations = self.detector.check_violations(self.last_detection)
                        if violations:
                            self.stats.violation_count += len(violations)
                            await self._handle_violations(frame, violations, self.last_detection)
                            
                    except Exception as e:
                        logger.error(f"[{self.config.camera_id}] 检测异常: {e}")
                
                # 显示画面 - 始终使用 last_detection 保持显示稳定
                if self.enable_display:
                    display_frame = frame.copy()
                    if self.last_detection:
                        display_frame = self.detector.draw_results(display_frame, self.last_detection)
                    display_frame = self._draw_status(display_frame)
                    cv2.imshow(f"Monitor - {self.config.camera_id}", display_frame)
                    
                    # 键盘控制
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q'):
                        logger.info(f"[{self.config.camera_id}] 用户按q退出")
                        self.running = False
                        return False
                    elif key == ord('p'):
                        self.paused = not self.paused
                        logger.info(f"[{self.config.camera_id}] {'暂停' if self.paused else '继续'}")
                
                # 定期上报状态（每30秒）
                if time.time() - last_status_time > 30:
                    await self._report_status()
                    last_status_time = time.time()
                    
                # 让出控制权
                await asyncio.sleep(0.001)
                
        except Exception as e:
            logger.error(f"[{self.config.camera_id}] 流处理异常: {e}")
            return True
        finally:
            cap.release()
            
        return False  # 正常结束
        
    def _draw_status(self, frame: np.ndarray) -> np.ndarray:
        """在画面上绘制状态信息"""
        # 计算合规率
        persons = [d for d in self.last_detection if hasattr(d, 'class_name') and d.class_name == 'person']
        if persons:
            compliant = sum(1 for p in persons if getattr(p, 'has_helmet', False) and getattr(p, 'has_vest', False))
            compliance_rate = (compliant / len(persons) * 100)
        else:
            compliance_rate = 100
        
        # 状态文本
        lines = [
            f"FPS: {self.stats.fps:.1f}",
            f"Frames: {self.stats.frame_count}",
            f"Persons: {len(persons)}",
            f"Compliant: {compliance_rate:.0f}%",
            f"Violations: {self.stats.violation_count}",
            f"Status: {self.status.value}",
            "",
            "Keys: q=quit, p=pause"
        ]
        
        # 绘制背景
        y_offset = 30
        for i, line in enumerate(lines):
            y = y_offset + i * 25
            # 黑色背景
            (text_w, text_h), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
            cv2.rectangle(frame, (10, y - text_h - 5), (10 + text_w, y + 5), (0, 0, 0), -1)
            # 绿色文字
            cv2.putText(frame, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        return frame
        
    async def _handle_violations(self, frame: np.ndarray, violations: List[Dict],
                                  detections: List[Any]):
        """处理违规事件"""
        current_time = time.time()
        
        for violation in violations:
            # 限制保存频率
            if current_time - self.last_save_time < self.save_interval:
                continue
                
            self.last_save_time = current_time
            
            # 保存违规截图
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            violation_types = [v['type'] for v in violation.get('violations', [])]
            desc = "_".join(violation_types) if violation_types else "VIOLATION"
            
            filename = f"violation_{timestamp}_ID{violation.get('person_id', 'X')}_{desc}.jpg"
            filepath = self.output_dir / filename
            
            try:
                # 绘制检测结果
                result_frame = self.detector.draw_results(frame.copy(), detections)
                cv2.imwrite(str(filepath), result_frame)
                
                # 记录日志
                log_entry = {
                    "timestamp": timestamp,
                    "camera_id": self.config.camera_id,
                    "person_id": violation.get('person_id'),
                    "violation_types": violation_types,
                    "filepath": str(filepath)
                }
                self.violation_log.append(log_entry)
                
                logger.warning(
                    f"[{self.config.camera_id}] 违规: ID{violation.get('person_id')} - {desc}"
                )
                
                # 触发回调
                if self.event_callback:
                    await self.event_callback({
                        "type": "violation",
                        "camera_id": self.config.camera_id,
                        "data": log_entry
                    })
                    
            except Exception as e:
                logger.error(f"[{self.config.camera_id}] 保存违规截图失败: {e}")
                
    async def _report_status(self):
        """上报状态"""
        logger.info(
            f"[{self.config.camera_id}] 状态 - "
            f"帧: {self.stats.frame_count}, "
            f"FPS: {self.stats.fps:.1f}, "
            f"检测: {self.stats.detection_count}, "
            f"违规: {self.stats.violation_count}, "
            f"重连: {self.stats.reconnect_count}"
        )
        
        if self.event_callback:
            await self.event_callback({
                "type": "status",
                "camera_id": self.config.camera_id,
                "data": {
                    "status": self.status.value,
                    "stats": {
                        "frame_count": self.stats.frame_count,
                        "fps": self.stats.fps,
                        "detection_count": self.stats.detection_count,
                        "violation_count": self.stats.violation_count,
                        "reconnect_count": self.stats.reconnect_count
                    }
                }
            })
            
    async def _save_log(self):
        """保存日志"""
        if not self.violation_log:
            return
            
        log_file = self.output_dir / "violation_log.json"
        try:
            import json
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "camera_id": self.config.camera_id,
                    "start_time": datetime.fromtimestamp(self.stats.start_time).isoformat() if self.stats.start_time else None,
                    "end_time": datetime.now().isoformat(),
                    "stats": {
                        "total_frames": self.stats.frame_count,
                        "total_violations": self.stats.violation_count,
                        "reconnect_count": self.stats.reconnect_count
                    },
                    "violations": self.violation_log
                }, f, ensure_ascii=False, indent=2)
            logger.info(f"[{self.config.camera_id}] 日志已保存: {log_file}")
        except Exception as e:
            logger.error(f"[{self.config.camera_id}] 保存日志失败: {e}")
            
    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        return {
            "camera_id": self.config.camera_id,
            "name": self.config.name,
            "status": self.status.value,
            "enabled": self.config.enabled,
            "stats": {
                "frame_count": self.stats.frame_count,
                "fps": self.stats.fps,
                "detection_count": self.stats.detection_count,
                "violation_count": self.stats.violation_count,
                "reconnect_count": self.stats.reconnect_count,
                "error_count": self.stats.error_count
            }
        }
