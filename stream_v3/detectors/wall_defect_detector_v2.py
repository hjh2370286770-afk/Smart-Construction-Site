"""
墙面缺陷检测器 - V2版本
基于用户反馈重新设计：
1. 设备状态判断：检测金属色工作模组的运动
2. 墙面状态识别：通过颜色判断（水泥色=未做，白色=已做）
3. 帧提取：增加密度
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
    area: float
    severity: str
    mask: Optional[np.ndarray] = None


@dataclass
class WallQuality:
    """墙面质量评估"""
    score: float  # 0-100
    defect_count: int
    crack_count: int
    stain_count: int
    unevenness_count: int
    coverage_ratio: float


@dataclass
class DeviceStatus:
    """设备状态"""
    status: str  # idle, working, moving
    confidence: float
    motion_ratio: float
    module_detected: bool  # 是否检测到工作模组


@dataclass
class WallState:
    """墙面施工状态"""
    state: str  # unfinished(水泥色), finished(白色/浅色), in_progress(施工中), no_wall(无墙面)
    cement_ratio: float  # 水泥色占比
    white_ratio: float  # 白色/浅色占比
    confidence: float


@dataclass
class SceneState:
    """场景状态"""
    scene_type: str  # wall_view(对着墙面), other(其他场景), unknown(未知)
    wall_coverage: float  # 墙面区域占比
    confidence: float


class WallDefectDetectorV2(BaseDetector):
    """
    墙面缺陷检测器 V2
    
    核心改进：
    1. 设备状态：基于金属色工作模组的运动检测
    2. 墙面状态：基于颜色分析（水泥灰 vs 白色）
    3. 缺陷检测：保留但降低权重
    """
    
    # 类别定义
    CLASS_NAMES = {
        0: 'crack',
        1: 'stain', 
        2: 'unevenness'
    }
    
    # 颜色阈值（HSV空间）
    # 水泥灰色范围（未完成）- 扩大范围，包含更多灰色调
    CEMENT_HSV_RANGE = {
        'lower': np.array([0, 0, 40]),   # 降低下限
        'upper': np.array([180, 80, 160])  # 提高上限，包含浅水泥色
    }
    
    # 白色/浅色范围（已完成）- 提高亮度阈值，避免误判水泥色
    WHITE_HSV_RANGE = {
        'lower': np.array([0, 0, 160]),  # 提高亮度阈值
        'upper': np.array([180, 40, 255])
    }
    
    # 工作模组颜色范围（白色立柱 + 黑色部件）
    # 白色机械臂
    MODULE_WHITE_RANGE = {
        'lower': np.array([0, 0, 160]),   # 降低亮度要求
        'upper': np.array([180, 60, 255])
    }
    # 黑色电缆/部件
    MODULE_BLACK_RANGE = {
        'lower': np.array([0, 0, 0]),
        'upper': np.array([180, 255, 80])  # 提高亮度上限
    }
    
    # 刮抹刀具颜色范围（金属色/银灰色）- 扩大检测范围
    TOOL_METAL_RANGE = {
        'lower': np.array([0, 0, 100]),    # 降低亮度下限
        'upper': np.array([180, 60, 220])  # 扩大饱和度范围
    }
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        self.model_type = config.get('model_type', 'segment')
        
        # 缺陷历史
        self.defect_history: deque = deque(maxlen=30)
        
        # 设备状态跟踪 - 基于工作模组运动
        self.device_status = "idle"
        self.status_history: deque = deque(maxlen=60)
        self.prev_frame: Optional[np.ndarray] = None
        self.prev_module_pos: Optional[Tuple[int, int]] = None  # 工作模组位置
        
        # 墙面状态历史
        self.wall_state_history: deque = deque(maxlen=30)
        self.current_wall_state = "unknown"
        
        # 场景状态
        self.scene_state_history: deque = deque(maxlen=10)
        self.current_scene = "unknown"  # wall_view, other, unknown
        
        # 日报统计
        self.daily_stats = {
            'start_time': time.time(),
            'working_time': 0,
            'idle_time': 0,
            'moving_time': 0,
            'total_defects': 0,
            'frames_processed': 0
        }
        
        logger.info("墙面缺陷检测器V2初始化完成")
        
    def _load_model(self):
        """加载 YOLOv8 模型"""
        try:
            from ultralytics import YOLO
            
            model_path = self.config.get('path', 'yolov8n-crack-seg.pt')
            logger.info(f"加载模型: {model_path}")
            self.model = YOLO(model_path)
            
            if self.device == 'auto':
                import torch
                self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
                
            logger.info(f"使用设备: {self.device}")
            
        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            raise
    
    def detect(self, frame: np.ndarray) -> List[Detection]:
        """执行检测"""
        if self.model is None:
            return []
            
        try:
            # 1. 检测墙面状态（颜色分析）
            wall_state = self._analyze_wall_state(frame)
            self.wall_state_history.append(wall_state)
            if len(self.wall_state_history) >= 5:
                self.current_wall_state = self._get_dominant_wall_state()
            
            # 2. 检测设备状态（基于工作模组运动）
            device_status = self._detect_device_status_v2(frame)
            self._update_device_stats(device_status)
            
            # 3. 缺陷检测（YOLO）
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
            
            if results.boxes is not None:
                for i, box in enumerate(results.boxes):
                    cls_id = int(box.cls)
                    conf = float(box.conf)
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    
                    class_name = self.CLASS_NAMES.get(cls_id, f"class_{cls_id}")
                    area = (x2 - x1) * (y2 - y1)
                    severity = self._calculate_severity(area)
                    
                    defect = WallDefect(
                        type=class_name,
                        bbox=(x1, y1, x2, y2),
                        confidence=conf,
                        area=area,
                        severity=severity,
                        mask=None
                    )
                    wall_defects.append(defect)
                    
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
                'wall_state': wall_state,
                'device_status': device_status
            })
            
            self.daily_stats['frames_processed'] += 1
            self.daily_stats['total_defects'] += len(wall_defects)
            
            return detections
            
        except Exception as e:
            logger.error(f"检测失败: {e}")
            return []
    
    def _detect_scene(self, frame: np.ndarray) -> SceneState:
        """
        检测当前场景类型
        
        判断是否在对着墙面：
        - 画面下半部分有连续的垂直/水平纹理（墙面特征）
        - 有明显的颜色分布（水泥色或白色）
        - 不是天空、地面或其他杂乱场景
        """
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        height, width = frame.shape[:2]
        
        # 取下半部分分析
        lower_region = hsv[int(height*0.3):, :]
        
        # 计算墙面特征像素（水泥色 + 白色）
        cement_mask = cv2.inRange(lower_region, 
                                   self.CEMENT_HSV_RANGE['lower'], 
                                   self.CEMENT_HSV_RANGE['upper'])
        white_mask = cv2.inRange(lower_region,
                                  self.WHITE_HSV_RANGE['lower'],
                                  self.WHITE_HSV_RANGE['upper'])
        
        wall_mask = cv2.bitwise_or(cement_mask, white_mask)
        wall_pixels = np.sum(wall_mask > 0)
        total_pixels = lower_region.shape[0] * lower_region.shape[1]
        wall_coverage = wall_pixels / total_pixels
        
        # 判断场景类型
        if wall_coverage > 0.4:  # 墙面占比超过40%
            scene_type = "wall_view"
            confidence = min(0.95, wall_coverage)
        elif wall_coverage > 0.15:  # 有部分墙面
            scene_type = "partial_wall"
            confidence = wall_coverage * 2
        else:
            scene_type = "other"  # 其他场景（天空、地面、室内等）
            confidence = 1 - wall_coverage
        
        return SceneState(
            scene_type=scene_type,
            wall_coverage=wall_coverage,
            confidence=confidence
        )
    
    def _analyze_wall_state(self, frame: np.ndarray) -> WallState:
        """
        分析墙面施工状态（基于颜色）
        
        判断依据：
        - 水泥灰色占比高 -> unfinished（未做）
        - 白色/浅色占比高 -> finished（已做）
        - 混合 -> in_progress（施工中）
        - 无墙面 -> no_wall
        """
        # 先检测场景
        scene = self._detect_scene(frame)
        self.scene_state_history.append(scene)
        
        # 更新场景状态（使用多数投票）
        if len(self.scene_state_history) >= 5:
            from collections import Counter
            scene_counts = Counter([s.scene_type for s in self.scene_state_history])
            self.current_scene = scene_counts.most_common(1)[0][0]
        
        # 如果不是对着墙面，返回无墙面状态
        if scene.scene_type == "other":
            return WallState(
                state="no_wall",
                cement_ratio=0,
                white_ratio=0,
                confidence=scene.confidence
            )
        
        # 转换到HSV色彩空间
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        
        # 创建墙面区域掩码（排除前景设备）
        height, width = frame.shape[:2]
        wall_region = hsv[int(height*0.3):, :]  # 取下半部分
        
        # 计算水泥色像素
        cement_mask = cv2.inRange(wall_region, 
                                   self.CEMENT_HSV_RANGE['lower'], 
                                   self.CEMENT_HSV_RANGE['upper'])
        cement_pixels = np.sum(cement_mask > 0)
        
        # 计算白色/浅色像素
        white_mask = cv2.inRange(wall_region,
                                  self.WHITE_HSV_RANGE['lower'],
                                  self.WHITE_HSV_RANGE['upper'])
        white_pixels = np.sum(white_mask > 0)
        
        total_pixels = wall_region.shape[0] * wall_region.shape[1]
        
        cement_ratio = cement_pixels / total_pixels
        white_ratio = white_pixels / total_pixels
        
        # 判断墙面状态
        if white_ratio > 0.6:
            state = "finished"  # 已完成（白色为主）
        elif cement_ratio > 0.5:
            state = "unfinished"  # 未做（水泥色为主）
        else:
            state = "in_progress"  # 施工中（混合）
        
        return WallState(
            state=state,
            cement_ratio=cement_ratio,
            white_ratio=white_ratio,
            confidence=min(0.95, max(cement_ratio, white_ratio))
        )
    
    def _detect_device_status_v2(self, frame: np.ndarray) -> DeviceStatus:
        """
        V2设备状态检测 - 基于刮抹刀具（金属色）的运动和墙面接触
        
        步骤：
        1. 检测金属色刮抹刀具
        2. 检测刀具与墙面的接触（刀具在墙面下半区域）
        3. 计算刀具位置变化
        4. 判断运动状态（working=接触墙面且移动）
        """
        # 转换到HSV
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        
        height, width = frame.shape[:2]
        
        # 定义区域
        upper_region = hsv[:int(height*0.5), :]  # 上半部分（机械臂）
        middle_region = hsv[int(height*0.2):int(height*0.7), :]  # 中上部分（刀具活动区域）
        
        # 检测金属色刀具（关键！）
        tool_mask = cv2.inRange(middle_region,
                                self.TOOL_METAL_RANGE['lower'],
                                self.TOOL_METAL_RANGE['upper'])
        
        # 形态学操作
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        tool_mask = cv2.morphologyEx(tool_mask, cv2.MORPH_CLOSE, kernel)
        tool_mask = cv2.morphologyEx(tool_mask, cv2.MORPH_OPEN, kernel)
        
        # 查找刀具轮廓
        contours, _ = cv2.findContours(tool_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        tool_detected = False
        tool_center = None
        tool_area = 0
        
        if contours:
            # 找最大的金属区域（刮抹刀具）
            largest_contour = max(contours, key=cv2.contourArea)
            tool_area = cv2.contourArea(largest_contour)
            
            # 过滤太小的区域（降低阈值）
            if tool_area > 200:  # 降低刀具面积阈值，更容易检测到
                tool_detected = True
                M = cv2.moments(largest_contour)
                if M["m00"] != 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"]) + int(height*0.2)  # 加上区域偏移
                    tool_center = (cx, cy)
        
        # 检测刀具是否与墙面接触（刀具在墙面区域）
        wall_contact = False
        if tool_detected and tool_center is not None:
            # 如果刀具在画面下半部分（墙面区域），认为接触墙面
            if tool_center[1] > height * 0.4:
                wall_contact = True
        
        # 计算运动
        motion_ratio = 0.0
        if tool_detected and self.prev_module_pos is not None and tool_center is not None:
            dx = tool_center[0] - self.prev_module_pos[0]
            dy = tool_center[1] - self.prev_module_pos[1]
            displacement = np.sqrt(dx**2 + dy**2)
            motion_ratio = displacement / width
        
        # 更新历史位置
        if tool_center is not None:
            self.prev_module_pos = tool_center
        
        # 状态判断（基于刀具运动和墙面接触）
        if not tool_detected:
            status = "idle"
            confidence = 0.5
        elif wall_contact and motion_ratio > 0.001:
            # 刀具接触墙面且移动 -> 工作中（降低阈值）
            status = "working"
            confidence = min(0.95, 0.7 + motion_ratio * 10)
        elif motion_ratio > 0.02:
            # 大幅移动但未接触墙面 -> 移动中（复位）（降低阈值）
            status = "moving"
            confidence = min(0.9, motion_ratio * 15)
        elif motion_ratio > 0.003:
            # 小幅移动（降低阈值）
            status = "moving" if not wall_contact else "working"
            confidence = min(0.85, motion_ratio * 20)
        else:
            # 静止
            status = "idle"
            confidence = 0.8
        
        self.prev_frame = frame.copy()
        
        return DeviceStatus(
            status=status,
            confidence=confidence,
            motion_ratio=motion_ratio,
            module_detected=tool_detected
        )
    
    def _update_device_stats(self, device_status: DeviceStatus):
        """更新设备状态统计"""
        current_time = time.time()
        
        self.status_history.append({
            'timestamp': current_time,
            'status': device_status.status,
            'motion_ratio': device_status.motion_ratio
        })
        
        self.device_status = device_status.status
        
        # 更新时间统计
        if len(self.status_history) > 1:
            time_delta = current_time - self.status_history[-2]['timestamp']
            if device_status.status == 'working':
                self.daily_stats['working_time'] += time_delta
            elif device_status.status == 'idle':
                self.daily_stats['idle_time'] += time_delta
            elif device_status.status == 'moving':
                self.daily_stats['moving_time'] += time_delta
    
    def _get_dominant_wall_state(self) -> str:
        """获取主导墙面状态"""
        from collections import Counter
        states = [s.state for s in self.wall_state_history]
        state_counts = Counter(states)
        return state_counts.most_common(1)[0][0]
    
    def _calculate_severity(self, area: float) -> str:
        """根据面积计算严重程度"""
        if area < 500:
            return 'low'
        elif area < 2000:
            return 'medium'
        else:
            return 'high'
    
    def check_violations(self, detections: List[Detection]) -> List[Dict]:
        """检查质量问题"""
        violations = []
        
        # 基于墙面状态判断
        if self.current_wall_state == "unfinished":
            violations.append({
                'type': 'unfinished_wall',
                'description': '墙面未完成施工（水泥色为主）',
                'severity': 'info',
                'wall_state': self.current_wall_state
            })
        
        # 严重缺陷检测
        if self.defect_history:
            current_defects = self.defect_history[-1]['defects']
            for defect in current_defects:
                if defect.severity == 'high':
                    violations.append({
                        'type': 'severe_defect',
                        'description': f'严重{defect.type}',
                        'severity': 'high',
                        'defect_type': defect.type
                    })
        
        return violations
    
    def get_wall_quality(self) -> WallQuality:
        """评估墙面质量"""
        if not self.defect_history:
            return WallQuality(score=100, defect_count=0, 
                             crack_count=0, stain_count=0, unevenness_count=0,
                             coverage_ratio=0.0)
        
        recent_frames = list(self.defect_history)[-5:]
        
        total_defects = 0
        crack_count = 0
        stain_count = 0
        unevenness_count = 0
        
        for frame_data in recent_frames:
            defects = frame_data['defects']
            total_defects += len(defects)
            for defect in defects:
                if defect.type == 'crack':
                    crack_count += 1
                elif defect.type == 'stain':
                    stain_count += 1
                elif defect.type == 'unevenness':
                    unevenness_count += 1
        
        # 质量分数
        base_score = 100
        defect_penalty = min(total_defects * 2, 40)
        score = max(0, base_score - defect_penalty)
        
        return WallQuality(
            score=score,
            defect_count=total_defects,
            crack_count=crack_count,
            stain_count=stain_count,
            unevenness_count=unevenness_count,
            coverage_ratio=0.0
        )
    
    def get_device_status(self) -> Dict[str, Any]:
        """获取设备状态统计"""
        current_time = time.time()
        elapsed = current_time - self.daily_stats['start_time']
        
        return {
            'current_status': self.device_status,
            'current_wall_state': self.current_wall_state,
            'working_time': self.daily_stats['working_time'],
            'idle_time': self.daily_stats['idle_time'],
            'moving_time': self.daily_stats['moving_time'],
            'working_ratio': self.daily_stats['working_time'] / elapsed if elapsed > 0 else 0,
            'frames_processed': self.daily_stats['frames_processed']
        }
    
    def generate_daily_report(self) -> Dict[str, Any]:
        """生成日报"""
        current_time = time.time()
        elapsed = current_time - self.daily_stats['start_time']
        
        quality = self.get_wall_quality()
        
        return {
            'report_time': current_time,
            'duration': elapsed,
            'device_status': {
                'working_time': self.daily_stats['working_time'],
                'idle_time': self.daily_stats['idle_time'],
                'moving_time': self.daily_stats['moving_time'],
                'working_ratio': self.daily_stats['working_time'] / elapsed if elapsed > 0 else 0
            },
            'wall_state': self.current_wall_state,
            'quality_summary': {
                'average_score': quality.score,
                'total_defects': self.daily_stats['total_defects']
            },
            'frames_processed': self.daily_stats['frames_processed']
        }
    
    def draw_results(self, frame: np.ndarray, detections: List[Detection],
                     show_labels: bool = True, show_conf: bool = True) -> np.ndarray:
        """绘制检测结果"""
        result = frame.copy()
        
        # 获取当前信息
        if self.defect_history:
            current = self.defect_history[-1]
            wall_state = current['wall_state']
            device_status = current['device_status']
        else:
            wall_state = WallState('unknown', 0, 0, 0)
            device_status = DeviceStatus('unknown', 0, 0, False)
        
        # 绘制缺陷
        if self.defect_history:
            for defect in self.defect_history[-1]['defects']:
                x1, y1, x2, y2 = defect.bbox
                color = (0, 0, 255) if defect.severity == 'high' else (0, 255, 255)
                cv2.rectangle(result, (x1, y1), (x2, y2), color, 2)
        
        # 绘制状态面板
        self._draw_status_panel(result, wall_state, device_status)
        
        return result
    
    def _draw_status_panel(self, frame: np.ndarray, wall_state: WallState, 
                           device_status: DeviceStatus):
        """绘制状态信息面板"""
        quality = self.get_wall_quality()
        
        # 面板背景
        panel_x, panel_y = 10, 10
        panel_w, panel_h = 320, 200
        cv2.rectangle(frame, (panel_x, panel_y), 
                     (panel_x + panel_w, panel_y + panel_h), 
                     (0, 0, 0), -1)
        cv2.rectangle(frame, (panel_x, panel_y), 
                     (panel_x + panel_w, panel_y + panel_h), 
                     (255, 255, 255), 1)
        
        # 状态文本
        lines = [
            f"=== 墙面检测V2 ===",
            f"",
            f"场景: {self.current_scene}",
            f"墙面状态: {wall_state.state}",
            f"  水泥色: {wall_state.cement_ratio*100:.1f}%",
            f"  白色: {wall_state.white_ratio*100:.1f}%",
            f"",
            f"设备状态: {device_status.status}",
            f"  模组检测: {'是' if device_status.module_detected else '否'}",
            f"  运动比例: {device_status.motion_ratio*100:.2f}%",
            f"",
            f"质量评分: {quality.score:.1f}",
            f"缺陷数量: {quality.defect_count}",
            f"",
            f"按 Q 退出, P 暂停"
        ]
        
        y_offset = panel_y + 25
        for line in lines:
            cv2.putText(frame, line, (panel_x + 10, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            y_offset += 16
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取检测统计信息"""
        quality = self.get_wall_quality()
        device_status = self.get_device_status()
        
        return {
            'quality': {
                'score': quality.score,
                'defect_count': quality.defect_count
            },
            'device': device_status,
            'wall_state': self.current_wall_state,
            'scene': self.current_scene
        }
