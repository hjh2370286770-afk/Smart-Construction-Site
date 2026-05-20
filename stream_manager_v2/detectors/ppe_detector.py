#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PPE 检测器 - 使用验证过的检测逻辑
基于 stream_manager/detectors/ppe_detector.py
"""

import logging
from typing import List, Dict, Optional, Any
from pathlib import Path

import numpy as np
import cv2

from .base_detector import BaseDetector, Detection

logger = logging.getLogger(__name__)


class PPEDetector(BaseDetector):
    """
    PPE (Personal Protective Equipment) 检测器
    
    使用专门的工地安全检测模型，类别包括：
    - Hardhat (安全帽)
    - NO-Hardhat (未戴安全帽)
    - Safety Vest (反光衣/安全背心)
    - NO-Safety Vest (未穿反光衣)
    - Mask (口罩)
    - NO-Mask (未戴口罩)
    - Person (人员)
    """
    
    # 类别名称映射（根据模型训练时的类别）
    CLASS_NAMES = {
        0: 'Hardhat',
        1: 'Mask', 
        2: 'NO-Hardhat',
        3: 'NO-Mask',
        4: 'NO-Safety Vest',
        5: 'Person',
        6: 'Safety Cone',
        7: 'Safety Vest',
        8: 'machinery',
        9: 'vehicle'
    }
    
    # 类别分组
    HELMET_CLASSES = ['Hardhat']
    NO_HELMET_CLASSES = ['NO-Hardhat']
    VEST_CLASSES = ['Safety Vest']
    NO_VEST_CLASSES = ['NO-Safety Vest']
    MASK_CLASSES = ['Mask']
    NO_MASK_CLASSES = ['NO-Mask']
    PERSON_CLASSES = ['Person']
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化 PPE 检测器
        
        Args:
            config: 配置字典，包含模型路径、类别、参数等
        """
        super().__init__(config)
        
        # 跟踪相关
        self.next_track_id = 1
        self.tracks: Dict[int, Dict] = {}
        self.track_max_age = 30  # 最大丢失帧数
        
        logger.info(f"PPE检测器初始化完成")
        
    def _load_model(self):
        """加载 YOLOv8 模型"""
        try:
            from ultralytics import YOLO
            import os
            
            # 禁用自动下载
            os.environ['YOLO_OFFLINE'] = 'true'
            
            model_path = self.config.get('path', 'ppe_best.pt')
            original_path = model_path
            model_path_obj = Path(model_path)
            
            # 如果路径是相对路径，尝试在多个位置查找
            if not model_path_obj.is_absolute():
                possible_paths = [
                    Path(__file__).parent / 'models' / model_path_obj.name,
                    Path(__file__).parent.parent / 'stream_manager' / 'detectors' / 'models' / model_path_obj.name,
                    Path(__file__).parent.parent.parent / 'stream_manager' / 'detectors' / 'models' / model_path_obj.name,
                    Path.cwd() / model_path,
                    Path.cwd() / 'models' / model_path_obj.name,
                ]
                
                found = False
                for path in possible_paths:
                    if path.exists():
                        model_path = str(path.absolute())
                        found = True
                        break
                
                if not found:
                    raise FileNotFoundError(f"模型文件不存在: {original_path}, 尝试路径: {[str(p) for p in possible_paths]}")
                        
            logger.info(f"加载模型: {model_path}")
            self.model = YOLO(model_path, verbose=False)
            
            # 设置设备
            if self.device == 'auto':
                import torch
                self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
                
            logger.info(f"使用设备: {self.device}")
            
        except ImportError:
            logger.error("未安装 ultralytics，请运行: pip install ultralytics")
            raise
        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            raise
            
    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        执行 PPE 检测
        
        Args:
            frame: 输入图像 (BGR格式)
            
        Returns:
            检测结果列表（只返回人员，包含PPE状态）
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
            
            # 解析检测结果
            raw_detections = self._parse_detections(results)
            
            # 人员与 PPE 关联
            person_detections = self._associate_ppe(raw_detections, frame.shape)
            
            # 更新跟踪
            import time
            person_detections = self._update_tracking(person_detections, time.time())
            
            # 转换为 BaseDetector 的 Detection 格式
            detections = []
            for ppe_det in person_detections:
                det = Detection(
                    bbox=ppe_det['bbox'],
                    class_id=5,  # Person
                    class_name='person',
                    confidence=ppe_det['confidence']
                )
                det.track_id = ppe_det['track_id']
                det.has_helmet = ppe_det['has_helmet']
                det.has_vest = ppe_det['has_vest']
                det.has_mask = ppe_det['has_mask']
                detections.append(det)
            
            return detections
            
        except Exception as e:
            logger.error(f"检测失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _parse_detections(self, results) -> List[Dict]:
        """解析 YOLO 检测结果"""
        detections = []
        
        if results.boxes is None:
            return detections
        
        for box in results.boxes:
            cls_id = int(box.cls)
            cls_name = self.CLASS_NAMES.get(cls_id, f"class_{cls_id}")
            conf = float(box.conf)
            bbox = box.xyxy[0].tolist()  # [x1, y1, x2, y2]
            
            detections.append({
                'class_id': cls_id,
                'class_name': cls_name,
                'confidence': conf,
                'bbox': bbox
            })
        
        return detections
    
    def _associate_ppe(self, detections: List[Dict], frame_shape: tuple) -> List[Dict]:
        """
        将 PPE 与人员关联
        
        策略：
        1. 找到所有人员
        2. 对每个人员，找到与之重叠的 PPE
        3. 根据 IOU 和空间位置关联
        """
        # 分离人员和 PPE
        persons = [d for d in detections if d['class_name'] in self.PERSON_CLASSES]
        helmets = [d for d in detections if d['class_name'] in self.HELMET_CLASSES]
        no_helmets = [d for d in detections if d['class_name'] in self.NO_HELMET_CLASSES]
        vests = [d for d in detections if d['class_name'] in self.VEST_CLASSES]
        no_vests = [d for d in detections if d['class_name'] in self.NO_VEST_CLASSES]
        masks = [d for d in detections if d['class_name'] in self.MASK_CLASSES]
        no_masks = [d for d in detections if d['class_name'] in self.NO_MASK_CLASSES]
        
        person_detections = []
        
        for person in persons:
            p_bbox = person['bbox']
            
            # 创建 PPE 检测对象
            ppe_det = {
                'bbox': p_bbox,
                'confidence': person['confidence'],
                'track_id': 0,  # 临时ID，后续跟踪会更新
                'has_helmet': False,
                'has_vest': False,
                'has_mask': False
            }
            
            # 关联安全帽（优先匹配 helmet，如果没有则检查 no-helmet）
            best_helmet = self._find_best_match(p_bbox, helmets, iou_threshold=0.1)
            if best_helmet:
                ppe_det['has_helmet'] = True
            else:
                # 检查是否有未戴安全帽的标记
                best_no_helmet = self._find_best_match(p_bbox, no_helmets, iou_threshold=0.1)
                if best_no_helmet:
                    ppe_det['has_helmet'] = False
            
            # 关联反光衣
            best_vest = self._find_best_match(p_bbox, vests, iou_threshold=0.1)
            if best_vest:
                ppe_det['has_vest'] = True
            else:
                best_no_vest = self._find_best_match(p_bbox, no_vests, iou_threshold=0.1)
                if best_no_vest:
                    ppe_det['has_vest'] = False
            
            # 关联口罩
            best_mask = self._find_best_match(p_bbox, masks, iou_threshold=0.1)
            if best_mask:
                ppe_det['has_mask'] = True
            else:
                best_no_mask = self._find_best_match(p_bbox, no_masks, iou_threshold=0.1)
                if best_no_mask:
                    ppe_det['has_mask'] = False
            
            person_detections.append(ppe_det)
        
        return person_detections
    
    def _find_best_match(self, person_bbox: List[float], items: List[Dict], iou_threshold: float = 0.3) -> Optional[Dict]:
        """找到与人员最佳匹配的 PPE"""
        best_match = None
        best_score = iou_threshold
        
        for item in items:
            # 计算 IOU
            iou = self._iou(person_bbox, item['bbox'])
            
            # 也考虑中心点距离（对于小目标更可靠）
            p_center = self._get_center(person_bbox)
            i_center = self._get_center(item['bbox'])
            dist = np.sqrt((p_center[0] - i_center[0])**2 + (p_center[1] - i_center[1])**2)
            
            # 综合评分：IOU + 距离衰减
            max_dist = 200  # 最大考虑距离
            dist_score = max(0, 1 - dist / max_dist)
            score = iou * 0.7 + dist_score * 0.3
            
            if score > best_score:
                best_score = score
                best_match = item
        
        return best_match
    
    def _update_tracking(self, detections: List[Dict], timestamp: float) -> List[Dict]:
        """更新人员跟踪"""
        import time
        if timestamp is None:
            timestamp = time.time()
        
        # 简单的最近邻跟踪
        used_tracks = set()
        
        for det in detections:
            p_center = self._get_center(det['bbox'])
            
            # 找到最佳匹配的现有跟踪
            best_track_id = None
            best_dist = float('inf')
            
            for track_id, track in self.tracks.items():
                if track_id in used_tracks:
                    continue
                
                dist = np.sqrt(
                    (p_center[0] - track['center'][0])**2 + 
                    (p_center[1] - track['center'][1])**2
                )
                
                if dist < best_dist and dist < 100:  # 100像素阈值
                    best_dist = dist
                    best_track_id = track_id
            
            if best_track_id is not None:
                det['track_id'] = best_track_id
                used_tracks.add(best_track_id)
                self.tracks[best_track_id] = {
                    'center': p_center,
                    'bbox': det['bbox'],
                    'last_seen': timestamp
                }
            else:
                # 新跟踪
                det['track_id'] = self.next_track_id
                self.next_track_id += 1
                self.tracks[det['track_id']] = {
                    'center': p_center,
                    'bbox': det['bbox'],
                    'last_seen': timestamp
                }
        
        # 清理过期跟踪
        self._clean_tracks(timestamp)
        
        return detections
    
    def _clean_tracks(self, current_time: float):
        """清理过期跟踪"""
        expired = []
        for track_id, track in self.tracks.items():
            if current_time - track['last_seen'] > self.track_max_age * 0.1:  # 3秒过期
                expired.append(track_id)
        
        for track_id in expired:
            del self.tracks[track_id]
    
    def _iou(self, box1: List[float], box2: List[float]) -> float:
        """计算 IOU"""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box2[3], box2[3])
        
        inter_area = max(0, x2 - x1) * max(0, y2 - y1)
        box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
        box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])
        
        union_area = box1_area + box2_area - inter_area
        return inter_area / union_area if union_area > 0 else 0
    
    def _get_center(self, bbox: List[float]):
        """计算边界框中心"""
        return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
        
    def check_violations(self, detections: List[Detection]) -> List[Dict]:
        """
        检查 PPE 违规
        
        Returns:
            违规列表，每项包含类型、严重程度、涉及人员
        """
        violations = []
        
        for det in detections:
            if det.class_name != 'person':
                continue
                
            person_violations = []
            
            if not det.has_helmet:
                person_violations.append({
                    'type': 'no_helmet',
                    'description': '未戴安全帽',
                    'severity': 'high'
                })
                
            if not det.has_vest:
                person_violations.append({
                    'type': 'no_vest',
                    'description': '未穿反光衣',
                    'severity': 'medium'
                })
                
            if not det.has_mask:
                person_violations.append({
                    'type': 'no_mask',
                    'description': '未戴口罩',
                    'severity': 'low'
                })
                
            if person_violations:
                violations.append({
                    'person_id': det.track_id,
                    'bbox': det.bbox,
                    'violations': person_violations
                })
                
        return violations
        
    def draw_results(self, frame: np.ndarray, detections: List[Detection],
                     show_labels: bool = True, show_conf: bool = True) -> np.ndarray:
        """
        绘制检测结果（增强版，显示 PPE 状态）
        """
        result = frame.copy()
        
        for det in detections:
            if det.class_name != 'person':
                continue
                
            x1, y1, x2, y2 = map(int, det.bbox)
            
            # 根据合规状态选择颜色
            if det.has_helmet and det.has_vest:
                color = (0, 255, 0)  # 绿色：合规
                status = "OK"
            elif not det.has_helmet and not det.has_vest:
                color = (0, 0, 255)  # 红色：严重违规
                status = "NO Helmet+Vest!"
            elif not det.has_helmet:
                color = (0, 100, 255)  # 橙色：未戴安全帽
                status = "NO Helmet!"
            elif not det.has_vest:
                color = (0, 255, 255)  # 黄色：未穿反光衣
                status = "NO Vest!"
            else:
                color = (128, 128, 128)
                status = "Unknown"
            
            # 绘制人体框
            cv2.rectangle(result, (x1, y1), (x2, y2), color, 2)
            
            # 绘制标签
            label = f"ID:{det.track_id} {status}"
            label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
            cv2.rectangle(result, (x1, y1 - label_size[1] - 8),
                         (x1 + label_size[0], y1), color, -1)
            cv2.putText(result, label, (x1, y1 - 4),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # 绘制 PPE 状态图标
            icon_y = y1 + 20
            
            # 安全帽状态
            if det.has_helmet:
                cv2.putText(result, "H", (x2 + 5, icon_y),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            else:
                cv2.putText(result, "X", (x2 + 5, icon_y),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            
            # 反光衣状态
            icon_y += 20
            if det.has_vest:
                cv2.putText(result, "V", (x2 + 5, icon_y),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            else:
                cv2.putText(result, "X", (x2 + 5, icon_y),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            
            # 口罩状态
            icon_y += 20
            if det.has_mask:
                cv2.putText(result, "M", (x2 + 5, icon_y),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            else:
                cv2.putText(result, "X", (x2 + 5, icon_y),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        
        return result
        
    def get_statistics(self, detections: List[Detection]) -> Dict[str, Any]:
        """
        获取检测统计信息
        
        Returns:
            统计字典
        """
        persons = [d for d in detections if d.class_name == 'person']
        
        total = len(persons)
        with_helmet = sum(1 for p in persons if p.has_helmet)
        with_vest = sum(1 for p in persons if p.has_vest)
        with_mask = sum(1 for p in persons if p.has_mask)
        
        fully_compliant = sum(1 for p in persons 
                             if p.has_helmet and p.has_vest and p.has_mask)
        
        return {
            'total_persons': total,
            'with_helmet': with_helmet,
            'with_vest': with_vest,
            'with_mask': with_mask,
            'fully_compliant': fully_compliant,
            'compliance_rate': fully_compliant / total if total > 0 else 0,
            'helmet_compliance_rate': with_helmet / total if total > 0 else 0,
            'vest_compliance_rate': with_vest / total if total > 0 else 0,
        }
