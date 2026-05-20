#!/usr/bin/env python3
"""
萤石云视频流 PPE 检测测试 - 使用外部工具
由于 OpenCV 可能没有 FFmpeg 支持，使用 ffpyplayer 或 streamlink 作为备选方案
"""

import sys
import subprocess
import tempfile
import os
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "detectors"))


def check_ffmpeg():
    """检查系统是否安装了 FFmpeg"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except:
        return False


def download_frame_with_ffmpeg(stream_url: str, output_path: str, timeout: int = 30):
    """使用 FFmpeg 下载视频流的一帧"""
    cmd = [
        'ffmpeg',
        '-i', stream_url,
        '-ss', '00:00:01',  # 从1秒处开始
        '-vframes', '1',     # 只取1帧
        '-q:v', '2',         # 高质量
        '-y',                # 覆盖输出文件
        output_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0 and os.path.exists(output_path)
    except subprocess.TimeoutExpired:
        print("FFmpeg 超时")
        return False
    except Exception as e:
        print(f"FFmpeg 错误: {e}")
        return False


def test_with_ffmpeg():
    """使用 FFmpeg 测试视频流"""
    stream_url = "https://open.ys7.com/v3/openlive/J58749099_1_1.m3u8?expire=1805097058&id=955131347955273728&t=9142d9ce6a544a7c8569df965320fce7d2e78bba12f066d3ea7c176847107c3b&ev=101"
    
    print("=" * 70)
    print("萤石云视频流测试 (使用 FFmpeg)")
    print("=" * 70)
    
    # 检查 FFmpeg
    if not check_ffmpeg():
        print("[X] 未检测到 FFmpeg")
        print("请安装 FFmpeg: https://ffmpeg.org/download.html")
        return False
    
    print("[OK] FFmpeg 已安装")
    print(f"\n视频流地址: {stream_url[:60]}...")
    
    # 创建临时文件
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
        temp_path = tmp.name
    
    try:
        print("\n正在下载视频帧...")
        if download_frame_with_ffmpeg(stream_url, temp_path):
            print(f"[OK] 成功下载帧到: {temp_path}")
            
            # 使用 OpenCV 读取并显示
            import cv2
            frame = cv2.imread(temp_path)
            
            if frame is not None:
                print(f"[OK] 帧尺寸: {frame.shape[1]}x{frame.shape[0]}")
                
                # 显示
                cv2.imshow("YS7 Stream Frame", frame)
                print("\n按任意键关闭窗口")
                cv2.waitKey(0)
                cv2.destroyAllWindows()
                
                # 进行 PPE 检测
                print("\n是否进行 PPE 检测? (y/n): ", end="")
                try:
                    response = input().strip().lower()
                    if response == 'y':
                        run_ppe_detection(frame)
                except EOFError:
                    pass
                
                return True
            else:
                print("[X] 无法读取下载的帧")
                return False
        else:
            print("[X] 下载失败")
            print("可能原因:")
            print("  - 流地址已过期")
            print("  - 网络连接问题")
            print("  - 需要身份验证")
            return False
            
    finally:
        # 清理临时文件
        if os.path.exists(temp_path):
            os.remove(temp_path)


def run_ppe_detection(frame):
    """运行 PPE 检测"""
    print("\n" + "=" * 70)
    print("PPE 检测")
    print("=" * 70)
    
    from detectors.ppe_detector import PPEDetector
    import cv2
    
    print("正在初始化 PPE 检测器...")
    detector = PPEDetector(conf_threshold=0.4)
    print("✓ 检测器初始化完成")
    
    print("\n正在检测...")
    detections = detector.detect(frame)
    
    print(f"✓ 检测到 {len(detections)} 个人员")
    
    for i, det in enumerate(detections):
        print(f"\n  人员 {i+1} (ID: {det.track_id}):")
        print(f"    - 置信度: {det.confidence:.2f}")
        print(f"    - 安全帽: {'✓ 已戴' if det.has_helmet else '✗ 未戴'}")
        print(f"    - 反光衣: {'✓ 已穿' if det.has_vest else '✗ 未穿'}")
        print(f"    - 口罩: {'✓ 已戴' if det.has_mask else '✗ 未戴'}")
        print(f"    - 合规: {'✓' if det.is_compliant else '✗ 违规'}")
        if det.violation_type:
            print(f"    - 违规类型: {det.violation_type}")
    
    # 绘制结果
    result = detector.draw_results(frame, detections)
    
    # 保存结果
    output_path = "ys7_ppe_detection.jpg"
    cv2.imwrite(output_path, result)
    print(f"\n✓ 检测结果已保存: {output_path}")
    
    # 显示
    cv2.imshow("PPE Detection Result", result)
    print("按任意键关闭")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def test_stream_info():
    """使用 FFmpeg 获取视频流信息"""
    stream_url = "https://open.ys7.com/v3/openlive/J58749099_1_1.m3u8?expire=1805097058&id=955131347955273728&t=9142d9ce6a544a7c8569df965320fce7d2e78bba12f066d3ea7c176847107c3b&ev=101"
    
    print("=" * 70)
    print("获取视频流信息")
    print("=" * 70)
    
    if not check_ffmpeg():
        print("[X] 未检测到 FFmpeg")
        return
    
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 
           'format=duration', '-show_entries', 
           'stream=width,height,codec_name', 
           '-of', 'default=noprint_wrappers=1', stream_url]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        print("视频流信息:")
        print(result.stdout)
        if result.stderr:
            print("错误信息:", result.stderr)
    except Exception as e:
        print(f"获取信息失败: {e}")


def alternative_solution():
    """提供替代解决方案"""
    print("=" * 70)
    print("替代解决方案")
    print("=" * 70)
    print("""
由于您的 OpenCV 没有 FFmpeg 支持，无法直接播放 HLS 流。

解决方案:

1. **安装带 FFmpeg 的 OpenCV** (推荐)
   pip uninstall opencv-python
   pip install opencv-python-headless
   
   或者从源码编译:
   https://github.com/opencv/opencv-python#manual-builds

2. **使用 FFmpeg 实时转码**
   将 HLS 流转换为本地 RTMP/RTSP 流，然后用 OpenCV 读取
   
   ffmpeg -i "YOUR_HLS_URL" -f rtsp rtsp://localhost:8554/live

3. **使用 Python 的流媒体库**
   - streamlink: pip install streamlink
   - livestreamer: pip install livestreamer
   
   示例:
   streamlink "YOUR_HLS_URL" best -O | python your_script.py

4. **使用萤石云 SDK**
   萤石云提供官方 Python SDK，可以直接获取视频帧
   https://open.ys7.com/doc/zh/book/index.html

5. **下载视频文件后处理**
   先用 FFmpeg 下载一段视频，然后用 OpenCV 处理文件
   
   ffmpeg -i "YOUR_HLS_URL" -t 60 -c copy output.mp4
""")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='萤石云视频流测试工具')
    parser.add_argument('--info', '-i', action='store_true',
                       help='获取视频流信息')
    parser.add_argument('--alternative', '-a', action='store_true',
                       help='显示替代解决方案')
    args = parser.parse_args()
    
    if args.info:
        test_stream_info()
    elif args.alternative:
        alternative_solution()
    else:
        # 主测试
        success = test_with_ffmpeg()
        
        if not success:
            print("\n")
            alternative_solution()
