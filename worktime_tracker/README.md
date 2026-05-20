# 人员工作时间统计系统

基于视频流的人员检测和工作时间统计工具。

## 功能特点

- **RTSP视频流连接**：支持连接RTSP摄像头，自动重连机制处理不稳定连接
- **人员检测**：使用YOLOv8模型检测视频中的人员
- **人员跟踪**：为每个人员分配唯一ID，跟踪其在画面中的时间
- **工作时间统计**：记录每个人的工作时长、首次/最后出现时间
- **统计报告**：程序关闭时自动生成详细的工作时间报告（控制台输出+JSON文件）

## 安装依赖

```bash
pip install -r requirements.txt
```

首次运行时会自动下载YOLOv8n预训练模型（约6MB）。

## 使用方法

### 基本使用

```bash
python worktime_tracker.py
```

### 修改视频流地址

编辑 `worktime_tracker.py` 文件中的 `stream_url` 变量：

```python
stream_url = "rtsp://admin:abcd1234@192.168.2.64/h264/ch1/main/av_stream"
```

### 运行选项

```python
tracker.run(duration=None, enable_display=True)
```

- `duration`: 运行时长（秒），`None`表示无限运行直到手动退出
- `enable_display`: 是否显示视频窗口

### 键盘控制

- `q` - 退出程序
- `s` - 保存当前截图
- `p` - 暂停/继续

## 输出文件

程序运行后会生成以下文件在 `worktime_output` 目录：

- `worktime_report_YYYYMMDD_HHMMSS.json` - 工作时间统计报告（JSON格式）
- `screenshot_YYYYMMDD_HHMMSS.jpg` - 手动保存的截图

## 报告格式

JSON报告包含以下信息：

```json
{
  "start_time": "2026-04-17 10:00:00",
  "end_time": "2026-04-17 18:00:00",
  "total_runtime_seconds": 28800,
  "total_frames": 720000,
  "reconnect_count": 2,
  "total_persons": 5,
  "persons": [
    {
      "track_id": 1,
      "first_appearance": "2026-04-17 10:05:23",
      "last_appearance": "2026-04-17 17:45:12",
      "total_frames": 12500,
      "work_time_seconds": 27549,
      "work_time_formatted": "7:39:09",
      "appearance_count": 3
    }
  ]
}
```

## 工作原理

1. **视频流连接**：使用OpenCV的VideoCapture连接RTSP流
2. **人员检测**：每3帧运行一次YOLO检测，识别画面中的人员
3. **人员跟踪**：基于位置相似度为每个人员分配唯一跟踪ID
4. **时间统计**：记录每个人员的首次出现、最后出现时间，计算总工作时长
5. **时段管理**：如果人员离开超过5秒后再次出现，计为新的工作时段

## 注意事项

- 确保摄像头网络可达，RTSP地址正确
- 首次运行需要下载YOLO模型，请保持网络连接
- 视频流不稳定时会自动重连，重连次数会记录在报告中
- 人员ID在每次程序启动时重新分配，不跨会话保持
