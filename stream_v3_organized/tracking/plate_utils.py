"""
车牌识别优化工具
- 车牌格式验证
- 智能去重
- 结果过滤
- 车牌相似度计算 (统一实现 + 缓存)
"""

import re
from typing import Optional, List, Dict
from collections import defaultdict
from functools import lru_cache


@lru_cache(maxsize=5000)
def levenshtein_distance(s1: str, s2: str) -> int:
    """统一Levenshtein编辑距离计算 (带缓存)"""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def plate_similarity(p1: str, p2: str) -> float:
    """统一车牌相似度计算"""
    if not p1 or not p2:
        return 0.0
    if p1 == p2:
        return 1.0
    if abs(len(p1) - len(p2)) > 2:
        return 0.0

    max_len = max(len(p1), len(p2))
    distance = levenshtein_distance(p1, p2)
    base_sim = 1.0 - (distance / max_len)

    # 后缀相似度（去掉第一个字符）
    if len(p1) > 1 and len(p2) > 1:
        suffix_dist = levenshtein_distance(p1[1:], p2[1:])
        suffix_max = max(len(p1) - 1, len(p2) - 1)
        suffix_sim = 1.0 - (suffix_dist / suffix_max) if suffix_max > 0 else 1.0
        return max(base_sim, suffix_sim * 0.95)

    return base_sim

class PlateValidator:
    """车牌号码验证器"""
    
    # 省份简称
    PROVINCES = [
        '京', '津', '沪', '渝', '冀', '豫', '云', '辽',
        '黑', '湘', '皖', '鲁', '新', '苏', '浙', '赣',
        '鄂', '桂', '甘', '晋', '蒙', '陕', '吉', '闽',
        '贵', '粤', '川', '青', '藏', '琼', '宁'
    ]
    
    # 特殊车牌前缀
    SPECIAL_PREFIXES = ['军', '警', '使', '领', '港', '澳', '学', '挂']
    
    @classmethod
    def validate_plate(cls, plate_text: str) -> tuple:
        """
        验证车牌号
        
        Returns:
            (is_valid, reason, cleaned_plate)
        """
        if not plate_text:
            return False, "空字符串", None
            
        # 清理文本
        cleaned = cls._clean_plate(plate_text)
        if not cleaned:
            return False, "清理后为空", None
            
        # 长度检查（标准车牌7-8位，特殊可能更短）
        if len(cleaned) < 6 or len(cleaned) > 10:
            return False, f"长度异常: {len(cleaned)}", None
            
        # 检查是否包含省份或特殊前缀
        has_valid_prefix = (
            cleaned[0] in cls.PROVINCES or 
            cleaned[0] in cls.SPECIAL_PREFIXES
        )
        
        # 检查重复字符比例（超过50%可能是错误）
        char_counts = defaultdict(int)
        for c in cleaned:
            char_counts[c] += 1
        max_count = max(char_counts.values())
        if max_count > len(cleaned) * 0.5:
            return False, f"重复字符过多: {max_count}/{len(cleaned)}", None
            
        # 检查是否包含明显错误的字符组合
        error_patterns = ['危险', '品', '民', '警9', '险']
        for pattern in error_patterns:
            if pattern in cleaned:
                return False, f"包含错误模式: {pattern}", None
                
        # 基本格式验证：省份+字母+数字+字母/数字
        # 简化版验证
        if len(cleaned) >= 7:
            if has_valid_prefix:
                return True, "有效", cleaned
            else:
                # 可能是纯字母数字组合，但缺少省份
                # 如果看起来像合理格式，也接受
                if re.match(r'^[A-Z]\d{5,6}$', cleaned):
                    return True, "有效(无省份)", cleaned
                elif re.match(r'^[A-Z][A-Z0-9]{5,8}$', cleaned):
                    return True, "有效(无省份)", cleaned
                    
        return False, "格式不匹配", None
    
    @classmethod
    def _clean_plate(cls, text: str) -> Optional[str]:
        """清理车牌文字"""
        # 去除空格和特殊字符
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', text)
        # 转大写
        text = text.upper()
        return text if text else None


