#!/usr/bin/env python3
"""
萤石云视频流诊断工具
帮助诊断和解决视频流连接问题
"""

import subprocess
import sys
import tempfile
import os


def check_stream_with_ffprobe(stream_url: str):
    """使用 ffprobe 检查视频流信息"""
    print("\n" + "=" * 70)
    print("检查视频流信息")
    print("=" * 70)
    
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-show_format',
        '-show_streams',
        '-print_format', 'json',
        stream_url
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        
        if result.returncode != 0:
            print("[X] 无法获取流信息")
            print("错误输出:")
            print(result.stderr[:1000])
            return False
        
        print("[OK] 成功获取流信息")
        print("\n流信息 (JSON):")
        print(result.stdout[:2000])  # 只显示前2000字符
        return True
        
    except subprocess.TimeoutExpired:
        print("[X] 检查超时")
        return False
    except Exception as e:
        print(f"[X] 错误: {e}")
        return False


def download_and_analyze(stream_url: str):
    """下载并分析视频帧"""
    print("\n" + "=" * 70)
    print("下载并分析视频帧")
    print("=" * 70)
    
    temp_path = tempfile.mktemp(suffix='.jpg')
    
    # 尝试下载
    cmd = [
        'ffmpeg',
        '-i', stream_url,
        '-ss', '00:00:03',  # 等待3秒后截取
        '-vframes', '1',
        '-q:v', '2',
        '-y',
        temp_path
    ]
    
    try:
        print("正在下载视频帧 (可能需要几秒钟)...")
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        
        if result.returncode != 0:
            print("[X] 下载失败")
            print("\nFFmpeg 错误信息:")
            print(result.stderr.decode('utf-8', errors='ignore')[:1500])
            return False
        
        if not os.path.exists(temp_path):
            print("[X] 文件未生成")
            return False
        
        # 分析图片
        file_size = os.path.getsize(temp_path)
        print(f"[OK] 帧下载成功")
        print(f"  文件大小: {file_size} bytes")
        
        # 尝试用 OpenCV 读取
        try:
            import cv2
            frame = cv2.imread(temp_path)
            
            if frame is None:
                print("  [X] OpenCV 无法读取图像")
                return False
            
            height, width = frame.shape[:2]
            print(f"  图像尺寸: {width}x{height}")
            
            # 保存供用户查看
            output_path = "ys7_diagnostic_frame.jpg"
            cv2.imwrite(output_path, frame)
            print(f"  [OK] 图像已保存: {output_path}")
            
            # 检查是否是错误提示图片
            # 错误提示图片通常有特定的文字或尺寸
            if width < 100 or height < 100:
                print("\n  [!] 警告: 图像尺寸异常小，可能是错误提示")
            
            # 显示图像（如果可能）
            cv2.imshow("Diagnostic Frame", frame)
            print("\n  按任意键关闭图像窗口")
            cv2.waitKey(0)
            cv2.destroyAllWindows()
            
            return True
            
        except Exception as e:
            print(f"  [X] 分析图像时出错: {e}")
            return False
            
    except subprocess.TimeoutExpired:
        print("[X] 下载超时")
        return False
    except Exception as e:
        print(f"[X] 错误: {e}")
        return False
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def provide_solutions():
    """提供解决方案"""
    print("\n" + "=" * 70)
    print("可能的解决方案")
    print("=" * 70)
    print("""
根据诊断结果，视频流可能存在以下问题:

1. **视频编码问题** (最常见)
   错误: "视频编码类型非H264"
   解决: 
   - 登录萤石云控制台
   - 找到设备 J58749099
   - 修改视频编码为 H264
   - 路径: 设备管理 -> 视频参数 -> 编码格式 -> H264

2. **流地址过期**
   萤石云临时流地址有过期时间
   解决:
   - 重新获取新的流地址
   - 或使用永久流地址格式

3. **设备离线**
   设备可能不在线
   解决:
   - 检查设备电源和网络
   - 在萤石云APP确认设备在线状态

4. **权限问题**
   当前账号可能没有权限访问该设备
   解决:
   - 确认设备已添加到当前账号
   - 检查设备共享权限

5. **网络问题**
   无法连接到萤石云服务器
   解决:
   - 检查网络连接
   - 确认可以访问 open.ys7.com
""")


def test_with_opencv_directly(stream_url: str):
    """直接使用 OpenCV 测试（如果支持 FFmpeg）"""
    print("\n" + "=" * 70)
    print("尝试用 OpenCV 直接读取")
    print("=" * 70)
    
    try:
        import cv2
        
        print("检查 OpenCV FFmpeg 支持...")
        # 检查是否支持 FFmpeg
        info = cv2.getBuildInformation()
        if "FFmpeg" in info:
            print("[OK] OpenCV 支持 FFmpeg")
        else:
            print("[X] OpenCV 不支持 FFmpeg")
            print("无法直接用 OpenCV 读取 HLS 流")
            return False
        
        print("\n尝试打开视频流...")
        cap = cv2.VideoCapture(stream_url)
        
        if not cap.isOpened():
            print("[X] 无法打开视频流")
            return False
        
        print("[OK] 视频流已打开")
        
        # 读取一帧
        ret, frame = cap.read()
        
        if not ret:
            print("[X] 无法读取帧")
            cap.release()
            return False
        
        print("[OK] 成功读取帧")
        print(f"  尺寸: {frame.shape[1]}x{frame.shape[0]}")
        
        # 保存并显示
        cv2.imwrite("ys7_opencv_frame.jpg", frame)
        print("[OK] 帧已保存: ys7_opencv_frame.jpg")
        
        cv2.imshow("OpenCV Frame", frame)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
        
        cap.release()
        return True
        
    except Exception as e:
        print(f"[X] 错误: {e}")
        return False


def main():
    stream_url = "https://open.ys7.com/v3/openlive/J58749099_1_1.m3u8?expire=1805097058&id=955131347955273728&t=9142d9ce6a544a7c8569df965320fce7d2e78bba12f066d3ea7c176847107c3b&ev=101"
    
    print("=" * 70)
    print("萤石云视频流诊断工具")
    print("=" * 70)
    print(f"流地址: {stream_url[:70]}...")
    
    # 1. 检查流信息
    check_stream_with_ffprobe(stream_url)
    
    # 2. 下载并分析帧
    success = download_and_analyze(stream_url)
    
    # 3. 如果失败，提供解决方案
    if not success:
        provide_solutions()
        return
    
    # 4. 尝试 OpenCV（可选）
    print("\n是否尝试用 OpenCV 直接读取? (y/n): ", end="")
    try:
        response = input().strip().lower()
        if response == 'y':
            test_with_opencv_directly(stream_url)
    except EOFError:
        pass
    
    print("\n" + "=" * 70)
    print("诊断完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
