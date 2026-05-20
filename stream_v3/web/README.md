# FastAPI Web 后端

FastAPI-based Web API for stream_manager_v2.

## 目录结构

```
web/
├── __init__.py          # 包初始化
├── main.py              # FastAPI 主应用
├── routers/
│   ├── __init__.py
│   ├── sites.py         # 工地相关路由
│   ├── cameras.py       # 摄像头相关路由
│   ├── violations.py    # 违规记录路由
│   └── stats.py         # 统计信息路由
├── websocket/
│   ├── __init__.py
│   └── events.py        # WebSocket 事件处理
├── models/
│   ├── __init__.py
│   └── schemas.py       # Pydantic 数据模型
└── dependencies.py      # 依赖注入
```

## API 端点

### 工地管理
- `GET /api/sites` - 获取所有工地

### 摄像头管理
- `GET /api/cameras` - 获取所有摄像头
- `GET /api/cameras/{id}/status` - 获取摄像头状态
- `POST /api/cameras/{id}/start` - 启动摄像头
- `POST /api/cameras/{id}/stop` - 停止摄像头
- `GET /api/cameras/{id}/snapshot` - 获取当前帧截图

### 违规记录
- `GET /api/violations` - 查询违规记录

### 统计信息
- `GET /api/stats/realtime` - 实时统计

### WebSocket
- `/ws/events` - 实时事件推送（违规事件、状态更新）

## 启动方式

### 方式1：独立启动 Web 服务
```bash
python -m web.main
```

### 方式2：通过主程序启动（集成模式）
```bash
python main.py --web
```

## WebSocket 消息格式

### 违规事件
```json
{
  "type": "violation",
  "data": {
    "timestamp": "20240330_143052",
    "camera_id": "cam_001",
    "person_id": 1,
    "violation_types": ["no_helmet"],
    "filepath": "/path/to/snapshot.jpg"
  }
}
```

### 状态更新
```json
{
  "type": "status",
  "data": {
    "camera_id": "cam_001",
    "status": "running",
    "stats": {
      "frame_count": 1234,
      "fps": 25.0,
      "detection_count": 56,
      "violation_count": 2,
      "reconnect_count": 0
    }
  }
}
```
