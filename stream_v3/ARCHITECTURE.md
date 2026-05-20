# Stream V3 - 架构设计文档

## 一、项目结构

```
stream_v3/
├── main.py                    # 后端启动入口（仅启动服务器）
├── config/                    # 配置文件
│   ├── sites.yaml            # 工地/摄像头配置（可动态加载）
│   └── models.yaml           # 模型配置
├── detectors/                # 检测器功能包
│   ├── __init__.py          # 检测器注册表
│   ├── base.py              # 基础检测器接口
│   ├── ppe.py               # PPE检测
│   ├── vehicle.py           # 车辆检测
│   ├── wall_v1.py           # 墙面缺陷V1
│   ├── wall_v2.py           # 墙面缺陷V2（含设备状态）
│   └── tool.py              # 刀具检测
├── core/                     # 核心处理模块
│   ├── stream_processor.py  # 单路视频流处理器
│   └── stream_manager.py    # 多路流管理器
├── web/                      # Web后端
│   ├── main.py              # FastAPI应用
│   ├── routers/             # API路由
│   └── websocket/           # WebSocket
├── web_frontend/            # 前端（重写）
└── storage/                 # 存储（违规记录、截图）
```

## 二、核心设计

### 1. Main.py 职责（简化）
```python
# 只负责启动服务器
- 加载配置
- 初始化检测器
- 启动Web服务
- 提供API接口
```

### 2. 检测器架构（插件式）
```python
# detectors/__init__.py
class DetectorRegistry:
    """检测器注册中心"""
    detectors = {}
    
    @classmethod
    def register(cls, name, detector_class):
        cls.detectors[name] = detector_class
    
    @classmethod
    def get(cls, name):
        return cls.detectors.get(name)
    
    @classmethod
    def list_all(cls):
        return cls.detectors.keys()
```

### 3. 视频流动态管理
```yaml
# 支持通过API动态添加
POST /api/streams
{
    "name": "工地A-摄像头1",
    "url": "rtmp://...",
    "detector": "ppe_detector",  # 绑定检测器
    "enabled": true
}
```

### 4. 前端功能
- 视频流列表（可增删改查）
- 实时视频预览
- 检测器选择配置
- 违规记录查看
- 统计仪表盘

## 三、API设计

### 视频流管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/streams | 获取所有视频流 |
| POST | /api/streams | 添加视频流 |
| PUT | /api/streams/{id} | 更新视频流 |
| DELETE | /api/streams/{id} | 删除视频流 |
| POST | /api/streams/{id}/start | 启动检测 |
| POST | /api/streams/{id}/stop | 停止检测 |

### 检测器管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/detectors | 获取所有检测器 |
| GET | /api/detectors/{id} | 获取检测器详情 |

### 违规记录
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/violations | 查询违规记录 |
| GET | /api/violations/stats | 统计信息 |

## 四、启动方式

```bash
# 启动后端
python main.py

# 启动前端开发
cd web_frontend && npm run dev
```

## 五、前端页面设计

### 1. 监控大屏
- 视频流网格展示
- 实时统计卡片
- 违规告警

### 2. 视频流管理
- 摄像头列表
- 添加/编辑摄像头（URL、名称、检测器）
- 启动/停止控制

### 3. 违规记录
- 分页列表
- 筛选查询
- 截图查看

---

*设计完成时间: 2026-04-03*
