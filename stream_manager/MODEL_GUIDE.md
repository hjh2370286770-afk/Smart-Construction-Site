# 模型获取指南

## 现状

由于网络限制，我无法直接帮你从GitHub下载模型，但我为你准备了完整的解决方案。

---

## 方案1：使用现有YOLOv8模型（立即可用）✅

你已经有的 `yolov8n.pt` 可以直接使用，我写的 `safety_equipment_detector.py` 基于颜色分析，无需额外模型。

```python
from detectors.safety_equipment_detector import SafetyEquipmentDetector

detector = SafetyEquipmentDetector(
    model_path="yolov8n.pt",  # 使用你现有的模型
    use_custom_model=False     # 使用颜色分析检测
)
```

**优点**：
- 无需下载额外模型
- 立即可用
- 通过颜色特征检测安全帽和反光衣

---

## 方案2：手动下载预训练模型（推荐）

### 步骤1：搜索并下载模型

你可以从以下渠道搜索下载：

#### 国内可用资源：

1. **百度网盘**（推荐）
   - 搜索关键词：`YOLOv8 安全帽检测模型`、`YOLO 反光衣检测`
   - 常见文件名：`helmet_best.pt`、`safety_vest.pt`、`ppe_detection.pt`

2. **阿里ModelScope**
   - 网址：https://modelscope.cn/
   - 搜索：`安全帽检测`、`工地安全检测`

3. **飞桨PaddleHub**
   - 网址：https://www.paddlepaddle.org.cn/hub
   - 搜索：`helmet detection`

4. **CSDN下载**
   - 搜索：`YOLOv8安全帽检测权重`

#### 如果能访问GitHub：

搜索这些关键词：
- `yolov8 helmet detection`
- `safety vest detection yolo`
- `PPE detection yolov8`
- `construction safety yolo`

### 步骤2：放置模型文件

下载后将 `.pt` 文件放在项目根目录：

```
workspace/
├── yolov8n.pt              # 你现有的模型
├── helmet_best.pt          # 安全帽专用模型（下载后放置）
├── vest_best.pt            # 反光衣专用模型（下载后放置）
└── safety_equipment.pt     # 综合模型（下载后放置）
```

### 步骤3：修改配置使用

```python
# 使用专用模型
detector = SafetyEquipmentDetector(
    model_path="safety_equipment.pt",  # 专用模型
    use_custom_model=True               # 启用专用模型模式
)
```

---

## 方案3：训练自己的模型（最佳效果）

如果你能获得工地现场图片，我可以帮你训练专用模型。

### 需要的图片数量：
- 最少：每个类别 100 张
- 推荐：每个类别 500-1000 张
- 类别：person, helmet, no_helmet, vest, no_vest

### 标注工具：
- **LabelImg**：https://github.com/tzutalin/labelImg
- **LabelMe**：https://github.com/wkentaro/labelme
- **CVAT**（在线）：https://cvat.org/

### 我可以帮你：
1. 写数据标注指南
2. 写数据预处理脚本
3. 写训练脚本
4. 模型优化建议

---

## 推荐的预训练模型列表

如果你能下载，这些模型效果较好：

| 模型名称 | 来源 | 类别 | 说明 |
|---------|------|------|------|
| yolov8-helmet | GitHub | helmet, no_helmet, person | 安全帽专用 |
| yolov5-vest | GitHub | vest, no_vest, person | 反光衣专用 |
| yolov8-ppe | GitHub | helmet, vest, person | 综合PPE检测 |
| construction-safety | ModelScope | 多类别 | 工地安全综合 |

---

## 快速测试

现在就可以测试现有的检测功能：

```bash
cd stream_manager/detectors
python safety_equipment_detector.py
```

这会打开摄像头，实时检测安全帽和反光衣。

---

## 下一步建议

1. **立即测试**：运行上面的命令，看看现有效果
2. **收集图片**：用手机拍摄工地现场照片
3. **下载模型**：尝试从百度网盘搜索下载
4. **反馈效果**：告诉我检测结果如何，我可以优化算法

需要我帮你写数据标注指南或训练脚本吗？
