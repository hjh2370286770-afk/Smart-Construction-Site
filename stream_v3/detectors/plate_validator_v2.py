"""
车牌格式验证 V2 - 基于车牌颜色的严格验证
支持：蓝牌、绿牌(新能源)、黄牌、白牌、黑牌、港澳牌
"""

import re
from typing import Optional, Tuple, Dict
from dataclasses import dataclass
from enum import Enum


class PlateColor(Enum):
    """车牌颜色类型"""
    BLUE = "蓝色"      # 小型汽车
    GREEN = "绿色"     # 新能源汽车
    YELLOW = "黄色"    # 大型汽车/教练车
    WHITE = "白色"     # 警车/军车
    BLACK = "黑色"     # 港澳/领馆/外企
    UNKNOWN = "未知"


class PlateType(Enum):
    """车牌类型"""
    SMALL_CAR = "小型汽车"           # 蓝牌 7位
    NEW_ENERGY_SMALL = "新能源小型"   # 绿牌 8位，第3位=D/F
    NEW_ENERGY_LARGE = "新能源大型"   # 绿牌 8位，最后一位=A-K
    LARGE_CAR = "大型汽车"           # 黄牌 7位
    COACH_CAR = "教练车"             # 黄牌 8位，最后一位"学"
    TRAILER = "挂车"                 # 黄牌 7位，最后一位"挂"
    POLICE = "警车"                  # 白牌 7位，最后一位"警"
    MILITARY = "军车"                # 白牌 7位
    HONGKONG_MACAU = "港澳牌"        # 黑牌 7位
    CONSULATE = "领馆牌"             # 黑牌 7位
    FOREIGN = "外籍牌"               # 黑牌 7位
    SPECIAL = "特殊车牌"             # 其他


@dataclass
class PlateValidationResult:
    """车牌验证结果"""
    is_valid: bool
    plate_type: Optional[PlateType]
    plate_color: Optional[PlateColor]
    cleaned_plate: Optional[str]
    reason: str


