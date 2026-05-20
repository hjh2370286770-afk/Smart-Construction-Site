# Multi-Site Safety Monitor - 架构设计方案

## 项目愿景
构建可扩展的多工地安全监控平台，支持：
- 多路视频流并发处理
- 可配置的多模型检测
- 实时 Web 交互界面
- 向量记忆与智能分析

---

## 新架构设计

```
stream_manager_v2/
├── 📁 config/                    # 配置文件
│   ├── sites.yaml               # 工地配置
│   ├── models.yaml              # 检测模型配置
│   ├── cameras.yaml             # 摄像头配置
│   └── rules.yaml               # 检测规则配置
│
├── 📁 core/                      # 核心模块
│   ├── __init__.py
│   ├── stream_processor.py      # 视频流处理器
│   ├── detector_engine.py       # 检测引擎（多模型支持）
│   ├── tracker.py               # 人员跟踪器
│   └── event_manager.py         # 事件管理器
│
├── 📁 memory/                    # 向量记忆系统
│   ├── __init__.py
│   ├── vector_store.py          # 向量数据库接口
│   ├── person_memory.py         # 人员记忆管理
│   ├── violation_memory.py      # 违规事件记忆
│   └── pattern_analyzer.py      # 模式分析器
│
├── 📁 web/                       # Web 前端与API
│   ├── backend/                 # FastAPI 后端
│   │   ├── api/
│   │   ├── models/
│   │   └── services/
│   └── frontend/                # Vue/React 前端
│       ├── src/
│       └── public/
│
├── 📁 detectors/                 # 检测器模块
│   ├── base_detector.py         # 基础检测器类
│   ├── ppe_detector.py          # PPE检测
│   ├── vehicle_detector.py      # 车辆检测
│   ├── fire_detector.py         # 火灾检测
│   └── custom_detector.py       # 自定义检测器
│
├── 📁 storage/                   # 数据存储
│   ├── local_storage.py         # 本地文件存储
│   ├── cloud_storage.py         # 云端存储接口
│   └── database.py              # 数据库接口
│
├── 📁 utils/                     # 工具函数
│   ├── logger.py
│   ├── config_loader.py
│   └── image_utils.py
│
├── 📁 tests/                     # 测试
│   ├── unit/
│   └── integration/
│
├── main.py                       # 主入口
├── web_server.py                 # Web服务启动
└── requirements.txt
```

---

## 关键技术决策

### 1. 配置化设计
所有工地、摄像头、模型通过 YAML 配置，无需修改代码：

```yaml
# sites.yaml
sites:
  - id: site_001
    name: "工地A-实名制通道"
    location: "深圳市南山区"
    cameras:
      - id: cam_001
        name: "入口摄像头"
        url: "rtmp://..."
        models: ["ppe", "person_count"]
        rules:
          - type: "no_helmet"
            severity: "high"
            alert: true
          - type: "no_vest"
            severity: "medium"
            alert: true
```

### 2. 插件化检测器
每个检测器独立实现，支持热插拔：

```python
class BaseDetector(ABC):
    @abstractmethod
    def detect(self, frame) -> List[Detection]:
        pass
    
    @abstractmethod
    def get_supported_classes(self) -> List[str]:
        pass
```

### 3. 向量记忆系统
- 使用 ChromaDB 本地存储
- 支持人员特征向量匹配
- 违规事件语义检索

### 4. Web 技术栈
- **后端**: FastAPI (Python) + WebSocket 实时推送
- **前端**: Vue 3 + Element Plus
- **可视化**: ECharts 统计图表
- **视频**: HLS/DASH 流媒体播放

---

## 实施计划

### 阶段1: 核心架构重构 (1-2周)
1. 创建新目录结构
2. 实现配置加载系统
3. 重构检测引擎（支持多模型）
4. 实现基础向量记忆

### 阶段2: Web 界面开发 (2-3周)
1. FastAPI 后端 API
2. 前端监控面板
3. 实时视频流展示
4. 统计数据可视化

### 阶段3: 多工地扩展 (1-2周)
1. 多站点配置管理
2. 云端数据同步
3. 分布式部署支持

---

## 需要确认的问题

1. **向量存储**: 是否接受 ChromaDB 本地方案，还是需要云端方案？
2. **Web 前端**: 偏好 Vue 还是 React？
3. **部署方式**: 单机部署还是多机分布式？
4. **云端同步**: 是否需要云端备份和远程查看？
