#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple test with real-time output
"""

import sys
import io
sys.path.insert(0, '.')

# Force flush output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)

import cv2
import time
from pathlib import Path

print("Starting test...", flush=True)

VIDEO_PATH = r"D:\Users\Admini503\OneDrive\Desktop\文件\视觉识别\微信视频2026-04-23_090043_727.mp4"

print(f"Video path: {VIDEO_PATH}", flush=True)

# Check video exists
video_path = Path(VIDEO_PATH)
if not video_path.exists():
    print("ERROR: Video not found", flush=True)
    sys.exit(1)

print(f"Video size: {video_path.stat().st_size / 1024 / 1024:.1f} MB", flush=True)

# Open video
print("Opening video...", flush=True)
cap = cv2.VideoCapture(str(video_path))
if not cap.isOpened():
    print("ERROR: Cannot open video", flush=True)
    sys.exit(1)

fps = cap.get(cv2.CAP_PROP_FPS)
frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print(f"Video: {frame_count} frames, {fps:.1f} fps, {frame_count/fps:.1f}s", flush=True)

# Load detector
print("Loading detector...", flush=True)
try:
    from detectors.vehicle_wash_detector import VehicleWashDetector
    
    detector_config = {
        'path': 'yolov8n.pt',
        'device': 'cpu',
        'conf_threshold': 0.3,
        'iou_threshold': 0.45,
        'img_size': 640,
        'ocr_engine': 'paddleocr',
        'wash_time_min': 300,
        'wash_time_max': 1800,
        'entry_line_y': 300,
        'exit_line_y': 500,
        'save_images': False,
    }
    
    detector = VehicleWashDetector(detector_config)
    print("Detector loaded successfully", flush=True)
    
except Exception as e:
    print(f"ERROR loading detector: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Process first 100 frames only
print("\nProcessing first 100 frames...", flush=True)
frame_idx = 0
max_frames = 100
start_time = time.time()

while frame_idx < max_frames:
    ret, frame = cap.read()
    if not ret:
        print("Video ended", flush=True)
        break
    
    frame_idx += 1
    
    # Process every 3rd frame
    if frame_idx % 3 == 0:
        try:
            result_frame, updated_records = detector.process_frame(frame)
            
            if updated_records:
                for record in updated_records:
                    plate = record.license_plate
                    print(f"Frame {frame_idx}: Plate={plate}", flush=True)
        except Exception as e:
            print(f"Error at frame {frame_idx}: {e}", flush=True)
    
    # Print progress every 10 frames
    if frame_idx % 10 == 0:
        elapsed = time.time() - start_time
        fps_current = frame_idx / elapsed if elapsed > 0 else 0
        print(f"Progress: {frame_idx}/{max_frames} frames, FPS: {fps_current:.1f}", flush=True)

cap.release()

# Summary
elapsed = time.time() - start_time
print(f"\nDone! Processed {frame_idx} frames in {elapsed:.1f}s", flush=True)
print(f"Average FPS: {frame_idx/elapsed:.1f}", flush=True)

stats = detector.get_statistics()
print(f"Entries: {stats['total_entries']}, Exits: {stats['total_exits']}", flush=True)

print("\nActive vehicles:", flush=True)
for record in detector.get_active_records():
    print(f"  - {record.license_plate}", flush=True)
