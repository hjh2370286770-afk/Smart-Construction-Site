"""
YOLOv8 车牌检测器
基于 yolov8-plate 项目的车牌检测和识别
"""

import logging
from typing import Optional, Tuple, List, Dict
from pathlib import Path
import numpy as np
import cv2
import torch
import sys

# 添加 plate_recognition 模块路径
sys.path.insert(0, str(Path(__file__).parent))

logger = logging.getLogger(__name__)


class PlateDetector:
    """
    YOLOv8 车牌检测器
    
    功能：
    - 检测车牌位置
    - 识别车牌号码
    - 识别车牌颜色
    - 支持单层/双层车牌
    """
    
    def __init__(self, 
                 detect_model_path: str = 'models/yolov8-plate/yolov8-plate-master/weights/yolov8s.pt',
                 rec_model_path: str = 'models/yolov8-plate/yolov8-plate-master/weights/plate_rec_color.pth',
                 device: str = 'cpu',
                 img_size: int = 640,
                 conf_thresh: float = 0.4,
                 iou_thresh: float = 0.45):
        """
        初始化车牌检测器
        
        Args:
            detect_model_path: 车牌检测模型路径
            rec_model_path: 车牌识别模型路径
            device: 运行设备
            img_size: 输入图像大小
            conf_thresh: 置信度阈值
            iou_thresh: IOU阈值
        """
        self.device = torch.device(device if torch.cuda.is_available() else "cpu")
        self.img_size = img_size
        self.conf_thresh = conf_thresh
        self.iou_thresh = iou_thresh
        
        self.detect_model_path = Path(detect_model_path)
        self.rec_model_path = Path(rec_model_path)
        
        self.detect_model = None
        self.rec_model = None
        
    def init(self) -> bool:
        """初始化模型"""
        try:
            # 导入必要的模块
            from ultralytics import YOLO
            from plate_recognition.plate_rec import init_model
            
            # 检查模型文件是否存在
            if not self.detect_model_path.exists():
                logger.error(f"检测模型不存在: {self.detect_model_path}")
                return False
            if not self.rec_model_path.exists():
                logger.error(f"识别模型不存在: {self.rec_model_path}")
                return False
            
            # 加载检测模型 (使用YOLO类)
            logger.info(f"加载车牌检测模型: {self.detect_model_path}")
            self.yolo_model = YOLO(str(self.detect_model_path))
            self.yolo_model.to(self.device)
            
            # 加载识别模型
            logger.info(f"加载车牌识别模型: {self.rec_model_path}")
            self.rec_model = init_model(self.device, str(self.rec_model_path), is_color=True)
            
            logger.info("车牌检测器初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"车牌检测器初始化失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def letter_box(self, img: np.ndarray, size: Tuple[int, int] = (640, 640)) -> Tuple[np.ndarray, float, int, int]:
        """YOLO前处理letter_box操作"""
        h, w, _ = img.shape
        r = min(size[0]/h, size[1]/w)
        new_h, new_w = int(h*r), int(w*r)
        new_img = cv2.resize(img, (new_w, new_h))
        left = int((size[1]-new_w)/2)
        top = int((size[0]-new_h)/2)
        img = cv2.copyMakeBorder(new_img, top, top, left, left, 
                                 cv2.BORDER_CONSTANT, value=(114, 114, 114))
        return img, r, left, top
    
    def xywh2xyxy(self, det: torch.Tensor) -> torch.Tensor:
        """xywh转化为xyxy"""
        y = det.clone()
        y[:, 0] = det[:, 0] - det[:, 2]/2
        y[:, 1] = det[:, 1] - det[:, 3]/2
        y[:, 2] = det[:, 0] + det[:, 2]/2
        y[:, 3] = det[:, 1] + det[:, 3]/2
        return y
    
    def nms(self, dets: torch.Tensor, iou_thresh: float) -> List[int]:
        """NMS操作"""
        y = dets.clone()
        y_box_score = y[:, :5]
        index = torch.argsort(y_box_score[:, -1], descending=True)
        keep = []
        while index.size()[0] > 0:
            i = index[0].item()
            keep.append(i)
            x1 = torch.maximum(y_box_score[i, 0], y_box_score[index[1:], 0])
            y1 = torch.maximum(y_box_score[i, 1], y_box_score[index[1:], 1])
            x2 = torch.minimum(y_box_score[i, 2], y_box_score[index[1:], 2])
            y2 = torch.minimum(y_box_score[i, 3], y_box_score[index[1:], 3])
            zero_ = torch.tensor(0).to(self.device)
            w = torch.maximum(zero_, x2 - x1)
            h = torch.maximum(zero_, y2 - y1)
            inter_area = w * h
            union_area1 = (y_box_score[i, 2] - y_box_score[i, 0]) * (y_box_score[i, 3] - y_box_score[i, 1])
            union_area2 = (y_box_score[index[1:], 2] - y_box_score[index[1:], 0]) * (y_box_score[index[1:], 3] - y_box_score[index[1:], 1])
            iou = inter_area / (union_area1 + union_area2 - inter_area)
            idx = torch.where(iou <= iou_thresh)[0]
            index = index[idx + 1]
        return keep
    
    def restore_box(self, dets: torch.Tensor, r: float, left: int, top: int) -> torch.Tensor:
        """坐标还原到原图上"""
        dets[:, [0, 2]] = dets[:, [0, 2]] - left
        dets[:, [1, 3]] = dets[:, [1, 3]] - top
        dets[:, :4] /= r
        return dets
    
    def post_processing(self, prediction: torch.Tensor, conf: float, iou_thresh: float, 
                       r: float, left: int, top: int) -> List[torch.Tensor]:
        """后处理"""
        prediction = prediction.permute(0, 2, 1).squeeze(0)
        xc = prediction[:, 4:6].amax(1) > conf
        x = prediction[xc]
        if not len(x):
            return []
        boxes = x[:, :4]
        boxes = self.xywh2xyxy(boxes)
        score, index = torch.max(x[:, 4:6], dim=-1, keepdim=True)
        x = torch.cat((boxes, score, x[:, 6:14], index), dim=1)
        score = x[:, 4]
        keep = self.nms(x, iou_thresh)
        x = x[keep]
        x = self.restore_box(x, r, left, top)
        return x
    
    def pre_processing(self, img: np.ndarray) -> Tuple[torch.Tensor, float, int, int]:
        """前处理"""
        img, r, left, top = self.letter_box(img, (self.img_size, self.img_size))
        img = img[:, :, ::-1].transpose((2, 0, 1)).copy()
        img = torch.from_numpy(img).to(self.device)
        img = img.float()
        img = img / 255.0
        img = img.unsqueeze(0)
        return img, r, left, top
    
    def detect(self, image: np.ndarray) -> List[Dict]:
        """
        检测车牌 (使用YOLOv8标准接口)
        
        Args:
            image: 输入图像 (BGR格式)
            
        Returns:
            车牌信息列表
        """
        if self.yolo_model is None or self.rec_model is None:
            if not self.init():
                return []
        
        try:
            from plate_recognition.plate_rec import get_plate_result
            from plate_recognition.double_plate_split_merge import get_split_merge
            
            # 使用YOLOv8进行推理
            results = self.yolo_model(
                image,
                conf=self.conf_thresh,
                iou=self.iou_thresh,
                verbose=False,
                device=self.device
            )
            
            result_list = []
            for result in results:
                if result.boxes is None:
                    continue
                
                for box in result.boxes:
                    # 获取边界框
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = float(box.conf[0])
                    cls = int(box.cls[0]) if box.cls is not None else 0
                    
                    # 裁剪车牌区域
                    roi_img = image[y1:y2, x1:x2]
                    if roi_img.size == 0:
                        continue
                    
                    # 处理双层车牌
                    if cls == 1:  # 双层车牌
                        roi_img = get_split_merge(roi_img)
                    
                    # 识别车牌
                    plate_number, rec_prob, plate_color, color_conf = get_plate_result(
                        roi_img, self.device, self.rec_model, is_color=True
                    )
                    
                    result_dict = {
                        'plate_no': plate_number,
                        'plate_color': plate_color,
                        'rect': [x1, y1, x2, y2],
                        'detect_conf': conf,
                        'color_conf': color_conf,
                        'plate_type': cls
                    }
                    
                    result_list.append(result_dict)
            
            return result_list
            
        except Exception as e:
            logger.error(f"车牌检测失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def detect_in_vehicle(self, vehicle_roi: np.ndarray) -> Optional[Tuple[str, Tuple[int, int, int, int], str, float]]:
        """
        在车辆区域内检测车牌（返回颜色信息）
        
        Args:
            vehicle_roi: 车辆区域图像
            
        Returns:
            (车牌号, 车牌位置, 车牌颜色, 颜色置信度) 或 None
        """
        results = self.detect(vehicle_roi)
        
        if not results:
            return None
        
        # 返回置信度最高的结果
        best_result = max(results, key=lambda x: x['detect_conf'])
        return (
            best_result['plate_no'], 
            tuple(best_result['rect']),
            best_result.get('plate_color', ''),
            best_result.get('color_conf', 0.0)
        )


# 便捷函数
def create_plate_detector(device: str = 'cpu') -> PlateDetector:
    """创建车牌检测器实例"""
    base_path = Path(__file__).parent.parent / 'models' / 'yolov8-plate' / 'yolov8-plate-master' / 'weights'
    
    detector = PlateDetector(
        detect_model_path=str(base_path / 'yolov8s.pt'),
        rec_model_path=str(base_path / 'plate_rec_color.pth'),
        device=device
    )
    return detector
