#!/usr/bin/env python3
"""
萤石云视频流实时 PPE 检测
使用 FFmpeg 持续拉流并进行 AI 检测
"""

import subprocess
import sys
import threading
import queue
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "detectors"))

import cv2
import numpy as np
from detectors.ppe_detector import PPEDetector


class FFmpegFrameReader:
    """使用 FFmpeg 读取视频流帧"""
    
    def __init__(self, stream_url: str, width: int = 512, height: int = 288):
        self.stream_url = stream_url
        self.width = width
        self.height = height
        self.frame_queue = queue.Queue(maxsize=5)
        self.running = False
        self.thread = None
        
    def start(self):
        """启动 FFmpeg 读取线程"""
        self.running = True
        self.thread = threading.Thread(target=self._read_frames)
        self.thread.start()
        
    def stop(self):
        """停止读取"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
            
    def _read_frames(self):
        """后台线程读取帧"""
        # FFmpeg 命令：输出原始 RGB 帧
        cmd = [
            'ffmpeg',
            '-i', self.stream_url,
            '-vf', f'scale={self.width}:{self.height}',
            '-pix_fmt', 'bgr24',
            '-f', 'rawvideo',
            '-an',  # 禁用音频
            '-'     # 输出到 stdout
        ]
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=10**8
            )
            
            frame_size = self.width * self.height * 3
            
            while self.running:
                raw_frame = process.stdout.read(frame_size)
                
                if len(raw_frame) != frame_size:
                    print("[FFmpeg] 读取帧失败，可能流已断开")
                    break
                
                # 转换为 numpy 数组
                frame = np.frombuffer(raw_frame, dtype=np.uint8)
                frame = frame.reshape((self.height, self.width, 3))
                
                # 放入队列（如果队列满则丢弃旧帧）
                try:
                    self.frame_queue.put(frame, block=False)
                except queue.Full:
                    try:
                        self.frame_queue.get_nowait()
                        self.frame_queue.put(frame, block=False)
                    except:
                        pass
                        
        except Exception as e:
            print(f"[FFmpeg] 错误: {e}")
        finally:
            if 'process' in locals():
                process.terminate()
                
    def get_frame(self, timeout: float = 1.0):
        """获取一帧"""
        try:
            return self.frame_queue.get(timeout=timeout)
        except queue.Empty:
            return None


def main():
    stream_url = "https://open.ys7.com/v3/openlive/J58749099_1_1.m3u8?expire=1805097058&id=955131347955273728&t=9142d9ce6a544a7c8569df965320fce7d2e78bba12f066d3ea7c176847107c3b&ev=101"
    
    print("=" * 70)
    print("萤石云视频流实时 PPE 检测")
    print("=" * 70)
    print(f"流地址: {stream_url[:60]}...")
    print()
    
    # 初始化 PPE 检测器
    print("正在初始化 PPE 检测器...")
    try:
        detector = PPEDetector(conf_threshold=0.3)  # 降低阈值以适应低分辨率
        print("[OK] 检测器初始化成功")
    except Exception as e:
        print(f"[X] 初始化失败: {e}")
        return
    
    # 启动 FFmpeg 读取器
    print("\n正在启动 FFmpeg 视频流读取...")
    reader = FFmpegFrameReader(stream_url, width=512, height=288)
    reader.start()
    
    # 等待 FFmpeg 启动
    print("等待视频流...")
    time.sleep(3)
    
    # 检查是否成功获取帧
    test_frame = reader.get_frame(timeout=5)
    if test_frame is None:
        print("[X] 无法获取视频帧")
        reader.stop()
        return
    
    print(f"[OK] 视频流已连接")
    print(f"  分辨率: {test_frame.shape[1]}x{test_frame.shape[0]}")
    
    # 统计信息
    frame_count = 0
    detection_count = 0
    violation_count = 0
    start_time = time.time()
    
    # 跳帧检测（每3帧检测一次）
    detect_every_n = 3
    last_detections = []
    
    print("\n" + "=" * 70)
    print("实时检测已启动")
    print("=" * 70)
    print("按键说明:")
    print("  q - 退出")
    print("  s - 保存截图")
    print("  +/- - 调整检测阈值")
    print("=" * 70 + "\n")
    
    try:
        while True:
            # 获取帧
            frame = reader.get_frame(timeout=1.0)
            
            if frame is None:
                print("[警告] 获取帧超时")
                continue
            
            frame_count += 1
            
            # 每 N 帧检测一次
            if frame_count % detect_every_n == 0:
                detections = detector.detect(frame)
                last_detections = detections
                detection_count += len(detections)
                
                # 统计违规
                for det in detections:
                    if not det.is_compliant:
                        violation_count += 1
            
            # 绘制结果
            result = detector.draw_results(frame, last_detections)
            
            # 添加 FPS 信息
            elapsed = time.time() - start_time
            current_fps = frame_count / elapsed if elapsed > 0 else 0
            
            info_lines = [
                f"FPS: {current_fps:.1f}",
                f"Frames: {frame_count}",
                f"Persons: {len(last_detections)}",
                f"Threshold: {detector.conf_threshold:.2f}"
            ]
            
            y_offset = 30
            for line in info_lines:
                cv2.putText(result, line, (10, y_offset),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                y_offset += 20
            
            # 显示
            cv2.imshow("PPE Detection - Live Stream", result)
            
            # 键盘控制
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                filename = f"ys7_live_{frame_count}.jpg"
                cv2.imwrite(filename, result)
                print(f"[OK] 截图已保存: {filename}")
            elif key == ord('+') or key == ord('='):
                detector.conf_threshold = min(1.0, detector.conf_threshold + 0.05)
                print(f"阈值调整为: {detector.conf_threshold:.2f}")
            elif key == ord('-'):
                detector.conf_threshold = max(0.1, detector.conf_threshold - 0.05)
                print(f"阈值调整为: {detector.conf_threshold:.2f}")
                
    except KeyboardInterrupt:
        print("\n用户中断")
    finally:
        reader.stop()
        cv2.destroyAllWindows()
        
        # 打印统计
        elapsed = time.time() - start_time
        print("\n" + "=" * 70)
        print("检测统计")
        print("=" * 70)
        print(f"运行时间: {elapsed:.1f} 秒")
        print(f"处理帧数: {frame_count}")
        print(f"平均 FPS: {frame_count/elapsed:.1f}" if elapsed > 0 else "N/A")
        print(f"检测到人员: {detection_count} 人次")
        print(f"违规次数: {violation_count}")
        print("=" * 70)


if __name__ == "__main__":
    main()
