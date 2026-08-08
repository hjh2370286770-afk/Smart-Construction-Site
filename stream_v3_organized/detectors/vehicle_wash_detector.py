"""
车辆清洗检测器 - 基础检测器
仅负责：车辆检测 + 车牌识别
不包含：跟踪、进出场、清洗判定逻辑
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

import numpy as np
import cv2

from base_detector import BaseDetector, Detection
from plate_detector import PlateDetector, create_plate_detector
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class VehicleWashDetector(BaseDetector):
    """车辆清洗检测器 - 基础版，仅检测+车牌识别"""

    def __init__(self, config: Dict[str, Any]):
        self._normalize_config(config)
        super().__init__(config)

        self.plate_detector = None
        try:
            device = self.config.get('device', 'cpu')
            if device == 'auto':
                import torch
                device = 'cuda' if torch.cuda.is_available() else 'cpu'
            
            logger.info(f"正在初始化车牌检测器，设备: {device}")
            self.plate_detector = create_plate_detector(device=device)
            
            if self.plate_detector.init():
                logger.info("车牌检测器初始化成功")
            else:
                logger.error("车牌检测器初始化失败: 模型文件可能不存在或格式错误")
                self.plate_detector = None
        except Exception as e:
            logger.error(f"车牌检测器初始化异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.plate_detector = None

    def _normalize_config(self, config: Dict[str, Any]):
        if 'params' not in config:
            flat_keys = ['conf_threshold', 'iou_threshold', 'img_size', 'device']
            params = {}
            for key in flat_keys:
                if key in config:
                    params[key] = config[key]
            if params:
                config['params'] = params

    def _load_model(self):
        try:
            from ultralytics import YOLO
            model_path = self.config.get('path', str(Path(__file__).parent.parent / 'models' / 'yolov8n.pt'))
            logger.info(f"加载车辆检测模型: {model_path}")
            self.model = YOLO(model_path)
            # 单线程初始化阶段预融合，避免后续多线程并发推理触发 fuse 竞态
            try:
                self.model.fuse()
                logger.info("车辆检测模型已预融合")
            except Exception as e:
                logger.warning(f"车辆检测模型预融合失败（不影响后续使用）: {e}")

            if self.device == 'auto':
                import torch
                self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        except ImportError:
            logger.error("未安装 ultralytics")
            raise
        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            raise

    def detect(self, frame: np.ndarray) -> List[Detection]:
        if self.model is None:
            return []
        try:
            import torch
            with torch.no_grad():
                results = self.model(
                    frame,
                    conf=self.conf_threshold,
                    iou=self.iou_threshold,
                    imgsz=self.img_size,
                    device=self.device,
                    verbose=False,
                    classes=[2, 3, 5, 7]
                )
            detections = []
            for result in results:
                if result.boxes is None:
                    continue
                for box in result.boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    class_name = self._map_coco_class(cls_id)
                    if class_name is None:
                        continue
                    detection = Detection(
                        bbox=(x1, y1, x2, y2),
                        class_id=cls_id,
                        class_name=class_name,
                        confidence=conf
                    )
                    detections.append(detection)
            return detections
        except Exception as e:
            logger.error(f"检测失败: {e}")
            return []

    def _map_coco_class(self, coco_class_id: int) -> Optional[str]:
        mapping = {2: 'car', 3: 'motorcycle', 5: 'bus', 7: 'truck'}
        return mapping.get(coco_class_id)

    def detect_license_plate(self, frame: np.ndarray,
                             vehicle_bbox: Tuple[int, int, int, int]
                             ) -> Tuple[Optional[str], Optional[Tuple[int, int, int, int]], Optional[str], float]:
        """
        检测车牌（返回颜色信息）
        
        Returns:
            (车牌号, 车牌位置, 车牌颜色, 颜色置信度)
        """
        try:
            vx1, vy1, vx2, vy2 = vehicle_bbox
            vehicle_roi = frame[vy1:vy2, vx1:vx2]

            if vehicle_roi.size == 0 or vehicle_roi.shape[0] < 20 or vehicle_roi.shape[1] < 50:
                return None, None, None, 0.0

            if self.plate_detector is not None:
                result = self.plate_detector.detect_in_vehicle(vehicle_roi)
                if result:
                    plate_text, plate_rel_bbox, plate_color, color_conf = result
                    px1, py1, px2, py2 = plate_rel_bbox
                    abs_bbox = (vx1 + px1, vy1 + py1, vx1 + px2, vy1 + py2)
                    return plate_text, abs_bbox, plate_color, color_conf

            return None, None, None, 0.0
        except Exception as e:
            logger.error(f"车牌识别失败: {e}")
            return None, None, None, 0.0
