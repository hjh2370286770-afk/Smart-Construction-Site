"""
墙面缺陷检测测试脚本
测试视频流: rtmp://49.235.101.158/live/JHMH2411005018
测试时长: 5分钟
"""

import asyncio
import logging
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from core.stream_processor import VideoStreamProcessor, StreamConfig
from detectors.wall_defect_detector_v2 import WallDefectDetectorV2

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# 检测器配置 - V2版本
WALL_DEFECT_CONFIG = {
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


async def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("墙面缺陷检测测试")
    logger.info("=" * 60)
    
    # 创建输出目录
    output_dir = Path('./output/wall_defect_test')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建检测器
    logger.info("初始化检测器V2...")
    try:
        detector = WallDefectDetectorV2(WALL_DEFECT_CONFIG)
        logger.info("检测器V2初始化成功!")
    except Exception as e:
        logger.error(f"检测器初始化失败: {e}")
        return
    
    # 创建流配置
    stream_config = StreamConfig(
        camera_id='JHMH2411005018',
        name='墙面检测摄像头',
        url='rtmp://49.235.101.158/live/JHMH2411005018',
        stream_type='rtmp',
        enabled=True,
        fps=25,
        resolution=(960, 540),
        frame_skip=3  # 每3帧检测一次
    )
    
    # 事件回调
    async def event_callback(event):
        if event['type'] == 'violation':
            logger.warning(f"检测到质量问题: {event['data']}")
        elif event['type'] == 'status':
            stats = event['data']['stats']
            logger.info(
                f"状态更新 - 帧: {stats['frame_count']}, "
                f"FPS: {stats['fps']:.1f}, "
                f"检测: {stats['detection_count']}, "
                f"违规: {stats['violation_count']}"
            )
    
    # 创建处理器
    processor = VideoStreamProcessor(
        config=stream_config,
        detector=detector,
        output_dir=output_dir,
        event_callback=event_callback,
        enable_display=True
    )
    
    # 启动处理
    logger.info(f"开始处理视频流: {stream_config.url}")
    logger.info("按 Q 退出，按 P 暂停/继续")
    
    # 测试时长：5分钟
    TEST_DURATION = 300  # 秒
    start_time = asyncio.get_event_loop().time()
    last_status_time = start_time
    
    try:
        await processor.start()
        
        # 运行5分钟
        while processor.running:
            await asyncio.sleep(1)
            
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - start_time
            
            # 每10秒打印一次设备状态
            if current_time - last_status_time >= 10:
                last_status_time = current_time
                device_status = detector.get_device_status()
                quality = detector.get_wall_quality()
                stats = detector.get_statistics()
                
                logger.info("-" * 50)
                logger.info(f"[{(elapsed/60):.1f}分钟] 场景: {stats['scene']} | 墙面: {stats['wall_state']}")
                logger.info(f"  设备状态: {device_status['current_status']}")
                logger.info(f"  工作时间: {device_status['working_time']:.0f}s | 空闲: {device_status['idle_time']:.0f}s | 移动: {device_status['moving_time']:.0f}s")
                logger.info(f"  质量评分: {quality.score:.1f} | 缺陷数: {quality.defect_count} | FPS: {processor.stats.fps:.1f}")
                logger.info("-" * 50)
            
            # 5分钟后自动停止
            if elapsed >= TEST_DURATION:
                logger.info(f"\n测试时间达到 {TEST_DURATION/60} 分钟，自动停止...")
                break
        
    except KeyboardInterrupt:
        logger.info("用户中断")
    finally:
        # 停止处理
        await processor.stop()
        
        # 生成日报
        report = detector.generate_daily_report()
        stats = detector.get_statistics()
        logger.info("=" * 60)
        logger.info("测试报告 - V2检测器")
        logger.info("=" * 60)
        logger.info(f"运行时间: {report['duration']:.1f}秒")
        logger.info(f"处理帧数: {report['frames_processed']}")
        logger.info(f"场景分布: {stats.get('scene', 'unknown')}")
        logger.info(f"墙面状态: {report['wall_state']}")
        logger.info(f"平均质量: {report['quality_summary']['average_score']:.1f}")
        logger.info(f"总缺陷数: {report['quality_summary']['total_defects']}")
        logger.info(f"工作时间: {report['device_status']['working_time']:.1f}秒")
        logger.info(f"空闲时间: {report['device_status']['idle_time']:.1f}秒")
        logger.info(f"移动时间: {report['device_status']['moving_time']:.1f}秒")
        logger.info(f"工作占比: {report['device_status']['working_ratio']*100:.1f}%")
        logger.info("=" * 60)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"程序异常: {e}")
        import traceback
        traceback.print_exc()
