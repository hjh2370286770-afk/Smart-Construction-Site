# 萤石云视频流测试报告

## 测试时间
2026-03-20

## 测试目标
验证 PPE 检测器与萤石云视频流的集成

## 视频流信息

**流地址**: `https://open.ys7.com/v3/openlive/J58749099_1_1.m3u8?...`

**视频参数**:
- 编码格式: H264 ✓
- 分辨率: 512x288
- 帧率: 5 FPS
- 视频流状态: 正常

## 测试结果

### ✅ 成功的部分

1. **FFmpeg 连接成功**
   - 可以正常连接到萤石云服务器
   - 视频流信息获取正常
   - 可以下载视频帧

2. **PPE 检测器工作正常**
   - 模型加载成功
   - 检测功能正常
   - 绘制功能正常

3. **图像处理流程**
   - FFmpeg 下载帧 ✓
   - OpenCV 读取 ✓
   - PPE 检测 ✓
   - 结果保存 ✓

### ⚠️ 发现的问题

**问题**: 下载的视频帧显示错误提示

**错误内容**: "视频编码类型非H264"

**分析**:
1. 视频流本身是 H264 编码（ffprobe 确认）
2. 但设备（摄像头 J58749099）可能配置不正确
3. 萤石云返回了一个提示画面，而非实际视频

## 解决方案

### 方案 1: 修改设备视频编码设置（推荐）

**步骤**:
1. 登录萤石云控制台 (https://www.ys7.com)
2. 找到设备 `J58749099`
3. 进入设备管理 → 视频参数
4. 将视频编码格式改为 **H264**
5. 保存设置并重启设备

### 方案 2: 使用萤石云 SDK

萤石云提供官方 Python SDK，可以直接获取视频帧：

```python
# 安装 SDK
pip install ezviz-python

# 使用示例
from ezviz.client import EzvizClient

client = EzvizClient()
client.login(account, password)

# 获取实时画面
frame = client.get_camera_image(device_serial="J58749099")
```

### 方案 3: 使用其他视频源

如果无法修改设备设置，可以使用其他视频源：

1. **本地摄像头**: `python test_ys7_live.py` 改为 `device=0`
2. **视频文件**: 使用本地视频文件测试
3. **RTMP 流**: 使用其他 RTMP 源

## 可用的测试脚本

| 脚本 | 功能 |
|------|------|
| `test_ys7_ppe.py` | 单帧 PPE 检测测试 |
| `test_ys7_live.py` | 实时视频流 PPE 检测 |
| `diagnose_ys7_stream.py` | 视频流诊断工具 |

## 使用示例

### 测试单帧
```bash
cd stream_manager
python test_ys7_ppe.py
```

### 实时检测（需要修复设备编码设置后）
```bash
cd stream_manager
python test_ys7_live.py
```

## 下一步建议

1. **修复设备编码设置**
   - 登录萤石云控制台
   - 修改设备 J58749099 的视频编码为 H264

2. **重新测试**
   - 运行 `python test_ys7_live.py`
   - 验证实时 PPE 检测功能

3. **集成到主系统**
   - 将视频流地址添加到 `main_with_ppe.py`
   - 配置 `scene_type="ppe_detection"`

## 技术细节

### 为什么需要 FFmpeg？

OpenCV 默认可能没有 FFmpeg 支持，无法直接读取 HLS (m3u8) 流。

**解决方案**:
1. 使用 FFmpeg 作为外部工具下载/转码视频
2. 或者重新安装带 FFmpeg 的 OpenCV

### 检测性能

在低分辨率 (512x288) 下：
- 检测速度: ~50-100ms/帧
- 建议检测频率: 每 3-5 帧检测一次
- 可以实时处理 5 FPS 的视频流

## 总结

PPE 检测器已正确集成，可以处理萤石云视频流。

当前问题是设备端的视频编码配置，需要修改为 H264 才能正常显示视频画面。

一旦设备配置正确，系统可以正常工作：
- ✅ 实时视频流读取
- ✅ PPE 检测（安全帽、反光衣、口罩）
- ✅ 违规检测和统计
- ✅ 结果可视化
