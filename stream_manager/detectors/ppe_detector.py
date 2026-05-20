#!/usr/bin/env python3
"""
PPE (Personal Protective Equipment) 检测器
使用专门的工地安全检测模型 - 同时检测安全帽、反光衣、口罩等

基于 YOLOv8 训练模型，类别包括：
- Hardhat (安全帽)
- NO-Hardhat (未戴安全帽)
- Safety Vest (反光衣/安全背心)
- NO-Safety Vest (未穿反光衣)
- Mask (口罩)
- NO-Mask (未戴口罩)
- Person (人员)
- Safety Cone (安全锥)
- machinery (机械)
- vehicle (车辆)
"""

import cv2
import numpy as np
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from pathlib import Path
import time

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

logger = logging.getLogger(__name__)


@dataclass
class PPEDetection:
    """PPE 检测结果"""
    track_id: int
    person_bbox: List[float]       # [x1, y1, x2, y2]
    confidence: float
    
    # 安全帽
    has_helmet: bool = False
    helmet_bbox: Optional[List[float]] = None
    helmet_confidence: float = 0.0
    
    # 反光衣
    has_vest: bool = False
    vest_bbox: Optional[List[float]] = None
    vest_confidence: float = 0.0
    
    # 口罩
    has_mask: bool = False
    mask_bbox: Optional[List[float]] = None
    mask_confidence: float = 0.0
    
    # 综合合规状态
    @property
    def is_compliant(self) -> bool:
        """是否完全合规（安全帽 + 反光衣）"""
        return self.has_helmet and self.has_vest
    
    @property
    def violation_type(self) -> Optional[str]:
        """违规类型"""
        violations = []
        if not self.has_helmet:
            violations.append("no_helmet")
        if not self.has_vest:
            violations.append("no_vest")
        if not self.has_mask:
            violations.append("no_mask")
        
        if len(violations) == 0:
            return None
        elif len(violations) == 1:
            return violations[0]
        else:
            return "_and_".join(violations)


