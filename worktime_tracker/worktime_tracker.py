#!/usr/bin/env python3
"""
人员工作时间统计系统
基于视频流检测人员并统计工作时间

功能:
1. 连接RTSP视频流（支持自动重连）
2. 检测视频中的人员
3. 跟踪人员并统计每个人的工作时间
4. 程序关闭时输出工作时间统计报告
"""

import sys
import time
import json
import signal
import threading
import queue
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

import cv2
import numpy as np


@dataclass
class PersonWorkRecord:
    """单个人员的工作记录"""
    track_id: int
    first_appearance: datetime
    last_appearance: datetime
    total_frames: int = 0
    appearance_history: List[Tuple[datetime, datetime]] = field(default_factory=list)
    
    def update_appearance(self, timestamp: datetime):
        """更新出现时间"""
        self.last_appearance = timestamp
        self.total_frames += 1
        
        # 如果与上次出现间隔超过5秒，认为是新的工作时段
        if self.appearance_history:
            last_end = self.appearance_history[-1][1]
            gap = (timestamp - last_end).total_seconds()
            if gap > 5:
                self.appearance_history.append((timestamp, timestamp))
            else:
                # 延长当前时段
                self.appearance_history[-1] = (self.appearance_history[-1][0], timestamp)
        else:
            self.appearance_history.append((timestamp, timestamp))
    
    def get_total_work_time(self) -> timedelta:
        """获取总工作时间"""
        total_seconds = 0
        for start, end in self.appearance_history:
            total_seconds += (end - start).total_seconds()
        return timedelta(seconds=int(total_seconds))
    
    def to_dict(self) -> dict:
        return {
            'track_id': self.track_id,
            'first_appearance': self.first_appearance.strftime('%Y-%m-%d %H:%M:%S'),
            'last_appearance': self.last_appearance.strftime('%Y-%m-%d %H:%M:%S'),
            'total_frames': self.total_frames,
            'work_time_seconds': int(self.get_total_work_time().total_seconds()),
            'work_time_formatted': str(self.get_total_work_time()),
            'appearance_count': len(self.appearance_history)
        }


