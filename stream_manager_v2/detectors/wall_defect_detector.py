"""
墙面缺陷检测器
基于 YOLOv8-seg 的裂缝、污渍检测
继承自 BaseDetector
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from collections import deque
import time

import numpy as np
import cv2

from .base_detector import BaseDetector, Detection

logger = logging.getLogger(__name__)


@dataclass
class WallDefect:
    """墙面缺陷详情"""
    type: str  # crack, stain, unevenness
    bbox: Tuple[int, int, int, int]
    confidence: float
    area: float  # 缺陷面积（像素）
    severity: str  # low, medium, high
    mask: Optional[np.ndarray] = None  # 分割掩码（如果有）


@dataclass
class WallQuality:
    """墙面质量评估"""
    score: float  # 0-100
    defect_count: int
    crack_count: int
    stain_count: int
    unevenness_count: int
    coverage_ratio: float  # 缺陷覆盖比例


class WallDefectDetector(BaseDetector):
    """
    墙面缺陷检测器
    
    检测内容：
    - 裂缝 (crack)
    - 污渍 (stain)
    - 平整度问题 (unevenness)
    
    功能：
    - 缺陷检测（支持分割）
    - 质量评分
    - 缺陷跟踪（时序分析）
    - 施工阶段识别
    """
    
    # 类别定义
    CLASS_NAMES = {
        0: 'crack',
        1: 'stain',
        2: 'unevenness'
    }
    
    # 缺陷严重程度阈值（面积像素）
    SEVERITY_THRESHOLDS = {
        'low': 500,      # < 500px
        'medium': 2000,  # 500-2000px
        'high': float('inf')  # > 2000px
    }
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化墙面缺陷检测器
        
        Args:
            config: 配置字典
        """
        super().__init__(config)
        
        # 模型类型：检测或分割
        self.model_type = config.get('model_type', 'segment')  # 'detect' 或 'segment'
        
        # 缺陷历史（用于时序分析）
        self.defect_history: deque = deque(maxlen=30)  # 保存最近30帧
        
        # 施工阶段识别参数
        self.phase_history: deque = deque(maxlen=10)
        self.current_phase = "unknown"  # spraying, plastering, puttying, idle
        
        # 质量评分历史
        self.quality_history: deque = deque(maxlen=100)
        
        # 设备状态跟踪
        self.device_status = "idle"  # idle, working, moving
        self.status_history: deque = deque(maxlen=60)  # 1分钟状态历史（假设30fps）
        
        # 用于运动检测的前一帧
        self.prev_frame_gray: Optional[np.ndarray] = None
        self.motion_history: deque = deque(maxlen=10)  # 运动历史
        
        # 日报统计
        self.daily_stats = {
            'start_time': time.time(),
            'working_time': 0,
            'idle_time': 0,
            'moving_time': 0,
            'total_defects': 0,
            'frames_processed': 0
        }
        
        logger.info(f"墙面缺陷检测器初始化完成 (类型: {self.model_type})")
        
    def _load_model(self):
        """加载 YOLOv8 模型"""
        try:
            from ultralytics import YOLO
            
            model_path = self.config.get('path', 'yolov8n-crack-seg.pt')
            
            logger.info(f"加载模型: {model_path}")
            self.model = YOLO(model_path)
            
            # 设置设备
            if self.device == 'auto':
                import torch
                self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
                
            logger.info(f"使用设备: {self.device}")
            
        except ImportError:
            logger.error("未安装 ultralytics")
            raise
        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            raise
            
    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        执行墙面缺陷检测
        
        Args:
            frame: 输入图像 (BGR格式)
            
        Returns:
            检测结果列表
        """
        if self.model is None:
            logger.error("模型未加载")
            return []
            
        try:
            # 运行检测
            results = self.model(
                frame,
                conf=self.conf_threshold,
                iou=self.iou_threshold,
                imgsz=self.img_size,
                device=self.device,
                verbose=False
            )[0]
            
            detections = []
            wall_defects = []
            
            # 解析检测结果
            if results.boxes is not None:
                for i, box in enumerate(results.boxes):
                    cls_id = int(box.cls)
                    conf = float(box.conf)
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    
                    class_name = self.CLASS_NAMES.get(cls_id, f"class_{cls_id}")
                    
                    # 计算缺陷面积
                    area = (x2 - x1) * (y2 - y1)
                    
                    # 确定严重程度
                    severity = self._calculate_severity(area)
                    
                    # 获取掩码（如果是分割模型）
                    mask = None
                    if hasattr(results, 'masks') and results.masks is not None:
                        if i < len(results.masks):
                            # 正确获取掩码数据
                            mask_data = results.masks[i].data
                            if hasattr(mask_data, 'cpu'):
                                mask = mask_data.cpu().numpy()
                            else:
                                mask = np.array(mask_data)
                    
                    # 创建 WallDefect
                    defect = WallDefect(
                        type=class_name,
                        bbox=(x1, y1, x2, y2),
                        confidence=conf,
                        area=area,
                        severity=severity,
                        mask=mask
                    )
                    wall_defects.append(defect)
                    
                    # 创建 Detection（兼容基类）
                    detection = Detection(
                        bbox=(x1, y1, x2, y2),
                        class_id=cls_id,
                        class_name=class_name,
                        confidence=conf
                    )
                    detections.append(detection)
            
            # 更新历史
            self.defect_history.append({
                'timestamp': time.time(),
                'defects': wall_defects,
                'frame_shape': frame.shape
            })
            
            # 识别施工阶段
            self._detect_construction_phase(frame, wall_defects)
            
            # 更新设备状态
            self._update_device_status(frame, wall_defects)
            
            # 更新日报统计
            self.daily_stats['frames_processed'] += 1
            self.daily_stats['total_defects'] += len(wall_defects)
            
            return detections
            
        except Exception as e:
            logger.error(f"检测失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _calculate_severity(self, area: float) -> str:
        """根据面积计算严重程度"""
        if area < self.SEVERITY_THRESHOLDS['low']:
            return 'low'
        elif area < self.SEVERITY_THRESHOLDS['medium']:
            return 'medium'
        else:
            return 'high'
    
    def _detect_construction_phase(self, frame: np.ndarray, defects: List[WallDefect]):
        """
        识别施工阶段
        
        基于以下特征：
        - 喷涂阶段：大面积均匀覆盖，缺陷较少
        - 抹灰阶段：中等缺陷密度，有工具痕迹
        - 腻子阶段：精细处理，小缺陷多
        - 空闲：无明显施工活动
        """
        # 计算画面变化率（简化版）
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # 使用边缘密度判断施工活动
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.sum(edges > 0) / edges.size
        
        # 缺陷密度
        defect_density = len(defects) / (frame.shape[0] * frame.shape[1]) * 1000000  # 每百万像素
        
        # 判断阶段
        if edge_density < 0.05 and defect_density < 1:
            phase = "idle"
        elif edge_density > 0.15 and defect_density > 5:
            phase = "spraying"
        elif edge_density > 0.1 and 2 < defect_density < 8:
            phase = "plastering"
        elif defect_density > 3:
            phase = "puttying"
        else:
            phase = "working"
        
        self.phase_history.append(phase)
        
        # 使用多数投票确定当前阶段
        if len(self.phase_history) >= 5:
            from collections import Counter
            phase_counts = Counter(self.phase_history)
            self.current_phase = phase_counts.most_common(1)[0][0]
    
    def _update_device_status(self, frame: np.ndarray, defects: List[WallDefect]):
        """
        更新设备状态
        
        状态：
        - idle: 空闲（画面变化小，无施工活动）
        - working: 施工中（有缺陷检测，画面稳定）
        - moving: 移动中（画面剧烈变化，帧间差分大）
        """
        # 转换为灰度图
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # 如果有前一帧，计算帧间差分
        if self.prev_frame_gray is not None:
            # 计算帧间差分
            frame_diff = cv2.absdiff(self.prev_frame_gray, gray)
            
            # 二值化差分图像
            _, thresh = cv2.threshold(frame_diff, 30, 255, cv2.THRESH_BINARY)
            
            # 计算运动像素比例
            motion_pixels = np.sum(thresh > 0)
            total_pixels = thresh.size
            motion_ratio = motion_pixels / total_pixels
            
            # 计算运动强度（差分像素的平均值）
            motion_intensity = np.mean(frame_diff)
            
            self.motion_history.append({
                'ratio': motion_ratio,
                'intensity': motion_intensity
            })
            
            # 使用最近几帧的平均运动来判断状态
            if len(self.motion_history) >= 3:
                avg_motion_ratio = np.mean([m['ratio'] for m in self.motion_history])
                avg_motion_intensity = np.mean([m['intensity'] for m in self.motion_history])
                
                # 状态判断逻辑
                # moving: 运动比例 > 5% 或运动强度 > 15
                # idle: 运动比例 < 0.5% 且缺陷很少
                # working: 其他情况（有缺陷检测或轻微运动）
                if avg_motion_ratio > 0.05 or avg_motion_intensity > 15:
                    status = "moving"
                elif avg_motion_ratio < 0.005 and len(defects) < 1:
                    status = "idle"
                else:
                    status = "working"
            else:
                # 历史不足时，默认working
                status = "working"
        else:
            # 第一帧，默认working
            status = "working"
        
        # 保存当前帧用于下次比较
        self.prev_frame_gray = gray.copy()
        
        self.status_history.append({
            'timestamp': time.time(),
            'status': status,
            'defect_count': len(defects)
        })
        
        self.device_status = status
        
        # 更新日报统计
        current_time = time.time()
        if len(self.status_history) > 1:
            time_delta = current_time - self.status_history[-2]['timestamp']
            if status == 'working':
                self.daily_stats['working_time'] += time_delta
            elif status == 'idle':
                self.daily_stats['idle_time'] += time_delta
            elif status == 'moving':
                self.daily_stats['moving_time'] += time_delta
    
    def check_violations(self, detections: List[Detection]) -> List[Dict]:
        """
        检查质量问题（作为违规处理）
        
        Returns:
            质量问题列表
        """
        violations = []
        
        # 获取当前质量评估
        quality = self.get_wall_quality()
        
        # 质量分数低于阈值视为违规
        if quality.score < 60:
            violations.append({
                'type': 'poor_quality',
                'description': f'墙面质量较差，评分: {quality.score:.1f}',
                'severity': 'high' if quality.score < 40 else 'medium',
                'score': quality.score,
                'defect_count': quality.defect_count
            })
        
        # 严重缺陷检测
        for defect in self._get_current_defects():
            if defect.severity == 'high':
                violations.append({
                    'type': 'severe_defect',
                    'description': f'严重{defect.type}: 面积{defect.area}px',
                    'severity': 'high',
                    'defect_type': defect.type,
                    'area': defect.area,
                    'bbox': defect.bbox
                })
        
        return violations
    
    def _get_current_defects(self) -> List[WallDefect]:
        """获取当前帧的缺陷列表"""
        if self.defect_history:
            return self.defect_history[-1]['defects']
        return []
    
    def get_wall_quality(self) -> WallQuality:
        """
        评估墙面质量
        
        Returns:
            质量评估结果
        """
        if not self.defect_history:
            return WallQuality(score=100, defect_count=0, 
                             crack_count=0, stain_count=0, unevenness_count=0,
                             coverage_ratio=0.0)
        
        # 使用最近5帧的平均
        recent_frames = list(self.defect_history)[-5:]
        
        total_defects = 0
        crack_count = 0
        stain_count = 0
        unevenness_count = 0
        total_area = 0
        
        for frame_data in recent_frames:
            defects = frame_data['defects']
            total_defects += len(defects)
            
            for defect in defects:
                total_area += defect.area
                if defect.type == 'crack':
                    crack_count += 1
                elif defect.type == 'stain':
                    stain_count += 1
                elif defect.type == 'unevenness':
                    unevenness_count += 1
        
        # 计算覆盖率
        if recent_frames:
            frame_area = recent_frames[-1]['frame_shape'][0] * recent_frames[-1]['frame_shape'][1]
            coverage_ratio = (total_area / len(recent_frames)) / frame_area * 100
        else:
            coverage_ratio = 0
        
        # 计算质量分数 (0-100)
        # 基础分100，根据缺陷扣分
        base_score = 100
        defect_penalty = min(total_defects * 2, 40)  # 缺陷扣分，最多40
        coverage_penalty = min(coverage_ratio * 2, 30)  # 覆盖率扣分，最多30
        
        score = max(0, base_score - defect_penalty - coverage_penalty)
        
        quality = WallQuality(
            score=score,
            defect_count=total_defects,
            crack_count=crack_count,
            stain_count=stain_count,
            unevenness_count=unevenness_count,
            coverage_ratio=coverage_ratio
        )
        
        self.quality_history.append(quality)
        return quality
    
    def get_device_status(self) -> Dict[str, Any]:
        """
        获取设备状态统计
        
        Returns:
            设备状态信息
        """
        current_time = time.time()
        elapsed = current_time - self.daily_stats['start_time']
        
        return {
            'current_status': self.device_status,
            'current_phase': self.current_phase,
            'working_time': self.daily_stats['working_time'],
            'idle_time': self.daily_stats['idle_time'],
            'moving_time': self.daily_stats['moving_time'],
            'working_ratio': self.daily_stats['working_time'] / elapsed if elapsed > 0 else 0,
            'idle_ratio': self.daily_stats['idle_time'] / elapsed if elapsed > 0 else 0,
            'moving_ratio': self.daily_stats['moving_time'] / elapsed if elapsed > 0 else 0,
            'frames_processed': self.daily_stats['frames_processed'],
            'total_defects': self.daily_stats['total_defects']
        }
    
    def generate_daily_report(self) -> Dict[str, Any]:
        """
        生成日报
        
        Returns:
            日报数据
        """
        current_time = time.time()
        elapsed = current_time - self.daily_stats['start_time']
        
        # 计算平均质量
        avg_quality = 100
        if self.quality_history:
            avg_quality = sum(q.score for q in self.quality_history) / len(self.quality_history)
        
        report = {
            'report_time': current_time,
            'start_time': self.daily_stats['start_time'],
            'duration': elapsed,
            'device_status': {
                'working_time': self.daily_stats['working_time'],
                'idle_time': self.daily_stats['idle_time'],
                'moving_time': self.daily_stats['moving_time'],
                'working_ratio': self.daily_stats['working_time'] / elapsed if elapsed > 0 else 0
            },
            'quality_summary': {
                'average_score': avg_quality,
                'total_defects': self.daily_stats['total_defects'],
                'defects_per_frame': self.daily_stats['total_defects'] / self.daily_stats['frames_processed'] 
                                   if self.daily_stats['frames_processed'] > 0 else 0
            },
            'construction_phases': list(self.phase_history) if self.phase_history else [],
            'frames_processed': self.daily_stats['frames_processed']
        }
        
        return report
    
    def reset_daily_stats(self):
        """重置日报统计"""
        self.daily_stats = {
            'start_time': time.time(),
            'working_time': 0,
            'idle_time': 0,
            'moving_time': 0,
            'total_defects': 0,
            'frames_processed': 0
        }
        self.quality_history.clear()
        self.phase_history.clear()
    
    def draw_results(self, frame: np.ndarray, detections: List[Detection],
                     show_labels: bool = True, show_conf: bool = True) -> np.ndarray:
        """
        绘制检测结果（增强版）
        """
        result = frame.copy()
        
        # 获取当前缺陷详情
        defects = self._get_current_defects()
        
        # 绘制缺陷
        for defect in defects:
            x1, y1, x2, y2 = defect.bbox
            
            # 根据严重程度选择颜色
            if defect.severity == 'high':
                color = (0, 0, 255)  # 红色
            elif defect.severity == 'medium':
                color = (0, 165, 255)  # 橙色
            else:
                color = (0, 255, 255)  # 黄色
            
            # 绘制边界框
            cv2.rectangle(result, (x1, y1), (x2, y2), color, 2)
            
            # 绘制掩码（如果有）
            if defect.mask is not None:
                try:
                    # 确保掩码是2D数组
                    mask_2d = defect.mask
                    if len(mask_2d.shape) == 3:
                        mask_2d = mask_2d.squeeze()
                    
                    mask_resized = cv2.resize(mask_2d.astype(np.uint8), 
                                             (x2-x1, y2-y1))
                    mask_colored = np.zeros_like(result[y1:y2, x1:x2])
                    mask_colored[mask_resized > 0] = color
                    result[y1:y2, x1:x2] = cv2.addWeighted(
                        result[y1:y2, x1:x2], 0.7, mask_colored, 0.3, 0
                    )
                except Exception as e:
                    logger.debug(f"掩码绘制失败: {e}")
            
            # 绘制标签
            if show_labels:
                label = f"{defect.type}"
                if show_conf:
                    label += f" {defect.confidence:.2f}"
                label += f" [{defect.severity}]"
                
                (text_w, text_h), _ = cv2.getTextSize(
                    label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2
                )
                cv2.rectangle(
                    result,
                    (x1, y1 - text_h - 10),
                    (x1 + text_w, y1),
                    color, -1
                )
                cv2.putText(
                    result, label, (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2
                )
        
        # 绘制状态面板
        self._draw_status_panel(result)
        
        return result
    
    def _draw_status_panel(self, frame: np.ndarray):
        """绘制状态信息面板"""
        # 获取质量评估
        quality = self.get_wall_quality()
        device_status = self.get_device_status()
        
        # 面板背景
        panel_x, panel_y = 10, 10
        panel_w, panel_h = 280, 180
        cv2.rectangle(frame, (panel_x, panel_y), 
                     (panel_x + panel_w, panel_y + panel_h), 
                     (0, 0, 0), -1)
        cv2.rectangle(frame, (panel_x, panel_y), 
                     (panel_x + panel_w, panel_y + panel_h), 
                     (255, 255, 255), 1)
        
        # 状态文本
        lines = [
            f"=== 墙面检测 ===",
            f"质量评分: {quality.score:.1f}/100",
            f"缺陷数: {quality.defect_count} (裂缝:{quality.crack_count})",
            f"覆盖率: {quality.coverage_ratio:.2f}%",
            f"",
            f"施工阶段: {self.current_phase}",
            f"设备状态: {self.device_status}",
            f"工作时间: {device_status['working_time']:.0f}s",
            f"空闲时间: {device_status['idle_time']:.0f}s",
            f"",
            f"按 Q 退出, P 暂停"
        ]
        
        y_offset = panel_y + 25
        for line in lines:
            cv2.putText(frame, line, (panel_x + 10, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            y_offset += 16
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取检测统计信息
        """
        quality = self.get_wall_quality()
        device_status = self.get_device_status()
        
        return {
            'quality': {
                'score': quality.score,
                'defect_count': quality.defect_count,
                'crack_count': quality.crack_count,
                'stain_count': quality.stain_count,
                'coverage_ratio': quality.coverage_ratio
            },
            'device': device_status,
            'construction_phase': self.current_phase,
            'frames_processed': self.daily_stats['frames_processed']
        }
