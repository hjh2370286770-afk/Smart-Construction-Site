# 多路视频流管理器

基于 asyncio 的高并发 RTMP/RTSP 视频流管理器，支持多场景配置、帧队列管理和状态监控。

## 功能特性

- ✅ **异步并发**：基于 asyncio 的高性能多路拉流
- ✅ **自动重连**：断线自动重连，可配置重连策略
- ✅ **场景路由**：不同摄像头可配置不同检测场景/模型
- ✅ **帧队列管理**：带缓冲的帧队列，防止丢帧
- ✅ **跳帧控制**：支持跳帧降低处理负载
- ✅ **状态监控**：实时流状态监控和回调
- ✅ **低延迟优化**：最小化缓冲，实时性优先

## 快速开始

### 1. 安装依赖

```bash
pip install opencv-python numpy
```

### 2. 运行示例

```bash
cd stream_manager
python stream_manager.py
```

### 3. 基础用法

```python
import asyncio
from stream_manager import StreamManager, StreamConfig

async def main():
    # 创建管理器
    manager = StreamManager()
    
    # 配置视频流
    config = StreamConfig(
        stream_id="cam_001",
        url="rtmp://49.235.101.158/live/JHMH2411005018",
        scene_type="safety_helmet",  # 场景类型
        fps=15,
        buffer_size=10
    )
    
    # 添加并启动
    manager.add_stream(config)
    await manager.start_all()
    
    # 运行一段时间...
    await asyncio.sleep(60)
    
    # 停止
    await manager.stop_all()

asyncio.run(main())
```

## 配置说明

### StreamConfig 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `stream_id` | str | 必填 | 流唯一标识 |
| `url` | str | 必填 | RTMP/RTSP 流地址 |
| `scene_type` | str | "default" | 场景类型（决定使用哪个模型） |
| `fps` | int | 25 | 目标帧率 |
| `buffer_size` | int | 30 | 帧缓冲区大小 |
| `reconnect_interval` | float | 5.0 | 重连间隔（秒） |
| `max_reconnect_attempts` | int | 10 | 最大重连次数 |
| `frame_skip` | int | 0 | 跳帧数（0=不跳帧，1=隔1帧） |

## 回调函数

### 帧回调

```python
def on_frame(frame_data: FrameData):
    # frame_data 包含：
    # - stream_id: 流ID
    # - frame: numpy 数组 (BGR格式)
    # - timestamp: 时间戳
    # - frame_number: 帧序号
    # - scene_type: 场景类型
    # - metadata: 额外元数据
    
    # 进行模型推理...
    results = model(frame.frame)
    
    # 提取关键帧...
    if should_capture_keyframe(results):
        save_keyframe(frame)

manager.on_frame(on_frame)
```

### 状态回调

```python
def on_status(stream_id: str, status: StreamStatus):
    print(f"Stream {stream_id} is now {status.value}")

manager.on_status_change(on_status)
```

## 场景配置示例

```python
# 安全帽检测场景
safety_config = StreamConfig(
    stream_id="cam_safety",
    url="rtmp://xxx/live/xxx",
    scene_type="safety_helmet",
    fps=10,           # 安全帽检测不需要高帧率
    frame_skip=2      # 每秒处理3-4帧足够
)

# 人员计数场景
count_config = StreamConfig(
    stream_id="cam_count",
    url="rtmp://xxx/live/xxx",
    scene_type="person_count",
    fps=5,            # 计数可以更低帧率
    frame_skip=4
)

# 危险区域入侵检测
danger_config = StreamConfig(
    stream_id="cam_danger",
    url="rtmp://xxx/live/xxx",
    scene_type="danger_zone",
    fps=15,           # 入侵检测需要较高帧率
    frame_skip=1
)
```

## API 参考

### StreamManager

| 方法 | 说明 |
|------|------|
| `add_stream(config)` | 添加视频流 |
| `remove_stream(stream_id)` | 移除视频流 |
| `start_all()` | 启动所有流 |
| `stop_all()` | 停止所有流 |
| `start_stream(stream_id)` | 启动指定流 |
| `stop_stream(stream_id)` | 停止指定流 |
| `get_stream(stream_id)` | 获取流对象 |
| `get_status()` | 获取所有流状态 |
| `on_frame(callback)` | 注册全局帧回调 |
| `on_status_change(callback)` | 注册全局状态回调 |

### VideoStream

| 方法 | 说明 |
|------|------|
| `start()` | 启动流 |
| `stop()` | 停止流 |
| `on_frame(callback)` | 注册帧回调 |
| `on_status_change(callback)` | 注册状态回调 |
| `get_latest_frame()` | 获取最新帧 |
| `get_frame_batch(count)` | 获取批量帧 |

## 下一步

1. **集成 YOLOv8 模型**：在帧回调中进行目标检测
2. **关键帧提取**：根据检测结果保存关键帧
3. **云端上传**：将关键帧上传到云端存储
4. **场景路由引擎**：根据 scene_type 动态切换模型