class SimplePersonDetector:
    """
    简化版人员检测器
    使用YOLOv8或类似的预训练模型检测人员
    """
    
    def __init__(self, conf_threshold: float = 0.45, iou_threshold: float = 0.4):
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.model = None
        self.next_track_id = 1
        self.tracks = {}  # track_id -> {'center': (x, y), 'bbox': (x1,y1,x2,y2), 'last_seen': time}
        self.track_timeout = 10.0  # 10秒未检测到认为人员离开（增加稳定性）
        self.max_tracking_distance = 150  # 最大跟踪距离（像素）
        
        # 尝试加载YOLO模型
        self._load_model()
    
    def _load_model(self):
        """加载检测模型"""
        # 本地模型路径列表
        model_paths = [
            r"C:\Users\Admini503\.openclaw\workspace\yolov8n.pt",
            r"C:\Users\Admini503\.openclaw\workspace\models\pretrained\yolov8n.pt",
            "yolov8n.pt",  # 当前目录
        ]
        
        try:
            # 尝试使用ultralytics的YOLO
            from ultralytics import YOLO
            
            # 查找可用的本地模型
            model_path = None
            for path in model_paths:
                if Path(path).exists():
                    model_path = path
                    break
            
            if model_path:
                self.model = YOLO(model_path)
                print(f"[OK] YOLOv8模型加载成功: {model_path}")
            else:
                print("[WARN] 未找到本地模型文件，尝试在线下载...")
                self.model = YOLO('yolov8n.pt')
                print("[OK] YOLOv8模型下载并加载成功")
                
        except ImportError:
            print("[WARN] ultralytics未安装，尝试使用OpenCV DNN...")
            self._load_opencv_model()
        except Exception as e:
            print(f"[ERROR] 模型加载失败: {e}")
            self.model = None
    
    def _load_opencv_model(self):
        """使用OpenCV DNN作为备选"""
        try:
            # 使用OpenCV的预训练模型
            model_path = "yolov4-tiny.weights"
            config_path = "yolov4-tiny.cfg"
            
            # 检查文件是否存在
            if Path(model_path).exists() and Path(config_path).exists():
                self.model = cv2.dnn.readNet(model_path, config_path)
                self.model.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
                self.model.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
                print("[OK] OpenCV DNN模型加载成功")
            else:
                print("[WARN] 未找到YOLO模型文件，将使用背景减除法进行简单检测")
                self.model = None
        except Exception as e:
            print(f"[ERROR] OpenCV模型加载失败: {e}")
            self.model = None
    
    def detect(self, frame: np.ndarray) -> List[Dict]:
        """
        检测人员
        
        Returns:
            检测到的目标列表，每个包含: track_id, bbox, confidence
        """
        detections = []
        
        if self.model is None:
            # 无模型时使用简单方法（仅演示）
            return self._simple_detect(frame)
        
        try:
            # 使用YOLO检测
            if hasattr(self.model, 'predict'):
                # ultralytics YOLO
                results = self.model.predict(frame, classes=[0], conf=self.conf_threshold, verbose=False)
                for result in results:
                    boxes = result.boxes
                    for box in boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        conf = float(box.conf[0])
                        detections.append({
                            'bbox': (int(x1), int(y1), int(x2), int(y2)),
                            'confidence': conf
                        })
        except Exception as e:
            print(f"[ERROR] 检测异常: {e}")
        
        # 分配跟踪ID
        detections = self._assign_track_ids(detections)
        return detections
    
    def _simple_detect(self, frame: np.ndarray) -> List[Dict]:
        """简单的背景减除检测（备选方案）"""
        # 这里可以添加简单的移动物体检测
        # 目前返回空列表
        return []
    
    def _assign_track_ids(self, detections: List[Dict]) -> List[Dict]:
        """为检测结果分配跟踪ID - 改进版，使用IOU+距离综合评分"""
        current_time = time.time()
        assigned_track_ids = set()
        assigned_detections = set()
        
        # 准备当前检测的中心点和边界框
        det_info = []
        for i, det in enumerate(detections):
            bbox = det['bbox']
            center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
            det_info.append({
                'idx': i,
                'det': det,
                'center': center,
                'bbox': bbox
            })
        
        # 计算所有检测与所有跟踪的匹配分数
        matches = []  # (score, det_idx, track_id)
        for info in det_info:
            for track_id, track in self.tracks.items():
                # 检查跟踪是否过期
                if current_time - track['last_seen'] > self.track_timeout:
                    continue
                
                # 计算距离
                dist = ((info['center'][0] - track['center'][0]) ** 2 + 
                       (info['center'][1] - track['center'][1]) ** 2) ** 0.5
                
                # 计算IOU
                iou = self._compute_iou(info['bbox'], track['bbox'])
                
                # 综合评分：距离越小越好，IOU越大越好
                # 归一化距离分数（在max_tracking_distance内）
                dist_score = max(0, 1 - dist / self.max_tracking_distance)
                
                # 综合分数 = IOU * 0.6 + 距离分数 * 0.4
                score = iou * 0.6 + dist_score * 0.4
                
                # 只考虑距离在阈值内的匹配
                if dist < self.max_tracking_distance:
                    matches.append((score, info['idx'], track_id))
        
        # 按分数降序排序
        matches.sort(reverse=True)
        
        # 分配跟踪ID（贪心算法，优先匹配高分对）
        for score, det_idx, track_id in matches:
            if det_idx in assigned_detections or track_id in assigned_track_ids:
                continue
            
            # 分配ID
            detections[det_idx]['track_id'] = track_id
            assigned_track_ids.add(track_id)
            assigned_detections.add(det_idx)
            
            # 更新跟踪信息
            self.tracks[track_id] = {
                'center': det_info[det_idx]['center'],
                'bbox': det_info[det_idx]['bbox'],
                'last_seen': current_time
            }
        
        # 为未匹配的检测创建新跟踪
        for info in det_info:
            if info['idx'] not in assigned_detections:
                track_id = self.next_track_id
                self.next_track_id += 1
                
                detections[info['idx']]['track_id'] = track_id
                assigned_track_ids.add(track_id)
                
                self.tracks[track_id] = {
                    'center': info['center'],
                    'bbox': info['bbox'],
                    'last_seen': current_time
                }
        
        # 清理超时的跟踪
        expired_tracks = []
        for track_id, track in self.tracks.items():
            if current_time - track['last_seen'] > self.track_timeout:
                expired_tracks.append(track_id)
        
        for track_id in expired_tracks:
            del self.tracks[track_id]
        
        return detections
    
    def _compute_iou(self, box1, box2):
        """计算两个边界框的IOU"""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        
        inter_area = max(0, x2 - x1) * max(0, y2 - y1)
        box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
        box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])
        
        union_area = box1_area + box2_area - inter_area
        return inter_area / union_area if union_area > 0 else 0
    
    def draw_results(self, frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
        """在图像上绘制检测结果 - 改进版，更稳定的显示"""
        result = frame.copy()
        
        # 预定义颜色列表（更鲜明的颜色）
        colors = [
            (0, 255, 0),      # 绿色
            (0, 0, 255),      # 红色
            (255, 0, 0),      # 蓝色
            (0, 255, 255),    # 黄色
            (255, 0, 255),    # 紫色
            (255, 255, 0),    # 青色
            (0, 128, 255),    # 橙色
            (128, 0, 128),    # 深紫色
        ]
        
        for det in detections:
            x1, y1, x2, y2 = det['bbox']
            track_id = det.get('track_id', 0)
            conf = det.get('confidence', 0)
            
            # 根据ID选择颜色（循环使用颜色列表）
            color = colors[track_id % len(colors)]
            
            # 绘制边界框（加粗）
            cv2.rectangle(result, (x1, y1), (x2, y2), color, 3)
            
            # 绘制标签背景（更大的背景）
            label = f"ID:{track_id} {conf:.2f}"
            (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            
            # 标签位置（确保不超出图像边界）
            label_y = max(y1 - 8, text_h + 5)
            
            cv2.rectangle(result, (x1, label_y - text_h - 5),
                         (x1 + text_w + 5, label_y), color, -1)
            cv2.putText(result, label, (x1 + 2, label_y - 2),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # 绘制中心点（帮助可视化跟踪位置）
            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2
            cv2.circle(result, (center_x, center_y), 4, color, -1)
        
        return result


class WorkTimeTracker:
    """
    工作时间统计器
    管理视频流连接、人员检测和工作时间统计
    """
    
    def __init__(self, stream_url: str, output_dir: str = "./worktime_output"):
        self.stream_url = stream_url
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # 初始化检测器
        print("正在初始化人员检测器...")
        self.detector = SimplePersonDetector(conf_threshold=0.45)
        print("[OK] 检测器初始化完成")
        
        # 工作时间记录
        self.work_records: Dict[int, PersonWorkRecord] = {}
        self.current_persons: set = set()  # 当前在画面中的人员ID
        
        # 统计信息
        self.frame_count = 0
        self.start_time = None
        self.reconnect_count = 0
        self.running = False
        
        # 信号处理
        self.shutdown_requested = False
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """处理退出信号"""
        print("\n[INFO] 收到退出信号，正在保存数据...")
        self.shutdown_requested = True
        self.running = False
    
    def run(self, duration: int = None, enable_display: bool = True):
        """
        运行工作时间统计
        
        Args:
            duration: 运行时长（秒），None表示无限
            enable_display: 是否显示视频窗口
        """
        print("\n" + "=" * 70)
        print("人员工作时间统计系统")
        print("=" * 70)
        print(f"视频流: {self.stream_url}")
        print(f"运行时长: {'无限' if duration is None else f'{duration}秒'}")
        print(f"输出目录: {self.output_dir}")
        print("按键: q=退出, s=保存截图, p=暂停")
        print("=" * 70 + "\n")
        
        self.start_time = time.time()
        self.running = True
        
        if enable_display:
            cv2.namedWindow("WorkTime Tracker", cv2.WINDOW_NORMAL)
        
        try:
            while self.running and not self.shutdown_requested:
                # 检查运行时长
                elapsed = time.time() - self.start_time
                if duration and elapsed >= duration:
                    print(f"\n[INFO] 运行时长已达设定值 ({duration}秒)")
                    break
                
                # 启动或重启视频流连接
                remaining = None if duration is None else (duration - elapsed)
                success = self._run_stream_loop(remaining, enable_display)
                
                if not success:
                    break
                
                # 连接断开，尝试重连
                if self.running:
                    self.reconnect_count += 1
                    print(f"\n[RECONNECT] 第 {self.reconnect_count} 次重连...")
                    time.sleep(3)
                    
        except Exception as e:
            print(f"\n[ERROR] 程序异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.running = False
            if enable_display:
                cv2.destroyAllWindows()
            self._generate_report()
            print("[OK] 程序结束")
    
    def _run_stream_loop(self, duration: int = None, enable_display: bool = True) -> bool:
        """
        运行单次流连接循环
        
        Returns:
            bool: True=需要重连, False=正常结束
        """
        print(f"\n[STREAM] 正在连接视频流...")
        cap = cv2.VideoCapture(self.stream_url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        if not cap.isOpened():
            print("[ERROR] 无法打开视频流")
            return True
        
        print(f"[OK] 视频流已连接")
        if self.reconnect_count > 0:
            print(f"[STREAM] 重连后恢复运行")
        
        # 获取视频信息
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[INFO] 流信息: {width}x{height} @ {fps:.1f}fps")
        
        loop_start = time.time()
        last_log_time = time.time()
        last_save_time = time.time()
        empty_count = 0
        max_empty = 30
        paused = False
        
        try:
            while self.running and not self.shutdown_requested:
                # 检查本次连接的运行时长
                loop_elapsed = time.time() - loop_start
                if duration and loop_elapsed >= duration:
                    cap.release()
                    return False
                
                # 每30秒打印状态
                if time.time() - last_log_time > 30:
                    self._print_status()
                    last_log_time = time.time()
                
                if paused:
                    time.sleep(0.1)
                    continue
                
                # 读取帧
                ret, frame = cap.read()
                
                if not ret:
                    empty_count += 1
                    if empty_count > max_empty:
                        print(f"\n[ERROR] 视频流断开 - 连续 {empty_count} 次读取失败")
                        cap.release()
                        return True
                    continue
                else:
                    if empty_count > 0:
                        print(f"[WARN] 之前连续 {empty_count} 次读取异常，已恢复")
                    empty_count = 0
                
                # 缩放帧以提高性能
                if frame.shape[1] > 960:
                    frame = cv2.resize(frame, (960, 540))
                
                self.frame_count += 1
                current_time = datetime.now()
                
                # 每3帧检测一次
                detections = []
                if self.frame_count % 3 == 0:
                    try:
                        detections = self.detector.detect(frame)
                        self._update_work_records(detections, current_time)
                    except Exception as e:
                        print(f"[ERROR] 检测异常: {e}")
                
                # 显示
                if enable_display:
                    display_frame = frame.copy()
                    if detections:
                        display_frame = self.detector.draw_results(display_frame, detections)
                    self._draw_status(display_frame, detections)
                    cv2.imshow("WorkTime Tracker", display_frame)
                    
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q'):
                        print("\n[INFO] 用户退出")
                        self.running = False
                        cap.release()
                        return False
                    elif key == ord('s'):
                        self._save_screenshot(frame, detections)
                    elif key == ord('p'):
                        paused = not paused
                        print("[暂停]" if paused else "[继续]")
                        
        except Exception as e:
            print(f"\n[ERROR] 流循环异常: {e}")
            cap.release()
            return True
        finally:
            if cap.isOpened():
                cap.release()
    
    def _update_work_records(self, detections: List[Dict], timestamp: datetime):
        """更新工作时间记录"""
        current_ids = set()
        
        for det in detections:
            track_id = det.get('track_id')
            if track_id is None:
                continue
            
            current_ids.add(track_id)
            
            if track_id not in self.work_records:
                # 新人员
                self.work_records[track_id] = PersonWorkRecord(
                    track_id=track_id,
                    first_appearance=timestamp,
                    last_appearance=timestamp
                )
                print(f"[人员] ID{track_id} 进入画面")
            
            self.work_records[track_id].update_appearance(timestamp)
        
        # 检测离开的人员
        left_persons = self.current_persons - current_ids
        for pid in left_persons:
            if pid in self.work_records:
                work_time = self.work_records[pid].get_total_work_time()
                print(f"[人员] ID{pid} 离开画面，累计工作时间: {work_time}")
        
        self.current_persons = current_ids
    
    def _draw_status(self, frame: np.ndarray, detections: List[Dict]):
        """绘制状态信息"""
        elapsed = time.time() - self.start_time
        fps = self.frame_count / elapsed if elapsed > 0 else 0
        
        lines = [
            f"FPS: {fps:.1f}",
            f"Frames: {self.frame_count}",
            f"Current Persons: {len(detections)}",
            f"Total Unique: {len(self.work_records)}",
            f"Reconnects: {self.reconnect_count}",
            f"Runtime: {timedelta(seconds=int(elapsed))}"
        ]
        
        y = 30
        for line in lines:
            cv2.putText(frame, line, (10, y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            y += 25
        
        # 显示当前人员ID
        if detections:
            ids_text = "IDs: " + ", ".join([str(d.get('track_id', '?')) for d in detections])
            cv2.putText(frame, ids_text, (10, y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)
    
    def _print_status(self):
        """打印当前状态"""
        elapsed = time.time() - self.start_time
        print(f"[STATUS] 运行 {timedelta(seconds=int(elapsed))} | "
              f"帧: {self.frame_count} | "
              f"当前人员: {len(self.current_persons)} | "
              f"累计人员: {len(self.work_records)} | "
              f"重连: {self.reconnect_count}")
        
        # 打印每个人的工作时间
        for pid, record in sorted(self.work_records.items()):
            work_time = record.get_total_work_time()
            print(f"  - ID{pid}: {work_time}")
    
    def _save_screenshot(self, frame: np.ndarray, detections: List[Dict]):
        """保存截图"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.jpg"
        filepath = self.output_dir / filename
        
        display_frame = frame.copy()
        if detections:
            display_frame = self.detector.draw_results(display_frame, detections)
        self._draw_status(display_frame, detections)
        
        cv2.imwrite(str(filepath), display_frame)
        print(f"[截图] 已保存: {filepath}")
    
    def _generate_report(self):
        """生成工作时间统计报告"""
        print("\n" + "=" * 70)
        print("工作时间统计报告")
        print("=" * 70)
        
        if not self.work_records:
            print("未检测到任何人员")
            return
        
        # 按工作时间排序
        sorted_records = sorted(
            self.work_records.items(),
            key=lambda x: x[1].get_total_work_time(),
            reverse=True
        )
        
        total_work_time = timedelta()
        
        for pid, record in sorted_records:
            work_time = record.get_total_work_time()
            total_work_time += work_time
            
            print(f"\n人员 ID: {pid}")
            print(f"  首次出现: {record.first_appearance.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  最后出现: {record.last_appearance.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  工作时长: {work_time}")
            print(f"  出现次数: {record.appearance_count} 次")
            print(f"  检测帧数: {record.total_frames} 帧")
        
        print("\n" + "-" * 70)
        print(f"总人数: {len(self.work_records)}")
        print(f"总工作时间: {total_work_time}")
        print(f"平均工作时间: {total_work_time / len(self.work_records)}")
        print("=" * 70)
        
        # 保存JSON报告
        self._save_json_report()
    
    def _save_json_report(self):
        """保存JSON格式的报告"""
        elapsed = time.time() - self.start_time
        
        report = {
            'start_time': datetime.fromtimestamp(self.start_time).strftime('%Y-%m-%d %H:%M:%S'),
            'end_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_runtime_seconds': int(elapsed),
            'total_frames': self.frame_count,
            'reconnect_count': self.reconnect_count,
            'total_persons': len(self.work_records),
            'persons': [record.to_dict() for record in self.work_records.values()]
        }
        
        report_file = self.output_dir / f"worktime_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"\n[报告] 已保存到: {report_file}")


def main():
    # RTSP 流地址
    stream_url = "rtsp://admin:abcd1234@192.168.2.64/h264/ch1/main/av_stream"
    
    # 创建工作时间统计器
    tracker = WorkTimeTracker(
        stream_url=stream_url,
        output_dir="./worktime_output"
    )
    
    # 运行统计（None表示无限运行，直到按q退出）
    tracker.run(duration=None, enable_display=True)


if __name__ == "__main__":
    main()
