"""
Claw Vector Memory System
Claw 的向量记忆系统 - 提供长期语义记忆能力
"""

import os
import json
import hashlib
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# 尝试导入向量库
try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logger.warning("ChromaDB 未安装，使用模拟模式")

try:
    from sentence_transformers import SentenceTransformer
    EMBEDDING_MODEL = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    EMBEDDING_AVAILABLE = True
except ImportError:
    EMBEDDING_AVAILABLE = False
    logger.warning("sentence-transformers 未安装，使用简单哈希嵌入")


@dataclass
class MemoryEntry:
    """记忆条目"""
    id: str
    timestamp: str
    type: str  # conversation, project, preference, knowledge
    content: str
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class ClawMemory:
    """
    Claw 的向量记忆系统
    
    提供以下能力：
    1. 对话记忆的语义存储
    2. 项目演进的上下文追踪
    3. 用户偏好的学习
    4. 跨会话的记忆检索
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        初始化记忆系统
        
        Args:
            db_path: 数据库路径，默认在 workspace/memory/vector_db
        """
        if db_path is None:
            db_path = os.path.join(
                os.path.expanduser("~"),
                ".openclaw", "workspace", "memory", "vector_db"
            )
        
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        # 初始化 ChromaDB
        self.chroma_client = None
        self.collections = {}
        self._mock_mode = not CHROMADB_AVAILABLE
        
        # 模拟模式存储
        self._mock_memories: Dict[str, List[MemoryEntry]] = {
            'conversations': [],
            'projects': [],
            'preferences': [],
            'knowledge': []
        }
        
        self._init_db()
        
    def _init_db(self):
        """初始化数据库"""
        if self._mock_mode:
            logger.info("使用模拟模式（内存存储）")
            return
            
        try:
            self.chroma_client = chromadb.Client(Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=str(self.db_path)
            ))
            
            # 创建集合
            for collection_name in ['conversations', 'projects', 'preferences', 'knowledge']:
                self.collections[collection_name] = self.chroma_client.get_or_create_collection(
                    name=collection_name,
                    metadata={"hnsw:space": "cosine"}
                )
                
            logger.info("向量记忆数据库初始化完成")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            self._mock_mode = True
            
    def _get_embedding(self, text: str) -> List[float]:
        """
        获取文本的向量嵌入
        
        Args:
            text: 输入文本
            
        Returns:
            向量嵌入
        """
        if EMBEDDING_AVAILABLE:
            try:
                embedding = EMBEDDING_MODEL.encode(text)
                return embedding.tolist()
            except Exception as e:
                logger.warning(f"嵌入生成失败: {e}")
                
        # 备用：简单哈希嵌入
        return self._simple_hash_embedding(text)
        
    def _simple_hash_embedding(self, text: str, dim: int = 384) -> List[float]:
        """简单哈希嵌入（备用方案）"""
        # 使用多个哈希函数生成固定维度的向量
        embedding = []
        for i in range(dim):
            hash_val = hashlib.md5(f"{text}_{i}".encode()).hexdigest()
            # 转换为 -1 到 1 之间的浮点数
            val = int(hash_val[:8], 16) / 0xFFFFFFFF * 2 - 1
            embedding.append(val)
        return embedding
        
    def _generate_id(self, content: str) -> str:
        """生成唯一ID"""
        timestamp = datetime.now().isoformat()
        return hashlib.md5(f"{content}_{timestamp}".encode()).hexdigest()[:16]
        
    def remember_conversation(self, user_message: str, claw_response: str,
                              context: Optional[Dict] = None) -> str:
        """
        记住对话内容
        
        Args:
            user_message: 用户消息
            claw_response: Claw回复
            context: 上下文信息（项目、主题等）
            
        Returns:
            记忆ID
        """
        content = f"用户: {user_message}\nClaw: {claw_response}"
        embedding = self._get_embedding(content)
        memory_id = self._generate_id(content)
        
        entry = MemoryEntry(
            id=memory_id,
            timestamp=datetime.now().isoformat(),
            type='conversation',
            content=content,
            embedding=embedding,
            metadata={
                'user_message': user_message,
                'claw_response': claw_response,
                'context': context or {}
            }
        )
        
        self._store_entry('conversations', entry)
        logger.debug(f"记住对话: {memory_id}")
        return memory_id
        
    def remember_project_update(self, project_id: str, update_content: str,
                                 metadata: Optional[Dict] = None) -> str:
        """
        记住项目更新
        
        Args:
            project_id: 项目ID
            update_content: 更新内容
            metadata: 额外元数据
            
        Returns:
            记忆ID
        """
        content = f"项目 {project_id}: {update_content}"
        embedding = self._get_embedding(content)
        memory_id = self._generate_id(content)
        
        entry = MemoryEntry(
            id=memory_id,
            timestamp=datetime.now().isoformat(),
            type='project',
            content=content,
            embedding=embedding,
            metadata={
                'project_id': project_id,
                'update': update_content,
                **(metadata or {})
            }
        )
        
        self._store_entry('projects', entry)
        logger.info(f"记住项目更新 [{project_id}]: {update_content[:50]}...")
        return memory_id
        
    def remember_preference(self, category: str, preference: str,
                           confirmed: bool = True) -> str:
        """
        记住用户偏好
        
        Args:
            category: 偏好类别（communication, tech_stack, etc.）
            preference: 偏好内容
            confirmed: 是否已确认
            
        Returns:
            记忆ID
        """
        content = f"用户偏好 [{category}]: {preference}"
        embedding = self._get_embedding(content)
        memory_id = self._generate_id(content)
        
        entry = MemoryEntry(
            id=memory_id,
            timestamp=datetime.now().isoformat(),
            type='preference',
            content=content,
            embedding=embedding,
            metadata={
                'category': category,
                'preference': preference,
                'confirmed': confirmed
            }
        )
        
        self._store_entry('preferences', entry)
        logger.info(f"记住偏好: [{category}] {preference}")
        return memory_id
        
    def remember_knowledge(self, topic: str, knowledge: str,
                          source: Optional[str] = None) -> str:
        """
        记住知识
        
        Args:
            topic: 知识主题
            knowledge: 知识内容
            source: 知识来源
            
        Returns:
            记忆ID
        """
        content = f"知识 [{topic}]: {knowledge}"
        embedding = self._get_embedding(content)
        memory_id = self._generate_id(content)
        
        entry = MemoryEntry(
            id=memory_id,
            timestamp=datetime.now().isoformat(),
            type='knowledge',
            content=content,
            embedding=embedding,
            metadata={
                'topic': topic,
                'knowledge': knowledge,
                'source': source
            }
        )
        
        self._store_entry('knowledge', entry)
        logger.debug(f"记住知识: [{topic}]")
        return memory_id
        
    def _store_entry(self, collection_name: str, entry: MemoryEntry):
        """存储记忆条目"""
        if self._mock_mode:
            self._mock_memories[collection_name].append(entry)
            return
            
        try:
            collection = self.collections.get(collection_name)
            if collection:
                collection.add(
                    ids=[entry.id],
                    embeddings=[entry.embedding],
                    documents=[entry.content],
                    metadatas=[asdict(entry)]
                )
        except Exception as e:
            logger.error(f"存储记忆失败: {e}")
            
    def recall(self, query: str, memory_type: Optional[str] = None,
               top_k: int = 5) -> List[MemoryEntry]:
        """
        回忆相关记忆
        
        Args:
            query: 查询内容
            memory_type: 记忆类型（可选）
            top_k: 返回结果数量
            
        Returns:
            相关记忆列表
        """
        query_embedding = self._get_embedding(query)
        
        results = []
        
        # 确定要搜索的集合
        if memory_type:
            collections_to_search = [memory_type]
        else:
            collections_to_search = ['conversations', 'projects', 'preferences', 'knowledge']
            
        for collection_name in collections_to_search:
            entries = self._search_collection(collection_name, query_embedding, top_k)
            results.extend(entries)
            
        # 按相似度排序并返回前 top_k
        results = sorted(results, key=lambda x: x.metadata.get('distance', 0))[:top_k]
        return results
        
    def _search_collection(self, collection_name: str, 
                          query_embedding: List[float],
                          top_k: int) -> List[MemoryEntry]:
        """搜索单个集合"""
        if self._mock_mode:
            # 模拟模式：简单比较
            entries = self._mock_memories.get(collection_name, [])
            # 计算简单相似度（点积）
            scored = []
            for entry in entries:
                if entry.embedding:
                    similarity = np.dot(query_embedding, entry.embedding)
                    entry.metadata['distance'] = 1 - similarity
                    scored.append(entry)
            return sorted(scored, key=lambda x: x.metadata['distance'])[:top_k]
            
        try:
            collection = self.collections.get(collection_name)
            if not collection:
                return []
                
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["metadatas", "distances"]
            )
            
            entries = []
            if results['metadatas'] and results['metadatas'][0]:
                for i, metadata in enumerate(results['metadatas'][0]):
                    entry = MemoryEntry(**metadata)
                    entry.metadata['distance'] = results['distances'][0][i]
                    entries.append(entry)
                    
            return entries
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return []
            
    def get_project_context(self, project_id: str) -> Dict[str, Any]:
        """获取项目上下文"""
        # 搜索项目相关的所有记忆
        project_memories = self.recall(f"项目 {project_id}", memory_type='projects', top_k=10)
        conversation_memories = self.recall(f"{project_id}", memory_type='conversations', top_k=10)
        
        return {
            'project_id': project_id,
            'project_updates': [m.content for m in project_memories],
            'related_conversations': [m.content for m in conversation_memories],
            'last_updated': project_memories[0].timestamp if project_memories else None
        }
        
    def get_preferences(self, category: Optional[str] = None) -> List[Dict]:
        """获取用户偏好"""
        if category:
            memories = self.recall(f"偏好 {category}", memory_type='preferences', top_k=10)
        else:
            memories = self._mock_memories.get('preferences', [])
            
        return [
            {
                'category': m.metadata.get('category'),
                'preference': m.metadata.get('preference'),
                'confirmed': m.metadata.get('confirmed'),
                'timestamp': m.timestamp
            }
            for m in memories
        ]
        
    def persist(self):
        """持久化记忆（模拟模式下）"""
        if self._mock_mode:
            data = {
                collection: [
                    {
                        'id': e.id,
                        'timestamp': e.timestamp,
                        'type': e.type,
                        'content': e.content,
                        'embedding': e.embedding,
                        'metadata': e.metadata
                    }
                    for e in entries
                ]
                for collection, entries in self._mock_memories.items()
            }
            
            with open(self.db_path / "claw_memory.json", 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            logger.info("Claw 记忆已保存")


# 全局记忆实例
_claw_memory: Optional[ClawMemory] = None


def get_claw_memory() -> ClawMemory:
    """获取 Claw 记忆实例"""
    global _claw_memory
    if _claw_memory is None:
        _claw_memory = ClawMemory()
    return _claw_memory


# 便捷函数
def remember_conversation(user_msg: str, claw_response: str, context: Optional[Dict] = None):
    """记住对话"""
    return get_claw_memory().remember_conversation(user_msg, claw_response, context)


def remember_project_update(project_id: str, update: str, metadata: Optional[Dict] = None):
    """记住项目更新"""
    return get_claw_memory().remember_project_update(project_id, update, metadata)


def remember_preference(category: str, preference: str, confirmed: bool = True):
    """记住偏好"""
    return get_claw_memory().remember_preference(category, preference, confirmed)


def recall(query: str, memory_type: Optional[str] = None, top_k: int = 5) -> List[MemoryEntry]:
    """回忆记忆"""
    return get_claw_memory().recall(query, memory_type, top_k)


if __name__ == "__main__":
    # 测试记忆系统
    logging.basicConfig(level=logging.INFO)
    
    memory = get_claw_memory()
    
    # 测试记住对话
    memory.remember_conversation(
        "我们需要向量记忆系统",
        "好的，我来为你实现 Claw 的向量记忆系统",
        {"project": "stream_manager_v2", "topic": "架构设计"}
    )
    
    # 测试记住项目更新
    memory.remember_project_update(
        "stream_manager_v2",
        "完成架构设计文档和配置系统",
        {"milestone": "阶段1完成"}
    )
    
    # 测试记住偏好
    memory.remember_preference("communication", "使用中文交流", confirmed=True)
    
    # 测试回忆
    results = memory.recall("向量记忆")
    print(f"\n找到 {len(results)} 条相关记忆:")
    for r in results:
        print(f"- [{r.type}] {r.content[:50]}...")
        
    # 保存
    memory.persist()
