#!/usr/bin/env python3
"""
stream_manager_v2 视频流监控 - 直接使用原始代码
"""

import sys
import numpy as np
import time
import json
from datetime import datetime
from pathlib import Path

# 使用原始路径
sys.path.insert(0, r"C:\Users\Admini503\.openclaw\workspace\stream_manager")
sys.path.insert(0, r"C:\Users\Admini503\.openclaw\workspace\stream_manager\detectors")

import cv2
from detectors.ppe_detector import PPEDetector


class StreamMonitor:
    """视频流监控器 - 直接使用原始 ppe_monitor_opencv.py 的实现"""
    
    def __init__(self, stream_url: str, output_dir: str = "./output"):
        self.stream_url = stream_url
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # 初始化检测器 - 与原始代码完全一致
        print("正在初始化 PPE 检测器...")
        self.detector = PPEDetector(
            conf_threshold=0.45,
            iou_threshold=0.4
        )
        print("[OK] 检测器初始化完成")
        
        # 统计信息
        self.frame_count = 0
        self.detection_count = 0
        self.violation_count = 0
        self.violation_log = []
        self.start_time = None
        self.reconnect_count = 0
        
        # 运行状态
        self.running = False
        self.paused = False
        self.last_save_time = 0
        
    def run(self, duration: int = None, save_violations: bool = True):
        """运行监控"""
        print("\n" + "=" * 70)
        print("启动实时 PPE 监控 - stream_manager_v2")
        print("=" * 70)
        print(f"视频流: {self.stream_url}")
        print(f"运行时长: {'无限' if duration is None else f'{duration}秒'}")
        print(f"输出目录: {self.output_dir}")
        print("按键: q=退出, s=截图, p=暂停")
        print("=" * 70 + "\n")
        
        self.start_time = time.time()
        self.running = True
        
        # 创建显示窗口
        cv2.namedWindow("PPE Monitor", cv2.WINDOW_NORMAL)
        
        try:
            # 外层循环：支持重连
            while self.running:
                # 检查总运行时长
                elapsed = time.time() - self.start_time
                if duration and elapsed >= duration:
                    print(f"\n[INFO] 运行时长已达设定值 ({duration}秒)")
                    break
                
                # 启动或重启视频流连接
                remaining_duration = None if duration is None else (duration - elapsed)
                success = self._run_stream_loop(remaining_duration, save_violations)
                
                if not success:
                    break
                
                # 连接断开，尝试重连
                if self.running:
                    self.reconnect_count += 1
                    print(f"\n[RECONNECT] 第 {self.reconnect_count} 次重连...")
                    print("[RECONNECT] 3秒后继续...")
                    time.sleep(3)
                    
        except KeyboardInterrupt:
            print("\n[INFO] 用户中断")
        except Exception as e:
            print(f"\n[ERROR] 程序异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.running = False
            cv2.destroyAllWindows()
            self._print_summary()
            self._save_log()
            print("[OK] 程序结束")
    
    def _run_stream_loop(self, duration: int = None, save_violations: bool = True) -> bool:
        """运行单次流连接循环"""
        print(f"\n[STREAM] 正在连接视频流...")
        cap = cv2.VideoCapture(self.stream_url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        if not cap.isOpened():
            print("[ERROR] 无法打开视频流")
            return True
        
        print(f"[OK] 视频流已连接")
        if self.reconnect_count > 0:
            print(f"[STREAM] 重连后恢复运行，累计帧数: {self.frame_count}")
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[INFO] 流信息: {width}x{height} @ {fps:.1f}fps")
        
        loop_start_time = time.time()
        last_log_time = time.time()
        detections = []
        empty_count = 0
        max_empty = 30
        
        try:
            while self.running:
                loop_elapsed = time.time() - loop_start_time
                if duration and loop_elapsed >= duration:
                    print(f"\n[INFO] 单次连接运行时长已达设定值")
                    cap.release()
                    return False
                
                if time.time() - last_log_time > 30:
                    total_elapsed = time.time() - self.start_time
                    print(f"[STATUS] 总运行 {total_elapsed:.0f}s | "
                          f"本次连接 {loop_elapsed:.0f}s | "
                          f"帧: {self.frame_count} | "
                          f"人员: {self.detection_count} | "
                          f"违规: {self.violation_count} | "
                          f"重连: {self.reconnect_count}")
                    last_log_time = time.time()
                
                if self.paused:
                    time.sleep(0.1)
                    continue
                
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
                
                # 缩放帧
                if frame.shape[1] != 960 or frame.shape[0] != 540:
                    frame = cv2.resize(frame, (960, 540))
                
                self.frame_count += 1
                
                # 每3帧检测一次
                if self.frame_count % 3 == 0:
                    try:
                        detections = self.detector.detect(frame)
                    except Exception as e:
                        print(f"\n[ERROR] 检测异常: {e}")
                        detections = []
                    
                    # 检查违规
                    for det in detections:
                        if not (det.has_helmet and det.has_vest):
                            self.violation_count += 1
                            if save_violations and (time.time() - self.last_save_time) > 3:
                                self._save_violation(frame, det)
                                self.last_save_time = time.time()
                    
                    self.detection_count += len(detections)
                
                # 显示
                display_frame = frame.copy()
                if detections:
                    display_frame = self.detector.draw_results(display_frame, detections)
                self._draw_status(display_frame, detections)
                cv2.imshow("PPE Monitor", display_frame)
                
                # 键盘控制
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    print("\n[INFO] 用户退出")
                    self.running = False
                    cap.release()
                    return False
                elif key == ord('s'):
                    self._save_frame(frame, detections)
                elif key == ord('p'):
                    self.paused = not self.paused
                    print("[暂停]" if self.paused else "[继续]")
                    
        except Exception as e:
            print(f"\n[ERROR] 流循环异常: {e}")
            import traceback
            traceback.print_exc()
            cap.release()
            return True
        finally:
            if cap.isOpened():
                cap.release()
    
    def _draw_status(self, frame, detections):
        """绘制状态信息"""
        elapsed = time.time() - self.start_time
        fps = self.frame_count / elapsed if elapsed > 0 else 0
        
        compliant = sum(1 for d in detections if d.has_helmet and d.has_vest)
        total = len(detections)
        rate = (compliant / total * 100) if total > 0 else 100
        
        lines = [
            f"FPS: {fps:.1f}",
            f"Frames: {self.frame_count}",
            f"Persons: {total}",
            f"Compliant: {compliant}/{total} ({rate:.0f}%)",
            f"Violations: {self.violation_count}",
            f"Reconnects: {self.reconnect_count}"
        ]
        
        y = 30
        for line in lines:
            cv2.putText(frame, line, (10, y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            y += 25
    
    def _save_violation(self, frame, detection):
        """保存违规截图"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        violations = []
        if not detection.has_helmet:
            violations.append("NO_HELMET")
        if not detection.has_vest:
            violations.append("NO_VEST")
        desc = "_".join(violations) if violations else "VIOLATION"
        
        filename = f"violation_{timestamp}_ID{detection.track_id}_{desc}.jpg"
        filepath = self.output_dir / filename
        
        result = self.detector.draw_results(frame, [detection])
        cv2.imwrite(str(filepath), result)
        
        self.violation_log.append({
            "timestamp": timestamp,
            "track_id": detection.track_id,
            "violation_type": desc,
            "filepath": str(filepath)
        })
        
        print(f"[违规] ID{detection.track_id}: {desc}")
    
    def _save_frame(self, frame, detections):
        """保存当前帧"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"frame_{timestamp}.jpg"
        filepath = self.output_dir / filename
        
        result = self.detector.draw_results(frame, detections)
        cv2.imwrite(str(filepath), result)
        print(f"[截图] {filename}")
    
    def _print_summary(self):
        """打印统计摘要"""
        elapsed = time.time() - self.start_time
        print("\n" + "=" * 70)
        print("监控统计")
        print("=" * 70)
        print(f"运行时间: {elapsed:.1f} 秒")
        print(f"处理帧数: {self.frame_count}")
        print(f"平均 FPS: {self.frame_count/elapsed:.1f}" if elapsed > 0 else "N/A")
        print(f"检测到人员: {self.detection_count} 人次")
        print(f"违规次数: {self.violation_count}")
        print(f"重连次数: {self.reconnect_count}")
        print("=" * 70)
    
    def _save_log(self):
        """保存日志文件"""
        log_file = self.output_dir / "violation_log.json"
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump({
                "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
                "end_time": datetime.now().isoformat(),
                "total_frames": self.frame_count,
                "total_violations": self.violation_count,
                "reconnect_count": self.reconnect_count,
                "violations": self.violation_log
            }, f, ensure_ascii=False, indent=2)
        print(f"[日志] 已保存到: {log_file}")


def main():
    """主函数"""
    # RTMP 流地址
    stream_url = "rtmp://rtmp05open.ys7.com:1935/v3/openlive/G49745764_1_1?expire=1805439206&id=956566417183907840&t=c08663468482dadc8848af79d473a956f8d8aa105fca33609790d99a2816e19e&ev=101"
    
    monitor = StreamMonitor(
        stream_url=stream_url,
        output_dir="./output/monitor_test"
    )
    
    # 运行监控（60秒）
    monitor.run(duration=60, save_violations=True)


if __name__ == "__main__":
    main()
