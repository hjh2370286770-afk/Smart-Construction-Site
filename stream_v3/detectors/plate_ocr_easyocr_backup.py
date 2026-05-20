"""
车牌OCR识别模块
支持多种OCR引擎：EasyOCR、PaddleOCR
"""

import logging
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)


class PlateOCR:
    """车牌OCR识别器"""
    
    def __init__(self, engine: str = 'easyocr'):
        """
        初始化OCR引擎
        
        Args:
            engine: OCR引擎类型 ('easyocr', 'paddleocr')
        """
        self.engine = engine
        self._ocr = None
        
    def _init_easyocr(self):
        """初始化EasyOCR"""
        try:
            import easyocr
            # 支持中英文识别
            self._ocr = easyocr.Reader(['ch_sim', 'en'], gpu=True)
            logger.info("EasyOCR初始化成功")
        except ImportError:
            logger.error("未安装easyocr，请运行: pip install easyocr")
            raise
        except Exception as e:
            logger.error(f"EasyOCR初始化失败: {e}")
            raise
    
    def _init_paddleocr(self):
        """初始化PaddleOCR"""
        try:
            from paddleocr import PaddleOCR
            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang='ch',
                show_log=False,
                use_gpu=True
            )
            logger.info("PaddleOCR初始化成功")
        except ImportError:
            logger.error("未安装paddleocr，请运行: pip install paddleocr")
            raise
        except Exception as e:
            logger.error(f"PaddleOCR初始化失败: {e}")
            raise
    
    def init(self):
        """初始化OCR引擎"""
        if self._ocr is not None:
            return
            
        if self.engine == 'easyocr':
            self._init_easyocr()
        elif self.engine == 'paddleocr':
            self._init_paddleocr()
        else:
            raise ValueError(f"不支持的OCR引擎: {self.engine}")
    
    def recognize(self, plate_image: np.ndarray) -> Optional[str]:
        """
        识别车牌文字
        
        Args:
            plate_image: 车牌区域图像
            
        Returns:
            识别的车牌号或None
        """
        if self._ocr is None:
            self.init()
        
        try:
            if self.engine == 'easyocr':
                return self._recognize_easyocr(plate_image)
            elif self.engine == 'paddleocr':
                return self._recognize_paddleocr(plate_image)
        except Exception as e:
            logger.error(f"OCR识别失败: {e}")
            return None
    
    def _recognize_easyocr(self, plate_image: np.ndarray) -> Optional[str]:
        """使用EasyOCR识别"""
        results = self._ocr.readtext(plate_image)
        
        if not results:
            return None
        
        # 合并所有识别结果
        texts = []
        for result in results:
            text = result[1]  # 识别文字
            conf = result[2]  # 置信度
            if conf > 0.5:  # 置信度阈值
                texts.append(text)
        
        # 清理并合并
        plate_text = ''.join(texts)
        plate_text = self._clean_plate_text(plate_text)
        
        return plate_text if plate_text else None
    
    def _recognize_paddleocr(self, plate_image: np.ndarray) -> Optional[str]:
        """使用PaddleOCR识别"""
        result = self._ocr.ocr(plate_image, cls=True)
        
        if not result or not result[0]:
            return None
        
        texts = []
        for line in result[0]:
            text = line[1][0]  # 识别文字
            conf = line[1][1]  # 置信度
            if conf > 0.5:
                texts.append(text)
        
        plate_text = ''.join(texts)
        plate_text = self._clean_plate_text(plate_text)
        
        return plate_text if plate_text else None
    
    def _clean_plate_text(self, text: str) -> str:
        """
        清理车牌文字
        
        规则：
        - 去除空格和特殊字符
        - 保留中文字符、字母、数字
        - 转换为大写
        """
        import re
        
        # 去除空格
        text = text.replace(' ', '')
        
        # 只保留中文字符、字母、数字
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', text)
        
        # 转换为大写
        text = text.upper()
        
        return text


# 车牌格式验证
def validate_plate_number(plate: str) -> bool:
    """
    验证车牌号格式
    
    支持：
    - 普通车牌：京A12345
    - 新能源车牌：京AD12345
    - 警车车牌：京A1234警
    - 使馆车牌：使123456
    """
    import re
    
    if not plate or len(plate) < 7:
        return False
    
    patterns = [
        r'^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z][A-Z0-9]{4}[A-Z0-9挂学警港澳]$',  # 普通车牌
        r'^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z][DF][A-Z0-9]{5}$',  # 新能源
        r'^使\d{6}$',  # 使馆车牌
        r'^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z]\d{4}警$',  # 警车
    ]
    
    return any(re.match(p, plate) for p in patterns)
