#!/usr/bin/env python3
"""
萤石云 RTMP 视频流 PPE 检测测试
使用新的 RTMP 地址
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


def download_frame_ffmpeg(stream_url: str, output_path: str, timeout: int = 30):
    """使用 FFmpeg 下载一帧"""
    cmd = [
        'ffmpeg',
        '-i', stream_url,
        '-ss', '00:00:02',  # 从2秒处开始
        '-vframes', '1',     # 只取1帧
        '-q:v', '2',         # 高质量
        '-y',                # 覆盖
        output_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return result.returncode == 0 and os.path.exists(output_path)
    except Exception as e:
        print(f"[X] FFmpeg 错误: {e}")
        return False


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
    cv2.imwrite("rtmp_original.jpg", frame)
    print("[OK] 原图已保存: rtmp_original.jpg")
    
    # 初始化检测器
    print("\n[3/3] PPE 检测...")
    detector = PPEDetector(conf_threshold=0.3)  # 降低阈值
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
    cv2.imwrite("rtmp_ppe_result.jpg", result)
    print("\n[OK] 结果已保存: rtmp_ppe_result.jpg")
    
    # 显示
    cv2.imshow("PPE Detection Result", result)
    print("按任意键关闭")
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    
    return True


def test_live_stream(stream_url: str):
    """实时视频流测试"""
    print("\n" + "=" * 70)
    print("实时视频流 PPE 检测")
    print("=" * 70)
    
    # FFmpeg 命令：输出原始视频帧
    cmd = [
        'ffmpeg',
        '-i', stream_url,
        '-vf', 'scale=640:360',  # 缩放以提高处理速度
        '-pix_fmt', 'bgr24',
        '-f', 'rawvideo',
        '-an',
        '-'  # 输出到 stdout
    ]
    
    print("正在启动 FFmpeg...")
    print("按 'q' 退出\n")
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10**8
        )
        
        # 初始化检测器
        detector = PPEDetector(conf_threshold=0.3)
        
        width, height = 640, 360
        frame_size = width * height * 3
        
        frame_count = 0
        detections = []
        
        while True:
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
            
            # 绘制结果
            result = detector.draw_results(frame, detections)
            
            # 添加信息
            cv2.putText(result, f"Frame: {frame_count}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(result, f"Persons: {len(detections)}", (10, 55),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            # 显示
            cv2.imshow("Live PPE Detection", result)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        process.terminate()
        cv2.destroyAllWindows()
        
        print(f"\n共处理 {frame_count} 帧")
        return True
        
    except KeyboardInterrupt:
        print("\n用户中断")
        process.terminate()
        cv2.destroyAllWindows()
        return True
    except Exception as e:
        print(f"\n错误: {e}")
        return False


def main():
    # 新的 RTMP 流地址
    stream_url = "rtmp://rtmp05open.ys7.com:1935/v3/openlive/J58749099_1_1?expire=1805097951&id=955135090313248768&t=d529221810a3105929e812cdfa56c50e118ea70e0e72d019c4c679a6adef0723&ev=101"
    
    print("=" * 70)
    print("萤石云 RTMP 视频流 PPE 检测测试")
    print("=" * 70)
    print(f"流地址: {stream_url}")
    
    # 检查流信息
    check_stream_info(stream_url)
    
    # 测试单帧
    if test_single_frame(stream_url):
        # 询问是否测试实时流
        print("\n是否测试实时视频流? (y/n): ", end="")
        try:
            response = input().strip().lower()
            if response == 'y':
                test_live_stream(stream_url)
        except EOFError:
            pass
    
    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
