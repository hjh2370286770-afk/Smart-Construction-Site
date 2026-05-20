#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
施工视频标准帧提取工具
使用 OpenCV 进行长时间稳定的视频帧提取
"""

import cv2
import os
import sys
from pathlib import Path
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 视频文件列表
VIDEO_FILES = [
    "JHMH2405004008_20260401_132840.mp4",
    "JHMH2405004008_20260331_132219.mp4",
    "JHMH2405004008_20260331_141604 (1).mp4",
    "JHMH2405004008_20260331_133940.mp4",
    "JHMH2405004008_20260331_133957.mp4",
    "JHMH2405004008_20260331_135014.mp4",
    "JHMH2405004008_20260331_134013.mp4",
    "JHMH2405004008_20260401_133944.mp4",
    "JHMH2405004008_20260401_133925.mp4",
    "JHMH2405004008_20260401_133907.mp4",
    "JHMH2405004008_20260401_133848.mp4",
    "JHMH2405004008_20260401_133654.mp4",
    "JHMH2405004008_20260401_133635.mp4",
    "JHMH2405004008_20260401_133617.mp4",
    "JHMH2405004008_20260401_133559.mp4",
    "JHMH2405004008_20260401_133542.mp4",
    # 之前的视频
    "JHMH2405004008_20260331_135618.mp4",
    "JHMH2405004008_20260331_141510.mp4",
    "JHMH2405004008_20260331_141604.mp4",
    "JHMH2405004008_20260331_141621.mp4",
    "JHMH2405004008_20260331_141638.mp4",
    "JHMH2405004008_20260331_143044.mp4",
    "JHMH2405004008_20260331_143101.mp4",
    "JHMH2405004008_20260331_143118.mp4",
]

# 提取时间点（秒）
EXTRACT_TIMES = [2, 5, 8, 11]  # 从每个视频提取4个时间点

def extract_frames(video_path: str, output_dir: str, video_name: str):
    """
    从视频中提取标准帧
    
    Args:
        video_path: 视频文件路径
        output_dir: 输出目录
        video_name: 视频名称（用于生成文件名）
    """
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        logger.error(f"无法打开视频: {video_path}")
        return 0
    
    # 获取视频信息
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0
    
    logger.info(f"处理视频: {video_name}")
    logger.info(f"  FPS: {fps:.2f}, 总帧数: {total_frames}, 时长: {duration:.2f}s")
    
    extracted_count = 0
    
    for time_sec in EXTRACT_TIMES:
        if time_sec >= duration:
            logger.warning(f"  跳过 {time_sec}s (超出视频时长)")
            continue
        
        # 定位到指定时间
        frame_pos = int(time_sec * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
        
        ret, frame = cap.read()
        if not ret:
            logger.warning(f"  无法读取 {time_sec}s 处的帧")
            continue
        
        # 生成文件名: 视频名_时间戳.jpg
        base_name = Path(video_name).stem.replace(" ", "_")
        output_filename = f"{base_name}_t{time_sec:02d}s.jpg"
        output_path = os.path.join(output_dir, output_filename)
        
        # 保存帧
        cv2.imwrite(output_path, frame)
        logger.info(f"  已提取: {output_filename} ({frame.shape[1]}x{frame.shape[0]})")
        extracted_count += 1
        
        # 主动释放帧内存
        del frame
    
    cap.release()
    # 强制垃圾回收
    import gc
    gc.collect()
    
    logger.info(f"  完成: 提取 {extracted_count} 帧")
    return extracted_count

def main():
    """主函数"""
    # 路径配置
    downloads_dir = r"C:\Users\Admini503\Downloads"
    output_dir = r"C:\Users\Admini503\.openclaw\workspace\dataset\wall_inspection\raw_frames"
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    logger.info("=" * 60)
    logger.info("施工视频标准帧提取")
    logger.info(f"输出目录: {output_dir}")
    logger.info("=" * 60)
    
    total_extracted = 0
    success_count = 0
    
    for video_file in VIDEO_FILES:
        video_path = os.path.join(downloads_dir, video_file)
        
        if not os.path.exists(video_path):
            logger.warning(f"视频不存在: {video_file}")
            continue
        
        count = extract_frames(video_path, output_dir, video_file)
        total_extracted += count
        if count > 0:
            success_count += 1
        
        logger.info("")
    
    logger.info("=" * 60)
    logger.info(f"提取完成: {success_count}/{len(VIDEO_FILES)} 个视频, 共 {total_extracted} 帧")
    logger.info(f"输出目录: {output_dir}")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()
