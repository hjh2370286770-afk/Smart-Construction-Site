"""
stream_manager_v2 功能测试脚本
测试配置系统、检测器和向量记忆
"""

import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / 'utils'))
sys.path.insert(0, str(project_root / 'memory'))
sys.path.insert(0, str(project_root / 'detectors'))

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_config_system():
    """测试配置系统"""
    print("\n" + "="*60)
    print("测试1: 配置系统")
    print("="*60)
    
    try:
        from utils.config_loader import get_config
        
        config = get_config("./config")
        
        print("[OK] 配置加载成功")
        print(f"   - 站点数量: {len(config.sites)}")
        print(f"   - 模型数量: {len(config.models)}")
        
        # 显示站点信息
        for site in config.sites:
            print(f"\n   站点: {site.name} ({site.id})")
            print(f"   - 位置: {site.location}")
            print(f"   - 摄像头: {len(site.cameras)} 个")
            for cam in site.cameras:
                status = "启用" if cam.enabled else "禁用"
                print(f"     * {cam.name} [{status}]")
                print(f"       模型: {cam.models}")
        
        return True
    except Exception as e:
        print(f"[FAIL] 配置系统测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_detector_engine():
    """测试检测引擎"""
    print("\n" + "="*60)
    print("测试2: 检测引擎")
    print("="*60)
    
    try:
        from utils.config_loader import get_config
        from detectors.detector_engine import create_detector_engine
        
        config = get_config("./config")
        engine = create_detector_engine(config)
        
        print("[OK] 检测引擎创建成功")
        print(f"   - 已注册模型: {list(engine.model_configs.keys())}")
        
        # 显示模型信息
        for model_id in engine.model_configs:
            info = engine.get_model_info(model_id)
            if info:
                print(f"\n   模型: {info['name']} ({model_id})")
                print(f"   - 类型: {info['type']}")
                print(f"   - 类别: {info.get('classes', [])}")
        
        return True
    except Exception as e:
        print(f"[FAIL] 检测引擎测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_claw_memory():
    """测试 Claw 向量记忆"""
    print("\n" + "="*60)
    print("测试3: Claw 向量记忆系统")
    print("="*60)
    
    try:
        import sys
        sys.path.insert(0, '../memory')
        from claw_memory import get_claw_memory, remember_conversation, recall
        
        memory = get_claw_memory()
        
        print("[OK] 向量记忆系统初始化成功")
        print(f"   - 存储路径: {memory.db_path}")
        print(f"   - 模拟模式: {memory._mock_mode}")
        
        # 测试记住对话
        test_id = remember_conversation(
            "测试消息",
            "这是测试回复",
            {"test": True, "project": "stream_manager_v2"}
        )
        print(f"[OK] 记住对话: {test_id}")
        
        # 测试回忆
        results = recall("测试", top_k=3)
        print(f"[OK] 回忆检索: 找到 {len(results)} 条记忆")
        
        return True
    except Exception as e:
        print(f"[FAIL] 向量记忆测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ppe_detector_with_image():
    """使用测试图像测试 PPE 检测器"""
    print("\n" + "="*60)
    print("测试4: PPE 检测器（使用现有测试图像）")
    print("="*60)
    
    try:
        import cv2
        from utils.config_loader import get_config
        from detectors import PPEDetector
        
        # 查找测试图像
        test_image_paths = [
            project_root.parent / "stream_manager_solution2" / "ppe_monitor_output_solution2" / "violation_20260327_105104_ID1_NO_VEST.jpg",
            project_root.parent / "stream_manager" / "ppe_monitor_output_v2" / "violation_20260324_152235_ID1_NO_HELMET_NO_VEST.jpg",
        ]
        
        test_image = None
        for path in test_image_paths:
            if path.exists():
                test_image = str(path)
                break
        
        if test_image is None:
            print("[WARN] 未找到测试图像，跳过此测试")
            return True
        
        print(f"使用测试图像: {test_image}")
        
        # 加载图像
        frame = cv2.imread(test_image)
        if frame is None:
            print("[FAIL] 无法加载测试图像")
            return False
        
        print(f"图像尺寸: {frame.shape}")
        
        # 加载配置并创建检测器
        config = get_config("./config")
        model_config = config.get_model('ppe_detector')
        
        if model_config is None:
            print("[WARN] 未找到 PPE 模型配置")
            return True
        
        print("正在加载 PPE 检测器...")
        detector = PPEDetector(model_config.__dict__)
        
        print("执行检测...")
        detections = detector.detect(frame)
        
        print("[OK] 检测完成")
        print(f"   - 检测到 {len(detections)} 个目标")
        
        # 统计
        persons = [d for d in detections if d.class_name == 'person']
        helmets = [d for d in detections if d.class_name == 'helmet']
        vests = [d for d in detections if d.class_name == 'vest']
        
        print(f"   - 人员: {len(persons)}")
        print(f"   - 安全帽: {len(helmets)}")
        print(f"   - 反光衣: {len(vests)}")
        
        # 检查违规
        violations = detector.check_violations(detections)
        print(f"   - 违规: {len(violations)}")
        
        for v in violations:
            print(f"     * ID{v['person_id']}: {[vv['type'] for vv in v['violations']]}")
        
        # 保存结果图像
        result_frame = detector.draw_results(frame, detections)
        output_path = project_root / "test_output_ppe.jpg"
        cv2.imwrite(str(output_path), result_frame)
        print(f"[OK] 结果图像已保存: {output_path}")
        
        return True
    except Exception as e:
        print(f"[FAIL] PPE 检测器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_video_stream_processor():
    """测试视频流处理器（模拟）"""
    print("\n" + "="*60)
    print("测试5: 视频流处理器（模拟）")
    print("="*60)
    
    try:
        from utils.config_loader import get_config
        
        config = get_config("./config")
        enabled_cameras = config.get_enabled_cameras()
        
        print(f"[OK] 找到 {len(enabled_cameras)} 个启用的摄像头")
        
        for site, camera in enabled_cameras:
            print(f"\n   摄像头: {camera.name}")
            print(f"   - 站点: {site.name}")
            print(f"   - URL: {camera.url[:50]}...")
            print(f"   - 模型: {camera.models}")
        
        return True
    except Exception as e:
        print(f"[FAIL] 视频流处理器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """运行所有测试"""
    print("\n" + "="*60)
    print("stream_manager_v2 功能测试")
    print("="*60)
    
    results = {
        "配置系统": test_config_system(),
        "检测引擎": test_detector_engine(),
        "Claw向量记忆": test_claw_memory(),
        "PPE检测器": test_ppe_detector_with_image(),
        "视频流处理器": test_video_stream_processor(),
    }
    
    # 汇总结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "[OK] 通过" if result else "[FAIL] 失败"
        print(f"   {status}: {name}")
    
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n[OK] 所有测试通过!")
    else:
        print(f"\n[WARN] {total - passed} 项测试失败")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
