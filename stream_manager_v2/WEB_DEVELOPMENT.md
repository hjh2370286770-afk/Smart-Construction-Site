# Stream Manager V2 - Web 界面开发文档

## 项目结构

```
stream_manager_v2/
├── web/                          # FastAPI 后端
│   ├── main.py                   # FastAPI 主应用
│   ├── routers/                  # API 路由
│   │   ├── sites.py             # 工地管理 API
│   │   ├── cameras.py           # 摄像头管理 API
│   │   ├── violations.py        # 违规记录 API
│   │   └── stats.py             # 统计信息 API
│   ├── websocket/               # WebSocket 模块
│   │   └── events.py            # 实时事件推送
│   ├── models/                  # 数据模型
│   │   └── schemas.py           # Pydantic 模型
│   ├── dependencies.py          # 依赖注入
│   └── requirements.txt         # Python 依赖
│
└── web_frontend/                # Vue 3 前端
    ├── src/
    │   ├── components/          # 组件
    │   │   ├── LivePlayer.vue   # 视频播放器 + 检测框
    │   │   ├── CameraCard.vue   # 摄像头卡片
    │   │   └── StatCard.vue     # 统计卡片
    │   ├── views/               # 页面
    │   │   ├── DashboardView.vue    # 监控大屏
    │   │   ├── CameraDetailView.vue # 摄像头详情
    │   │   └── ViolationsView.vue   # 违规记录
    │   ├── stores/              # Pinia 状态管理
    │   │   ├── monitor.ts       # 监控状态
    │   │   └── websocket.ts     # WebSocket 连接
    │   ├── api/                 # API 客户端
    │   │   └── index.ts
    │   ├── App.vue              # 根组件
    │   └── main.ts              # 入口
    ├── package.json
    └── vite.config.ts
```

## 快速开始

### 1. 安装后端依赖

```bash
cd stream_manager_v2
pip install -r web/requirements.txt
```

### 2. 安装前端依赖

```bash
cd web_frontend
npm install
```

### 3. 启动开发服务器

**后端（方式1：集成模式）**
```bash
cd stream_manager_v2
python main.py --web
```

**后端（方式2：独立模式）**
```bash
cd stream_manager_v2/web
python main.py
```

**前端**
```bash
cd web_frontend
npm run dev
```

## API 文档

启动服务后访问：`http://localhost:8000/docs`

### 主要端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/sites` | 获取所有工地 |
| GET | `/api/cameras` | 获取所有摄像头 |
| GET | `/api/cameras/{id}/status` | 摄像头状态 |
| POST | `/api/cameras/{id}/start` | 启动摄像头 |
| POST | `/api/cameras/{id}/stop` | 停止摄像头 |
| GET | `/api/cameras/{id}/snapshot` | 获取截图 |
| GET | `/api/violations` | 查询违规记录 |
| GET | `/api/stats/realtime` | 实时统计 |
| WS | `/ws/events` | WebSocket 事件流 |

### WebSocket 消息格式

**违规事件**
```json
{
  "type": "violation",
  "data": {
    "timestamp": "20240330_143052",
    "camera_id": "cam_001",
    "person_id": 1,
    "violation_types": ["no_helmet", "no_vest"],
    "filepath": "/path/to/snapshot.jpg"
  }
}
```

**状态更新**
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
      "violation_count": 2
    }
  }
}
```

## 前端架构

### 技术栈
- **Vue 3** + TypeScript
- **Element Plus** - UI 组件库
- **Pinia** - 状态管理
- **flv.js** - RTMP 视频播放
- **Axios** - HTTP 客户端

### 核心组件

#### LivePlayer.vue
视频播放器组件，支持：
- flv.js 播放 RTMP 流
- Canvas 叠加检测框
- 实时 PPE 状态显示

```vue
<LivePlayer
  :stream-url="camera.url"
  :detections="detections"
  :canvas-width="960"
  :canvas-height="540"
/>
```

### 状态管理

#### monitor.ts
```typescript
// 监控状态
const cameras = ref<Camera[]>([])
const onlineCameras = computed(() => cameras.value.filter(c => c.status === 'running'))
const totalPersons = computed(() => /* 从检测数据计算 */)
const todayViolations = ref(0)
```

#### websocket.ts
```typescript
// WebSocket 连接管理
const ws = ref<WebSocket | null>(null)
const status = ref<'connected' | 'connecting' | 'disconnected'>('disconnected')

function connect() { /* 连接逻辑 */ }
function onMessage(handler: (data: any) => void) { /* 消息监听 */ }
```

## 视频流方案

### 方案 A：flv.js + RTMP（当前采用）

**优点：**
- 延迟低（1-3秒）
- 实现简单

**缺点：**
- 需要 Flash 插件或 MSE 支持
- 移动端兼容性一般

**使用方式：**
```javascript
import flvjs from 'flv.js'

const player = flvjs.createPlayer({
  type: 'flv',
  url: 'ws://localhost:8001/rtmp_proxy/cam_001',  // 通过 WebSocket 代理
  isLive: true
})
player.attachMediaElement(videoElement)
player.load()
player.play()
```

### 备选方案

**方案 B：HLS 转码**
- 使用 FFmpeg 将 RTMP 转 HLS
- 兼容性好，延迟 5-10 秒

**方案 C：WebRTC**
- 超低延迟（< 500ms）
- 实现复杂，需要 SFU 服务器

## 开发计划

### Phase 1: 基础功能 ✅
- [x] FastAPI 后端框架
- [x] REST API 端点
- [x] WebSocket 实时推送
- [x] Vue 3 前端框架
- [x] 监控大屏页面

### Phase 2: 视频播放 ⏳
- [ ] flv.js 集成
- [ ] 检测框 Canvas 叠加
- [ ] 摄像头详情页

### Phase 3: 高级功能
- [ ] 违规记录查询
- [ ] 历史数据统计
- [ ] 用户认证
- [ ] 告警通知

## 常见问题

### Q: 前端无法连接到后端？
A: 检查 CORS 配置和端口设置：
```python
# web/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # 前端开发服务器地址
    ...
)
```

### Q: WebSocket 连接断开？
A: 检查 nginx/防火墙配置，确保 WebSocket 端口开放。

### Q: 视频无法播放？
A: 
1. 确认摄像头 URL 可访问
2. 检查 flv.js 是否支持该流格式
3. 查看浏览器控制台错误信息

## 相关链接

- FastAPI 文档: https://fastapi.tiangolo.com/
- Vue 3 文档: https://vuejs.org/
- Element Plus: https://element-plus.org/
- flv.js: https://github.com/bilibili/flv.js
