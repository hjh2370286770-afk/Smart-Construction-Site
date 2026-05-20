#!/usr/bin/env python3
"""
测试脚本 - 验证工作时间统计系统功能
不显示窗口，只处理几帧后退出
"""

import sys
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np

warnings.filterwarnings('ignore')

# 导入我们的模块
from worktime_tracker import SimplePersonDetector, PersonWorkRecord, WorkTimeTracker


def test_detector():
    """测试检测器"""
    print("\n" + "="*50)
    print("测试1: 检测器初始化")
    print("="*50)
    
    detector = SimplePersonDetector(conf_threshold=0.45)
    print(f"[OK] 检测器初始化完成")
    print(f"     模型类型: {type(detector.model)}")
    return detector


def test_detection(detector, frame):
    """测试检测功能"""
    print("\n" + "="*50)
    print("测试2: 人员检测")
    print("="*50)
    
    detections = detector.detect(frame)
    print(f"[OK] 检测到 {len(detections)} 个人员")
    
    for i, det in enumerate(detections):
        print(f"     人员{i+1}: ID={det.get('track_id')}, "
              f"置信度={det.get('confidence', 0):.2f}")
    
    return detections


def test_work_records():
    """测试工作时间记录"""
    print("\n" + "="*50)
    print("测试3: 工作时间记录")
    print("="*50)
    
    now = datetime.now()
    record = PersonWorkRecord(
        track_id=1,
        first_appearance=now,
        last_appearance=now
    )
    
    # 模拟多次更新
    for i in range(5):
        record.update_appearance(now)
    
    print(f"[OK] 工作记录创建成功")
    print(f"     人员ID: {record.track_id}")
    print(f"     首次出现: {record.first_appearance.strftime('%H:%M:%S')}")
    print(f"     最后出现: {record.last_appearance.strftime('%H:%M:%S')}")
    print(f"     检测帧数: {record.total_frames}")
    print(f"     工作时段: {len(record.appearance_history)}")
    
    data = record.to_dict()
    print(f"     工作时间: {data['work_time_formatted']}")
    
    return record


def test_video_stream():
    """测试视频流连接"""
    print("\n" + "="*50)
    print("测试4: 视频流连接")
    print("="*50)
    
    stream_url = "rtsp://admin:abcd1234@192.168.2.64/h264/ch1/main/av_stream"
    
    print(f"[INFO] 连接视频流: {stream_url}")
    cap = cv2.VideoCapture(stream_url)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    
    if not cap.isOpened():
        print("[ERROR] 无法打开视频流")
        return None
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    print(f"[OK] 视频流已连接")
    print(f"     分辨率: {width}x{height}")
    print(f"     FPS: {fps:.1f}")
    
    # 读取几帧测试
    frames = []
    for i in range(3):
        ret, frame = cap.read()
        if ret:
            frames.append(frame)
            print(f"     帧{i+1}: {frame.shape}")
        else:
            print(f"     帧{i+1}: 读取失败")
    
    cap.release()
    print(f"[OK] 成功读取 {len(frames)} 帧")
    
    return frames[0] if frames else None


def test_full_pipeline():
    """测试完整流程"""
    print("\n" + "="*50)
    print("测试5: 完整流程测试")
    print("="*50)
    
    # 初始化
    detector = SimplePersonDetector()
    work_records = {}
    current_persons = set()
    
    # 连接视频流
    stream_url = "rtsp://admin:abcd1234@192.168.2.64/h264/ch1/main/av_stream"
    cap = cv2.VideoCapture(stream_url)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    
    if not cap.isOpened():
        print("[ERROR] 无法打开视频流")
        return
    
    print("[OK] 开始处理视频流（处理10帧后退出）...")
    
    frame_count = 0
    max_frames = 10
    
    try:
        while frame_count < max_frames:
            ret, frame = cap.read()
            if not ret:
                print(f"[WARN] 帧{frame_count+1} 读取失败")
                continue
            
            # 缩放帧
            if frame.shape[1] > 960:
                frame = cv2.resize(frame, (960, 540))
            
            frame_count += 1
            current_time = datetime.now()
            
            # 每3帧检测一次
            if frame_count % 3 == 0:
                detections = detector.detect(frame)
                
                # 更新工作记录
                current_ids = set()
                for det in detections:
                    track_id = det.get('track_id')
                    if track_id is None:
                        continue
                    
                    current_ids.add(track_id)
                    
                    if track_id not in work_records:
                        work_records[track_id] = PersonWorkRecord(
                            track_id=track_id,
                            first_appearance=current_time,
                            last_appearance=current_time
                        )
                        print(f"[人员] ID{track_id} 进入画面")
                    
                    work_records[track_id].update_appearance(current_time)
                
                # 检测离开的人员
                left_persons = current_persons - current_ids
                for pid in left_persons:
                    if pid in work_records:
                        work_time = work_records[pid].get_total_work_time()
                        print(f"[人员] ID{pid} 离开画面，工作时间: {work_time}")
                
                current_persons = current_ids
                
                print(f"[帧{frame_count}] 检测到 {len(detections)} 个人员, "
                      f"当前在画面中: {list(current_ids)}")
            else:
                print(f"[帧{frame_count}] 跳过检测")
                
    except KeyboardInterrupt:
        print("\n[INFO] 用户中断")
    finally:
        cap.release()
    
    # 生成报告
    print("\n" + "="*50)
    print("工作时间统计报告")
    print("="*50)
    
    if not work_records:
        print("未检测到任何人员")
    else:
        for pid, record in sorted(work_records.items()):
            work_time = record.get_total_work_time()
            print(f"\n人员 ID: {pid}")
            print(f"  首次出现: {record.first_appearance.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  最后出现: {record.last_appearance.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  工作时长: {work_time}")
            print(f"  检测帧数: {record.total_frames}")
        
        print(f"\n总人数: {len(work_records)}")
    
    print("="*50)


def main():
    print("\n" + "="*70)
    print("人员工作时间统计系统 - 功能测试")
    print("="*70)
    
    # 运行所有测试
    try:
        # 测试1: 检测器
        detector = test_detector()
        
        # 测试2: 获取视频帧并进行检测
        frame = test_video_stream()
        if frame is not None:
            detections = test_detection(detector, frame)
        
        # 测试3: 工作时间记录
        record = test_work_records()
        
        # 测试4: 完整流程
        test_full_pipeline()
        
        print("\n" + "="*70)
        print("所有测试完成！")
        print("="*70)
        
    except Exception as e:
        print(f"\n[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
