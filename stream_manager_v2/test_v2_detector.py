#!/usr/bin/env python3
"""
测试 WallDefectDetectorV2
验证新的设备状态判断和墙面状态识别
"""

import sys
from pathlib import Path
import cv2
import logging

sys.path.insert(0, str(Path(__file__).parent))

from detectors.wall_defect_detector_v2 import WallDefectDetectorV2, WallState, DeviceStatus

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# 检测器配置
CONFIG = {
    'name': 'wall_defect_detector_v2',
    'type': 'yolov8-seg',
    'path': r'C:\Users\Admini503\.openclaw\workspace\models\pretrained\yolov8n-crack-seg.pt',
    'model_type': 'segment',
    'version': '2.0',
    'classes': [
        {'id': 0, 'name': 'crack', 'color': [0, 0, 255]},
        {'id': 1, 'name': 'stain', 'color': [0, 255, 255]},
        {'id': 2, 'name': 'unevenness', 'color': [255, 0, 0]}
    ],
    'params': {
        'conf_threshold': 0.25,
        'iou_threshold': 0.4,
        'img_size': 640,
        'device': 'auto'
    }
}


def test_on_images(image_dir: str):
    """在提取的帧上测试检测器"""
    image_dir = Path(image_dir)
    image_files = sorted(image_dir.glob("*.jpg"))
    
    if not image_files:
        logger.error(f"未找到图像文件: {image_dir}")
        return
    
    logger.info(f"找到 {len(image_files)} 张图像")
    
    # 初始化检测器
    logger.info("初始化检测器V2...")
    detector = WallDefectDetectorV2(CONFIG)
    
    # 创建输出目录
    output_dir = Path("output/v2_test")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 处理每张图像
    results = []
    for i, img_path in enumerate(image_files):
        logger.info(f"\n处理 [{i+1}/{len(image_files)}]: {img_path.name}")
        
        # 读取图像
        frame = cv2.imread(str(img_path))
        if frame is None:
            logger.warning(f"无法读取图像: {img_path}")
            continue
        
        # 执行检测
        detections = detector.detect(frame)
        
        # 获取状态
        device_status = detector.get_device_status()
        wall_state = detector.current_wall_state
        
        logger.info(f"  墙面状态: {wall_state}")
        logger.info(f"  设备状态: {device_status['current_status']}")
        logger.info(f"  检测到的缺陷: {len(detections)}")
        
        # 绘制结果
        result_frame = detector.draw_results(frame, detections)
        
        # 保存结果
        output_path = output_dir / f"result_{img_path.name}"
        cv2.imwrite(str(output_path), result_frame)
        
        results.append({
            'image': img_path.name,
            'wall_state': wall_state,
            'device_status': device_status['current_status'],
            'defects': len(detections)
        })
    
    # 打印汇总
    logger.info("\n" + "="*60)
    logger.info("测试结果汇总")
    logger.info("="*60)
    for r in results:
        logger.info(f"{r['image']}: 墙面={r['wall_state']}, 设备={r['device_status']}, 缺陷={r['defects']}")
    
    logger.info(f"\n输出目录: {output_dir}")


if __name__ == '__main__':
    test_on_images("dataset/wall_inspection_v2/frames")
