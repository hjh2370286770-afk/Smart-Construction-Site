#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提取视频指定时间的帧
"""

import cv2
from pathlib import Path

VIDEO_PATH = r"D:\Users\Admini503\OneDrive\Desktop\文件\视觉识别\微信视频2026-04-23_090043_727.mp4"

# 打开视频
cap = cv2.VideoCapture(VIDEO_PATH)
if not cap.isOpened():
    print("无法打开视频")
    exit(1)

fps = cap.get(cv2.CAP_PROP_FPS)
frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

print(f"视频信息: {frame_count}帧, {fps:.1f}fps, {frame_count/fps:.1f}秒")

# 3分10秒 = 190秒
target_time = 190  # 秒
target_frame = int(target_time * fps)

print(f"提取时间: {target_time}秒")
print(f"目标帧: {target_frame}")

# 跳到目标帧
cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)

# 读取帧
ret, frame = cap.read()
if ret:
    # 保存图片
    output_path = f"storage/frame_at_3m10s.jpg"
    Path("storage").mkdir(exist_ok=True)
    cv2.imwrite(output_path, frame)
    print(f"已保存: {output_path}")
    print(f"图片尺寸: {frame.shape[1]}x{frame.shape[0]}")
else:
    print("无法读取该帧")

cap.release()
