# 检测器模块

## 概述

检测器模块包含多个核心检测算法：

1. **PPE综合检测** (`ppe_detector.py`) ⭐ 推荐
2. **安全帽检测** (`helmet_detector.py`)
3. **反光衣检测** (`vest_detector.py`)
4. **安全装备综合检测** (`safety_equipment_detector.py`)
5. **车辆进出检测** (`vehicle_counter.py`)

以及一个统一管理器：`detector_manager.py`

---

## 🆕 PPE 综合检测 (ppe_detector.py) - 推荐

### 功能

- 同时检测安全帽、反光衣、口罩
- 识别未戴安全帽、未穿反光衣、未戴口罩
- 人员跟踪和关联
- 合规性自动判断
- 专用 YOLOv8 模型，精度更高

### 模型

- **文件**: `models/ppe_best.pt` (~6.2MB)
- **来源**: [Construction-Site-Safety-PPE-Detection](https://github.com/snehilsanyal/Construction-Site-Safety-PPE-Detection)
- **类别**: 10类 (Hardhat, Mask, NO-Hardhat, NO-Mask, NO-Safety Vest, Person, Safety Cone, Safety Vest, machinery, vehicle)

### 使用示例

```python
from detectors.ppe_detector import PPEDetector

# 创建检测器（自动加载模型）
detector = PPEDetector(conf_threshold=0.4)

# 检测
detections = detector.detect(frame)

# 处理结果
for det in detections:
    print(f"人员 {det.track_id}:")
    print(f"  安全帽: {'✓' if det.has_helmet else '✗'}")
    print(f"  反光衣: {'✓' if det.has_vest else '✗'}")
    print(f"  口罩: {'✓' if det.has_mask else '✗'}")
    print(f"  合规: {'✓' if det.is_compliant else '✗'}")

# 获取统计摘要
summary = detector.get_summary(detections)
print(f"合规率: {summary['compliance_rate']:.1%}")

# 绘制结果
result = detector.draw_results(frame, detections)
```

### 检测结果结构

```python
@dataclass
class PPEDetection:
    track_id: int
    person_bbox: List[float]       # [x1, y1, x2, y2]
    confidence: float
    
    has_helmet: bool = False
    helmet_bbox: Optional[List[float]] = None
    helmet_confidence: float = 0.0
    
    has_vest: bool = False
    vest_bbox: Optional[List[float]] = None
    vest_confidence: float = 0.0
    
    has_mask: bool = False
    mask_bbox: Optional[List[float]] = None
    mask_confidence: float = 0.0
    
    @property
    def is_compliant(self) -> bool:      # 安全帽 + 反光衣
    @property
    def violation_type(self) -> str:     # 违规类型
```

### 测试

```bash
# 测试摄像头
python ppe_detector.py

# 测试图片
python ppe_detector.py path/to/image.jpg

# 运行测试脚本
python test_ppe_model.py
```

### 文档

- [PPE 集成指南](PPE_INTEGRATION_GUIDE.md)
- [模型资源说明](MODEL_RESOURCES.md)

---

## 安全帽检测 (helmet_detector.py)

### 功能

- 检测人员是否佩戴安全帽
- 识别安全帽颜色（红/黄/蓝/白）
- 关联人体和头部区域

### 使用示例

```python
from detectors.helmet_detector import HelmetDetector

# 创建检测器
detector = HelmetDetector(
    model_path="yolov8n.pt",
    conf_threshold=0.5
)

# 检测
detections = detector.detect(frame)

# 获取结果摘要
summary = detector.get_summary(detections)
print(f"Total: {summary['total_persons']}")
print(f"With helmet: {summary['with_helmet']}")
print(f"Without helmet: {summary['without_helmet']}")
print(f"Compliance rate: {summary['compliance_rate']:.1%}")

# 绘制结果
result = detector.draw_results(frame, detections)
```

### 检测结果结构

```python
@dataclass
class HelmetDetection:
    bbox: List[float]          # [x1, y1, x2, y2]
    confidence: float
    has_helmet: bool           # True=戴安全帽
    helmet_color: Optional[str]  # red/yellow/blue/white
    person_bbox: Optional[List[float]]
```

---

## 反光衣检测 (vest_detector.py)

### 功能

- 检测人员是否穿着反光衣
- 识别反光衣颜色（橙色/黄色/红色）
- 分析反光条纹特征
- 反光特征评分

### 使用示例

```python
from detectors.vest_detector import ReflectiveVestDetector

# 创建检测器
detector = ReflectiveVestDetector(
    model_path="yolov8n.pt",
    conf_threshold=0.5,
    reflective_threshold=0.3  # 反光特征阈值
)

# 检测
detections = detector.detect(frame)

# 获取结果摘要
summary = detector.get_summary(detections)
print(f"With vest: {summary['with_vest']}")
print(f"Without vest: {summary['without_vest']}")
print(f"Avg reflective score: {summary['avg_reflective_score']:.2f}")
```

### 检测结果结构

```python
@dataclass
class VestDetection:
    bbox: List[float]
    confidence: float
    has_vest: bool
    vest_color: Optional[str]  # orange/yellow/red
    person_bbox: Optional[List[float]]
    reflective_score: float    # 0-1
```

---

## 车辆进出检测 (vehicle_counter.py)

### 功能

- 车辆检测和类型识别（轿车/卡车/巴士/摩托车）
- 车辆跟踪和轨迹分析
- 进出方向判断
- 跨线计数

### 使用示例

```python
from detectors.vehicle_counter import VehicleCounter

# 创建计数器
counter = VehicleCounter(
    model_path="yolov8n.pt",
    conf_threshold=0.5
)

# 添加计数线（从画面下方进入算"进"）
counter.add_count_line(
    name="main_gate",
    start_point=(100, 300),
    end_point=(540, 300),
    in_direction="bottom"
)

# 检测和跟踪
timestamp = time.time()
tracks = counter.detect_and_track(frame, timestamp)

# 获取统计摘要
summary = counter.get_summary()
print(f"Total IN: {summary['total_in']}")
print(f"Total OUT: {summary['total_out']}")
print(f"Current tracks: {summary['current_tracks']}")

# 绘制结果
result = counter.draw_results(frame, tracks)
```

### 计数线配置

```python
# 水平线，从下方进入算"进"
counter.add_count_line("gate", (100, 300), (540, 300), "bottom")

# 水平线，从上方进入算"进"
counter.add_count_line("gate", (100, 300), (540, 300), "top")

# 垂直线，从左侧进入算"进"
counter.add_count_line("gate", (300, 100), (300, 400), "left")
```

---

## 检测器管理器 (detector_manager.py)

### 功能

- 统一管理所有检测模型
- 根据场景类型自动路由
- 统一结果格式
- 统一绘制方法

### 使用示例

```python
from detectors.detector_manager import DetectorManager

# 创建管理器
manager = DetectorManager(models_dir="..")

# 配置并初始化
configs = {
    "helmet": {"conf_threshold": 0.5},
    "vest": {"conf_threshold": 0.5},
    "vehicle": {"conf_threshold": 0.5}
}
manager.initialize(configs)

# 配置车辆计数线
manager.configure_vehicle_line("gate", (100, 300), (540, 300), "bottom")

# 根据场景类型自动选择检测器
result = manager.detect(frame, "safety_helmet")
result = manager.detect(frame, "reflective_vest")
result = manager.detect(frame, "vehicle_count", timestamp=time.time())

# 统一绘制结果
display = manager.draw_results(frame, scene_type, result)
```

### 场景类型映射

| 场景标识 | 检测器 | 说明 |
|---------|--------|------|
| `safety_helmet` / `helmet` | HelmetDetector | 安全帽检测 |
| `reflective_vest` / `vest` | ReflectiveVestDetector | 反光衣检测 |
| `vehicle_count` / `vehicle` / `car` | VehicleCounter | 车辆进出计数 |

### 统一结果格式

```python
{
    "success": True,
    "scene_type": "safety_helmet",
    "detections": [...],
    "summary": {...},
    "count": 10,
    "violation_count": 2  # 违规数量（安全帽/反光衣场景）
}
```

---

## 测试

每个检测器都可以独立测试：

```bash
cd stream_manager/detectors

# 测试安全帽检测
python helmet_detector.py

# 测试反光衣检测
python vest_detector.py

# 测试车辆计数
python vehicle_counter.py

# 测试检测器管理器
python detector_manager.py
```

---

## 模型优化建议

### 1. 专用模型训练

当前使用通用 YOLOv8n 模型，建议针对工地场景训练专用模型：

```python
# 安全帽检测专用模型
# 类别：person, helmet, no_helmet

# 反光衣检测专用模型
# 类别：person, reflective_vest, no_vest

# 车辆检测
# 使用 yolov8n 即可，已有 car, truck, bus, motorcycle
```

### 2. 模型量化加速

```python
# 导出 ONNX 格式
model.export(format="onnx", simplify=True)

# 使用 TensorRT 加速（NVIDIA GPU）
model.export(format="engine", device=0)
```

### 3. 多模型融合

对于复杂场景，可以组合多个检测器：

```python
# 同时进行安全帽和反光衣检测
helmet_result = manager.detect(frame, "safety_helmet")
vest_result = manager.detect(frame, "reflective_vest")

# 合并违规人员
violations = []
for h_det in helmet_result["detections"]:
    if not h_det["has_helmet"]:
        violations.append({
            "type": "no_helmet",
            "bbox": h_det["bbox"]
        })
```
