#!/usr/bin/env python3
"""
PPE 检测模型测试脚本
验证下载的模型是否可以正常加载和运行
"""

import sys
import cv2
import numpy as np
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent))

def test_model_loading():
    """测试模型加载"""
    print("=" * 60)
    print("测试1: 模型加载")
    print("=" * 60)
    
    try:
        from ppe_detector import PPEDetector
        print("✓ PPEDetector 模块导入成功")
        
        # 尝试初始化检测器
        print("正在加载模型 models/ppe_best.pt ...")
        detector = PPEDetector(conf_threshold=0.4)
        print(f"✓ 模型加载成功")
        print(f"  - 设备: {detector.device}")
        print(f"  - 置信度阈值: {detector.conf_threshold}")
        print(f"  - IOU阈值: {detector.iou_threshold}")
        return detector
        
    except Exception as e:
        print(f"✗ 模型加载失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_detection(detector):
    """测试检测功能"""
    print("\n" + "=" * 60)
    print("测试2: 检测功能")
    print("=" * 60)
    
    # 创建一个模拟图像（彩色方块模拟PPE）
    print("创建测试图像...")
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # 绘制一些模拟对象
    # 黄色安全帽
    cv2.ellipse(frame, (200, 150), (40, 30), 0, 0, 360, (0, 255, 255), -1)
    # 橙色反光衣
    cv2.rectangle(frame, (160, 180), (240, 300), (0, 100, 255), -1)
    # 人体轮廓
    cv2.rectangle(frame, (150, 150), (250, 350), (100, 100, 100), 2)
    
    # 另一个没有PPE的人
    cv2.rectangle(frame, (400, 150), (500, 350), (100, 100, 100), 2)
    cv2.ellipse(frame, (450, 150), (30, 25), 0, 0, 360, (80, 60, 40), -1)  # 头部
    
    print("✓ 测试图像创建完成")
    
    try:
        print("运行检测...")
        detections = detector.detect(frame)
        print(f"✓ 检测完成，发现 {len(detections)} 个人员")
        
        for i, det in enumerate(detections):
            print(f"  人员 {i+1}:")
            print(f"    - 跟踪ID: {det.track_id}")
            print(f"    - 置信度: {det.confidence:.2f}")
            print(f"    - 安全帽: {'✓' if det.has_helmet else '✗'}")
            print(f"    - 反光衣: {'✓' if det.has_vest else '✗'}")
            print(f"    - 口罩: {'✓' if det.has_mask else '✗'}")
            print(f"    - 合规: {'✓' if det.is_compliant else '✗'}")
        
        # 测试绘制功能
        print("\n测试绘制功能...")
        result = detector.draw_results(frame, detections)
        print("✓ 绘制完成")
        
        # 保存结果
        output_path = "test_ppe_output.jpg"
        cv2.imwrite(output_path, result)
        print(f"✓ 结果已保存到: {output_path}")
        
        # 测试统计功能
        summary = detector.get_summary(detections)
        print("\n检测统计:")
        print(f"  - 总人数: {summary['total_persons']}")
        print(f"  - 合规人数: {summary['compliant']}")
        print(f"  - 合规率: {summary['compliance_rate']:.1%}")
        print(f"  - 违规情况: {summary['violations']}")
        
        return True
        
    except Exception as e:
        print(f"✗ 检测失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_with_camera(detector):
    """使用摄像头测试"""
    print("\n" + "=" * 60)
    print("测试3: 摄像头实时检测（按 'q' 退出）")
    print("=" * 60)
    
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("✗ 无法打开摄像头，跳过此测试")
        return False
    
    print("✓ 摄像头已打开")
    print("提示: 按 'q' 退出，按 's' 保存截图")
    
    frame_count = 0
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # 检测
            detections = detector.detect(frame)
            
            # 绘制
            result = detector.draw_results(frame, detections)
            
            # 显示FPS
            frame_count += 1
            cv2.putText(result, f"Frames: {frame_count}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            cv2.imshow("PPE Detection Test", result)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                filename = f"ppe_capture_{frame_count}.jpg"
                cv2.imwrite(filename, result)
                print(f"✓ 截图已保存: {filename}")
        
        cap.release()
        cv2.destroyAllWindows()
        print(f"✓ 摄像头测试完成，共处理 {frame_count} 帧")
        return True
        
    except Exception as e:
        print(f"✗ 摄像头测试失败: {e}")
        cap.release()
        cv2.destroyAllWindows()
        return False


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("PPE 检测模型测试")
    print("=" * 60)
    print()
    
    # 测试1: 模型加载
    detector = test_model_loading()
    if detector is None:
        print("\n✗ 模型加载失败，停止测试")
        return 1
    
    # 测试2: 检测功能
    if not test_detection(detector):
        print("\n✗ 检测功能测试失败")
        return 1
    
    # 测试3: 摄像头测试（可选）
    print("\n是否测试摄像头? (y/n): ", end="")
    try:
        response = input().strip().lower()
        if response == 'y':
            test_with_camera(detector)
    except EOFError:
        # 非交互式环境，跳过摄像头测试
        print("非交互式环境，跳过摄像头测试")
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)
    print("\n现在你可以使用 PPE 检测模型了:")
    print("  from ppe_detector import PPEDetector")
    print("  detector = PPEDetector()")
    print("  detections = detector.detect(frame)")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
