"""
向量记忆系统 - Vector Memory System
提供人员特征存储、违规事件检索、模式分析能力
"""

import numpy as np
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import hashlib
import logging

logger = logging.getLogger(__name__)


try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logger.warning("ChromaDB 未安装，向量记忆功能将使用模拟模式")


@dataclass
class PersonEmbedding:
    """人员特征向量"""
    id: str
    embedding: List[float]
    first_seen: str
    last_seen: str
    site_id: str
    camera_id: str
    violation_history: List[str]
    compliance_rate: float
    appearance_count: int


@dataclass
class ViolationEvent:
    """违规事件"""
    id: str
    timestamp: str
    site_id: str
    camera_id: str
    person_id: Optional[str]
    violation_type: str
    severity: str
    image_path: Optional[str]
    description: str
    embedding: Optional[List[float]] = None


class VectorMemory:
    """
    向量记忆系统主类
    提供人员识别、违规检索、模式分析功能
    """
    
    def __init__(self, db_path: str = "./memory_db", similarity_threshold: float = 0.85):
        self.db_path = Path(db_path)
        self.similarity_threshold = similarity_threshold
        self.chroma_client = None
        self.person_collection = None
        self.violation_collection = None
        self.pattern_collection = None
        
        # 模拟模式（当 ChromaDB 不可用时）
        self._mock_persons: Dict[str, PersonEmbedding] = {}
        self._mock_violations: List[ViolationEvent] = []
        self._mock_mode = not CHROMADB_AVAILABLE
        
        self._init_db()
        
    def _init_db(self):
        """初始化向量数据库"""
        if self._mock_mode:
            logger.info("使用模拟模式（内存存储）")
            return
            
        try:
            self.chroma_client = chromadb.Client(Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=str(self.db_path)
            ))
            
            # 创建集合
            self.person_collection = self.chroma_client.get_or_create_collection(
                name="persons",
                metadata={"hnsw:space": "cosine"}
            )
            self.violation_collection = self.chroma_client.get_or_create_collection(
                name="violations",
                metadata={"hnsw:space": "cosine"}
            )
            self.pattern_collection = self.chroma_client.get_or_create_collection(
                name="patterns",
                metadata={"hnsw:space": "cosine"}
            )
            
            logger.info("向量数据库初始化完成")
        except Exception as e:
            logger.error(f"向量数据库初始化失败: {e}")
            self._mock_mode = True
            
    def add_person(self, embedding: List[float], site_id: str, camera_id: str,
                   metadata: Optional[Dict] = None) -> Tuple[str, bool]:
        """
        添加或更新人员
        
        Returns:
            (person_id, is_new): 人员ID，是否是新人员
        """
        # 搜索相似人员
        similar_person = self._find_similar_person(embedding)
        
        now = datetime.now().isoformat()
        
        if similar_person:
            # 更新现有人员
            person_id = similar_person.id
            person = PersonEmbedding(
                id=person_id,
                embedding=embedding,
                first_seen=similar_person.first_seen,
                last_seen=now,
                site_id=site_id,
                camera_id=camera_id,
                violation_history=similar_person.violation_history,
                compliance_rate=similar_person.compliance_rate,
                appearance_count=similar_person.appearance_count + 1
            )
            is_new = False
        else:
            # 创建新人员
            person_id = self._generate_id(embedding)
            person = PersonEmbedding(
                id=person_id,
                embedding=embedding,
                first_seen=now,
                last_seen=now,
                site_id=site_id,
                camera_id=camera_id,
                violation_history=[],
                compliance_rate=1.0,
                appearance_count=1
            )
            is_new = True
        
        # 保存到数据库
        self._save_person(person)
        
        return person_id, is_new
        
    def _find_similar_person(self, embedding: List[float]) -> Optional[PersonEmbedding]:
        """查找相似人员"""
        if self._mock_mode:
            # 模拟模式：简单欧氏距离比较
            for person in self._mock_persons.values():
                dist = np.linalg.norm(np.array(embedding) - np.array(person.embedding))
                if dist < (1 - self.similarity_threshold):
                    return person
            return None
        
        # ChromaDB 查询
        try:
            results = self.person_collection.query(
                query_embeddings=[embedding],
                n_results=1,
                include=["metadatas", "distances"]
            )
            
            if results['distances'][0]:
                distance = results['distances'][0][0]
                similarity = 1 - distance
                if similarity >= self.similarity_threshold:
                    metadata = results['metadatas'][0][0]
                    return PersonEmbedding(**metadata)
        except Exception as e:
            logger.error(f"查询相似人员失败: {e}")
            
        return None
        
    def _save_person(self, person: PersonEmbedding):
        """保存人员到数据库"""
        if self._mock_mode:
            self._mock_persons[person.id] = person
            return
            
        try:
            self.person_collection.upsert(
                ids=[person.id],
                embeddings=[person.embedding],
                metadatas=[asdict(person)]
            )
        except Exception as e:
            logger.error(f"保存人员失败: {e}")
            
    def add_violation(self, person_id: Optional[str], violation_type: str,
                      severity: str, site_id: str, camera_id: str,
                      image_path: Optional[str] = None,
                      description: str = "") -> str:
        """添加违规事件"""
        violation_id = self._generate_id(f"{person_id}{violation_type}{datetime.now()}")
        
        event = ViolationEvent(
            id=violation_id,
            timestamp=datetime.now().isoformat(),
            site_id=site_id,
            camera_id=camera_id,
            person_id=person_id,
            violation_type=violation_type,
            severity=severity,
            image_path=image_path,
            description=description
        )
        
        # 更新人员违规历史
        if person_id and person_id in self._mock_persons:
            person = self._mock_persons[person_id]
            person.violation_history.append(violation_type)
            # 重新计算合规率
            total = person.appearance_count
            violations = len(person.violation_history)
            person.compliance_rate = (total - violations) / total if total > 0 else 1.0
        
        # 保存违规事件
        self._save_violation(event)
        
        return violation_id
        
    def _save_violation(self, event: ViolationEvent):
        """保存违规事件"""
        if self._mock_mode:
            self._mock_violations.append(event)
            return
            
        try:
            self.violation_collection.add(
                ids=[event.id],
                documents=[event.description],
                metadatas=[asdict(event)]
            )
        except Exception as e:
            logger.error(f"保存违规事件失败: {e}")
            
    def search_violations(self, query: str = "", filters: Optional[Dict] = None,
                          top_k: int = 10) -> List[ViolationEvent]:
        """搜索违规事件"""
        if self._mock_mode:
            # 模拟模式：简单过滤
            results = self._mock_violations
            if filters:
                if 'site_id' in filters:
                    results = [v for v in results if v.site_id == filters['site_id']]
                if 'violation_type' in filters:
                    results = [v for v in results if v.violation_type == filters['violation_type']]
            return results[-top_k:]
        
        try:
            where_clause = {}
            if filters:
                for key, value in filters.items():
                    where_clause[key] = value
                    
            results = self.violation_collection.query(
                query_texts=[query] if query else None,
                n_results=top_k,
                where=where_clause if where_clause else None,
                include=["metadatas"]
            )
            
            events = []
            for metadata in results['metadatas'][0]:
                events.append(ViolationEvent(**metadata))
            return events
        except Exception as e:
            logger.error(f"搜索违规事件失败: {e}")
            return []
            
    def get_person_history(self, person_id: str) -> List[ViolationEvent]:
        """获取人员违规历史"""
        if self._mock_mode:
            return [v for v in self._mock_violations if v.person_id == person_id]
            
        try:
            results = self.violation_collection.get(
                where={"person_id": person_id}
            )
            events = []
            for metadata in results['metadatas']:
                events.append(ViolationEvent(**metadata))
            return sorted(events, key=lambda x: x.timestamp)
        except Exception as e:
            logger.error(f"获取人员历史失败: {e}")
            return []
            
    def get_site_statistics(self, site_id: str, time_range: Optional[Tuple[str, str]] = None) -> Dict:
        """获取工地统计信息"""
        violations = self.search_violations(filters={"site_id": site_id}, top_k=1000)
        
        # 统计违规类型
        violation_types = {}
        severity_count = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        
        for v in violations:
            violation_types[v.violation_type] = violation_types.get(v.violation_type, 0) + 1
            severity_count[v.severity] = severity_count.get(v.severity, 0) + 1
            
        return {
            "total_violations": len(violations),
            "violation_types": violation_types,
            "severity_distribution": severity_count,
            "unique_persons": len(set(v.person_id for v in violations if v.person_id))
        }
        
    def _generate_id(self, content: Any) -> str:
        """生成唯一ID"""
        content_str = str(content)
        return hashlib.md5(content_str.encode()).hexdigest()[:16]
        
    def persist(self):
        """持久化数据（模拟模式下保存到文件）"""
        if self._mock_mode:
            data = {
                "persons": {k: asdict(v) for k, v in self._mock_persons.items()},
                "violations": [asdict(v) for v in self._mock_violations]
            }
            self.db_path.mkdir(parents=True, exist_ok=True)
            with open(self.db_path / "memory.json", 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("记忆数据已保存")


# 全局向量记忆实例
_memory_instance: Optional[VectorMemory] = None


def get_memory(db_path: str = "./memory_db", similarity_threshold: float = 0.85) -> VectorMemory:
    """获取向量记忆实例"""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = VectorMemory(db_path, similarity_threshold)
    return _memory_instance


if __name__ == "__main__":
    # 测试向量记忆系统
    logging.basicConfig(level=logging.INFO)
    
    memory = get_memory("./test_memory")
    
    # 测试添加人员
    test_embedding = [0.1] * 512
    person_id, is_new = memory.add_person(
        embedding=test_embedding,
        site_id="site_001",
        camera_id="cam_001"
    )
    print(f"添加人员: {person_id}, 是否新人员: {is_new}")
    
    # 测试添加违规
    violation_id = memory.add_violation(
        person_id=person_id,
        violation_type="NO_HELMET",
        severity="high",
        site_id="site_001",
        camera_id="cam_001",
        description="未佩戴安全帽"
    )
    print(f"添加违规: {violation_id}")
    
    # 测试查询
    history = memory.get_person_history(person_id)
    print(f"人员违规历史: {len(history)} 条")
    
    # 保存数据
    memory.persist()
