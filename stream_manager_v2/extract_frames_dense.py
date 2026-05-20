#!/usr/bin/env python3
"""
视频帧提取工具 - V2版本
增加提取密度：15秒视频提取8帧（每2秒一帧）
"""

import cv2
import os
from pathlib import Path
import argparse


def extract_frames_dense(video_path: str, output_dir: str, interval: float = 2.0):
    """
    密集提取视频帧
    
    Args:
        video_path: 视频文件路径
        output_dir: 输出目录
        interval: 提取间隔（秒），默认2秒
    """
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 打开视频
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"Error: 无法打开视频 {video_path}")
        return
    
    # 获取视频信息
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0
    
    print(f"视频信息:")
    print(f"  分辨率: {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
    print(f"  FPS: {fps:.2f}")
    print(f"  总帧数: {total_frames}")
    print(f"  时长: {duration:.1f}秒")
    print(f"  提取间隔: {interval}秒")
    print()
    
    # 计算提取时间点
    extract_times = []
    current_time = 0.0
    while current_time < duration:
        extract_times.append(current_time)
        current_time += interval
    
    print(f"将提取 {len(extract_times)} 帧")
    print()
    
    # 提取帧
    extracted_frames = []
    for i, time_sec in enumerate(extract_times):
        # 设置到指定时间
        frame_pos = int(time_sec * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
        
        ret, frame = cap.read()
        if not ret:
            print(f"Warning: 无法在 {time_sec:.1f}s 读取帧")
            continue
        
        # 保存帧
        output_name = f"{video_path.stem}_t{time_sec:04.1f}s.jpg"
        output_path = output_dir / output_name
        cv2.imwrite(str(output_path), frame)
        extracted_frames.append(output_path)
        
        print(f"  [{i+1}/{len(extract_times)}] {time_sec:5.1f}s -> {output_name}")
    
    cap.release()
    
    print()
    print(f"完成！共提取 {len(extracted_frames)} 帧")
    print(f"输出目录: {output_dir}")
    
    return extracted_frames


def main():
    parser = argparse.ArgumentParser(description='密集提取视频帧')
    parser.add_argument('video', help='视频文件路径')
    parser.add_argument('-o', '--output', default='./extracted_frames', help='输出目录')
    parser.add_argument('-i', '--interval', type=float, default=2.0, help='提取间隔（秒），默认2秒')
    
    args = parser.parse_args()
    
    extract_frames_dense(args.video, args.output, args.interval)


if __name__ == '__main__':
    main()
