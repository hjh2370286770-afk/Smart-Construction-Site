# Claw Vector Memory - Claw 向量记忆系统

## 概述

为 Claw 提供长期语义记忆能力，支持：
- 对话内容的语义存储与检索
- 项目演进的上下文关联
- 用户偏好和习惯学习
- 跨会话的记忆延续

## 存储位置

```
C:\Users\Admini503\.openclaw\workspace\memory\
├── vector_db\              # 向量数据库
│   ├── conversations\       # 对话记忆
│   ├── projects\            # 项目记忆
│   ├── preferences\         # 用户偏好
│   └── knowledge\           # 知识记忆
├── memory_index.json        # 记忆索引
└── MEMORY.md               # 文本记忆（现有）
```

## 记忆类型

### 1. 对话记忆 (Conversation Memory)
```json
{
  "id": "conv_20260327_001",
  "timestamp": "2026-03-27T17:14:00",
  "type": "conversation",
  "content": "用户确认实现向量记忆系统",
  "embedding": [0.1, 0.2, ...],
  "metadata": {
    "topic": "向量记忆系统",
    "project": "stream_manager_v2",
    "importance": "high",
    "tags": ["架构设计", "记忆系统", "确认"]
  }
}
```

### 2. 项目记忆 (Project Memory)
```json
{
  "id": "proj_stream_manager_v2",
  "type": "project",
  "name": "stream_manager_v2",
  "description": "多工地安全监控平台",
  "embedding": [...],
  "metadata": {
    "status": "开发中",
    "tech_stack": ["Python", "OpenCV", "YOLOv8", "FastAPI", "Vue"],
    "milestones": [
      {"date": "2026-03-24", "event": "初次对话，理解项目"},
      {"date": "2026-03-27", "event": "20分钟测试完成"},
      {"date": "2026-03-27", "event": "架构重构开始"}
    ]
  }
}
```

### 3. 偏好记忆 (Preference Memory)
```json
{
  "id": "pref_user_001",
  "type": "preference",
  "category": "communication",
  "content": "用户使用中文交流",
  "embedding": [...],
  "metadata": {
    "confirmed": true,
    "source": "初次对话"
  }
}
```

### 4. 知识记忆 (Knowledge Memory)
```json
{
  "id": "knowledge_yolo_001",
  "type": "knowledge",
  "topic": "YOLOv8 PPE检测",
  "content": "YOLOv8模型用于检测安全帽、反光衣、口罩",
  "embedding": [...],
  "metadata": {
    "source": "stream_manager项目",
    "reliability": "high"
  }
}
```

## 使用场景

1. **对话上下文恢复**
   - 用户问："我们昨天讨论的那个方案"
   - 向量搜索找到相关对话

2. **项目演进追踪**
   - 自动关联当前工作与历史决策
   - 提醒之前的技术选择原因

3. **个性化响应**
   - 记住用户的技术偏好
   - 调整回答风格

4. **知识积累**
   - 从对话中提取技术知识
   - 形成可检索的知识库

## API 设计

```python
class ClawMemory:
    def remember_conversation(self, user_msg, claw_response, context)
    def remember_project_update(self, project_id, update_content)
    def remember_preference(self, category, preference)
    def recall(self, query, memory_type=None, top_k=5)
    def get_project_context(self, project_id)
    def get_conversation_history(self, topic=None, time_range=None)
```
