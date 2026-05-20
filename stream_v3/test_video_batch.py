#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test video in batches to avoid memory issues
"""

import sys
import io
sys.path.insert(0, '.')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import cv2
import time
from pathlib import Path

print("=" * 60)
print("Vehicle Wash Detector - Batch Video Test")
print("=" * 60)

VIDEO_PATH = r"D:\Users\Admini503\OneDrive\Desktop\文件\视觉识别\微信视频2026-04-23_090043_727.mp4"

video_path = Path(VIDEO_PATH)
if not video_path.exists():
    print("[FAIL] Video file not found")
    sys.exit(1)

print(f"[OK] Found video: {video_path.name}")

# Load detector
print("\n[1] Loading detector...")
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
        'save_images': True,
        'image_save_path': 'storage/test_video_batch',
    }
    
    detector = VehicleWashDetector(detector_config)
    print("[OK] Detector loaded")
    
except Exception as e:
    print(f"[FAIL] Failed to load detector: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Open video
print("\n[2] Opening video...")
cap = cv2.VideoCapture(str(video_path))
if not cap.isOpened():
    print("[FAIL] Cannot open video")
    sys.exit(1)

fps = cap.get(cv2.CAP_PROP_FPS)
frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

print(f"[OK] Video info:")
print(f"   Resolution: {width}x{height}")
print(f"   FPS: {fps:.1f}")
print(f"   Total frames: {frame_count}")
print(f"   Duration: {frame_count/fps:.1f}s")

# Process in batches
print("\n[3] Processing video (batch mode)...")
print("-" * 60)

batch_size = 500  # Process 500 frames at a time
frame_idx = 0
process_every_n_frames = 2
start_time = time.time()

recognized_plates = {}

while frame_idx < frame_count:
    batch_start = frame_idx
    batch_end = min(frame_idx + batch_size, frame_count)
    
    print(f"\nProcessing batch: {batch_start}-{batch_end} ({batch_end-batch_start} frames)")
    
    batch_frames = 0
    while frame_idx < batch_end:
        ret, frame = cap.read()
        if not ret:
            print("[INFO] Video ended")
            break
        
        frame_idx += 1
        batch_frames += 1
        
        if frame_idx % process_every_n_frames == 0:
            try:
                result_frame, updated_records = detector.process_frame(frame)
                
                if updated_records:
                    for record in updated_records:
                        status = "Washed" if record.is_washed else "Not Washed"
                        plate = record.license_plate
                        print(f"  [Record] Plate:{plate} | Time:{record.dwell_time:.1f}s | {status}")
                        
                        if not plate.startswith("UNKNOWN"):
                            if plate not in recognized_plates:
                                recognized_plates[plate] = 0
                            recognized_plates[plate] += 1
            except Exception as e:
                print(f"  [Error processing frame {frame_idx}]: {e}")
    
    # Batch summary
    elapsed = time.time() - start_time
    progress = frame_idx / frame_count * 100
    fps_current = frame_idx / elapsed if elapsed > 0 else 0
    print(f"Batch complete. Progress: {progress:.1f}% | FPS:{fps_current:.1f}")
    
    # Print current stats
    stats = detector.get_statistics()
    print(f"  Current stats - Entries:{stats['total_entries']} Exits:{stats['total_exits']} Washed:{stats['washed_count']}")

# Release resources
cap.release()

# Final Summary
elapsed = time.time() - start_time
print("\n" + "=" * 60)
print("Test Complete")
print("=" * 60)
print(f"Frames processed: {frame_idx}")
print(f"Time elapsed: {elapsed:.1f}s")
print(f"Average FPS: {frame_idx/elapsed:.1f}")
print()
print("Final Statistics:")
stats = detector.get_statistics()
print(f"  Total entries: {stats['total_entries']}")
print(f"  Total exits: {stats['total_exits']}")
print(f"  Washed: {stats['washed_count']}")
print(f"  Wash rate: {stats['wash_rate']*100:.1f}%")
print()
print("Recognized plates:")
if recognized_plates:
    for plate, count in sorted(recognized_plates.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {plate}: {count} times")
else:
    print("  None")
print()
print("Active vehicles:")
for record in detector.get_active_records():
    print(f"  - {record.license_plate} (Entry: {record.entry_time.strftime('%H:%M:%S')})")
print()
print("Completed records:")
for record in detector.get_completed_records():
    status = "Washed" if record.is_washed else "Not Washed"
    print(f"  - {record.license_plate} | {record.dwell_time:.1f}s | {status}")
