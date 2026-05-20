#!/usr/bin/env python3
"""
PPE 检测集成测试
验证 DetectorManager 和 PPE 检测器的集成
"""

import sys
import cv2
import time
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "detectors"))

from detectors.detector_manager import DetectorManager


def test_detector_manager():
    """测试 DetectorManager 的 PPE 检测功能"""
    print("=" * 70)
    print("DetectorManager PPE 检测集成测试")
    print("=" * 70)
    
    # 创建 DetectorManager
    manager = DetectorManager(models_dir="..")
    
    # 配置检测器
    configs = {
        "helmet": {"conf_threshold": 0.5},
        "vest": {"conf_threshold": 0.5},
        "ppe": {"conf_threshold": 0.4},
        "vehicle": {"conf_threshold": 0.5}
    }
    
    print("\n1. 初始化检测器...")
    manager.initialize(configs)
    print(f"✓ 已初始化检测器: {manager.list_detectors()}")
    
    # 创建测试图像
    print("\n2. 创建测试图像...")
    frame = create_test_image()
    print("✓ 测试图像创建完成")
    
    # 测试不同场景的检测
    scenes = [
        ("safety_helmet", "安全帽检测"),
        ("reflective_vest", "反光衣检测"),
        ("safety_equipment", "安全装备综合检测（颜色分析）"),
        ("ppe_detection", "PPE综合检测（专用模型）⭐"),
        ("construction_safety", "工地安全检测（PPE模型）⭐"),
    ]
    
    print("\n3. 测试各场景检测...")
    for scene_type, description in scenes:
        print(f"\n  测试: {description} ({scene_type})")
        
        try:
            result = manager.detect(frame, scene_type, timestamp=time.time())
            
            if result.get("success"):
                print(f"    ✓ 检测成功")
                print(f"      - 检测数量: {result.get('count', 0)}")
                
                if "compliance_rate" in result:
                    print(f"      - 合规率: {result['compliance_rate']:.1%}")
                if "violation_count" in result:
                    print(f"      - 违规数: {result['violation_count']}")
                    
                # 测试绘制
                drawn = manager.draw_results(frame.copy(), scene_type, result)
                if drawn is not None:
                    print(f"    ✓ 绘制成功")
            else:
                print(f"    ✗ 检测失败: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            print(f"    ✗ 异常: {e}")
    
    print("\n" + "=" * 70)
    print("测试完成!")
    print("=" * 70)
    
    return manager


def create_test_image():
    """创建测试图像（模拟工地场景）"""
    # 创建黑色背景
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # 绘制模拟人员1（戴安全帽、穿反光衣）
    # 身体
    cv2.rectangle(frame, (100, 200), (180, 400), (100, 100, 100), -1)
    # 头部
    cv2.ellipse(frame, (140, 170), (35, 30), 0, 0, 360, (80, 60, 40), -1)
    # 黄色安全帽
    cv2.ellipse(frame, (140, 155), (40, 25), 0, 0, 360, (0, 255, 255), -1)
    # 橙色反光衣
    cv2.rectangle(frame, (100, 220), (180, 350), (0, 100, 255), -1)
    # 反光条纹
    cv2.rectangle(frame, (100, 250), (180, 260), (220, 220, 220), -1)
    cv2.rectangle(frame, (100, 300), (180, 310), (220, 220, 220), -1)
    
    # 绘制模拟人员2（未戴安全帽、未穿反光衣）
    # 身体
    cv2.rectangle(frame, (400, 200), (480, 400), (100, 100, 100), -1)
    # 头部（裸头）
    cv2.ellipse(frame, (440, 170), (35, 30), 0, 0, 360, (80, 60, 40), -1)
    # 普通衣服（深色）
    cv2.rectangle(frame, (400, 220), (480, 350), (50, 50, 50), -1)
    
    return frame


def test_with_camera():
    """使用摄像头测试"""
    print("\n" + "=" * 70)
    print("摄像头实时测试")
    print("=" * 70)
    
    # 初始化
    manager = DetectorManager(models_dir="..")
    manager.initialize({
        "ppe": {"conf_threshold": 0.4}
    })
    
    # 打开摄像头
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("✗ 无法打开摄像头")
        return
    
    print("✓ 摄像头已打开")
    print("按键说明:")
    print("  1 - PPE检测模式（推荐）")
    print("  2 - 安全帽检测模式")
    print("  3 - 反光衣检测模式")
    print("  4 - 安全装备综合检测")
    print("  s - 打印统计信息")
    print("  q - 退出")
    print("=" * 70)
    
    current_scene = "ppe_detection"
    frame_count = 0
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            
            # 执行检测
            result = manager.detect(frame, current_scene, timestamp=time.time())
            
            # 绘制结果
            if result.get("success"):
                display = manager.draw_results(frame, current_scene, result)
                
                # 显示当前模式
                mode_text = f"Mode: {current_scene}"
                cv2.putText(display, mode_text, (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                # 显示统计
                if "compliance_rate" in result:
                    stats_text = f"Compliance: {result['compliance_rate']:.0%}"
                    cv2.putText(display, stats_text, (10, 60),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            else:
                display = frame.copy()
                cv2.putText(display, f"Error: {result.get('error')}", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            
            cv2.imshow("PPE Detection Test", display)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('1'):
                current_scene = "ppe_detection"
                print("切换到: PPE检测模式")
            elif key == ord('2'):
                current_scene = "safety_helmet"
                print("切换到: 安全帽检测模式")
            elif key == ord('3'):
                current_scene = "reflective_vest"
                print("切换到: 反光衣检测模式")
            elif key == ord('4'):
                current_scene = "safety_equipment"
                print("切换到: 安全装备综合检测")
            elif key == ord('s'):
                print(f"\n当前模式: {current_scene}")
                print(f"检测结果: {result.get('summary', {})}")
                
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print(f"\n共处理 {frame_count} 帧")


if __name__ == "__main__":
    import numpy as np
    
    # 运行基础测试
    test_detector_manager()
    
    # 询问是否测试摄像头
    print("\n是否测试摄像头? (y/n): ", end="")
    try:
        response = input().strip().lower()
        if response == 'y':
            test_with_camera()
    except EOFError:
        print("非交互式环境，跳过摄像头测试")
    
    print("\n✓ 所有测试完成!")
