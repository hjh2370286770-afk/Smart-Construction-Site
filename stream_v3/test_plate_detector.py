"""
测试车牌检测器 - 验证YOLOv8车牌识别功能
"""

import sys
import cv2
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 70)
print("测试 YOLOv8 车牌检测器")
print("=" * 70)

# 测试图片路径（使用视频的第一帧）
VIDEO_PATH = r"D:\Users\Admini503\OneDrive\Desktop\文件\视觉识别\微信视频2026-04-23_090043_727.mp4"
TEST_IMAGE = "storage/test_frame.jpg"

# 提取一帧用于测试
cap = cv2.VideoCapture(VIDEO_PATH)
ret, frame = cap.read()
if ret:
    cv2.imwrite(TEST_IMAGE, frame)
    print(f"已保存测试帧: {TEST_IMAGE}")
    print(f"帧大小: {frame.shape[1]}x{frame.shape[0]}")
cap.release()

# 加载车牌检测器
print("\n加载车牌检测器...")
try:
    from detectors.plate_detector import PlateDetector, create_plate_detector
    
    print("  创建检测器实例...", end=' ')
    detector = create_plate_detector(device='cuda')
    print("OK")
    
    print("  初始化模型...", end=' ')
    if detector.init():
        print("OK")
        
        # 测试检测
        print("\n开始检测...")
        image = cv2.imread(TEST_IMAGE)
        print(f"  图像大小: {image.shape[1]}x{image.shape[0]}")
        
        results = detector.detect(image)
        
        if results:
            print(f"\n检测结果: 发现 {len(results)} 个车牌")
            for i, result in enumerate(results):
                print(f"\n  车牌 #{i+1}:")
                print(f"    车牌号: {result['plate_no']}")
                print(f"    车牌颜色: {result['plate_color']}")
                print(f"    检测置信度: {result['detect_conf']:.3f}")
                print(f"    颜色置信度: {result['color_conf']:.3f}")
                print(f"    位置: {result['rect']}")
                print(f"    类型: {'双层' if result['plate_type'] == 1 else '单层'}")
            
            # 绘制结果
            for result in results:
                x1, y1, x2, y2 = result['rect']
                cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f"{result['plate_no']} ({result['plate_color']})"
                cv2.putText(image, label, (x1, y1 - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            
            output_path = "storage/plate_detection_result.jpg"
            cv2.imwrite(output_path, image)
            print(f"\n结果已保存: {output_path}")
        else:
            print("\n未检测到车牌")
    
    else:
        print("FAILED!")
        print("错误: 车牌检测器初始化失败")
        
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
