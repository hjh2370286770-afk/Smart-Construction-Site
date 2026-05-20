# PPE 检测器集成指南

## 概述

已成功下载并配置 PPE (Personal Protective Equipment) 检测模型，可以同时检测：
- ✅ 安全帽 (Helmet)
- ✅ 反光衣/安全背心 (Safety Vest)
- ✅ 口罩 (Mask)
- ✅ 人员跟踪 (Person Tracking)

## 已下载的文件

```
stream_manager/detectors/
├── models/
│   └── ppe_best.pt          # PPE检测模型 (~6.2MB)
├── ppe_detector.py          # 新的PPE检测器
├── safety_equipment_detector.py  # 原有的安全装备检测器
├── test_ppe_model.py        # 测试脚本
├── MODEL_RESOURCES.md       # 模型资源文档
└── README.md                # 检测器说明
```

## 快速开始

### 1. 测试模型

```bash
cd stream_manager/detectors

# 运行测试（无需摄像头）
python test_ppe_model.py

# 测试摄像头
python ppe_detector.py
```

### 2. 在项目中使用

#### 方式1: 直接使用 PPEDetector（推荐）

```python
from detectors.ppe_detector import PPEDetector
import cv2

# 初始化检测器
detector = PPEDetector(
    model_path="detectors/models/ppe_best.pt",  # 可选，默认路径
    conf_threshold=0.4,  # 置信度阈值
    device='cpu'  # 或 'cuda' 如果你有GPU
)

# 读取图像
frame = cv2.imread("your_image.jpg")

# 检测
detections = detector.detect(frame)

# 处理结果
for det in detections:
    print(f"人员 {det.track_id}:")
    print(f"  安全帽: {'✓' if det.has_helmet else '✗'}")
    print(f"  反光衣: {'✓' if det.has_vest else '✗'}")
    print(f"  口罩: {'✓' if det.has_mask else '✗'}")
    print(f"  合规: {'✓' if det.is_compliant else '✗'}")

# 绘制结果
result = detector.draw_results(frame, detections)
cv2.imwrite("output.jpg", result)
```

#### 方式2: 在 StreamManager 中集成

```python
# stream_manager/main.py 或相关文件

from detectors.ppe_detector import PPEDetector

class StreamManager:
    def __init__(self):
        # 初始化PPE检测器
        self.ppe_detector = PPEDetector(
            conf_threshold=0.4
        )
        
    def process_frame(self, frame, scene_type="construction"):
        """处理视频帧"""
        
        if scene_type == "construction":
            # PPE检测
            detections = self.ppe_detector.detect(frame)
            
            # 检查违规
            violations = [d for d in detections if not d.is_compliant]
            if violations:
                self.handle_safety_violations(violations)
            
            # 绘制结果
            result = self.ppe_detector.draw_results(frame, detections)
            
            # 获取统计
            summary = self.ppe_detector.get_summary(detections)
            print(f"合规率: {summary['compliance_rate']:.1%}")
            
        return result
    
    def handle_safety_violations(self, violations):
        """处理安全违规"""
        for v in violations:
            violation_type = v.violation_type
            print(f"警告: 人员 {v.track_id} {violation_type}")
            # 可以在这里添加报警逻辑
```

## API 参考

### PPEDetector 类

#### 初始化参数

```python
detector = PPEDetector(
    model_path=None,        # 模型路径，默认 models/ppe_best.pt
    conf_threshold=0.4,     # 置信度阈值 (0-1)
    iou_threshold=0.45,     # NMS IOU阈值
    device=None             # 设备 ('cpu', 'cuda', None=自动)
)
```

#### 检测方法

```python
detections = detector.detect(
    frame,                  # numpy数组 (BGR格式)
    timestamp=None          # 时间戳（用于跟踪）
)
# 返回: List[PPEDetection]
```

#### 绘制方法

```python
result = detector.draw_results(
    frame,                  # 原始图像
    detections,             # 检测结果
    show_stats=True         # 是否显示统计面板
)
# 返回: 绘制后的图像
```

#### 统计方法

```python
summary = detector.get_summary(detections)
# 返回: {
#     "total_persons": int,
#     "compliant": int,
#     "compliance_rate": float,
#     "violations": {
#         "no_helmet": int,
#         "no_vest": int,
#         "no_mask": int,
#         "no_helmet_no_vest": int
#     }
# }
```

### PPEDetection 数据类

```python
@dataclass
class PPEDetection:
    track_id: int              # 跟踪ID
    person_bbox: List[float]   # 人员边界框 [x1, y1, x2, y2]
    confidence: float          # 置信度
    
    has_helmet: bool           # 是否戴安全帽
    helmet_bbox: List[float]   # 安全帽边界框
    helmet_confidence: float   # 安全帽置信度
    
    has_vest: bool             # 是否穿反光衣
    vest_bbox: List[float]     # 反光衣边界框
    vest_confidence: float     # 反光衣置信度
    
    has_mask: bool             # 是否戴口罩
    mask_bbox: List[float]     # 口罩边界框
    mask_confidence: float     # 口罩置信度
    
    @property
    def is_compliant(self) -> bool:  # 是否完全合规
    
    @property  
    def violation_type(self) -> str:  # 违规类型
```

## 模型类别说明

模型可以检测以下10个类别：

| 类别ID | 类别名称 | 说明 |
|--------|----------|------|
| 0 | Hardhat | 戴安全帽 |
| 1 | Mask | 戴口罩 |
| 2 | NO-Hardhat | 未戴安全帽 |
| 3 | NO-Mask | 未戴口罩 |
| 4 | NO-Safety Vest | 未穿反光衣 |
| 5 | Person | 人员 |
| 6 | Safety Cone | 安全锥 |
| 7 | Safety Vest | 穿反光衣 |
| 8 | machinery | 机械 |
| 9 | vehicle | 车辆 |

## 性能优化建议

### 1. GPU 加速

如果你有 NVIDIA GPU，可以启用 CUDA 加速：

```python
detector = PPEDetector(device='cuda')
```

### 2. 调整置信度阈值

- 高精度需求: `conf_threshold=0.5` 或更高
- 高召回需求: `conf_threshold=0.3`
- 平衡: `conf_threshold=0.4` (默认)

### 3. 跳帧处理

对于实时视频，可以每隔 N 帧检测一次：

```python
frame_count = 0
detections = []

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    # 每3帧检测一次
    if frame_count % 3 == 0:
        detections = detector.detect(frame)
    
    # 使用上一次的检测结果绘制
    result = detector.draw_results(frame, detections)
    frame_count += 1
```

## 常见问题

### Q: 模型加载失败？

检查：
1. `models/ppe_best.pt` 文件是否存在
2. ultralytics 是否安装: `pip install ultralytics`
3. 模型文件是否完整（大小应为 ~6.2MB）

### Q: 检测效果不佳？

尝试：
1. 调整 `conf_threshold`（降低阈值可以看到更多检测结果）
2. 确保图像质量良好（光线充足、清晰）
3. 人员距离摄像头不要太远

### Q: 如何训练自己的模型？

如果你有工地现场图片，可以：
1. 使用 LabelImg 标注数据
2. 使用 YOLOv8 训练脚本
3. 替换 `ppe_best.pt`

我可以帮你写训练脚本！

## 下一步

1. ✅ 下载 PPE 检测模型
2. ✅ 创建检测器类
3. ✅ 编写测试脚本
4. ⏳ 集成到你的 stream_manager 项目
5. ⏳ 根据实际场景调优

告诉我你需要如何集成到现有项目中，我可以帮你修改代码！
