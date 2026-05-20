#!/usr/bin/env python3
"""
PPE 实时监控 - 后台无窗口版本
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


def main():
    stream_url = "rtmp://rtmp05open.ys7.com:1935/v3/openlive/G49745764_1_1?expire=1805439206&id=956566417183907840&t=c08663468482dadc8848af79d473a956f8d8aa105fca33609790d99a2816e19e&ev=101"
    output_dir = Path("./ppe_monitor_output_test")
    output_dir.mkdir(exist_ok=True)
    
    print("=" * 70)
    print("PPE 实时监控系统启动")
    print("=" * 70)
    print(f"视频流: {stream_url}")
    print(f"输出目录: {output_dir}")
    print(f"运行时长: 300秒 (5分钟)")
    print("=" * 70)
    
    # 初始化检测器
    print("\n[1/3] 初始化检测器...")
    detector = PPEDetector(conf_threshold=0.45, iou_threshold=0.4)
    print("[OK] 检测器就绪")
    
    # FFmpeg 命令
    cmd = [
        'ffmpeg',
        '-i', stream_url,
        '-vf', 'scale=960:540',
        '-pix_fmt', 'bgr24',
        '-f', 'rawvideo',
        '-an',
        '-'
    ]
    
    print("[2/3] 启动视频流...")
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=10**8
    )
    
    width, height = 960, 540
    frame_size = width * height * 3
    
    # 统计
    frame_count = 0
    detection_count = 0
    violation_count = 0
    violation_log = []
    detections = []
    last_violation_time = 0
    
    start_time = time.time()
    duration = 300  # 5分钟
    
    print("[3/3] 开始监控...\n")
    
    try:
        while True:
            if (time.time() - start_time) > duration:
                print("\n[OK] 运行时长已达设定值 (5分钟)")
                break
            
            # 读取帧
            raw_frame = process.stdout.read(frame_size)
            
            if len(raw_frame) != frame_size:
                print("\n[X] 视频流断开")
                break
            
            # 转换
            frame = np.frombuffer(raw_frame, dtype=np.uint8)
            frame = frame.reshape((height, width, 3))
            
            frame_count += 1
            
            # 每3帧检测一次
            if frame_count % 3 == 0:
                detections = detector.detect(frame)
                
                # 检查违规
                for det in detections:
                    is_compliant = det.has_helmet and det.has_vest
                    
                    if not is_compliant:
                        violation_count += 1
                        
                        # 限制保存频率 (每5秒保存一次)
                        current_time = time.time()
                        if (current_time - last_violation_time) > 5:
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            violations = []
                            if not det.has_helmet:
                                violations.append("NO_HELMET")
                            if not det.has_vest:
                                violations.append("NO_VEST")
                            violation_desc = "_".join(violations) if violations else "VIOLATION"
                            
                            filename = f"violation_{timestamp}_ID{det.track_id}_{violation_desc}.jpg"
                            filepath = output_dir / filename
                            
                            result = detector.draw_results(frame, [det])
                            cv2.imwrite(str(filepath), result)
                            
                            violation_log.append({
                                "timestamp": timestamp,
                                "track_id": det.track_id,
                                "violation_type": violation_desc
                            })
                            
                            print(f"[违规] ID{det.track_id}: {violation_desc} -> {filename}")
                            last_violation_time = current_time
                
                detection_count += len(detections)
            
            # 每100帧打印状态
            if frame_count % 100 == 0:
                elapsed = time.time() - start_time
                fps = frame_count / elapsed
                remaining = duration - elapsed
                print(f"[状态] 帧数: {frame_count} | FPS: {fps:.1f} | 人员: {len(detections)} | 剩余: {remaining:.0f}s")
                
    except KeyboardInterrupt:
        print("\n用户中断")
    finally:
        process.terminate()
        
        # 保存日志
        log_file = output_dir / "violation_log.json"
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump({
                "start_time": datetime.fromtimestamp(start_time).isoformat(),
                "end_time": datetime.now().isoformat(),
                "total_frames": frame_count,
                "total_detections": detection_count,
                "total_violations": violation_count,
                "violations": violation_log
            }, f, ensure_ascii=False, indent=2)
        
        # 打印摘要
        elapsed = time.time() - start_time
        print("\n" + "=" * 70)
        print("监控统计")
        print("=" * 70)
        print(f"运行时间: {elapsed:.1f} 秒")
        print(f"处理帧数: {frame_count}")
        print(f"平均 FPS: {frame_count/elapsed:.1f}" if elapsed > 0 else "N/A")
        print(f"检测到人员: {detection_count} 人次")
        print(f"违规次数: {violation_count}")
        print(f"违规截图: {len(violation_log)} 张")
        print(f"输出目录: {output_dir}")
        print("=" * 70)


if __name__ == "__main__":
    main()
