"""
测试车牌检测器 - 使用有车辆的帧
"""

import sys
import cv2
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

print("=" * 70)
print("测试 YOLOv8 车牌检测器 (使用有车辆的帧)")
print("=" * 70)

VIDEO_PATH = r"D:\Users\Admini503\OneDrive\Desktop\文件\视觉识别\微信视频2026-04-23_090043_727.mp4"

# 提取第100帧（应该有车辆）
cap = cv2.VideoCapture(VIDEO_PATH)
cap.set(cv2.CAP_PROP_POS_FRAMES, 100)
ret, frame = cap.read()
if ret:
    test_image = "storage/test_frame_100.jpg"
    cv2.imwrite(test_image, frame)
    print(f"已保存第100帧: {test_image}")
    print(f"帧大小: {frame.shape[1]}x{frame.shape[0]}")
cap.release()

# 加载车牌检测器
print("\n加载车牌检测器...")
try:
    from detectors.plate_detector import PlateDetector, create_plate_detector
    
    detector = create_plate_detector(device='cuda')
    
    if detector.init():
        print("✓ 检测器初始化成功")
        
        # 测试检测
        image = cv2.imread(test_image)
        print(f"\n开始检测... (图像大小: {image.shape[1]}x{image.shape[0]})")
        
        results = detector.detect(image)
        
        if results:
            print(f"\n✓ 发现 {len(results)} 个车牌!")
            for i, result in enumerate(results):
                print(f"\n  车牌 #{i+1}:")
                print(f"    车牌号: {result['plate_no']}")
                print(f"    车牌颜色: {result['plate_color']}")
                print(f"    置信度: {result['detect_conf']:.3f}")
                
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
            
            print("\n" + "=" * 70)
            print("结论: YOLOv8车牌检测器可以正常识别车牌号!")
            print("       不需要使用OCR!")
            print("=" * 70)
        else:
            print("\n× 未检测到车牌")
            print("尝试降低置信度阈值...")
            
            detector.conf_thresh = 0.1
            results = detector.detect(image)
            
            if results:
                print(f"\n✓ 降低阈值后发现 {len(results)} 个车牌!")
                for i, result in enumerate(results):
                    print(f"  车牌 #{i+1}: {result['plate_no']}")
            else:
                print("\n× 即使降低阈值也未检测到车牌")
                print("可能原因:")
                print("  1. 该帧确实没有车辆")
                print("  2. 车辆距离太远")
                print("  3. 需要其他帧进行测试")
    
    else:
        print("× 检测器初始化失败")
        
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
