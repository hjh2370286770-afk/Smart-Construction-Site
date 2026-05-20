"""
基于YOLOv8的车牌检测器
使用CCPD数据集训练的专用车牌检测模型
"""

import logging
from typing import Optional, Tuple, List
from pathlib import Path
import numpy as np
import cv2

logger = logging.getLogger(__name__)


class PlateDetectorYOLO:
    """
    YOLOv8车牌检测器
    
    功能：
    - 在图像中检测车牌位置
    - 返回车牌边界框坐标
    """
    
    def __init__(self, model_path: Optional[str] = None, device: str = 'cpu'):
        """
        初始化车牌检测器
        
        Args:
            model_path: YOLOv8模型路径，如果为None则使用默认路径
            device: 运行设备 ('cpu' 或 'cuda')
        """
        self.device = device
        self.model = None
        
        # 默认模型路径
        if model_path is None:
            model_path = 'models/plate_detection/plate_detect.pt'
        
        self.model_path = Path(model_path)
        
    def load_model(self) -> bool:
        """
        加载YOLOv8模型
        
        Returns:
            是否加载成功
        """
        try:
            from ultralytics import YOLO
            
            if not self.model_path.exists():
                logger.warning(f"车牌检测模型不存在: {self.model_path}")
                logger.info("将使用车辆检测框直接进行OCR识别")
                return False
            
            logger.info(f"加载车牌检测模型: {self.model_path}")
            self.model = YOLO(str(self.model_path))
            
            # 设置设备
            if self.device == 'auto':
                import torch
                self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
            
            logger.info(f"车牌检测模型加载成功，设备: {self.device}")
            return True
            
        except ImportError:
            logger.error("未安装 ultralytics")
            return False
        except Exception as e:
            logger.error(f"车牌检测模型加载失败: {e}")
            return False
    
    def detect(self, image: np.ndarray, conf_threshold: float = 0.5) -> Optional[Tuple[int, int, int, int]]:
        """
        检测车牌位置
        
        Args:
            image: 输入图像 (BGR格式)
            conf_threshold: 置信度阈值
            
        Returns:
            车牌边界框 (x1, y1, x2, y2) 或 None
        """
        if self.model is None:
            if not self.load_model():
                return None
        
        try:
            results = self.model(
                image,
                conf=conf_threshold,
                verbose=False,
                device=self.device
            )
            
            # 获取最佳检测结果
            best_box = None
            best_conf = 0
            
            for result in results:
                if result.boxes is None:
                    continue
                
                for box in result.boxes:
                    conf = float(box.conf[0])
                    if conf > best_conf:
                        best_conf = conf
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        best_box = (x1, y1, x2, y2)
            
            if best_box:
                logger.debug(f"检测到车牌: {best_box}, 置信度: {best_conf:.2f}")
                return best_box
            
            return None
            
        except Exception as e:
            logger.error(f"车牌检测失败: {e}")
            return None
    
    def detect_in_region(self, image: np.ndarray, region_bbox: Tuple[int, int, int, int], 
                         conf_threshold: float = 0.5) -> Optional[Tuple[int, int, int, int]]:
        """
        在指定区域内检测车牌
        
        Args:
            image: 完整图像
            region_bbox: 搜索区域 (x1, y1, x2, y2)
            conf_threshold: 置信度阈值
            
        Returns:
            车牌在完整图像中的边界框 (x1, y1, x2, y2) 或 None
        """
        x1, y1, x2, y2 = region_bbox
        
        # 裁剪区域
        region = image[y1:y2, x1:x2]
        if region.size == 0:
            return None
        
        # 在区域内检测车牌
        plate_bbox = self.detect(region, conf_threshold)
        if plate_bbox is None:
            return None
        
        # 转换坐标到完整图像
        px1, py1, px2, py2 = plate_bbox
        return (x1 + px1, y1 + py1, x1 + px2, y1 + py2)


# 简单的车牌检测函数（不使用专用模型）
def detect_plate_in_vehicle_simple(vehicle_roi: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    """
    简单方法：在车辆区域内检测车牌位置
    
    策略：
    1. 车牌通常在车辆下半部分
    2. 使用颜色特征（蓝牌、黄牌、绿牌等）
    3. 使用边缘检测
    
    Args:
        vehicle_roi: 车辆区域图像
        
    Returns:
        车牌相对位置 (x1, y1, x2, y2) 或 None
    """
    try:
        h, w = vehicle_roi.shape[:2]
        
        # 车牌通常在车辆下半部分的中间区域
        # 搜索区域：下半部分的60%，横向中间80%
        search_y1 = int(h * 0.5)
        search_y2 = int(h * 0.95)
        search_x1 = int(w * 0.1)
        search_x2 = int(w * 0.9)
        
        # 确保搜索区域有效
        if search_y2 - search_y1 < 30 or search_x2 - search_x1 < 100:
            return None
        
        # 在搜索区域内查找蓝色/黄色区域（车牌颜色）
        search_region = vehicle_roi[search_y1:search_y2, search_x1:search_x2]
        
        # 转换到HSV颜色空间
        hsv = cv2.cvtColor(search_region, cv2.COLOR_BGR2HSV)
        
        # 蓝色车牌范围
        lower_blue = np.array([100, 50, 50])
        upper_blue = np.array([130, 255, 255])
        blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)
        
        # 黄色车牌范围
        lower_yellow = np.array([20, 100, 100])
        upper_yellow = np.array([35, 255, 255])
        yellow_mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
        
        # 合并掩码
        mask = cv2.bitwise_or(blue_mask, yellow_mask)
        
        # 形态学操作
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        
        # 查找轮廓
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # 寻找最可能是车牌的轮廓
        best_box = None
        best_score = 0
        
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            
            # 车牌宽高比一般在 2:1 到 5:1 之间
            aspect_ratio = cw / ch if ch > 0 else 0
            if aspect_ratio < 2 or aspect_ratio > 6:
                continue
            
            # 车牌面积不能太小
            if cw < 60 or ch < 20:
                continue
            
            # 计算分数（面积 + 宽高比接近3.5）
            area = cw * ch
            ratio_score = 1 - abs(aspect_ratio - 3.5) / 3.5
            score = area * ratio_score
            
            if score > best_score:
                best_score = score
                # 转换到完整车辆区域坐标
                abs_x1 = search_x1 + x
                abs_y1 = search_y1 + y
                abs_x2 = abs_x1 + cw
                abs_y2 = abs_y1 + ch
                best_box = (abs_x1, abs_y1, abs_x2, abs_y2)
        
        return best_box
        
    except Exception as e:
        logger.debug(f"简单车牌检测失败: {e}")
        return None
