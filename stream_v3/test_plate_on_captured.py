"""
测试车牌检测器 - 使用抓拍的图片
"""

import cv2
import sys
from pathlib import Path
import glob

sys.path.insert(0, str(Path(__file__).parent))

from detectors.plate_detector import create_plate_detector

def test_on_captured_images():
    """在抓拍的图片上测试车牌检测"""
    print("=" * 70)
    print("车牌检测器测试 - 使用抓拍的车辆图片")
    print("=" * 70)
    
    # 创建检测器
    print("\n1. 创建车牌检测器...")
    detector = create_plate_detector(device='cpu')
    
    # 初始化
    print("2. 初始化模型...")
    if not detector.init():
        print("初始化失败！")
        return
    
    print("3. 模型初始化成功！\n")
    
    # 获取抓拍的图片
    image_paths = glob.glob('storage/full_video_test/entry_*.jpg')
    
    # 选择前10张和最后10张进行测试
    test_images = image_paths[:5] + image_paths[-5:] if len(image_paths) > 10 else image_paths
    
    detected_count = 0
    for img_path in test_images:
        img_name = Path(img_path).name
        print(f"测试: {img_name}")
        
        # 读取图片
        img = cv2.imread(img_path)
        if img is None:
            print(f"  无法读取图片")
            continue
        
        # 检测车牌
        results = detector.detect(img)
        
        if results:
            detected_count += 1
            print(f"  检测到 {len(results)} 个车牌:")
            for i, result in enumerate(results):
                print(f"    [{i+1}] {result['plate_no']} | {result['plate_color']} | 置信度:{result['detect_conf']:.2f}")
        else:
            print(f"  未检测到车牌")
        print()
    
    print("=" * 70)
    print(f"测试完成: {detected_count}/{len(test_images)} 张图片检测到车牌")
    print("=" * 70)

if __name__ == "__main__":
    test_on_captured_images()
