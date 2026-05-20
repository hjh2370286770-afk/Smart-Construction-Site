#!/usr/bin/env python3
"""
萤石云视频流 PPE 检测 - 实际测试
"""

import sys
import subprocess
import tempfile
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "detectors"))

import cv2
from detectors.ppe_detector import PPEDetector


def download_frame(stream_url: str, output_path: str):
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
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        return result.returncode == 0 and os.path.exists(output_path)
    except Exception as e:
        print(f"Error: {e}")
        return False


def main():
    stream_url = "https://open.ys7.com/v3/openlive/J58749099_1_1.m3u8?expire=1805097058&id=955131347955273728&t=9142d9ce6a544a7c8569df965320fce7d2e78bba12f066d3ea7c176847107c3b&ev=101"
    
    print("=" * 70)
    print("萤石云视频流 PPE 检测测试")
    print("=" * 70)
    
    # Step 1: Download frame
    print("\n[1/4] 正在从视频流下载帧...")
    temp_path = tempfile.mktemp(suffix='.jpg')
    
    if not download_frame(stream_url, temp_path):
        print("[X] 下载失败")
        return
    
    print("[OK] 帧下载成功")
    
    # Step 2: Load frame
    print("\n[2/4] 加载图像...")
    frame = cv2.imread(temp_path)
    os.remove(temp_path)
    
    if frame is None:
        print("[X] 无法加载图像")
        return
    
    print(f"[OK] 图像尺寸: {frame.shape[1]}x{frame.shape[0]}")
    
    # Save original
    cv2.imwrite("ys7_original.jpg", frame)
    print("[OK] 原图已保存: ys7_original.jpg")
    
    # Step 3: Initialize detector
    print("\n[3/4] 初始化 PPE 检测器...")
    try:
        detector = PPEDetector(conf_threshold=0.4)
        print("[OK] 检测器初始化成功")
    except Exception as e:
        print(f"[X] 初始化失败: {e}")
        return
    
    # Step 4: Run detection
    print("\n[4/4] 运行 PPE 检测...")
    detections = detector.detect(frame)
    
    print(f"[OK] 检测到 {len(detections)} 个人员")
    
    # Print details
    for i, det in enumerate(detections):
        print(f"\n  人员 {i+1} (ID: {det.track_id}):")
        print(f"    置信度: {det.confidence:.2f}")
        print(f"    安全帽: {'[OK] 已戴' if det.has_helmet else '[X] 未戴'}")
        print(f"    反光衣: {'[OK] 已穿' if det.has_vest else '[X] 未穿'}")
        print(f"    口罩: {'[OK] 已戴' if det.has_mask else '[X] 未戴'}")
        print(f"    合规: {'[OK] 是' if det.is_compliant else '[X] 否 (违规)'}")
        if det.violation_type:
            print(f"    违规类型: {det.violation_type}")
    
    # Draw and save results
    result = detector.draw_results(frame, detections)
    cv2.imwrite("ys7_ppe_result.jpg", result)
    print("\n[OK] 检测结果已保存: ys7_ppe_result.jpg")
    
    # Summary
    summary = detector.get_summary(detections)
    print("\n" + "=" * 70)
    print("检测摘要")
    print("=" * 70)
    print(f"总人数: {summary['total_persons']}")
    print(f"合规人数: {summary['compliant']}")
    print(f"合规率: {summary['compliance_rate']:.1%}")
    print(f"违规情况: {summary['violations']}")
    print("=" * 70)
    
    # Show image
    print("\n正在显示结果图片...")
    cv2.imshow("PPE Detection Result", result)
    print("按任意键关闭窗口")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
