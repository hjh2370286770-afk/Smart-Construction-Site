"""
视频流处理器 - Stream Processor
支持多路视频流的实时处理和检测
使用独立线程读取视频，主线程处理检测
"""

import asyncio
import logging
import time
import queue
import threading
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
    stream_type: str = "rtmp"
    enabled: bool = True
    fps: int = 25
    resolution: tuple = (960, 540)
    buffer_size: int = 1
    reconnect_interval: int = 3
    max_reconnects: int = 10
    frame_skip: int = 3


class VideoStreamProcessor:
    """
    视频流处理器
    
    使用独立线程读取视频帧，异步处理检测
    """
    
    def __init__(self, config: StreamConfig, detector: Optional[BaseDetector],
                 output_dir: Path, event_callback: Optional[Callable] = None,
                 enable_display: bool = False):
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
        self.save_interval = 3
        
        # 帧队列（生产者-消费者模式）
        self.frame_queue: queue.Queue = queue.Queue(maxsize=2)
        
        # 视频捕获线程
        self.capture_thread: threading.Thread = None
        self.stop_capture_event = threading.Event()
        
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
        
        # 停止捕获线程
        if self.capture_thread and self.capture_thread.is_alive():
            self.stop_capture_event.set()
            self.capture_thread.join(timeout=3)
        
        self.status = StreamStatus.STOPPED
        
        # 关闭显示窗口
        if self.enable_display:
            cv2.destroyWindow(f"Monitor - {self.config.camera_id}")
        
        await self._save_log()
        
    def pause(self):
        """暂停"""
        self.paused = True
        self.status = StreamStatus.PAUSED
        logger.info(f"[{self.config.camera_id}] 暂停处理")
        
    def resume(self):
        """恢复"""
        self.paused = False
        self.status = StreamStatus.RUNNING
        logger.info(f"[{self.config.camera_id}] 恢复处理")
    
    def get_latest_frame(self) -> Optional[np.ndarray]:
        """获取最新帧（带检测框），供 snapshot API 和 MJPEG 流使用"""
        try:
            # 非阻塞获取最新帧
            latest_frame = None
            while True:
                try:
                    timestamp, frame = self.frame_queue.get_nowait()
                    latest_frame = frame
                except queue.Empty:
                    break
            
            if latest_frame is None:
                return None
            
            # 复制帧避免被修改
            latest_frame = latest_frame.copy()
            
            # 调整分辨率
            if latest_frame.shape[1] != self.config.resolution[0] or \
               latest_frame.shape[0] != self.config.resolution[1]:
                latest_frame = cv2.resize(latest_frame, self.config.resolution)
            
            # 如果有检测结果，使用检测器的 draw_results 方法绘制
            detections = getattr(self, 'last_detection', [])
            if detections and self.detector:
                try:
                    latest_frame = self.detector.draw_results(latest_frame, detections)
                except Exception as e:
                    logger.warning(f"[{self.config.camera_id}] 绘制检测框失败: {e}")
                    # 降级：简单画框
                    for det in detections:
                        if hasattr(det, 'x1'):
                            x1, y1, x2, y2 = int(det.x1), int(det.y1), int(det.x2), int(det.y2)
                            label = getattr(det, 'class_name', str(det))
                            cv2.rectangle(latest_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                            cv2.putText(latest_frame, label, (x1, y1-5), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            
            # 画状态信息
            fps_text = f"FPS: {self.stats.fps:.1f}"
            cv2.putText(latest_frame, fps_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # 画违规信息
            if hasattr(self, 'last_violations') and self.last_violations:
                y_offset = 60
                cv2.putText(latest_frame, "VIOLATIONS:", (10, y_offset), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                for i, v in enumerate(self.last_violations[:3]):
                    cv2.putText(latest_frame, f"- {v}", (10, y_offset + 25 * (i + 1)), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            
            return latest_frame
        except Exception as e:
            logger.debug(f"[{self.config.camera_id}] 获取最新帧失败: {e}")
            return None
        
    def _capture_loop(self):
        """
        独立的视频捕获线程
        负责持续读取视频帧，不阻塞主线程
        """
        logger.info(f"[{self.config.camera_id}] 捕获线程开始")
        
        cap = None
        reconnect_count = 0
        
        while self.running and not self.stop_capture_event.is_set():
            try:
                # 如果还没打开视频流，或者连接断开了
                if cap is None or not cap.isOpened():
                    if cap is not None:
                        cap.release()
                    
                    self.status = StreamStatus.CONNECTING
                    logger.info(f"[{self.config.camera_id}] 连接视频流...")
                    
                    cap = cv2.VideoCapture(self.config.url)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, self.config.buffer_size)
                    
                    if not cap.isOpened():
                        logger.warning(f"[{self.config.camera_id}] 连接失败，等待重连...")
                        time.sleep(self.config.reconnect_interval)
                        reconnect_count += 1
                        if reconnect_count > self.config.max_reconnects:
                            logger.error(f"[{self.config.camera_id}] 重连次数过多，停止")
                            break
                        continue
                    
                    reconnect_count = 0
                    self.status = StreamStatus.RUNNING
                    logger.info(f"[{self.config.camera_id}] 视频流已连接")
                
                # 读取帧
                ret, frame = cap.read()
                
                if not ret:
                    logger.warning(f"[{self.config.camera_id}] 读取帧失败")
                    cap.release()
                    cap = None
                    continue
                
                # 将帧放入队列（非阻塞）
                try:
                    if not self.frame_queue.full():
                        self.frame_queue.put_nowait((time.time(), frame))
                    else:
                        # 队列满了，跳过一些帧
                        try:
                            self.frame_queue.get_nowait()
                            self.frame_queue.put_nowait((time.time(), frame))
                        except:
                            pass
                except queue.Full:
                    pass
                    
            except Exception as e:
                logger.error(f"[{self.config.camera_id}] 捕获异常: {e}")
                if cap:
                    cap.release()
                    cap = None
                time.sleep(1)
        
        # 清理
        if cap:
            cap.release()
        logger.info(f"[{self.config.camera_id}] 捕获线程结束")
        
    async def _process_loop(self):
        """
        主处理循环（异步）
        从队列获取帧，处理检测
        优化：检测不阻塞主循环，使用后台任务
        """
        logger.info(f"[{self.config.camera_id}] 处理循环开始")
        
        # 启动独立的捕获线程
        self.stop_capture_event.clear()
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()
        
        frame_count = 0
        last_fps_time = time.time()
        last_status_time = time.time()
        detection_task = None  # 后台检测任务
        
        try:
            while self.running:
                # 从队列获取帧（非阻塞轮询）
                timestamp, frame = None, None
                try:
                    timestamp, frame = self.frame_queue.get_nowait()
                except queue.Empty:
                    pass
                
                if frame is None:
                    await asyncio.sleep(0.001)  # 让出控制权，避免忙等待
                    continue
                
                if self.paused:
                    continue
                
                # 更新统计
                self.stats.frame_count += 1
                self.stats.last_frame_time = timestamp
                frame_count += 1
                
                # 计算 FPS（每秒更新一次）
                current_time = time.time()
                if current_time - last_fps_time >= 1.0:
                    elapsed = current_time - last_fps_time
                    self.stats.fps = frame_count / elapsed if elapsed > 0 else 0
                    frame_count = 0
                    last_fps_time = current_time
                
                # 检测（每隔 frame_skip 帧）- 使用后台任务避免阻塞
                if self.detector and frame_count % self.config.frame_skip == 0:
                    # 如果上一个检测任务还在运行，跳过这一帧的检测
                    if detection_task is None or detection_task.done():
                        detection_task = asyncio.create_task(self._run_detection(frame))
                
                # 显示（如果启用）
                if self.enable_display:
                    display_frame = self._draw_status(frame.copy(), [])
                    cv2.imshow(f"Monitor - {self.config.camera_id}", display_frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q'):
                        self.running = False
                        break
                    elif key == ord('p'):
                        if self.paused:
                            self.resume()
                        else:
                            self.pause()
                
                # 定期上报状态
                if time.time() - last_status_time > 30:
                    await self._report_status()
                    last_status_time = time.time()
                    
        except Exception as e:
            logger.error(f"[{self.config.camera_id}] 处理异常: {e}")
        finally:
            self.status = StreamStatus.STOPPED
            logger.info(f"[{self.config.camera_id}] 处理循环结束")
    
    async def _run_detection(self, frame):
        """在后台运行检测"""
        try:
            # 在线程池中运行 CPU 密集型检测
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(None, lambda: self.detector.detect(frame))
            self.last_detection = results
            self.stats.detection_count += len(results)
            
            # 使用检测器的 check_violations 方法分析违规
            if hasattr(self.detector, 'check_violations'):
                violations = self.detector.check_violations(results)
            else:
                # 降级：使用内置分析
                violations = self._analyze_detection(results)
            
            self.last_violations = violations  # 保存违规信息供显示
            
            # 如果有违规，触发回调并保存截图
            if violations:
                self.stats.violation_count += len(violations)
                violation_types = []
                for v in violations:
                    if 'violations' in v:
                        violation_types.extend([vv['type'] for vv in v['violations']])
                
                logger.warning(f"[{self.config.camera_id}] 检测到违规: {violation_types}")
                
                # 保存违规截图
                await self._save_violation_screenshot(frame, violations)
                
                # 触发事件回调
                if self.event_callback:
                    for v in violations:
                        await self.event_callback({
                            'type': 'violation',
                            'data': {
                                'camera_id': self.config.camera_id,
                                'camera_name': self.config.name,
                                'violation_types': [vv['type'] for vv in v.get('violations', [])],
                                'timestamp': datetime.now().strftime("%Y%m%d_%H%M%S"),
                                'person_id': v.get('person_id', 'unknown')
                            }
                        })
                
        except Exception as e:
            logger.warning(f"[{self.config.camera_id}] 检测异常: {e}")
            
    def _analyze_detection(self, results) -> List[str]:
        """分析检测结果，返回违规类型列表"""
        violations = []
        
        # 分类检测结果
        has_helmet = False
        has_no_helmet = False
        has_vest = False
        has_no_vest = False
        has_person = False
        
        for r in results:
            class_name = r.class_name if hasattr(r, 'class_name') else str(r)
            
            if 'Hardhat' in class_name:
                has_helmet = True
            elif 'NO-Hardhat' in class_name or 'no_hardhat' in class_name.lower():
                has_no_helmet = True
            elif 'Safety Vest' in class_name:
                has_vest = True
            elif 'NO-Safety Vest' in class_name or 'no_vest' in class_name.lower():
                has_no_vest = True
            elif 'Person' in class_name:
                has_person = True
        
        # 判断违规
        if has_person:
            if has_no_helmet:
                violations.append('no_helmet')
            if has_no_vest:
                violations.append('no_vest')
                
        return violations
        
    async def _save_violation_screenshot(self, frame: np.ndarray, violations: List[Dict]):
        """保存违规截图"""
        try:
            # 限制保存频率（每3秒最多保存一次）
            current_time = time.time()
            if hasattr(self, '_last_violation_save_time'):
                if current_time - self._last_violation_save_time < 3:
                    return
            self._last_violation_save_time = current_time
            
            # 生成文件名 - 从违规信息中提取类型
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            violation_types = []
            for v in violations:
                if 'violations' in v:
                    violation_types.extend([vv['type'] for vv in v['violations']])
            violation_str = "_".join(violation_types) if violation_types else "VIOLATION"
            
            # 获取第一个违规的人员ID
            person_id = violations[0].get('person_id', 'X') if violations else 'X'
            filename = f"violation_{timestamp}_ID{person_id}_{violation_str}.jpg"
            filepath = self.output_dir / filename
            
            # 绘制检测结果后保存
            save_frame = frame.copy()
            if self.last_detection and self.detector:
                save_frame = self.detector.draw_results(save_frame, self.last_detection)
            
            # 添加时间戳
            cv2.putText(save_frame, timestamp, (10, save_frame.shape[0] - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # 保存图片
            cv2.imwrite(str(filepath), save_frame)
            logger.info(f"[{self.config.camera_id}] 违规截图已保存: {filepath}")
            
            # 记录到日志
            self.violation_log.append({
                'timestamp': timestamp,
                'camera_id': self.config.camera_id,
                'person_id': person_id,
                'violation_types': violation_types,
                'filepath': str(filepath)
            })
            
        except Exception as e:
            logger.error(f"[{self.config.camera_id}] 保存违规截图失败: {e}")

    async def _report_status(self):
        """上报状态"""
        logger.info(
            f"[{self.config.camera_id}] 状态 - "
            f"帧: {self.stats.frame_count}, FPS: {self.stats.fps:.1f}, "
            f"检测: {self.stats.detection_count}, 违规: {self.stats.violation_count}, "
            f"重连: {self.stats.reconnect_count}"
        )
        
        if self.event_callback:
            await self.event_callback({
                'type': 'status',
                'data': {
                    'camera_id': self.config.camera_id,
                    'stats': asdict(self.stats)
                }
            })
            
    async def _save_log(self):
        """保存日志"""
        if self.violation_log:
            log_file = self.output_dir / f"violation_log_{datetime.now().strftime('%Y%m%d')}.json"
            try:
                with open(log_file, 'w', encoding='utf-8') as f:
                    json.dump(self.violation_log, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"保存日志失败: {e}")
                
    def _draw_status(self, frame: np.ndarray, violations: List[str]) -> np.ndarray:
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
        ]
        
        # 绘制背景
        y_offset = 30
        for i, line in enumerate(lines):
            y = y_offset + i * 25
            (text_w, text_h), _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
            cv2.rectangle(frame, (10, y - text_h - 5), (10 + text_w, y + 5), (0, 0, 0), -1)
            cv2.putText(frame, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        # 绘制违规信息
        if violations:
            y_offset = 200
            cv2.putText(frame, "Violations:", (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            for i, v in enumerate(violations[:5]):
                cv2.putText(frame, f"- {v}", (20, y_offset + 25 * (i + 1)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        
        return frame
        
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return asdict(self.stats)
        
    def get_status(self) -> StreamStatus:
        """获取状态"""
        return self.status


from dataclasses import asdict
import json
