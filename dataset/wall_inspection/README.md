# 墙面质量检测数据集

## 数据集概况

- **总帧数**: 96 帧
- **分辨率**: 1280x720
- **来源**: 24 个施工视频（每个视频 15 秒）
- **提取策略**: 每个视频提取 4 个时间点（2s, 5s, 8s, 11s）

## 场景分类

根据图像内容，将帧分为以下类别：

### 1. 施工阶段 (construction_phase)
- `preparation` - 准备阶段（基层处理、放线）
- `spraying` - 喷涂阶段（正在喷涂砂浆/石膏）
- `leveling` - 找平阶段（刮平、收光）
- `curing` - 养护阶段（已施工完成，正在干燥）
- `inspection` - 检查阶段（工人检查质量）

### 2. 墙面状态 (wall_status)
- `bare` - 裸基层（混凝土/砌块墙面）
- `meshed` - 已铺网格布
- `coated` - 已涂覆砂浆/石膏
- `finished` - 已完成（干燥状态）

### 3. 质量问题标签 (defects) - 用于目标检测

#### 裂缝类 (crack)
- `hairline_crack` - 发丝裂缝
- `structural_crack` - 结构裂缝
- `shrinkage_crack` - 收缩裂缝

#### 表面缺陷 (surface_defect)
- `hollow` - 空鼓
- `peeling` - 起皮/剥落
- `stain` - 污渍
- `uneven` - 不平整

#### 工艺缺陷 (workmanship)
- `insufficient_coverage` - 覆盖不足
- `sagging` - 流坠
- `mesh_exposed` - 网格布外露
- `joint_visible` - 接缝明显

### 4. 设备状态 (equipment_status)
- `idle` - 待机
- `spraying` - 正在喷涂
- `moving` - 移动中
- `cleaning` - 清洗维护

## 标注规范

### 目标检测标注 (YOLO 格式)
```
<class_id> <x_center> <y_center> <width> <height>
```

类别编号：
```yaml
0: crack          # 裂缝
1: hollow         # 空鼓
2: stain          # 污渍
3: uneven         # 不平整
4: mesh           # 网格布
5: anchor         # 锚栓
6: equipment      # 设备
7: worker         # 工人
```

### 分类标注
在 `metadata.json` 中记录每张图的分类标签：
```json
{
  "filename": "JHMH2405004008_20260401_132840_t05s.jpg",
  "phase": "spraying",
  "wall_status": "coated",
  "equipment_status": "spraying",
  "defects": ["uneven"],
  "quality_score": 75
}
```

## 文件结构

```
dataset/wall_inspection/
├── raw_frames/              # 原始提取的帧
│   ├── JHMH2405004008_20260401_132840_t02s.jpg
│   ├── JHMH2405004008_20260401_132840_t05s.jpg
│   └── ...
├── train/
│   ├── images/              # 训练集图像
│   └── labels/              # YOLO 标注文件
├── val/
│   ├── images/              # 验证集图像
│   └── labels/              # YOLO 标注文件
├── metadata.json            # 分类标注信息
└── README.md                # 本文件
```

## 下一步工作

1. **人工标注**: 使用 LabelImg 或 CVAT 进行目标检测标注
2. **质量评估**: 专家评估每张图的质量分数
3. **数据增强**: 对少量样本进行旋转、翻转、亮度调整
4. **划分训练/验证集**: 建议 80% 训练，20% 验证

## 训练目标

### 检测器 1: WallDefectDetector (墙面缺陷检测)
- 输入: 1280x720 图像
- 输出: 缺陷位置 (bbox) + 缺陷类型
- 目标类别: crack, hollow, stain, uneven

### 检测器 2: FlatnessDetector (平整度检测)
- 输入: 1280x720 图像
- 输出: 平整度评分 (0-100)
- 方法: 纹理分析 + 深度学习回归

### 检测器 3: EquipmentStateDetector (设备状态检测)
- 输入: 1280x720 图像序列
- 输出: 设备状态 (idle/spraying/moving/cleaning)
- 用途: 统计施工时间、休息时间

### 检测器 4: MeshDetector (网格布检测)
- 输入: 1280x720 图像
- 输出: 网格布位置 + 铺设质量评估
- 检测: mesh, anchor

## 注意事项

1. **类别不平衡**: 正常样本可能远多于缺陷样本，考虑使用 Focal Loss
2. **小目标检测**: 裂缝可能很细，需要使用高分辨率特征图
3. **实时性**: 模型需要轻量化，适合边缘设备部署
4. **长时间运行**: 参考 stream_manager_v2 的内存管理机制
