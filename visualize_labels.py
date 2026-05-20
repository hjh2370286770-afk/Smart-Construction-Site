#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
半自动标注结果可视化工具
生成带标注的图像，方便人工审核
"""

import cv2
import numpy as np
import json
import os
from pathlib import Path

class LabelVisualizer:
    """标注可视化器"""
    
    def __init__(self):
        self.raw_frames_dir = r"C:\Users\Admini503\.openclaw\workspace\dataset\wall_inspection\raw_frames"
        self.labels_file = r"C:\Users\Admini503\.openclaw\workspace\dataset\wall_inspection\semi_auto_labels\semi_auto_labels.json"
        self.output_dir = r"C:\Users\Admini503\.openclaw\workspace\dataset\wall_inspection\semi_auto_labels\visualizations"
        
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 颜色定义
        self.colors = {
            'crack': (0, 0, 255),      # 红色 - 裂缝
            'stain': (0, 165, 255),    # 橙色 - 污渍
            'hollow': (255, 0, 0),     # 蓝色 - 空鼓
            'uneven': (255, 255, 0),   # 青色 - 不平整
            'mesh': (0, 255, 0),       # 绿色 - 网格布
            'text': (255, 255, 255),   # 白色 - 文字
            'info_bg': (50, 50, 50)    # 深灰 - 信息背景
        }
    
    def load_labels(self):
        """加载标注数据"""
        with open(self.labels_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data['suggestions']
    
    def visualize(self, image_path: str, label_data: dict) -> np.ndarray:
        """
        可视化单张图像的标注
        
        Args:
            image_path: 图像路径
            label_data: 标注数据
            
        Returns:
            可视化后的图像
        """
        img = cv2.imread(image_path)
        if img is None:
            return None
        
        result = img.copy()
        h, w = result.shape[:2]
        
        # 获取标注信息
        labels = label_data.get('suggested_labels', {})
        defects = labels.get('defects', [])
        
        # 绘制缺陷标注
        for i, defect in enumerate(defects):
            bbox = defect.get('bbox', [0, 0, 0, 0])
            defect_type = defect.get('type', 'unknown')
            confidence = defect.get('confidence', 0)
            
            x, y, bw, bh = bbox
            color = self.colors.get(defect_type, (128, 128, 128))
            
            # 绘制边界框
            cv2.rectangle(result, (x, y), (x+bw, y+bh), color, 2)
            
            # 绘制标签
            label = f"{defect_type} #{i} ({confidence:.1f})"
            (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
            
            # 标签背景
            cv2.rectangle(result, (x, y-text_h-4), (x+text_w, y), color, -1)
            cv2.putText(result, label, (x, y-2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, self.colors['text'], 1)
        
        # 绘制信息面板
        self._draw_info_panel(result, labels, len(defects))
        
        return result
    
    def _draw_info_panel(self, img: np.ndarray, labels: dict, defect_count: int):
        """绘制信息面板"""
        h, w = img.shape[:2]
        
        # 面板设置
        panel_height = 120
        panel_y = h - panel_height
        
        # 绘制半透明背景
        overlay = img.copy()
        cv2.rectangle(overlay, (0, panel_y), (w, h), self.colors['info_bg'], -1)
        cv2.addWeighted(overlay, 0.8, img, 0.2, 0, img)
        
        # 绘制文字信息
        phase = labels.get('phase', 'unknown')
        wall_status = labels.get('wall_status', 'unknown')
        equipment = labels.get('equipment_status', 'unknown')
        quality = labels.get('quality_score', 0)
        
        y_offset = panel_y + 25
        line_height = 22
        
        texts = [
            f"Phase: {phase} | Wall: {wall_status} | Equipment: {equipment}",
            f"Defects: {defect_count} | Quality Score: {quality}/100",
            "[REVIEW NEEDED] Press 'y' to confirm, 'n' to reject, 'q' to quit"
        ]
        
        for i, text in enumerate(texts):
            cv2.putText(img, text, (10, y_offset + i*line_height), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.colors['text'], 2)
    
    def process_all(self):
        """处理所有图像"""
        suggestions = self.load_labels()
        
        print(f"开始可视化 {len(suggestions)} 张图像...")
        
        for i, suggestion in enumerate(suggestions):
            filename = suggestion['filename']
            image_path = os.path.join(self.raw_frames_dir, filename)
            
            print(f"[{i+1}/{len(suggestions)}] 处理: {filename}")
            
            result = self.visualize(image_path, suggestion)
            if result is not None:
                output_path = os.path.join(self.output_dir, f"labeled_{filename}")
                cv2.imwrite(output_path, result)
        
        print(f"\n可视化完成!")
        print(f"结果保存到: {self.output_dir}")
    
    def interactive_review(self):
        """
        交互式审核模式
        允许用户查看并确认/修改标注
        """
        suggestions = self.load_labels()
        
        print("\n交互式审核模式")
        print("按键说明:")
        print("  'y' - 确认当前标注")
        print("  'n' - 拒绝当前标注（标记为需重新标注）")
        print("  's' - 跳过当前图像")
        print("  'q' - 退出")
        print()
        
        review_results = []
        
        for i, suggestion in enumerate(suggestions):
            filename = suggestion['filename']
            image_path = os.path.join(self.raw_frames_dir, filename)
            
            result = self.visualize(image_path, suggestion)
            if result is None:
                continue
            
            cv2.imshow('Semi-Auto Labeling Review', result)
            
            print(f"[{i+1}/{len(suggestions)}] {filename}")
            print(f"  建议: phase={suggestion['suggested_labels'].get('phase')}, "
                  f"defects={len(suggestion['suggested_labels'].get('defects', []))}")
            
            key = cv2.waitKey(0) & 0xFF
            
            if key == ord('y'):
                suggestion['review_status'] = 'confirmed'
                print("  -> 已确认")
            elif key == ord('n'):
                suggestion['review_status'] = 'rejected'
                print("  -> 已拒绝")
            elif key == ord('s'):
                suggestion['review_status'] = 'skipped'
                print("  -> 已跳过")
            elif key == ord('q'):
                print("  -> 退出")
                break
            
            review_results.append(suggestion)
        
        cv2.destroyAllWindows()
        
        # 保存审核结果
        output_file = os.path.join(self.output_dir, 'review_results.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                'reviewed_at': str(datetime.now()),
                'total': len(suggestions),
                'reviewed': len(review_results),
                'results': review_results
            }, f, indent=2, ensure_ascii=False)
        
        print(f"\n审核结果已保存: {output_file}")


def main():
    """主函数"""
    visualizer = LabelVisualizer()
    
    # 生成所有可视化图像
    visualizer.process_all()
    
    # 如果需要交互式审核，取消下面注释
    # visualizer.interactive_review()

if __name__ == "__main__":
    from datetime import datetime
    main()
