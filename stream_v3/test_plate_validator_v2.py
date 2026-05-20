"""
测试车牌验证器V2 - 验证各颜色车牌格式
"""

from detectors.plate_validator_v2 import PlateValidatorV2, PlateColor, PlateType

def safe_print(text):
    """安全打印，处理编码问题"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def test_plate(plate_text, plate_color, expected_valid, expected_type=None, description=""):
    """测试单个车牌"""
    result = PlateValidatorV2.validate(plate_text, plate_color, 0.9)
    status = "[OK]" if result.is_valid == expected_valid else "[FAIL]"
    type_match = ""
    if expected_type and result.is_valid:
        type_match = f" [类型: {result.plate_type.value if result.plate_type else 'None'}]"
    safe_print(f"{status} [{plate_color or '未知颜色'}] {plate_text:12s} -> "
          f"{'有效' if result.is_valid else '无效':4s} | {result.reason:30s}{type_match}")
    if description:
        safe_print(f"   说明: {description}")
    return result.is_valid == expected_valid

safe_print("=" * 80)
safe_print("车牌验证器V2 格式测试")
safe_print("=" * 80)

all_passed = True

# ==================== 绿色车牌（新能源）====================
print("\n【绿色车牌 - 新能源】要求: 8位")
print("-" * 60)

# 小型新能源: 省份+字母+D/F+5位
test_cases_green_small = [
    ("沪AD12345", "绿色", True, PlateType.NEW_ENERGY_SMALL, "小型新能源: 沪AD12345"),
    ("沪AF12345", "绿色", True, PlateType.NEW_ENERGY_SMALL, "小型新能源: 沪AF12345"),
    ("京AD12345", "绿色", True, PlateType.NEW_ENERGY_SMALL, "小型新能源: 京AD12345"),
    ("沪AA12345", "绿色", False, None, "小型新能源错误: 第3位不是D/F"),
    ("沪AD1234", "绿色", False, None, "小型新能源错误: 只有7位"),
    ("沪AD123456", "绿色", False, None, "小型新能源错误: 9位"),
]

# 大型新能源: 省份+字母+5位+A-K
test_cases_green_large = [
    ("沪A12345A", "绿色", True, PlateType.NEW_ENERGY_LARGE, "大型新能源: 沪A12345A (末位A)"),
    ("沪A12345B", "绿色", True, PlateType.NEW_ENERGY_LARGE, "大型新能源: 沪A12345B (末位B)"),
    ("沪A12345K", "绿色", True, PlateType.NEW_ENERGY_LARGE, "大型新能源: 沪A12345K (末位K)"),
    ("沪A12345I", "绿色", False, None, "大型新能源错误: 末位I不允许"),
    ("沪A12345O", "绿色", False, None, "大型新能源错误: 末位O不允许"),
    ("沪A12345Z", "绿色", False, None, "大型新能源错误: 末位Z不在A-K范围"),
]

for plate, color, valid, ptype, desc in test_cases_green_small + test_cases_green_large:
    if not test_plate(plate, color, valid, ptype, desc):
        all_passed = False

# ==================== 蓝色车牌（小型汽车）====================
print("\n【蓝色车牌 - 小型汽车】要求: 7位")
print("-" * 60)

test_cases_blue = [
    ("沪A12345", "蓝色", True, PlateType.SMALL_CAR, "标准蓝牌: 沪A12345"),
    ("京B12345", "蓝色", True, PlateType.SMALL_CAR, "标准蓝牌: 京B12345"),
    ("沪A1234", "蓝色", False, None, "蓝牌错误: 只有6位"),
    ("沪A123456", "蓝色", False, None, "蓝牌错误: 8位"),
    ("沪112345", "蓝色", False, None, "蓝牌错误: 第二位不是字母"),
    ("XXA12345", "蓝色", False, None, "蓝牌错误: 无效省份"),
]

for plate, color, valid, ptype, desc in test_cases_blue:
    if not test_plate(plate, color, valid, ptype, desc):
        all_passed = False

# ==================== 黄色车牌（大型/教练/挂车）====================
print("\n【黄色车牌 - 大型汽车/教练车/挂车】要求: 7位或8位")
print("-" * 60)

test_cases_yellow = [
    # 普通大型汽车: 7位
    ("沪A12345", "黄色", True, PlateType.LARGE_CAR, "普通黄牌: 沪A12345"),
    ("京B12345", "黄色", True, PlateType.LARGE_CAR, "普通黄牌: 京B12345"),
    ("沪A1234", "黄色", False, None, "黄牌错误: 只有6位，普通黄牌要求7位"),
    ("沪A123456", "黄色", False, None, "黄牌错误: 8位，普通黄牌要求7位"),

    # 教练车: 7位，末位"学"
    ("沪A1234学", "黄色", True, PlateType.COACH_CAR, "教练车: 沪A1234学 (7位)"),
    ("沪A123学", "黄色", False, None, "教练车错误: 只有6位"),
    ("沪A12345学", "黄色", False, None, "教练车错误: 8位"),

    # 挂车: 7位，末位"挂"
    ("沪A1234挂", "黄色", True, PlateType.TRAILER, "挂车: 沪A1234挂 (7位)"),
    ("沪A123挂", "黄色", False, None, "挂车错误: 只有6位"),
    ("沪A12345挂", "黄色", False, None, "挂车错误: 8位"),
]

for plate, color, valid, ptype, desc in test_cases_yellow:
    if not test_plate(plate, color, valid, ptype, desc):
        all_passed = False

# ==================== 白色车牌（警车/军车）====================
print("\n【白色车牌 - 警车/军车】要求: 7位或8位")
print("-" * 60)

test_cases_white = [
    # 警车: 7位，末位"警"
    ("沪A1234警", "白色", True, PlateType.POLICE, "警车: 沪A1234警"),
    ("沪A123警", "白色", False, None, "警车错误: 只有6位"),
    ("沪A12345警", "白色", False, None, "警车错误: 8位"),
    ("沪AA234警", "白色", False, None, "警车错误: 中间不是4位数字"),

    # 军车: 特殊前缀
    ("军V12345", "白色", True, PlateType.MILITARY, "军车: 军V12345"),
    ("V123456", "白色", True, PlateType.MILITARY, "军车: V123456"),
]

for plate, color, valid, ptype, desc in test_cases_white:
    if not test_plate(plate, color, valid, ptype, desc):
        all_passed = False

# ==================== 黑色车牌（港澳/领馆/外籍）====================
print("\n【黑色车牌 - 港澳/领馆/外籍】要求: 7位或8位")
print("-" * 60)

test_cases_black = [
    # 港澳牌: 7位，末位"港"/"澳"
    ("沪A1234港", "黑色", True, PlateType.HONGKONG_MACAU, "港澳牌: 沪A1234港 (7位)"),
    ("沪A1234澳", "黑色", True, PlateType.HONGKONG_MACAU, "港澳牌: 沪A1234澳 (7位)"),

    # 领馆牌: "使"/"领"开头
    ("使A1234", "黑色", True, PlateType.CONSULATE, "领馆牌: 使A1234 (5位)"),
    ("领B1234", "黑色", True, PlateType.CONSULATE, "领馆牌: 领B1234 (5位)"),
]

for plate, color, valid, ptype, desc in test_cases_black:
    if not test_plate(plate, color, valid, ptype, desc):
        all_passed = False

# ==================== 未知颜色（自动推断）====================
print("\n【未知颜色 - 自动推断】")
print("-" * 60)

test_cases_unknown = [
    ("沪AD12345", None, True, PlateType.NEW_ENERGY_SMALL, "未知颜色推断: 8位->新能源小型"),
    ("沪A12345", None, True, PlateType.SMALL_CAR, "未知颜色推断: 7位->蓝牌"),
    ("沪A12345A", None, True, PlateType.NEW_ENERGY_LARGE, "未知颜色推断: 8位末位A->新能源大型"),
    ("沪A1234学", None, True, PlateType.COACH_CAR, "未知颜色推断: 7位末位学->教练车"),
    ("沪A1234挂", None, True, PlateType.TRAILER, "未知颜色推断: 7位末位挂->挂车"),
    ("沪A1234警", None, True, PlateType.POLICE, "未知颜色推断: 7位末位警->警车"),
    ("沪A132618A", None, False, None, "错误: 9位车牌应被拒绝"),
    ("沪A1234567", None, False, None, "错误: 9位车牌应被拒绝"),
]

for plate, color, valid, ptype, desc in test_cases_unknown:
    if not test_plate(plate, color, valid, ptype, desc):
        all_passed = False

# ==================== 实际测试案例 ====================
print("\n【实际测试案例】")
print("-" * 60)

real_cases = [
    ("沪A32618A", "绿色", True, PlateType.NEW_ENERGY_LARGE, "用户案例: 沪A32618A (大型新能源)"),
    ("沪A132618A", "绿色", False, None, "用户案例错误: 沪A132618A (9位应被拒绝)"),
    ("沪FS2687", "蓝色", True, PlateType.SMALL_CAR, "用户案例: 沪FS2687 (蓝牌)"),
    ("沪G9980挂", "黄色", True, PlateType.TRAILER, "用户案例: 沪G9980挂 (挂车)"),
]

for plate, color, valid, ptype, desc in real_cases:
    if not test_plate(plate, color, valid, ptype, desc):
        all_passed = False

safe_print("\n" + "=" * 80)
if all_passed:
    safe_print("[OK] 所有测试通过!")
else:
    safe_print("[FAIL] 存在测试失败!")
safe_print("=" * 80)
