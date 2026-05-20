#!/usr/bin/env python3
"""
校准墙面颜色阈值
通过视频流实时观察水泥色和白色的HSV值
"""

import cv2
import numpy as np
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def analyze_wall_color(frame):
    """分析墙面颜色分布"""
    # 转换到HSV
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    
    # 取下半部分作为墙面区域
    height, width = frame.shape[:2]
    wall_region = hsv[int(height*0.3):, :]
    
    # 计算平均HSV值
    avg_h = np.mean(wall_region[:,:,0])
    avg_s = np.mean(wall_region[:,:,1])
    avg_v = np.mean(wall_region[:,:,2])
    
    # 计算亮度分布
    v_channel = wall_region[:,:,2]
    dark_pixels = np.sum(v_channel < 80)  # 深色（水泥）
    mid_pixels = np.sum((v_channel >= 80) & (v_channel < 150))  # 中色
    bright_pixels = np.sum(v_channel >= 150)  # 亮色（已做）
    total = wall_region.shape[0] * wall_region.shape[1]
    
    return {
        'avg_h': avg_h,
        'avg_s': avg_s,
        'avg_v': avg_v,
        'dark_ratio': dark_pixels / total,
        'mid_ratio': mid_pixels / total,
        'bright_ratio': bright_pixels / total
    }


def main():
    # 视频流地址
    stream_url = "rtmp://49.235.101.158/live/JHMH2511011001"
    
    logger.info(f"连接到视频流: {stream_url}")
    cap = cv2.VideoCapture(stream_url)
    
    if not cap.isOpened():
        logger.error("无法打开视频流")
        return
    
    logger.info("按 'q' 退出，按 's' 保存当前帧颜色分析")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            logger.warning("无法读取帧")
            continue
        
        # 分析颜色
        color_info = analyze_wall_color(frame)
        
        # 在画面上显示信息
        info_lines = [
            f"Avg HSV: ({color_info['avg_h']:.1f}, {color_info['avg_s']:.1f}, {color_info['avg_v']:.1f})",
            f"Dark (<80): {color_info['dark_ratio']*100:.1f}% (Cement)",
            f"Mid (80-150): {color_info['mid_ratio']*100:.1f}%",
            f"Bright (>150): {color_info['bright_ratio']*100:.1f}% (Finished)",
            "",
            "Press 'q' to quit, 's' to save analysis"
        ]
        
        y_offset = 30
        for line in info_lines:
            cv2.putText(frame, line, (10, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            y_offset += 25
        
        # 显示画面
        cv2.imshow("Wall Color Calibration", frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            logger.info(f"颜色分析: H={color_info['avg_h']:.1f}, S={color_info['avg_s']:.1f}, V={color_info['avg_v']:.1f}")
            logger.info(f"  深色(水泥): {color_info['dark_ratio']*100:.1f}%")
            logger.info(f"  亮色(已做): {color_info['bright_ratio']*100:.1f}%")
    
    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