class PPEDetector:
    """
    个人防护装备检测器
    
    使用专门的 YOLOv8 模型检测工地安全装备
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
    
    def __init__(self, 
                 model_path: str = None,
                 conf_threshold: float = 0.4,
                 iou_threshold: float = 0.45,
                 device: str = None):
        """
        初始化 PPE 检测器
        
        Args:
            model_path: 模型路径，默认使用 models/ppe_best.pt
            conf_threshold: 置信度阈值
            iou_threshold: NMS IOU 阈值
            device: 运行设备 ('cpu', 'cuda', 'mps', None=auto)
        """
        if YOLO is None:
            raise ImportError("需要安装 ultralytics: pip install ultralytics")
        
        # 默认模型路径
        if model_path is None:
            current_dir = Path(__file__).parent
            model_path = current_dir / "models" / "ppe_best.pt"
        
        self.model_path = str(model_path)
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        
        # 加载模型
        logger.info(f"正在加载 PPE 检测模型: {self.model_path}")
        self.model = YOLO(self.model_path)
        
        # 设置设备
        if device:
            self.device = device
        else:
            import torch
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        
        logger.info(f"PPE 检测器初始化完成，使用设备: {self.device}")
        
        # 跟踪相关
        self.next_track_id = 1
        self.tracks: Dict[int, Dict] = {}
        self.track_max_age = 30  # 最大丢失帧数
        
    def detect(self, frame: np.ndarray, timestamp: float = None) -> List[PPEDetection]:
        """
        检测图像中的 PPE
        
        Args:
            frame: 输入图像 (BGR格式)
            timestamp: 时间戳（用于跟踪）
            
        Returns:
            PPE 检测结果列表
        """
        # 运行检测
        results = self.model(
            frame, 
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            device=self.device,
            verbose=False
        )[0]
        
        # 解析检测结果
        detections = self._parse_detections(results)
        
        # 人员与 PPE 关联
        person_detections = self._associate_ppe(detections, frame.shape)
        
        # 更新跟踪
        person_detections = self._update_tracking(person_detections, timestamp)
        
        return person_detections
    
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
    
    def _associate_ppe(self, detections: List[Dict], frame_shape: Tuple) -> List[PPEDetection]:
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
            ppe_det = PPEDetection(
                track_id=0,  # 临时ID，后续跟踪会更新
                person_bbox=p_bbox,
                confidence=person['confidence']
            )
            
            # 关联安全帽（优先匹配 helmet，如果没有则检查 no-helmet）
            best_helmet = self._find_best_match(p_bbox, helmets, iou_threshold=0.1)
            if best_helmet:
                ppe_det.has_helmet = True
                ppe_det.helmet_bbox = best_helmet['bbox']
                ppe_det.helmet_confidence = best_helmet['confidence']
            else:
                # 检查是否有未戴安全帽的标记
                best_no_helmet = self._find_best_match(p_bbox, no_helmets, iou_threshold=0.1)
                if best_no_helmet:
                    ppe_det.has_helmet = False
            
            # 关联反光衣
            best_vest = self._find_best_match(p_bbox, vests, iou_threshold=0.1)
            if best_vest:
                ppe_det.has_vest = True
                ppe_det.vest_bbox = best_vest['bbox']
                ppe_det.vest_confidence = best_vest['confidence']
            else:
                best_no_vest = self._find_best_match(p_bbox, no_vests, iou_threshold=0.1)
                if best_no_vest:
                    ppe_det.has_vest = False
            
            # 关联口罩
            best_mask = self._find_best_match(p_bbox, masks, iou_threshold=0.1)
            if best_mask:
                ppe_det.has_mask = True
                ppe_det.mask_bbox = best_mask['bbox']
                ppe_det.mask_confidence = best_mask['confidence']
            else:
                best_no_mask = self._find_best_match(p_bbox, no_masks, iou_threshold=0.1)
                if best_no_mask:
                    ppe_det.has_mask = False
            
            person_detections.append(ppe_det)
        
        return person_detections
    
    def _find_best_match(self, 
                         person_bbox: List[float], 
                         items: List[Dict],
                         iou_threshold: float = 0.3) -> Optional[Dict]:
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
    
    def _update_tracking(self, 
                         detections: List[PPEDetection], 
                         timestamp: float) -> List[PPEDetection]:
        """更新人员跟踪"""
        if timestamp is None:
            timestamp = time.time()
        
        # 简单的最近邻跟踪
        used_tracks = set()
        
        for det in detections:
            p_center = self._get_center(det.person_bbox)
            
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
                det.track_id = best_track_id
                used_tracks.add(best_track_id)
                self.tracks[best_track_id] = {
                    'center': p_center,
                    'bbox': det.person_bbox,
                    'last_seen': timestamp
                }
            else:
                # 新跟踪
                det.track_id = self.next_track_id
                self.next_track_id += 1
                self.tracks[det.track_id] = {
                    'center': p_center,
                    'bbox': det.person_bbox,
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
        y2 = min(box1[3], box2[3])
        
        inter_area = max(0, x2 - x1) * max(0, y2 - y1)
        box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
        box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])
        
        union_area = box1_area + box2_area - inter_area
        return inter_area / union_area if union_area > 0 else 0
    
    def _get_center(self, bbox: List[float]) -> Tuple[float, float]:
        """计算边界框中心"""
        return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
    
    def draw_results(self, 
                     frame: np.ndarray, 
                     detections: List[PPEDetection],
                     show_stats: bool = True) -> np.ndarray:
        """
        绘制检测结果
        
        Args:
            frame: 输入图像
            detections: 检测结果列表
            show_stats: 是否显示统计面板
            
        Returns:
            绘制后的图像
        """
        result = frame.copy()
        
        for det in detections:
            x1, y1, x2, y2 = map(int, det.person_bbox)
            
            # 根据合规状态选择颜色
            if det.is_compliant:
                color = (0, 255, 0)  # 绿色 - 完全合规
                status = "OK"
            elif not det.has_helmet and not det.has_vest:
                color = (0, 0, 255)  # 红色 - 严重违规
                status = "NO Helmet+Vest!"
            elif not det.has_helmet:
                color = (0, 100, 255)  # 橙色 - 未戴安全帽
                status = "NO Helmet!"
            elif not det.has_vest:
                color = (0, 255, 255)  # 黄色 - 未穿反光衣
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
        
        # 绘制统计面板
        if show_stats:
            self._draw_stats_panel(result, detections)
        
        return result
    
    def _draw_stats_panel(self, frame: np.ndarray, detections: List[PPEDetection]):
        """绘制统计面板"""
        h, w = frame.shape[:2]
        panel_w = 320
        panel_h = 200
        x = w - panel_w - 10
        y = 10
        
        # 半透明背景
        overlay = frame.copy()
        cv2.rectangle(overlay, (x, y), (x + panel_w, y + panel_h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        # 统计
        total = len(detections)
        compliant = sum(1 for d in detections if d.is_compliant)
        no_helmet = sum(1 for d in detections if not d.has_helmet)
        no_vest = sum(1 for d in detections if not d.has_vest)
        no_mask = sum(1 for d in detections if not d.has_mask)
        
        # 标题
        cv2.putText(frame, "PPE Safety Check", (x + 10, y + 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        
        # 分隔线
        cv2.line(frame, (x + 10, y + 40), (x + panel_w - 10, y + 40), (200, 200, 200), 1)
        
        # 统计信息
        lines = [
            f"Total Persons: {total}",
            f"Compliant: {compliant} ({compliant/total*100:.0f}%)" if total > 0 else "Compliant: 0 (0%)",
            f"No Helmet: {no_helmet}",
            f"No Vest: {no_vest}",
            f"No Mask: {no_mask}"
        ]
        
        y_offset = y + 70
        for line in lines:
            cv2.putText(frame, line, (x + 10, y_offset),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
            y_offset += 25
    
    def get_summary(self, detections: List[PPEDetection]) -> Dict:
        """获取检测摘要"""
        total = len(detections)
        if total == 0:
            return {
                "total_persons": 0,
                "compliant": 0,
                "compliance_rate": 0.0,
                "violations": {}
            }
        
        compliant = sum(1 for d in detections if d.is_compliant)
        
        violations = {
            "no_helmet": sum(1 for d in detections if not d.has_helmet),
            "no_vest": sum(1 for d in detections if not d.has_vest),
            "no_mask": sum(1 for d in detections if not d.has_mask),
            "no_helmet_no_vest": sum(1 for d in detections if not d.has_helmet and not d.has_vest)
        }
        
        return {
            "total_persons": total,
            "compliant": compliant,
            "compliance_rate": compliant / total,
            "violations": violations
        }


# ==================== 测试代码 ====================

def test_camera():
    """使用摄像头测试 PPE 检测"""
    import time
    
    # 初始化检测器
    detector = PPEDetector(conf_threshold=0.4)
    
    # 打开摄像头
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("无法打开摄像头")
        return
    
    print("=" * 50)
    print("PPE 检测器测试")
    print("=" * 50)
    print("按键说明：")
    print("  q - 退出")
    print("  s - 打印统计信息")
    print("  f - 保存当前帧")
    print("=" * 50)
    
    frame_count = 0
    fps_time = time.time()
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_count += 1
        
        # 检测
        timestamp = time.time()
        detections = detector.detect(frame, timestamp)
        
        # 绘制结果
        result = detector.draw_results(frame, detections)
        
        # 计算 FPS
        if frame_count % 30 == 0:
            fps = 30 / (time.time() - fps_time)
            fps_time = time.time()
            cv2.putText(result, f"FPS: {fps:.1f}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        cv2.imshow("PPE Detection", result)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            summary = detector.get_summary(detections)
            print("\n" + "=" * 50)
            print("检测统计:")
            print(f"  总人数: {summary['total_persons']}")
            print(f"  合规人数: {summary['compliant']}")
            print(f"  合规率: {summary['compliance_rate']:.1%}")
            print(f"  违规情况: {summary['violations']}")
            print("=" * 50 + "\n")
        elif key == ord('f'):
            filename = f"ppe_capture_{int(time.time())}.jpg"
            cv2.imwrite(filename, result)
            print(f"已保存: {filename}")
    
    cap.release()
    cv2.destroyAllWindows()


def test_image(image_path: str):
    """测试单张图片"""
    detector = PPEDetector(conf_threshold=0.4)
    
    frame = cv2.imread(image_path)
    if frame is None:
        print(f"无法加载图片: {image_path}")
        return
    
    detections = detector.detect(frame)
    result = detector.draw_results(frame, detections)
    
    summary = detector.get_summary(detections)
    print("\n检测统计:")
    print(f"  总人数: {summary['total_persons']}")
    print(f"  合规人数: {summary['compliant']}")
    print(f"  合规率: {summary['compliance_rate']:.1%}")
    print(f"  违规情况: {summary['violations']}")
    
    cv2.imshow("PPE Detection", result)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # 测试图片
        test_image(sys.argv[1])
    else:
        # 测试摄像头
        test_camera()
