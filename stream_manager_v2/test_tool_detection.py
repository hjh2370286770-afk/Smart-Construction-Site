"""
刀具检测测试脚本
测试视频: JHMH2405004008_20260403_072541.mp4
目标: 识别金属色刮抹刀具并判断其运动状态
"""

import sys
import cv2
import numpy as np
import logging
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from detectors.wall_defect_detector_v2 import WallDefectDetectorV2

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_tool_detection():
    """测试刀具检测"""
    
    # 初始化检测器
    config = {
        'name': 'wall_defect_detector_v2',
        'type': 'yolov8-seg',
        'path': r'C:\Users\Admini503\.openclaw\workspace\models\pretrained\yolov8n-crack-seg.pt',
        'model_type': 'segment',
        'conf_threshold': 0.25,
        'iou_threshold': 0.4,
        'img_size': 640,
        'device': 'auto'
    }
    
    detector = WallDefectDetectorV2(config)
    logger.info("检测器初始化完成")
    
    # 视频路径
    video_path = r"C:\Users\Admini503\Downloads\JHMH2405004008_20260403_072541.mp4"
    
    # 打开视频
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"无法打开视频: {video_path}")
        return
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    logger.info(f"视频信息: {total_frames}帧, {fps}fps")
    
    # 创建输出目录
    output_dir = Path("output/tool_test")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    frame_count = 0
    results = []
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_count += 1
        timestamp = frame_count / fps
        
        # 检测
        detections = detector.detect(frame)
        
        # 获取状态
        device_status = detector.get_device_status()
        
        # 记录结果
        result = {
            'frame': frame_count,
            'timestamp': f"{timestamp:.2f}s",
            'scene': detector.current_scene,
            'wall_state': detector.current_wall_state,
            'device_status': device_status['current_status'],
            'tool_detected': device_status.get('tool_detected', False),
            'defects': len(detections)
        }
        results.append(result)
        
        # 每帧输出
        logger.info(f"[{timestamp:.2f}s] 场景:{detector.current_scene} | "
                   f"墙面:{detector.current_wall_state} | "
                   f"设备:{device_status['current_status']} | "
                   f"缺陷:{len(detections)}")
        
        # 保存关键帧（每2秒）
        if frame_count % int(fps * 2) == 0:
            # 添加状态信息到图像
            display_frame = frame.copy()
            h, w = display_frame.shape[:2]
            
            # 绘制状态面板
            panel_y = 10
            cv2.putText(display_frame, f"Scene: {detector.current_scene}", (10, panel_y+20), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(display_frame, f"Wall: {detector.current_wall_state}", (10, panel_y+45),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.putText(display_frame, f"Device: {device_status['current_status']}", (10, panel_y+70),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            # 保存
            output_path = output_dir / f"frame_{frame_count:04d}_{timestamp:.1f}s.jpg"
            cv2.imwrite(str(output_path), display_frame)
    
    cap.release()
    
    # 输出统计
    logger.info("\n" + "="*60)
    logger.info("测试结果统计")
    logger.info("="*60)
    
    # 统计设备状态
    status_counts = {}
    for r in results:
        status = r['device_status']
        status_counts[status] = status_counts.get(status, 0) + 1
    
    logger.info(f"总帧数: {frame_count}")
    logger.info("设备状态分布:")
    for status, count in status_counts.items():
        logger.info(f"  {status}: {count}帧 ({count/frame_count*100:.1f}%)")
    
    logger.info(f"\n结果图像保存到: {output_dir}")
    
    return results


if __name__ == "__main__":
    test_tool_detection()
