#!/usr/bin/env python3
"""
PPE 检测器集成示例
展示如何在 stream_manager 中使用新的 PPE 检测模型
"""

import sys
import cv2
import time
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from detectors.ppe_detector import PPEDetector


class SimplePPEMonitor:
    """简单的 PPE 监控示例"""
    
    def __init__(self, conf_threshold=0.4):
        """初始化监控器"""
        print("正在初始化 PPE 检测器...")
        self.detector = PPEDetector(conf_threshold=conf_threshold)
        print("✓ PPE 检测器初始化完成")
        
        # 违规统计
        self.violation_history = []
        self.frame_count = 0
        
    def process_video(self, source=0, display=True, save_output=None):
        """
        处理视频流
        
        Args:
            source: 视频源（0=摄像头，或视频文件路径）
            display: 是否显示实时画面
            save_output: 保存输出视频的路径（可选）
        """
        # 打开视频源
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            print(f"✗ 无法打开视频源: {source}")
            return
        
        # 获取视频信息
        fps = int(cap.get(cv2.CAP_PROP_FPS)) or 30
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        print(f"\n视频信息:")
        print(f"  分辨率: {width}x{height}")
        print(f"  FPS: {fps}")
        
        # 视频写入器（如果需要保存）
        writer = None
        if save_output:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(save_output, fourcc, fps, (width, height))
            print(f"  输出保存到: {save_output}")
        
        print("\n" + "=" * 60)
        print("PPE 监控已启动")
        print("=" * 60)
        print("按键说明:")
        print("  q - 退出")
        print("  s - 打印统计信息")
        print("  p - 暂停/继续")
        print("  f - 保存当前帧截图")
        print("=" * 60 + "\n")
        
        paused = False
        start_time = time.time()
        
        try:
            while True:
                if not paused:
                    ret, frame = cap.read()
                    if not ret:
                        print("视频结束")
                        break
                    
                    self.frame_count += 1
                    timestamp = time.time() - start_time
                    
                    # PPE 检测
                    detections = self.detector.detect(frame, timestamp)
                    
                    # 检查违规
                    for det in detections:
                        if not det.is_compliant:
                            self.violation_history.append({
                                'frame': self.frame_count,
                                'time': timestamp,
                                'track_id': det.track_id,
                                'violation': det.violation_type
                            })
                    
                    # 绘制结果
                    result = self.detector.draw_results(frame, detections)
                    
                    # 添加 FPS 信息
                    elapsed = time.time() - start_time
                    current_fps = self.frame_count / elapsed if elapsed > 0 else 0
                    cv2.putText(result, f"FPS: {current_fps:.1f}", (10, 30),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    
                    # 保存视频
                    if writer:
                        writer.write(result)
                    
                    # 显示
                    if display:
                        cv2.imshow("PPE Monitor", result)
                
                # 键盘控制
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('s'):
                    self.print_statistics()
                elif key == ord('p'):
                    paused = not paused
                    print("暂停" if paused else "继续")
                elif key == ord('f'):
                    filename = f"ppe_capture_{self.frame_count}.jpg"
                    cv2.imwrite(filename, result)
                    print(f"✓ 截图已保存: {filename}")
                    
        except KeyboardInterrupt:
            print("\n用户中断")
        finally:
            cap.release()
            if writer:
                writer.release()
            cv2.destroyAllWindows()
            
            # 打印最终统计
            self.print_statistics()
    
    def process_image(self, image_path, save_output=None):
        """
        处理单张图片
        
        Args:
            image_path: 图片路径
            save_output: 保存输出图片的路径（可选）
        """
        # 读取图片
        frame = cv2.imread(image_path)
        if frame is None:
            print(f"✗ 无法读取图片: {image_path}")
            return
        
        print(f"处理图片: {image_path}")
        
        # 检测
        detections = self.detector.detect(frame)
        
        # 绘制结果
        result = self.detector.draw_results(frame, detections)
        
        # 获取统计
        summary = self.detector.get_summary(detections)
        
        print("\n检测结果:")
        print(f"  总人数: {summary['total_persons']}")
        print(f"  合规人数: {summary['compliant']}")
        print(f"  合规率: {summary['compliance_rate']:.1%}")
        print(f"  违规情况: {summary['violations']}")
        
        # 显示
        cv2.imshow("PPE Detection", result)
        
        # 保存
        if save_output:
            cv2.imwrite(save_output, result)
            print(f"\n✓ 结果已保存: {save_output}")
        
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    
    def print_statistics(self):
        """打印统计信息"""
        print("\n" + "=" * 60)
        print("PPE 监控统计")
        print("=" * 60)
        print(f"总处理帧数: {self.frame_count}")
        print(f"历史违规记录: {len(self.violation_history)} 次")
        
        if self.violation_history:
            print("\n最近10次违规:")
            for v in self.violation_history[-10:]:
                print(f"  帧 {v['frame']} @ {v['time']:.1f}s - "
                      f"人员{v['track_id']}: {v['violation']}")
        print("=" * 60 + "\n")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='PPE 检测监控示例')
    parser.add_argument('--source', '-s', default='0',
                       help='视频源 (0=摄像头, 或视频文件路径, 或图片路径)')
    parser.add_argument('--conf', '-c', type=float, default=0.4,
                       help='置信度阈值 (默认: 0.4)')
    parser.add_argument('--output', '-o', default=None,
                       help='保存输出视频/图片的路径')
    parser.add_argument('--no-display', action='store_true',
                       help='不显示实时画面')
    
    args = parser.parse_args()
    
    # 创建监控器
    monitor = SimplePPEMonitor(conf_threshold=args.conf)
    
    # 解析视频源
    source = args.source
    if source == '0':
        source = 0  # 摄像头
    elif source.isdigit():
        source = int(source)
    
    # 判断是图片还是视频
    if isinstance(source, str) and source.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp')):
        # 处理图片
        monitor.process_image(source, args.output)
    else:
        # 处理视频/摄像头
        monitor.process_video(
            source=source,
            display=not args.no_display,
            save_output=args.output
        )


if __name__ == "__main__":
    main()
