"""
多模型检测引擎
支持动态加载和管理多个检测模型
"""

import logging
from typing import Dict, List, Optional, Any, Type
from pathlib import Path
import numpy as np

from .base_detector import BaseDetector, Detection, DetectionResult
from .detector_registry import get_detector_registry, DetectorInfo

logger = logging.getLogger(__name__)


class DetectorEngine:
    """
    检测引擎
    管理多个检测模型的加载、卸载和推理
    """
    
    def __init__(self, config_manager):
        """
        初始化检测引擎
        
        Args:
            config_manager: 配置管理器实例
        """
        self.config_manager = config_manager
        self.loaded_models: Dict[str, BaseDetector] = {}
        self.model_configs: Dict[str, Dict] = {}
        
        # 模型管理配置
        self.max_loaded_models = 3
        self.lazy_loading = True
        self.model_access_count: Dict[str, int] = {}
        
    def register_model(self, model_id: str, detector_class: Type[BaseDetector]):
        """
        注册检测模型
        
        Args:
            model_id: 模型ID
            detector_class: 检测器类
        """
        config = self.config_manager.get_model(model_id)
        if config is None:
            logger.warning(f"模型配置不存在: {model_id}")
            return
            
        self.model_configs[model_id] = {
            'class': detector_class,
            'config': config,
            'loaded': False
        }
        
        logger.info(f"注册模型: {model_id}")
        
    def load_model(self, model_id: str) -> Optional[BaseDetector]:
        """
        加载指定模型
        
        Args:
            model_id: 模型ID
            
        Returns:
            加载的检测器实例，失败返回 None
        """
        if model_id in self.loaded_models:
            self.model_access_count[model_id] = self.model_access_count.get(model_id, 0) + 1
            return self.loaded_models[model_id]
            
        if model_id not in self.model_configs:
            logger.error(f"未注册的模型: {model_id}")
            return None
            
        # 检查是否需要卸载其他模型
        if len(self.loaded_models) >= self.max_loaded_models:
            self._unload_least_used_model()
            
        # 加载模型
        try:
            model_info = self.model_configs[model_id]
            detector_class = model_info['class']
            config = model_info['config']
            
            logger.info(f"加载模型: {model_id}")
            detector = detector_class(config.__dict__)
            
            self.loaded_models[model_id] = detector
            self.model_access_count[model_id] = 1
            self.model_configs[model_id]['loaded'] = True
            
            return detector
        except Exception as e:
            logger.error(f"加载模型失败 {model_id}: {e}")
            return None
            
    def unload_model(self, model_id: str):
        """卸载指定模型"""
        if model_id in self.loaded_models:
            logger.info(f"卸载模型: {model_id}")
            del self.loaded_models[model_id]
            if model_id in self.model_access_count:
                del self.model_access_count[model_id]
            if model_id in self.model_configs:
                self.model_configs[model_id]['loaded'] = False
                
    def _unload_least_used_model(self):
        """卸载使用最少的模型"""
        if not self.model_access_count:
            return
            
        least_used = min(self.model_access_count, key=self.model_access_count.get)
        self.unload_model(least_used)
        
    def detect(self, frame: np.ndarray, model_ids: List[str]) -> Dict[str, DetectionResult]:
        """
        使用多个模型进行检测
        
        Args:
            frame: 输入图像
            model_ids: 要使用的模型ID列表
            
        Returns:
            各模型的检测结果字典
        """
        results = {}
        
        for model_id in model_ids:
            detector = self.load_model(model_id)
            if detector is None:
                logger.warning(f"模型未加载: {model_id}")
                continue
                
            try:
                detections = detector.detect(frame)
                violations = detector.check_violations(detections)
                
                result = DetectionResult(
                    detections=detections,
                    frame_id=0,  # 由调用者设置
                    timestamp=0.0,  # 由调用者设置
                    person_count=len([d for d in detections if d.class_name == 'person']),
                    violations=violations
                )
                
                results[model_id] = result
            except Exception as e:
                logger.error(f"检测失败 {model_id}: {e}")
                
        return results
        
    def get_loaded_models(self) -> List[str]:
        """获取已加载的模型列表"""
        return list(self.loaded_models.keys())
        
    def get_model_info(self, model_id: str) -> Optional[Dict]:
        """获取模型信息"""
        if model_id in self.loaded_models:
            return self.loaded_models[model_id].get_model_info()
        elif model_id in self.model_configs:
            config = self.model_configs[model_id]['config']
            return {
                "name": config.name,
                "type": config.type,
                "version": config.version,
                "loaded": False
            }
        return None
        
    def get_all_models_info(self) -> List[Dict]:
        """获取所有模型信息"""
        info_list = []
        for model_id in self.model_configs:
            info = self.get_model_info(model_id)
            if info:
                info['id'] = model_id
                info_list.append(info)
        return info_list


# 导入具体检测器
from .ppe_detector import PPEDetector
from .vehicle_detector import VehicleDetector
from .wall_defect_detector import WallDefectDetector


def create_detector_engine(config_manager) -> DetectorEngine:
    """
    创建并初始化检测引擎
    
    Args:
        config_manager: 配置管理器
        
    Returns:
        配置好的检测引擎实例
    """
    engine = DetectorEngine(config_manager)
    
    # 注册所有可用模型
    engine.register_model('ppe_detector', PPEDetector)
    engine.register_model('vehicle_detector', VehicleDetector)
    engine.register_model('wall_defect_detector', WallDefectDetector)
    
    return engine
