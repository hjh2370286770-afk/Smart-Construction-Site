#!/usr/bin/env python3
"""
萤石云视频流 PPE 检测测试
使用提供的 HLS 流地址测试 PPE 检测
"""

import sys
import cv2
import time
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "detectors"))

from detectors.ppe_detector import PPEDetector


def test_ys7_stream():
    """测试萤石云视频流"""
    
    # 萤石云视频流地址
    stream_url = "https://open.ys7.com/v3/openlive/J58749099_1_1.m3u8?expire=1805097058&id=955131347955273728&t=9142d9ce6a544a7c8569df965320fce7d2e78bba12f066d3ea7c176847107c3b&ev=101"
    
    print("=" * 70)
    print("萤石云视频流 PPE 检测测试")
    print("=" * 70)
    print(f"视频流地址: {stream_url[:60]}...")
    print()
    
    # 初始化 PPE 检测器
    print("正在初始化 PPE 检测器...")
    try:
        detector = PPEDetector(
            conf_threshold=0.4,
            device='cpu'  # 可以根据需要改为 'cuda'
        )
        print("✓ PPE 检测器初始化成功")
    except Exception as e:
        print(f"✗ 初始化失败: {e}")
        return
    
    # 打开视频流
    print(f"\n正在连接视频流...")
    cap = cv2.VideoCapture(stream_url)
    
    # 设置缓冲区大小（对于网络流很重要）
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)
    
    # 检查是否成功打开
    if not cap.isOpened():
        print("✗ 无法打开视频流")
        print("可能的原因:")
        print("  - 流地址已过期")
        print("  - 网络连接问题")
        print("  - 需要特定的解码器")
        return
    
    print("✓ 视频流连接成功")
    
    # 获取视频信息
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
    
    print(f"\n视频信息:")
    print(f"  分辨率: {width}x{height}")
    print(f"  FPS: {fps:.1f}")
    
    print("\n" + "=" * 70)
    print("检测已启动")
    print("=" * 70)
    print("按键说明:")
    print("  q - 退出")
    print("  s - 保存当前帧截图")
    print("  p - 暂停/继续")
    print("  f - 切换全屏")
    print("=" * 70 + "\n")
    
    # 统计信息
    frame_count = 0
    detection_count = 0
    violation_count = 0
    start_time = time.time()
    paused = False
    
    # 跳帧处理（每3帧检测一次，减轻CPU负担）
    detect_every_n_frames = 3
    last_detections = []
    
    try:
        while True:
            if not paused:
                ret, frame = cap.read()
                
                if not ret:
                    print("\n视频流读取失败，尝试重新连接...")
                    time.sleep(1)
                    cap.release()
                    cap = cv2.VideoCapture(stream_url)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)
                    continue
                
                frame_count += 1
                
                # 每 N 帧检测一次
                if frame_count % detect_every_n_frames == 0:
                    timestamp = time.time()
                    detections = detector.detect(frame, timestamp)
                    last_detections = detections
                    detection_count += len(detections)
                    
                    # 统计违规
                    for det in detections:
                        if not det.is_compliant:
                            violation_count += 1
                
                # 绘制结果（使用最新的检测结果）
                result = detector.draw_results(frame, last_detections)
                
                # 添加 FPS 和统计信息
                elapsed = time.time() - start_time
                current_fps = frame_count / elapsed if elapsed > 0 else 0
                
                info_lines = [
                    f"FPS: {current_fps:.1f}",
                    f"Frames: {frame_count}",
                    f"Persons: {len(last_detections)}",
                ]
                
                if last_detections:
                    compliant = sum(1 for d in last_detections if d.is_compliant)
                    info_lines.append(f"Compliance: {compliant}/{len(last_detections)}")
                
                y_offset = 30
                for line in info_lines:
                    cv2.putText(result, line, (10, y_offset),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    y_offset += 25
                
                # 显示结果
                cv2.imshow("PPE Detection - YS7 Stream", result)
            
            # 键盘控制
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                filename = f"ys7_capture_{frame_count}.jpg"
                cv2.imwrite(filename, result)
                print(f"✓ 截图已保存: {filename}")
            elif key == ord('p'):
                paused = not paused
                print("暂停" if paused else "继续")
            elif key == ord('f'):
                # 切换全屏
                is_fullscreen = cv2.getWindowProperty("PPE Detection - YS7 Stream", cv2.WND_PROP_FULLSCREEN)
                cv2.setWindowProperty("PPE Detection - YS7 Stream", cv2.WND_PROP_FULLSCREEN, 
                                     cv2.WINDOW_FULLSCREEN if is_fullscreen != 1 else cv2.WINDOW_NORMAL)
    
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cap.release()
        cv2.destroyAllWindows()
        
        # 打印最终统计
        elapsed = time.time() - start_time
        print("\n" + "=" * 70)
        print("测试完成")
        print("=" * 70)
        print(f"总运行时间: {elapsed:.1f} 秒")
        print(f"处理帧数: {frame_count}")
        print(f"平均 FPS: {frame_count/elapsed:.1f}" if elapsed > 0 else "N/A")
        print(f"检测到人员: {detection_count} 人次")
        print(f"违规次数: {violation_count}")
        print("=" * 70)


def test_with_simple_display():
    """
    简化版测试 - 只显示原始视频，不进行AI检测
    用于验证视频流是否正常
    """
    stream_url = "https://open.ys7.com/v3/openlive/J58749099_1_1.m3u8?expire=1805097058&id=955131347955273728&t=9142d9ce6a544a7c8569df965320fce7d2e78bba12f066d3ea7c176847107c3b&ev=101"
    
    print("=" * 70)
    print("萤石云视频流连接测试（无AI检测）")
    print("=" * 70)
    
    cap = cv2.VideoCapture(stream_url)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)
    
    if not cap.isOpened():
        print("✗ 无法打开视频流")
        return False
    
    print("✓ 视频流连接成功")
    print("按 'q' 退出\n")
    
    frame_count = 0
    start_time = time.time()
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("读取失败，重试中...")
                time.sleep(0.5)
                continue
            
            frame_count += 1
            
            # 显示 FPS
            elapsed = time.time() - start_time
            fps = frame_count / elapsed if elapsed > 0 else 0
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            cv2.imshow("YS7 Stream Test", frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
    
    print(f"\n共显示 {frame_count} 帧")
    return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='萤石云视频流PPE检测测试')
    parser.add_argument('--simple', '-s', action='store_true',
                       help='仅测试视频流连接，不进行AI检测')
    args = parser.parse_args()
    
    if args.simple:
        test_with_simple_display()
    else:
        test_ys7_stream()
