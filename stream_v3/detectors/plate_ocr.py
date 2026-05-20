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
            import warnings
            
            # 抑制PaddleOCR的下载进度输出
            warnings.filterwarnings('ignore')
            
            print("[OCR] 正在初始化PaddleOCR，首次使用需要下载模型（约100MB）...")
            print("[OCR] 这可能需要1-3分钟，请耐心等待...")
            
            # 使用CPU模式（更稳定）
            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang='ch',
                show_log=False,
                use_gpu=False,  # 使用CPU避免GPU内存问题
                enable_mkldnn=True  # 启用MKLDNN加速
            )
            print("[OCR] PaddleOCR初始化成功!")
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
        import tempfile
        import os
        
        # PaddleOCR 需要图片路径，先保存临时文件
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            # 保存图片
            import cv2
            cv2.imwrite(tmp_path, plate_image)
            
            # 识别
            result = self._ocr.ocr(tmp_path, cls=True)
            
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
        finally:
            # 清理临时文件
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    
    def _clean_plate_text(self, text: str) -> str:
        """
        清理车牌文字
        
        规则：
        - 去除空格和特殊字符
        - 保留中文字符、字母、数字
        - 转换为大写
        - 提取符合车牌格式的部分
        """
        import re
        
        # 去除空格
        text = text.replace(' ', '')
        
        # 转换为大写
        text = text.upper()
        
        # 尝试提取车牌（中国车牌格式）
        # 匹配模式：省份简称 + 字母 + 字母/数字组合
        plate_patterns = [
            # 普通蓝牌/黄牌（7位）：如 沪EE7028, 京A12345, 苏FL2773
            # 注意：有些黄牌是双字母开头，如 苏F·L2773 可能被识别为 苏FL2773
            r'([京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z]{1,2}[0-9]{4,7})',
            # 新能源车牌（8位）：如 京AD12345, 沪AZ50584
            # 新能源车牌第二位可以是任意字母
            r'([京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z][A-Z][0-9]{5})',
            # 使馆车牌：如 使123456
            r'(使\d{6})',
            # 警车车牌：如 沪A1234警
            r'([京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z]\d{4}警)',
        ]
        
        # 收集所有匹配的车牌
        all_plates = []
        for pattern in plate_patterns:
            matches = re.findall(pattern, text)
            all_plates.extend(matches)
        
        if all_plates:
            # 返回最长的匹配（通常是完整的车牌）
            return max(all_plates, key=len)
        
        # 如果没有匹配到标准车牌格式，只保留中文字符、字母、数字
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', text)
        
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
        # 普通蓝牌（7位）：京A12345
        r'^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z]\d{5}$',
        # 黄牌（7位）：沪EE7028, 苏FL2773（双字母开头）
        r'^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z]{2}\d{4,5}$',
        # 新能源车牌（8位）：京AD12345, 沪AZ50584
        # 新能源车牌第二位可以是任意字母（D、F是常见，但也有其他）
        r'^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z][A-Z]\d{5}$',
        # 使馆车牌：使123456
        r'^使\d{6}$',
        # 警车车牌：沪A1234警
        r'^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z]\d{4}警$',
        # 教练车/挂车等（8位）：京A1234学
        r'^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z][A-Z0-9]{4}[挂学警港澳]$',
    ]
    
    return any(re.match(p, plate) for p in patterns)
