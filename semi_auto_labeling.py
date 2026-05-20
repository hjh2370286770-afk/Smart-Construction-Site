#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
半自动标注工具 - 结合传统CV和深度学习
用于生成初步标注，人工审核后作为训练数据
"""

import cv2
import numpy as np
import os
import json
from pathlib import Path
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SemiAutoLabeling:
    """半自动标注系统"""
    
    def __init__(self):
        self.output_dir = r"C:\Users\Admini503\.openclaw\workspace\dataset\wall_inspection\semi_auto_labels"
        os.makedirs(self.output_dir, exist_ok=True)
        
    def analyze_and_suggest(self, image_path: str) -> dict:
        """
        分析图像并生成标注建议
        
        Returns:
            包含建议标注的字典
        """
        img = cv2.imread(image_path)
        if img is None:
            return {}
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        suggestions = {
            'filename': os.path.basename(image_path),
            'suggested_labels': {
                'phase': self._suggest_phase(img, gray, hsv),
                'wall_status': self._suggest_wall_status(img, gray, hsv),
                'equipment_status': self._suggest_equipment_status(img, gray),
                'defects': self._suggest_defects(img, gray),
                'quality_score': self._estimate_quality_score(img, gray)
            },
            'confidence': {},
            'needs_review': True,  # 所有建议都需要人工审核
            'review_notes': []
        }
        
        # 计算各建议的置信度
        for key, value in suggestions['suggested_labels'].items():
            if key == 'defects':
                suggestions['confidence'][key] = 0.6  # 缺陷检测置信度较低
            elif key == 'quality_score':
                suggestions['confidence'][key] = 0.5
            else:
                suggestions['confidence'][key] = 0.7
        
        # 添加审核建议
        if suggestions['suggested_labels']['defects']:
            suggestions['review_notes'].append(
                f"检测到 {len(suggestions['suggested_labels']['defects'])} 个潜在缺陷，请人工确认"
            )
        
        return suggestions
    
    def _suggest_phase(self, img, gray, hsv) -> str:
        """建议施工阶段"""
        # 分析亮度分布
        mean_v = np.mean(hsv[:,:,2])
        mean_s = np.mean(hsv[:,:,1])
        
        # 分析纹理
        lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        # 分析边缘密度
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.sum(edges > 0) / (edges.shape[0] * edges.shape[1])
        
        # 判断逻辑
        if edge_density > 0.08 and mean_v < 100:
            return 'preparation'  # 准备阶段：高纹理、较暗
        elif mean_v > 120 and mean_s < 40 and lap_var < 500:
            return 'spraying'  # 喷涂阶段：较亮、低饱和度、较平滑
        elif edge_density < 0.03 and mean_v > 100:
            return 'finished'  # 完成阶段：低边缘密度、均匀
        else:
            return 'unknown'
    
    def _suggest_wall_status(self, img, gray, hsv) -> str:
        """建议墙面状态"""
        mean_v = np.mean(hsv[:,:,2])
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.sum(edges > 0) / (edges.shape[0] * edges.shape[1])
        
        # 检测网格纹理（使用霍夫变换检测直线）
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, 50, minLineLength=50, maxLineGap=10)
        grid_like = False
        if lines is not None and len(lines) > 20:
            # 检查是否有大量平行线（网格特征）
            angles = []
            for line in lines:
                x1, y1, x2, y2 = line[0]
                angle = np.abs(np.arctan2(y2-y1, x2-x1) * 180 / np.pi)
                angles.append(angle)
            # 如果有很多接近0或90度的线，可能是网格
            vertical = sum(1 for a in angles if a < 20 or a > 160)
            horizontal = sum(1 for a in angles if 70 < a < 110)
            if vertical > 10 and horizontal > 10:
                grid_like = True
        
        if grid_like and edge_density > 0.05:
            return 'meshed'  # 已铺网格布
        elif mean_v < 80:
            return 'bare'  # 裸基层
        elif mean_v > 120 and edge_density < 0.05:
            return 'coated'  # 已涂层
        else:
            return 'unknown'
    
    def _suggest_equipment_status(self, img, gray) -> str:
        """建议设备状态"""
        # 检测图像中的运动模糊（表示移动）
        blur_metric = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        # 检测是否有喷涂雾状特征
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        # 喷涂时通常有白色/灰色雾状区域
        lower_gray = np.array([0, 0, 150])
        upper_gray = np.array([180, 50, 255])
        spray_mask = cv2.inRange(hsv, lower_gray, upper_gray)
        spray_ratio = np.sum(spray_mask > 0) / spray_mask.size
        
        if spray_ratio > 0.1:
            return 'spraying'  # 正在喷涂
        elif blur_metric < 100:
            return 'moving'  # 移动中（模糊）
        else:
            return 'idle'  # 待机
    
    def _suggest_defects(self, img, gray) -> list:
        """建议缺陷（改进版，减少误检）"""
        defects = []
        
        # 1. 裂缝检测（改进算法）
        cracks = self._detect_cracks_improved(img, gray)
        for crack in cracks:
            defects.append({
                'type': 'crack',
                'bbox': crack['bbox'],
                'confidence': crack['confidence'],
                'notes': f"长度:{crack['length']}px, 宽度:{crack['width']}px"
            })
        
        # 2. 污渍检测
        stains = self._detect_stains(img, gray)
        for stain in stains:
            defects.append({
                'type': 'stain',
                'bbox': stain['bbox'],
                'confidence': stain['confidence'],
                'notes': '颜色异常区域'
            })
        
        return defects
    
    def _detect_cracks_improved(self, img, gray) -> list:
        """改进的裂缝检测算法"""
        cracks = []
        
        # 1. 预处理
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        
        # 2. 黑帽变换（提取暗线）
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        blackhat = cv2.morphologyEx(blurred, cv2.MORPH_BLACKHAT, kernel)
        
        # 3. 阈值分割
        _, thresh = cv2.threshold(blackhat, 10, 255, cv2.THRESH_BINARY)
        
        # 4. 查找轮廓
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 20 or area > 5000:  # 过滤太小或太大的区域
                continue
            
            x, y, w, h = cv2.boundingRect(cnt)
            aspect_ratio = max(w, h) / (min(w, h) + 1e-5)
            
            # 裂缝特征：细长、不规则
            if aspect_ratio > 4:
                # 计算轮廓的圆形度（裂缝应该是不规则的）
                perimeter = cv2.arcLength(cnt, True)
                circularity = 4 * np.pi * area / (perimeter ** 2 + 1e-5)
                
                # 裂缝通常圆形度较低（细长）
                if circularity < 0.3:
                    # 检查是否在墙面区域（排除电缆等区域）
                    roi = gray[y:y+h, x:x+w]
                    if roi.size > 0:
                        roi_mean = np.mean(roi)
                        roi_std = np.std(roi)
                        
                        # 裂缝区域通常较暗且对比度较高
                        if roi_mean < 100 and roi_std > 30:
                            cracks.append({
                                'bbox': [x, y, w, h],
                                'confidence': min(0.9, aspect_ratio / 10),
                                'length': max(w, h),
                                'width': min(w, h)
                            })
        
        return cracks
    
    def _detect_stains(self, img, gray) -> list:
        """检测污渍"""
        stains = []
        
        # 使用颜色异常检测
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # 检测褐色/黄色污渍
        lower_brown = np.array([10, 50, 50])
        upper_brown = np.array([30, 255, 200])
        brown_mask = cv2.inRange(hsv, lower_brown, upper_brown)
        
        contours, _ = cv2.findContours(brown_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 100:
                x, y, w, h = cv2.boundingRect(cnt)
                stains.append({
                    'bbox': [x, y, w, h],
                    'confidence': 0.6,
                    'type': 'brown_stain'
                })
        
        return stains
    
    def _estimate_quality_score(self, img, gray) -> int:
        """估计质量分数（0-100）"""
        # 基于多个指标综合评分
        scores = []
        
        # 1. 亮度均匀性
        brightness_std = np.std(gray)
        brightness_score = max(0, 100 - brightness_std)
        scores.append(brightness_score)
        
        # 2. 纹理平滑度
        lap_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        texture_score = max(0, 100 - lap_var / 50)
        scores.append(texture_score)
        
        # 3. 缺陷扣分
        defects = self._suggest_defects(img, gray)
        defect_penalty = len(defects) * 5  # 每个缺陷扣5分
        
        final_score = int(np.mean(scores) - defect_penalty)
        return max(0, min(100, final_score))
    
    def process_dataset(self):
        """处理整个数据集"""
        raw_frames_dir = r"C:\Users\Admini503\.openclaw\workspace\dataset\wall_inspection\raw_frames"
        
        frame_files = sorted([f for f in os.listdir(raw_frames_dir) if f.endswith('.jpg')])
        
        logger.info(f"开始处理 {len(frame_files)} 帧图像...")
        
        all_suggestions = []
        
        for i, frame_file in enumerate(frame_files):
            frame_path = os.path.join(raw_frames_dir, frame_file)
            
            logger.info(f"[{i+1}/{len(frame_files)}] 分析: {frame_file}")
            
            suggestion = self.analyze_and_suggest(frame_path)
            all_suggestions.append(suggestion)
            
            # 打印关键建议
            labels = suggestion.get('suggested_labels', {})
            logger.info(f"  阶段: {labels.get('phase', 'unknown')}, "
                       f"墙面: {labels.get('wall_status', 'unknown')}, "
                       f"缺陷: {len(labels.get('defects', []))}个, "
                       f"质量分: {labels.get('quality_score', 0)}")
        
        # 保存所有建议
        output_file = os.path.join(self.output_dir, 'semi_auto_labels.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                'created_at': datetime.now().isoformat(),
                'total_frames': len(frame_files),
                'suggestions': all_suggestions,
                'note': '所有标注建议都需要人工审核确认'
            }, f, indent=2, ensure_ascii=False)
        
        logger.info(f"\n半自动标注完成!")
        logger.info(f"结果保存到: {output_file}")
        logger.info(f"请人工审核后，将确认的结果更新到 metadata.json")
        
        return all_suggestions


def main():
    """主函数"""
    labeler = SemiAutoLabeling()
    labeler.process_dataset()

if __name__ == "__main__":
    main()
