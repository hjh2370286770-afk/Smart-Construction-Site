# 工地安全检测 - 预训练模型资源

## 已下载的模型

### PPE 综合检测模型（已下载 ✓）

**模型文件**: `models/ppe_best.pt`
**来源**: [Construction-Site-Safety-PPE-Detection](https://github.com/snehilsanyal/Construction-Site-Safety-PPE-Detection)
**框架**: YOLOv8
**大小**: ~6.2 MB
**检测类别** (10类):
1. Hardhat (安全帽) ✓
2. Mask (口罩) ✓
3. NO-Hardhat (未戴安全帽) ✓
4. NO-Mask (未戴口罩) ✓
5. NO-Safety Vest (未穿反光衣) ✓
6. Person (人员) ✓
7. Safety Cone (安全锥)
8. Safety Vest (反光衣/安全背心) ✓
9. machinery (机械)
10. vehicle (车辆)

**适用场景**: 工地安全监控、人员PPE合规检测

---

## 使用方法

### 方法1: 使用新的 PPE 检测器（推荐）

```python
from ppe_detector import PPEDetector

# 初始化检测器（自动加载 models/ppe_best.pt）
detector = PPEDetector(conf_threshold=0.4)

# 检测图像
detections = detector.detect(frame)

# 绘制结果
result = detector.draw_results(frame, detections)

# 获取统计摘要
summary = detector.get_summary(detections)
print(f"合规率: {summary['compliance_rate']:.1%}")
```

### 方法2: 使用原有的安全装备检测器

```python
from safety_equipment_detector import SafetyEquipmentDetector

# 使用专用模型
detector = SafetyEquipmentDetector(
    model_path="models/ppe_best.pt",
    use_custom_model=True,
    conf_threshold=0.4
)
```

---

## 模型对比

| 特性 | ppe_best.pt (新) | yolov8n.pt (原有) |
|------|------------------|-------------------|
| 检测类别 | 10类PPE相关 | 80类COCO通用 |
| 安全帽检测 | ✓ 专用训练 | 基于颜色分析 |
| 反光衣检测 | ✓ 专用训练 | 基于颜色分析 |
| 口罩检测 | ✓ 支持 | ✗ 不支持 |
| 精度 | 高（专用模型） | 中（通用模型） |
| 速度 | 快 | 快 |
| 模型大小 | 6.2 MB | 6.0 MB |

---

## 推荐的预训练模型（GitHub）

### 1. 安全帽检测模型

#### 推荐项目：

**项目1: yolov5-helmet-detection**
- GitHub: https://github.com/topics/helmet-detection
- 说明：基于YOLOv5的安全帽检测
- 类别：person, head, helmet

**项目2: HelmetDetection**
- GitHub: https://github.com/wujixiu/helmet-detection
- 说明：安全帽佩戴检测
- 预训练模型可用

**项目3: yolov8-helmet**
- GitHub: 搜索 "yolov8 helmet detection"
- 说明：基于YOLOv8的安全帽检测

### 2. 反光衣检测模型

**项目1: safety-vest-detection**
- GitHub: https://github.com/topics/safety-vest-detection
- 说明：反光衣/安全背心检测

**项目2: PPE-Detection**
- GitHub: 搜索 "PPE detection yolo"
- 说明：个人防护装备检测（包含反光衣）

### 3. 综合安全检测模型（推荐）

**项目1: yolov5-ppe-detection**
- GitHub: https://github.com/topics/ppe-detection
- 说明：综合PPE检测（安全帽+反光衣+其他）
- 类别：helmet, vest, person 等

**项目2: construction-safety-detection**
- 搜索关键词："construction safety detection yolo"
- 说明：工地安全综合检测

---

## 如何下载使用

### 方法1：直接下载预训练权重

```bash
# 示例：下载YOLOv5安全帽检测模型
wget https://github.com/xxx/helmet-detection/releases/download/v1.0/best.pt

# 示例：下载YOLOv8安全帽检测模型
wget https://github.com/xxx/yolov8-helmet/releases/download/v1.0/helmet_best.pt
```

### 方法2：使用GitHub上的模型

```python
from ultralytics import YOLO

# 加载本地模型
model = YOLO("path/to/helmet_best.pt")

# 或使用我提供的整合检测器
from safety_equipment_detector import SafetyEquipmentDetector

detector = SafetyEquipmentDetector(
    model_path="path/to/helmet_best.pt",  # 专用模型
    use_custom_model=True
)
```

---

## 推荐的模型下载链接

### 国内可用（Gitee/百度网盘）

由于GitHub访问可能不稳定，推荐以下国内资源：

1. **百度网盘搜索**：
   - 搜索关键词："YOLO安全帽检测模型"
   - 搜索关键词："YOLO反光衣检测模型"

2. **阿里天池/ModelScope**：
   - https://modelscope.cn/
   - 搜索：安全帽检测、工地安全检测

3. **飞桨PaddleHub**：
   - https://www.paddlepaddle.org.cn/hub
   - 有现成的安全帽检测模型

---

## 我提供的解决方案

### 方案1：使用专用PPE模型（已下载，推荐）

**文件**: `ppe_detector.py` + `models/ppe_best.pt`

**优点**：
- ✓ 专用训练模型，精度高
- ✓ 同时检测安全帽、反光衣、口罩
- ✓ 支持未戴/未穿的负样本检测
- ✓ 人员跟踪和关联

**使用方法**：
```python
from ppe_detector import PPEDetector

detector = PPEDetector()  # 自动加载模型
detections = detector.detect(frame)
```

### 方案2：使用通用YOLOv8模型 + 颜色分析（原有）

**文件**: `safety_equipment_detector.py`

**优点**：
- 无需额外下载模型
- 直接使用你现有的 yolov8n.pt
- 通过颜色分析检测安全帽和反光衣

**缺点**：
- 精度不如专用模型
- 依赖颜色特征

**使用方法**：
```python
from safety_equipment_detector import SafetyEquipmentDetector

detector = SafetyEquipmentDetector(
    model_path="yolov8n.pt",
    use_custom_model=False  # 使用颜色分析
)
```

### 方案3：使用专用模型（原有兼容方式）

**步骤1：下载预训练模型**

你可以从以下渠道获取：

| 来源 | 链接/方法 | 说明 |
|------|----------|------|
| GitHub | 搜索 "yolov8 helmet vest detection" | 可能需要科学上网 |
| 百度网盘 | 搜索 "YOLOv8安全帽反光衣模型" | 国内可用 |
| 阿里ModelScope | modelscope.cn | 国内可用 |
| 飞桨PaddleHub | paddlepaddle.org.cn/hub | 国内可用 |

**步骤2：使用专用模型**

```python
from safety_equipment_detector import SafetyEquipmentDetector

# 使用专用模型
detector = SafetyEquipmentDetector(
    model_path="safety_equipment_best.pt",  # 专用模型
    use_custom_model=True
)
```

---

## 快速开始

### 立即使用（推荐）

```bash
cd stream_manager/detectors

# 测试摄像头
python ppe_detector.py

# 测试图片
python ppe_detector.py path/to/image.jpg
```

### 在项目中集成

```python
from detectors.ppe_detector import PPEDetector

class YourSystem:
    def __init__(self):
        self.ppe_detector = PPEDetector(conf_threshold=0.4)
    
    def process_frame(self, frame):
        # 检测PPE
        detections = self.ppe_detector.detect(frame)
        
        # 检查是否有违规
        for det in detections:
            if not det.is_compliant:
                self.handle_violation(det)
        
        # 绘制结果
        result = self.ppe_detector.draw_results(frame, detections)
        return result
```

---

## 模型训练（如果需要）

如果你有工地现场图片，我可以帮你训练专用模型：

### 需要的训练数据

```
dataset/
├── images/
│   ├── train/      # 训练图片
│   └── val/        # 验证图片
└── labels/
    ├── train/      # 训练标注
    └── val/        # 验证标注
```

### 标注类别建议

```yaml
# data.yaml
nc: 5
names: ['person', 'helmet', 'no_helmet', 'vest', 'no_vest']
```

### 训练命令

```python
from ultralytics import YOLO

# 加载预训练模型
model = YOLO('yolov8n.pt')

# 训练
model.train(
    data='data.yaml',
    epochs=100,
    imgsz=640,
    batch=16,
    name='safety_equipment'
)
```

---

## 需要帮助？

告诉我：
1. 你能访问GitHub吗？
2. 你有工地现场图片可以用于训练吗？
3. 你希望我先帮你实现哪个功能？

我可以：
- 帮你下载和配置预训练模型 ✓ 已完成
- 写数据标注脚本
- 写模型训练脚本
- 优化检测算法