class PlateDeduplicator:
    """车牌智能去重器"""
    
    def __init__(self, similarity_threshold: float = 0.7, 
                 time_window: float = 30.0,
                 min_appearances: int = 2):
        """
        Args:
            similarity_threshold: 相似度阈值 (0-1)
            time_window: 时间窗口（秒）
            min_appearances: 最少出现次数才确认为有效车牌
        """
        self.similarity_threshold = similarity_threshold
        self.time_window = time_window
        self.min_appearances = min_appearances
        
        # 存储已确认的车牌
        self.confirmed_plates: Dict[str, dict] = {}
        
        # 存储候选车牌（待确认）
        self.candidate_plates: Dict[str, List[tuple]] = defaultdict(list)
    
    def add_plate(self, plate_text: str, timestamp: float, 
                  confidence: float = 1.0) -> Optional[str]:
        """
        添加检测到的车牌
        
        Returns:
            确认的车牌号（如果达到阈值），否则返回None
        """
        if not plate_text:
            return None
            
        # 清理并验证
        is_valid, _, cleaned = PlateValidator.validate_plate(plate_text)
        if not is_valid or not cleaned:
            return None
            
        # 检查是否与已确认的相似
        confirmed_match = self._find_similar(cleaned, self.confirmed_plates.keys())
        if confirmed_match:
            # 更新时间戳
            self.confirmed_plates[confirmed_match]['last_seen'] = timestamp
            self.confirmed_plates[confirmed_match]['count'] += 1
            return confirmed_match
            
        # 添加到候选列表
        self.candidate_plates[cleaned].append((timestamp, confidence))
        
        # 清理过期候选
        self._cleanup_candidates(timestamp)
        
        # 统计该候选的出现次数
        recent_count = sum(
            1 for t, c in self.candidate_plates[cleaned]
            if timestamp - t <= self.time_window
        )
        
        # 检查是否达到确认阈值
        if recent_count >= self.min_appearances:
            # 确认这个车牌
            self.confirmed_plates[cleaned] = {
                'first_seen': min(t for t, c in self.candidate_plates[cleaned]),
                'last_seen': timestamp,
                'count': len(self.candidate_plates[cleaned]),
                'avg_confidence': sum(c for t, c in self.candidate_plates[cleaned]) / len(self.candidate_plates[cleaned])
            }
            
            # 从候选中移除
            del self.candidate_plates[cleaned]
            
            return cleaned
            
        return None
    
    def _find_similar(self, plate: str, existing_plates: list) -> Optional[str]:
        """查找相似的车牌"""
        for existing in existing_plates:
            similarity = self._calculate_similarity(plate, existing)
            if similarity >= self.similarity_threshold:
                return existing
        return None
    
    def _calculate_similarity(self, plate1: str, plate2: str) -> float:
        """计算两个车牌的相似度"""
        if not plate1 or not plate2:
            return 0.0
            
        # 完全相同
        if plate1 == plate2:
            return 1.0
            
        # 长度差异太大
        if abs(len(plate1) - len(plate2)) > 2:
            return 0.0
            
        # 编辑距离相似度
        distance = self._levenshtein_distance(plate1, plate2)
        max_len = max(len(plate1), len(plate2))
        similarity = 1.0 - (distance / max_len)
        
        return similarity
    
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """计算编辑距离"""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
            
        if len(s2) == 0:
            return len(s1)
            
        previous_row = range(len(s2) + 1)
        
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
                
            previous_row = current_row
            
        return previous_row[-1]
    
    def _cleanup_candidates(self, current_time: float):
        """清理过期的候选"""
        expired = []
        for plate, records in self.candidate_plates.items():
            # 只保留时间窗口内的记录
            valid_records = [
                (t, c) for t, c in records
                if current_time - t <= self.time_window
            ]
            if not valid_records:
                expired.append(plate)
            else:
                self.candidate_plates[plate] = valid_records
                
        for plate in expired:
            del self.candidate_plates[plate]
    
    def get_confirmed_plates(self) -> List[Dict]:
        """获取所有已确认的车牌"""
        result = []
        for plate, info in self.confirmed_plates.items():
            result.append({
                'plate': plate,
                **info
            })
        return sorted(result, key=lambda x: x['first_seen'])
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        return {
            'confirmed_count': len(self.confirmed_plates),
            'candidate_count': len(self.candidate_plates),
            'total_candidates': sum(len(v) for v in self.candidate_plates.values())
        }


def validate_and_filter_plate(plate_text: str) -> tuple:
    """
    快速验证和过滤车牌
    
    Returns:
        (is_valid, cleaned_plate, reason)
    """
    return PlateValidator.validate_plate(plate_text)


def create_plate_deduplicator(**kwargs) -> PlateDeduplicator:
    """创建去重器实例"""
    return PlateDeduplicator(**kwargs)
