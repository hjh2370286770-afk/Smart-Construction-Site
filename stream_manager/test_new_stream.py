#!/usr/bin/env python3
"""
萤石云 RTMP 视频流 PPE 检测测试 - 新流地址
使用流: rtmp://rtmp05open.ys7.com:1935/v3/openlive/G49745764_1_1
"""

import sys
import subprocess
import tempfile
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "detectors"))

import cv2
import numpy as np
from detectors.ppe_detector import PPEDetector


# 新的 RTMP 流地址
STREAM_URL = "rtmp://rtmp05open.ys7.com:1935/v3/openlive/G49745764_1_1?expire=1805439206&id=956566417183907840&t=c08663468482dadc8848af79d473a956f8d8aa105fca33609790d99a2816e19e&ev=101"


def check_stream_info(stream_url: str):
    """检查视频流信息"""
    print("\n" + "=" * 70)
    print("检查视频流信息")
    print("=" * 70)
    
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'stream=codec_name,width,height,avg_frame_rate',
        '-of', 'default=noprint_wrappers=1',
        stream_url
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            print("[OK] 视频流信息:")
            print(result.stdout)
            return True
        else:
            print("[X] 无法获取流信息")
            print("错误:", result.stderr[:500])
            return False
    except Exception as e:
        print(f"[X] 错误: {e}")
        return False


def download_frame_ffmpeg(stream_url: str, output_path: str, timeout: int = 30):
    """使用 FFmpeg 下载一帧"""
    cmd = [
        'ffmpeg',
        '-i', stream_url,
        '-ss', '00:00:02',
        '-vframes', '1',
        '-q:v', '2',
        '-y',
        output_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return result.returncode == 0 and os.path.exists(output_path)
    except Exception as e:
        print(f"[X] FFmpeg 错误: {e}")
        return False


def test_single_frame(stream_url: str):
    """测试单帧 PPE 检测"""
    print("\n" + "=" * 70)
    print("单帧 PPE 检测测试")
    print("=" * 70)
    
    # 下载一帧
    print("\n[1/3] 下载视频帧...")
    temp_path = tempfile.mktemp(suffix='.jpg')
    
    if not download_frame_ffmpeg(stream_url, temp_path):
        print("[X] 下载失败")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return False
    
    print("[OK] 帧下载成功")
    
    # 加载图像
    print("\n[2/3] 加载图像...")
    frame = cv2.imread(temp_path)
    os.remove(temp_path)
    
    if frame is None:
        print("[X] 无法加载图像")
        return False
    
    print(f"[OK] 图像尺寸: {frame.shape[1]}x{frame.shape[0]}")
    
    # 保存原图
    output_original = "test_g49745764_original.jpg"
    cv2.imwrite(output_original, frame)
    print(f"[OK] 原图已保存: {output_original}")
    
    # 初始化检测器
    print("\n[3/3] PPE 检测...")
    detector = PPEDetector(conf_threshold=0.3)
    detections = detector.detect(frame)
    
    print(f"[OK] 检测到 {len(detections)} 个人员")
    
    # 打印详情
    for i, det in enumerate(detections):
        print(f"\n  人员 {i+1} (ID: {det.track_id}):")
        print(f"    安全帽: {'[OK] 已戴' if det.has_helmet else '[X] 未戴'}")
        print(f"    反光衣: {'[OK] 已穿' if det.has_vest else '[X] 未穿'}")
        print(f"    口罩: {'[OK] 已戴' if det.has_mask else '[X] 未戴'}")
        print(f"    合规: {'[OK] 是' if det.is_compliant else '[X] 否'}")
    
    # 绘制结果
    result = detector.draw_results(frame, detections)
    output_result = "test_g49745764_ppe_result.jpg"
    cv2.imwrite(output_result, result)
    print(f"\n[OK] 结果已保存: {output_result}")
    
    # 显示
    cv2.imshow("PPE Detection Result", result)
    print("按任意键继续...")
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    
    return True


def test_live_stream(stream_url: str, duration: int = 60):
    """实时视频流测试"""
    print("\n" + "=" * 70)
    print("实时视频流 PPE 检测")
    print("=" * 70)
    
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
    
    print("正在启动 FFmpeg...")
    print("按 'q' 退出\n")
    
    process = None
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10**8
        )
        
        # 初始化检测器
        detector = PPEDetector(conf_threshold=0.3)
        
        width, height = 960, 540
        frame_size = width * height * 3
        
        frame_count = 0
        detection_count = 0
        violation_count = 0
        detections = []
        
        import time
        start_time = time.time()
        
        while True:
            # 检查运行时长
            if duration and (time.time() - start_time) > duration:
                print(f"\n[OK] 已达到设定时长 {duration} 秒")
                break
            
            # 读取一帧
            raw_frame = process.stdout.read(frame_size)
            
            if len(raw_frame) != frame_size:
                print("[X] 流已断开")
                break
            
            # 转换为 numpy
            frame = np.frombuffer(raw_frame, dtype=np.uint8)
            frame = frame.reshape((height, width, 3))
            
            frame_count += 1
            
            # 每3帧检测一次
            if frame_count % 3 == 0:
                detections = detector.detect(frame)
                detection_count += len(detections)
                
                # 统计违规
                for det in detections:
                    if not det.is_compliant:
                        violation_count += 1
            
            # 绘制结果
            result = detector.draw_results(frame, detections)
            
            # 添加信息
            elapsed = time.time() - start_time
            fps = frame_count / elapsed if elapsed > 0 else 0
            
            info_lines = [
                f"FPS: {fps:.1f}",
                f"Frame: {frame_count}",
                f"Persons: {len(detections)}",
                f"Violations: {violation_count}"
            ]
            
            y_offset = 30
            for line in info_lines:
                cv2.putText(result, line, (10, y_offset),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                y_offset += 25
            
            # 显示
            cv2.imshow("Live PPE Detection - G49745764", result)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        # 打印统计
        elapsed = time.time() - start_time
        print("\n" + "=" * 70)
        print("监控统计")
        print("=" * 70)
        print(f"运行时间: {elapsed:.1f} 秒")
        print(f"处理帧数: {frame_count}")
        print(f"平均 FPS: {frame_count/elapsed:.1f}" if elapsed > 0 else "N/A")
        print(f"检测到人员: {detection_count} 人次")
        print(f"违规次数: {violation_count}")
        print("=" * 70)
        
        return True
        
    except KeyboardInterrupt:
        print("\n用户中断")
        return True
    except Exception as e:
        print(f"\n错误: {e}")
        return False
    finally:
        if process:
            process.terminate()
        cv2.destroyAllWindows()


def main():
    print("=" * 70)
    print("萤石云 RTMP 视频流 PPE 检测测试")
    print("=" * 70)
    print(f"流地址: {STREAM_URL}")
    
    # 检查流信息
    check_stream_info(STREAM_URL)
    
    # 测试单帧
    if test_single_frame(STREAM_URL):
        # 询问是否测试实时流
        print("\n" + "=" * 70)
        print("是否测试实时视频流?")
        print("  y - 测试60秒")
        print("  n - 跳过")
        print("=" * 70)
        print("选择 (y/n): ", end="")
        
        try:
            response = input().strip().lower()
            if response == 'y':
                test_live_stream(STREAM_URL, duration=60)
        except EOFError:
            pass
    
    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
