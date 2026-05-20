# Vector Memory System - 向量记忆系统

## 概述

为工地安全监控系统提供长期记忆能力，支持：
- 人员特征向量存储（用于跨视频流人员识别）
- 违规事件语义检索
- 工地场景模式学习
- 历史数据统计分析

## 技术选型

### 方案A: 轻量级本地向量存储 (推荐初期使用)
- **ChromaDB**: 嵌入式向量数据库，零配置
- **Sentence-Transformers**: 文本向量化
- **CLIP/ResNet**: 图像特征提取

### 方案B: 云端向量服务 (后期扩展)
- **Pinecone**: 托管向量数据库
- **Milvus**: 开源分布式向量数据库

## 数据结构

### 1. 人员特征向量 (Person Embedding)
```json
{
  "id": "person_uuid",
  "embedding": [0.1, 0.2, ...],  // 512维特征向量
  "metadata": {
    "first_seen": "2026-03-27T10:50:00",
    "last_seen": "2026-03-27T11:11:00",
    "site_id": "site_001",
    "camera_id": "cam_001",
    "violation_history": ["NO_HELMET", "NO_VEST"],
    "compliance_rate": 0.3
  }
}
```

### 2. 违规事件向量 (Violation Event)
```json
{
  "id": "violation_uuid",
  "embedding": [0.1, 0.2, ...],  // 图像特征 + 文本描述
  "metadata": {
    "timestamp": "2026-03-27T10:51:04",
    "site_id": "site_001",
    "camera_id": "cam_001",
    "violation_type": "NO_HELMET_NO_VEST",
    "person_id": "person_uuid",
    "image_path": "violation_xxx.jpg"
  }
}
```

### 3. 工地场景向量 (Site Pattern)
```json
{
  "id": "site_pattern_uuid",
  "embedding": [0.1, 0.2, ...],
  "metadata": {
    "site_id": "site_001",
    "time_range": "morning",
    "avg_person_count": 15,
    "violation_rate": 0.75,
    "common_violations": ["NO_VEST", "NO_HELMET"]
  }
}
```

## API 设计

```python
class VectorMemory:
    def add_person(self, person_features, metadata) -> str
    def search_person(self, query_features, top_k=5) -> List[Person]
    def add_violation(self, image, description, metadata) -> str
    def search_violations(self, query, filters=None) -> List[Violation]
    def get_person_history(self, person_id) -> List[Violation]
    def analyze_site_patterns(self, site_id, time_range) -> SitePattern
```

## 使用场景

1. **跨摄像头人员追踪**: 同一人出现在不同摄像头时识别
2. **惯犯检测**: 识别多次违规的同一人员
3. **违规模式分析**: 发现特定时间/地点的高频违规类型
4. **相似违规检索**: 查找历史上相似的违规事件
