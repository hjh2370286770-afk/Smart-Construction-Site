#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
预训练裂缝检测模型测试
使用多种方法进行裂缝检测验证
"""

import cv2
import numpy as np
import os
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 路径配置
DATASET_DIR = r"C:\Users\Admini503\.openclaw\workspace\dataset\wall_inspection\raw_frames"
OUTPUT_DIR = r"C:\Users\Admini503\.openclaw\workspace\dataset\wall_inspection\predictions"

class CrackDetector:
    """基于传统CV的裂缝检测器（无需预训练模型）"""
    
    def __init__(self):
        self.min_area = 50  # 最小裂缝面积
        self.max_area = 50000  # 最大裂缝面积
        
    def detect(self, image_path: str) -> tuple:
        """
        检测裂缝
        
        Returns:
            (annotated_image, cracks_info)
        """
        # 读取图像
        img = cv2.imread(image_path)
        if img is None:
            logger.error(f"无法读取图像: {image_path}")
            return None, []
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 1. 高斯模糊去噪
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # 2. 自适应阈值处理
        thresh = cv2.adaptiveThreshold(
            blurred, 255, 
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 11, 2
        )
        
        # 3. 形态学操作 - 去除小噪点
        kernel = np.ones((3, 3), np.uint8)
        morph = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)
        morph = cv2.morphologyEx(morph, cv2.MORPH_OPEN, kernel, iterations=1)
        
        # 4. Canny边缘检测
        edges = cv2.Canny(blurred, 50, 150)
        
        # 5. 查找轮廓
        contours, _ = cv2.findContours(
            morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        
        cracks = []
        result = img.copy()
        
        for i, cnt in enumerate(contours):
            area = cv2.contourArea(cnt)
            
            # 过滤太小或太大的区域
            if area < self.min_area or area > self.max_area:
                continue
            
            # 计算长宽比（裂缝通常是细长的）
            x, y, w, h = cv2.boundingRect(cnt)
            aspect_ratio = max(w, h) / (min(w, h) + 1e-5)
            
            # 裂缝特征：细长、面积适中
            if aspect_ratio > 3 and area > 100:
                # 获取最小外接矩形
                rect = cv2.minAreaRect(cnt)
                box = cv2.boxPoints(rect)
                box = np.int0(box)
                
                # 绘制检测结果
                cv2.drawContours(result, [box], 0, (0, 0, 255), 2)
                
                # 计算裂缝长度（近似）
                length = max(w, h)
                width = min(w, h)
                
                crack_info = {
                    'id': i,
                    'bbox': (x, y, w, h),
                    'area': area,
                    'length': length,
                    'width': width,
                    'aspect_ratio': aspect_ratio
                }
                cracks.append(crack_info)
                
                # 标注
                label = f"#{i} L:{length}px"
                cv2.putText(result, label, (x, y-5),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
        
        # 添加统计信息
        info_text = f"Cracks detected: {len(cracks)}"
        cv2.putText(result, info_text, (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        return result, cracks


class WallStateAnalyzer:
    """墙面状态分析器 - 半自动标注辅助"""
    
    def __init__(self):
        pass
    
    def analyze(self, image_path: str) -> dict:
        """
        分析墙面状态
        
        Returns:
            状态字典
        """
        img = cv2.imread(image_path)
        if img is None:
            return {}
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # 1. 亮度分析
        mean_brightness = np.mean(gray)
        brightness_std = np.std(gray)
        
        # 2. 颜色分析
        mean_hue = np.mean(hsv[:,:,0])
        mean_sat = np.mean(hsv[:,:,1])
        mean_val = np.mean(hsv[:,:,2])
        
        # 3. 纹理分析（使用Laplacian方差）
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        # 4. 边缘密度
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.sum(edges > 0) / (edges.shape[0] * edges.shape[1])
        
        # 5. 判断墙面状态
        wall_status = self._classify_wall_state(
            mean_brightness, brightness_std, 
            laplacian_var, edge_density
        )
        
        # 6. 判断施工阶段
        phase = self._classify_construction_phase(
            mean_brightness, mean_sat, edge_density
        )
        
        return {
            'brightness': mean_brightness,
            'brightness_std': brightness_std,
            'texture_complexity': laplacian_var,
            'edge_density': edge_density,
            'mean_hue': mean_hue,
            'mean_saturation': mean_sat,
            'wall_status': wall_status,
            'phase': phase
        }
    
    def _classify_wall_state(self, brightness, brightness_std, 
                            texture, edge_density) -> str:
        """分类墙面状态"""
        # 裸基层：较暗、纹理复杂
        if brightness < 80 and texture > 500:
            return 'bare'
        
        # 已涂层：较亮、较平滑
        if brightness > 120 and brightness_std < 40:
            return 'coated'
        
        # 网格布：有明显网格纹理
        if edge_density > 0.05 and texture > 1000:
            return 'meshed'
        
        return 'unknown'
    
    def _classify_construction_phase(self, brightness, saturation, 
                                     edge_density) -> str:
        """分类施工阶段"""
        # 喷涂中：表面湿润反光，饱和度较低
        if brightness > 100 and saturation < 30:
            return 'spraying'
        
        # 准备阶段：裸墙，高纹理
        if edge_density > 0.08:
            return 'preparation'
        
        # 完成阶段：较均匀
        if edge_density < 0.03:
            return 'finished'
        
        return 'unknown'


def main():
    """主函数 - 测试所有样本"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 初始化检测器
    crack_detector = CrackDetector()
    state_analyzer = WallStateAnalyzer()
    
    # 获取所有帧
    frame_files = sorted([f for f in os.listdir(DATASET_DIR) if f.endswith('.jpg')])
    
    logger.info(f"开始处理 {len(frame_files)} 帧图像...")
    
    results_summary = []
    
    for i, frame_file in enumerate(frame_files):
        frame_path = os.path.join(DATASET_DIR, frame_file)
        
        logger.info(f"[{i+1}/{len(frame_files)}] 处理: {frame_file}")
        
        # 1. 裂缝检测
        result_img, cracks = crack_detector.detect(frame_path)
        
        if result_img is None:
            continue
        
        # 2. 状态分析
        state = state_analyzer.analyze(frame_path)
        
        # 3. 保存结果
        output_path = os.path.join(OUTPUT_DIR, f"pred_{frame_file}")
        cv2.imwrite(output_path, result_img)
        
        # 4. 记录结果
        result_info = {
            'filename': frame_file,
            'crack_count': len(cracks),
            'cracks': cracks,
            'wall_state': state.get('wall_status', 'unknown'),
            'phase': state.get('phase', 'unknown'),
            'brightness': state.get('brightness', 0),
            'texture': state.get('texture_complexity', 0)
        }
        results_summary.append(result_info)
        
        logger.info(f"  检测到 {len(cracks)} 条裂缝, 状态: {state.get('wall_status', 'unknown')}")
    
    # 保存汇总结果
    import json
    summary_path = os.path.join(OUTPUT_DIR, 'detection_summary.json')
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(results_summary, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n处理完成!")
    logger.info(f"结果保存到: {OUTPUT_DIR}")
    logger.info(f"汇总报告: {summary_path}")
    
    # 统计
    total_cracks = sum(r['crack_count'] for r in results_summary)
    logger.info(f"\n统计:")
    logger.info(f"  总帧数: {len(frame_files)}")
    logger.info(f"  检测到裂缝总数: {total_cracks}")
    logger.info(f"  平均每帧裂缝数: {total_cracks/len(frame_files):.2f}")

if __name__ == "__main__":
    main()