class PlateValidatorV2:
    """
    车牌验证器 V2
    基于车牌颜色和格式的严格验证
    """
    
    # 省份简称
    PROVINCES = set([
        '京', '津', '沪', '渝', '冀', '豫', '云', '辽',
        '黑', '湘', '皖', '鲁', '新', '苏', '浙', '赣',
        '鄂', '桂', '甘', '晋', '蒙', '陕', '吉', '闽',
        '贵', '粤', '川', '青', '藏', '琼', '宁'
    ])
    
    # 特殊前缀
    SPECIAL_PREFIXES = set(['军', '警', '使', '领', '港', '澳', '学', '挂', '应急'])
    
    # 新能源车牌第3位（小型）或最后一位（大型）的允许字符
    NEW_ENERGY_CHARS = set('ABCDEFGHJKLMNPQRSTUVWXYZ')  # 不含I,O
    
    # 标准车牌字符（不含I,O）
    PLATE_CHARS = set('0123456789ABCDEFGHJKLMNPQRSTUVWXYZ')
    
    @classmethod
    def validate(cls, plate_text: str, plate_color: str = None, 
                 color_conf: float = 0.0) -> PlateValidationResult:
        """
        验证车牌
        
        Args:
            plate_text: 识别到的车牌文本
            plate_color: 识别到的车牌颜色（蓝色/绿色/黄色/白色/黑色）
            color_conf: 颜色识别置信度
            
        Returns:
            PlateValidationResult
        """
        if not plate_text:
            return PlateValidationResult(False, None, None, None, "空字符串")
        
        # 清理文本
        cleaned = cls._clean_plate(plate_text)
        if not cleaned:
            return PlateValidationResult(False, None, None, None, "清理后为空")
        
        # 确定颜色类型
        color_enum = cls._parse_color(plate_color, color_conf)
        
        # 根据颜色和格式进行验证
        if color_enum == PlateColor.GREEN:
            return cls._validate_green_plate(cleaned)
        elif color_enum == PlateColor.BLUE:
            return cls._validate_blue_plate(cleaned)
        elif color_enum == PlateColor.YELLOW:
            return cls._validate_yellow_plate(cleaned)
        elif color_enum == PlateColor.WHITE:
            return cls._validate_white_plate(cleaned)
        elif color_enum == PlateColor.BLACK:
            return cls._validate_black_plate(cleaned)
        else:
            # 未知颜色，尝试所有规则
            return cls._validate_unknown_color(cleaned)
    
    @classmethod
    def _parse_color(cls, color_text: str, color_conf: float) -> PlateColor:
        """解析颜色文本为枚举"""
        if not color_text or color_conf < 0.5:
            return PlateColor.UNKNOWN
        
        color_map = {
            '蓝色': PlateColor.BLUE,
            '绿色': PlateColor.GREEN,
            '黄色': PlateColor.YELLOW,
            '白色': PlateColor.WHITE,
            '黑色': PlateColor.BLACK,
        }
        return color_map.get(color_text, PlateColor.UNKNOWN)
    
    @classmethod
    def _clean_plate(cls, text: str) -> Optional[str]:
        """清理车牌文本"""
        # 去除空格和特殊字符，保留中文、字母、数字
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', text)
        text = text.upper()
        
        # 去除常见误识别字符
        text = text.replace('I', '1').replace('O', '0')
        
        return text if text else None
    
    @classmethod
    def _validate_green_plate(cls, plate: str) -> PlateValidationResult:
        """
        验证新能源车牌（绿色）
        格式：省份 + 字母 + [D/F] + 5位字母数字（小型，8位）
        或：省份 + 字母 + 5位字母数字 + [A-K]（大型，8位）
        """
        if len(plate) != 8:
            return PlateValidationResult(
                False, None, PlateColor.GREEN, plate,
                f"新能源车牌长度必须为8位，当前{len(plate)}位"
            )
        
        # 检查省份
        if plate[0] not in cls.PROVINCES:
            return PlateValidationResult(
                False, None, PlateColor.GREEN, plate,
                f"无效省份: {plate[0]}"
            )
        
        # 检查第二位（字母）
        if not ('A' <= plate[1] <= 'Z'):
            return PlateValidationResult(
                False, None, PlateColor.GREEN, plate,
                f"第二位必须是字母: {plate[1]}"
            )
        
        # 检查第3位（小型新能源为D/F，大型新能源为数字）
        third_char = plate[2]
        last_char = plate[7]
        
        # 小型新能源：第3位是D或F
        if third_char in 'DF':
            # 检查后5位
            for i in range(3, 8):
                if plate[i] not in cls.PLATE_CHARS:
                    return PlateValidationResult(
                        False, None, PlateColor.GREEN, plate,
                        f"第{i+1}位包含无效字符: {plate[i]}"
                    )
            return PlateValidationResult(
                True, PlateType.NEW_ENERGY_SMALL, PlateColor.GREEN, plate, "有效"
            )
        
        # 大型新能源：最后一位是A-K
        elif last_char in 'ABCDEFGHJK':
            # 检查前7位
            for i in range(2, 7):
                if plate[i] not in cls.PLATE_CHARS:
                    return PlateValidationResult(
                        False, None, PlateColor.GREEN, plate,
                        f"第{i+1}位包含无效字符: {plate[i]}"
                    )
            return PlateValidationResult(
                True, PlateType.NEW_ENERGY_LARGE, PlateColor.GREEN, plate, "有效"
            )
        
        else:
            return PlateValidationResult(
                False, None, PlateColor.GREEN, plate,
                f"新能源车牌格式错误: 第3位={third_char}, 末位={last_char}"
            )
    
    @classmethod
    def _validate_blue_plate(cls, plate: str) -> PlateValidationResult:
        """
        验证小型汽车车牌（蓝色）
        格式：省份 + 字母 + 5位字母数字（7位）
        """
        if len(plate) != 7:
            return PlateValidationResult(
                False, None, PlateColor.BLUE, plate,
                f"蓝牌长度必须为7位，当前{len(plate)}位"
            )
        
        # 检查省份
        if plate[0] not in cls.PROVINCES:
            return PlateValidationResult(
                False, None, PlateColor.BLUE, plate,
                f"无效省份: {plate[0]}"
            )
        
        # 检查第二位（字母）
        if not ('A' <= plate[1] <= 'Z'):
            return PlateValidationResult(
                False, None, PlateColor.BLUE, plate,
                f"第二位必须是字母: {plate[1]}"
            )
        
        # 检查后5位
        for i in range(2, 7):
            if plate[i] not in cls.PLATE_CHARS:
                return PlateValidationResult(
                    False, None, PlateColor.BLUE, plate,
                    f"第{i+1}位包含无效字符: {plate[i]}"
                )
        
        return PlateValidationResult(
            True, PlateType.SMALL_CAR, PlateColor.BLUE, plate, "有效"
        )
    
    @classmethod
    def _validate_yellow_plate(cls, plate: str) -> PlateValidationResult:
        """
        验证大型汽车/教练车/挂车车牌（黄色）
        普通大型车：省份 + 字母 + 5位字母数字（7位）
        教练车：省份 + 字母 + 4位字母数字 + "学"（7位）
        挂车：省份 + 字母 + 4位字母数字 + "挂"（7位）
        """
        if len(plate) not in [6, 7]:
            return PlateValidationResult(
                False, None, PlateColor.YELLOW, plate,
                f"黄牌长度必须为6或7位，当前{len(plate)}位"
            )
        
        # 检查省份
        if plate[0] not in cls.PROVINCES:
            return PlateValidationResult(
                False, None, PlateColor.YELLOW, plate,
                f"无效省份: {plate[0]}"
            )
        
        # 检查第二位（字母）
        if not ('A' <= plate[1] <= 'Z'):
            return PlateValidationResult(
                False, None, PlateColor.YELLOW, plate,
                f"第二位必须是字母: {plate[1]}"
            )
        
        # 教练车检查：以"学"结尾
        if plate.endswith('学'):
            if len(plate) != 7:
                return PlateValidationResult(
                    False, None, PlateColor.YELLOW, plate,
                    "教练车车牌长度应为7位"
                )
            # 检查中间4位（第3-6位，索引2-5）
            for i in range(2, 6):
                if plate[i] not in cls.PLATE_CHARS:
                    return PlateValidationResult(
                        False, None, PlateColor.YELLOW, plate,
                        f"第{i+1}位包含无效字符: {plate[i]}"
                    )
            return PlateValidationResult(
                True, PlateType.COACH_CAR, PlateColor.YELLOW, plate, "有效(教练车)"
            )
        
        # 挂车检查：以"挂"结尾
        if plate.endswith('挂'):
            if len(plate) != 7:
                return PlateValidationResult(
                    False, None, PlateColor.YELLOW, plate,
                    "挂车车牌长度应为7位"
                )
            # 检查中间4位（第3-6位，索引2-5）
            for i in range(2, 6):
                if plate[i] not in cls.PLATE_CHARS:
                    return PlateValidationResult(
                        False, None, PlateColor.YELLOW, plate,
                        f"第{i+1}位包含无效字符: {plate[i]}"
                    )
            return PlateValidationResult(
                True, PlateType.TRAILER, PlateColor.YELLOW, plate, "有效(挂车)"
            )
        
        # 普通黄牌（大型汽车）
        if len(plate) != 7:
            return PlateValidationResult(
                False, None, PlateColor.YELLOW, plate,
                "普通黄牌长度应为7位"
            )
        
        for i in range(2, 7):
            if plate[i] not in cls.PLATE_CHARS:
                return PlateValidationResult(
                    False, None, PlateColor.YELLOW, plate,
                    f"第{i+1}位包含无效字符: {plate[i]}"
                )
        
        return PlateValidationResult(
            True, PlateType.LARGE_CAR, PlateColor.YELLOW, plate, "有效(大型汽车)"
        )
    
    @classmethod
    def _validate_white_plate(cls, plate: str) -> PlateValidationResult:
        """
        验证警车/军车车牌（白色）
        警车、军车一律不通过
        """
        return PlateValidationResult(
            False, None, PlateColor.WHITE, plate,
            "不支持的白色车牌类型（警车/军车）"
        )
    
    @classmethod
    def _validate_black_plate(cls, plate: str) -> PlateValidationResult:
        """
        验证港澳/领馆/外籍车牌（黑色）
        领馆牌、外籍牌、港澳牌一律不通过
        """
        return PlateValidationResult(
            False, None, PlateColor.BLACK, plate,
            "不支持的黑色车牌类型（港澳/领馆/外籍）"
        )
    
    @classmethod
    def _validate_unknown_color(cls, plate: str) -> PlateValidationResult:
        """
        未知颜色时，尝试匹配所有规则
        严格验证：根据常见车牌长度范围进行验证
        """
        # 严格长度检查：合法车牌长度范围
        if len(plate) not in [5, 6, 7, 8]:
            return PlateValidationResult(
                False, None, PlateColor.UNKNOWN, plate,
                f"车牌长度异常: {len(plate)}位，合法范围为5-8位"
            )
        
        # 优先尝试新能源（8位）
        if len(plate) == 8:
            green_result = cls._validate_green_plate(plate)
            if green_result.is_valid:
                return green_result
        
        # 尝试蓝牌/黄牌/白牌/黑牌
        if len(plate) in [5, 6, 7]:
            for validator in [cls._validate_blue_plate, cls._validate_yellow_plate,
                             cls._validate_white_plate, cls._validate_black_plate]:
                result = validator(plate)
                if result.is_valid:
                    return result
        
        return PlateValidationResult(
            False, None, PlateColor.UNKNOWN, plate,
            f"无法识别的车牌格式: 长度={len(plate)}"
        )
    
    @classmethod
    def get_plate_info(cls, plate_text: str, plate_color: str = None,
                       color_conf: float = 0.0) -> Dict:
        """
        获取车牌详细信息
        
        Returns:
            {
                'is_valid': bool,
                'plate_type': str,
                'plate_color': str,
                'cleaned_plate': str,
                'reason': str,
                'length': int,
                'province': str,
            }
        """
        result = cls.validate(plate_text, plate_color, color_conf)
        
        return {
            'is_valid': result.is_valid,
            'plate_type': result.plate_type.value if result.plate_type else "未知",
            'plate_color': result.plate_color.value if result.plate_color else "未知",
            'cleaned_plate': result.cleaned_plate,
            'reason': result.reason,
            'length': len(result.cleaned_plate) if result.cleaned_plate else 0,
            'province': result.cleaned_plate[0] if result.cleaned_plate else "",
        }


# 便捷函数
def validate_plate_v2(plate_text: str, plate_color: str = None, 
                      color_conf: float = 0.0) -> Tuple[bool, Optional[str], str]:
    """
    快速验证车牌
    
    Returns:
        (is_valid, cleaned_plate, reason)
    """
    result = PlateValidatorV2.validate(plate_text, plate_color, color_conf)
    return result.is_valid, result.cleaned_plate, result.reason
