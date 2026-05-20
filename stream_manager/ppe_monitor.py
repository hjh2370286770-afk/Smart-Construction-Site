#!/usr/bin/env python3
"""
萤石云 RTMP 视频流实时 PPE 检测监控
持续监控并记录违规事件
"""

import sys
import subprocess
import numpy as np
import time
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "detectors"))

import cv2
from detectors.ppe_detector import PPEDetector


class PPEMonitor:
    """PPE 实时监控系统"""
    
    def __init__(self, stream_url: str, output_dir: str = "./monitor_output"):
        self.stream_url = stream_url
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # 初始化检测器
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
        
    def run(self, duration: int = None, save_violations: bool = True):
        """运行监控"""
        print("\n" + "=" * 70)
        print("启动实时 PPE 监控")
        print("=" * 70)
        print(f"视频流: {self.stream_url}")
        print(f"运行时长: {'无限' if duration is None else f'{duration}秒'}")
        print("按键: q=退出, s=截图, p=暂停")
        print("=" * 70 + "\n")
        
        # FFmpeg 命令
        cmd = [
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'error',
            '-i', self.stream_url,
            '-vf', 'scale=960:540',
            '-pix_fmt', 'bgr24',
            '-f', 'rawvideo',
            '-an',
            '-'
        ]
        
        # 启动 FFmpeg
        stderr_file = open(self.output_dir / "ffmpeg.log", "w")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            bufsize=10**8
        )
        print(f"[OK] FFmpeg PID: {process.pid}")
        
        width, height = 960, 540
        frame_size = width * height * 3
        
        self.start_time = time.time()
        paused = False
        last_save_time = 0
        detections = []
        
        cv2.namedWindow("PPE Monitor", cv2.WINDOW_NORMAL)
        
        try:
            empty_count = 0
            last_log_time = time.time()
            
            while True:
                # 检查运行时长
                elapsed = time.time() - self.start_time
                if duration and elapsed > duration:
                    print(f"\n[INFO] 运行时长已达设定值 ({duration}秒)")
                    break
                
                # 每30秒打印状态
                if time.time() - last_log_time > 30:
                    print(f"[STATUS] 运行 {elapsed:.0f}s | 帧: {self.frame_count} | 人员: {self.detection_count} | 违规: {self.violation_count}")
                    last_log_time = time.time()
                
                if not paused:
                    # 读取帧
                    raw_frame = process.stdout.read(frame_size)
                    
                    if len(raw_frame) != frame_size:
                        empty_count += 1
                        if empty_count > 30:
                            print(f"\n[ERROR] 视频流断开 - 连续 {empty_count} 次读取失败")
                            ret = process.poll()
                            if ret is not None:
                                print(f"[ERROR] FFmpeg 已退出，返回码: {ret}")
                                stderr_file.flush()
                                with open(self.output_dir / "ffmpeg.log", "r") as f:
                                    log = f.read()
                                    if log:
                                        print(f"[ERROR] FFmpeg日志: {log[-300:]}")
                            break
                        continue
                    else:
                        empty_count = 0
                    
                    # 处理帧
                    frame = np.frombuffer(raw_frame, dtype=np.uint8)
                    frame = frame.reshape((height, width, 3))
                    
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
                                if save_violations and (time.time() - last_save_time) > 3:
                                    self._save_violation(frame, det)
                                    last_save_time = time.time()
                        
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
                    break
                elif key == ord('s'):
                    self._save_frame(frame, detections)
                elif key == ord('p'):
                    paused = not paused
                    print("[暂停]" if paused else "[继续]")
                    
        except KeyboardInterrupt:
            print("\n[INFO] 用户中断")
        except Exception as e:
            print(f"\n[ERROR] 程序异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print("\n[INFO] 正在清理资源...")
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except:
                    process.kill()
            stderr_file.close()
            cv2.destroyAllWindows()
            self._print_summary()
            self._save_log()
            print("[OK] 程序结束")
    
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
            f"Violations: {self.violation_count}"
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
                "violations": self.violation_log
            }, f, ensure_ascii=False, indent=2)


def main():
    # RTMP 流地址
    stream_url = "rtmp://rtmp05open.ys7.com:1935/v3/openlive/G49745764_1_1?expire=1805439206&id=956566417183907840&t=c08663468482dadc8848af79d473a956f8d8aa105fca33609790d99a2816e19e&ev=101"
    
    monitor = PPEMonitor(
        stream_url=stream_url,
        output_dir="./ppe_monitor_output_v2"
    )
    
    monitor.run(duration=360, save_violations=True)


if __name__ == "__main__":
    main()
