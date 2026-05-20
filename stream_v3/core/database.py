#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库模块 - SQLite 数据持久化
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ViolationRecord:
    """违规记录数据类"""
    id: str
    timestamp: str
    stream_id: str
    stream_name: str
    violation_type: str
    confidence: float
    image_path: Optional[str]
    location: str


@dataclass
class DailyReport:
    """日报数据类"""
    date: str
    total_violations: int
    total_streams: int
    active_streams: int
    violation_types: str  # JSON
    hourly_stats: str  # JSON
    stream_stats: str  # JSON
    created_at: str


class Database:
    """SQLite 数据库管理器"""
    
    def __init__(self, db_path: str = "storage/stream_v3.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self):
        """初始化数据库表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 违规记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS violations (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    stream_id TEXT NOT NULL,
                    stream_name TEXT NOT NULL,
                    violation_type TEXT NOT NULL,
                    confidence REAL DEFAULT 0.0,
                    image_path TEXT,
                    location TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_violations_stream 
                ON violations(stream_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_violations_date 
                ON violations(timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_violations_type 
                ON violations(violation_type)
            """)
            
            # 日报表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_reports (
                    date TEXT PRIMARY KEY,
                    total_violations INTEGER DEFAULT 0,
                    total_streams INTEGER DEFAULT 0,
                    active_streams INTEGER DEFAULT 0,
                    violation_types TEXT,  -- JSON
                    hourly_stats TEXT,     -- JSON
                    stream_stats TEXT,     -- JSON
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 系统状态历史表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_status_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    cpu_usage REAL,
                    memory_usage REAL,
                    disk_usage REAL,
                    active_streams INTEGER,
                    total_violations INTEGER
                )
            """)
            
            conn.commit()
            logger.info("数据库初始化完成")
    
    # ==================== 违规记录操作 ====================
    
    def add_violation(self, violation: ViolationRecord) -> bool:
        """添加违规记录"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO violations 
                    (id, timestamp, stream_id, stream_name, violation_type, 
                     confidence, image_path, location)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    violation.id, violation.timestamp, violation.stream_id,
                    violation.stream_name, violation.violation_type,
                    violation.confidence, violation.image_path, violation.location
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"添加违规记录失败: {e}")
            return False
    
    def get_violations(
        self,
        stream_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        violation_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[ViolationRecord], int]:
        """查询违规记录"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 构建查询条件
                conditions = []
                params = []
                
                if stream_id:
                    conditions.append("stream_id = ?")
                    params.append(stream_id)
                
                if start_date:
                    conditions.append("timestamp >= ?")
                    params.append(start_date)
                
                if end_date:
                    conditions.append("timestamp <= ?")
                    params.append(end_date)
                
                if violation_type:
                    conditions.append("violation_type = ?")
                    params.append(violation_type)
                
                where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
                
                # 查询总数
                count_sql = f"SELECT COUNT(*) FROM violations {where_clause}"
                cursor.execute(count_sql, params)
                total = cursor.fetchone()[0]
                
                # 查询数据
                sql = f"""
                    SELECT * FROM violations 
                    {where_clause}
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                """
                cursor.execute(sql, params + [limit, offset])
                
                rows = cursor.fetchall()
                violations = [
                    ViolationRecord(
                        id=row['id'],
                        timestamp=row['timestamp'],
                        stream_id=row['stream_id'],
                        stream_name=row['stream_name'],
                        violation_type=row['violation_type'],
                        confidence=row['confidence'],
                        image_path=row['image_path'],
                        location=row['location']
                    )
                    for row in rows
                ]
                
                return violations, total
        except Exception as e:
            logger.error(f"查询违规记录失败: {e}")
            return [], 0
    
    def get_violation_stats(
        self,
        days: int = 7,
        stream_id: Optional[str] = None
    ) -> Dict:
        """获取违规统计"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 计算日期范围
                end_date = datetime.now()
                start_date = end_date - timedelta(days=days)
                
                # 按类型统计
                type_sql = """
                    SELECT violation_type, COUNT(*) as count 
                    FROM violations 
                    WHERE timestamp >= ? AND timestamp <= ?
                """
                type_params = [start_date.isoformat(), end_date.isoformat()]
                
                if stream_id:
                    type_sql += " AND stream_id = ?"
                    type_params.append(stream_id)
                
                type_sql += " GROUP BY violation_type"
                
                cursor.execute(type_sql, type_params)
                by_type = {row['violation_type']: row['count'] for row in cursor.fetchall()}
                
                # 按视频流统计
                stream_sql = """
                    SELECT stream_id, stream_name, COUNT(*) as count 
                    FROM violations 
                    WHERE timestamp >= ? AND timestamp <= ?
                    GROUP BY stream_id
                """
                cursor.execute(stream_sql, [start_date.isoformat(), end_date.isoformat()])
                by_stream = [
                    {"stream_id": row['stream_id'], "stream_name": row['stream_name'], "count": row['count']}
                    for row in cursor.fetchall()
                ]
                
                # 按小时统计（最近24小时）
                hourly_sql = """
                    SELECT substr(timestamp, 12, 2) as hour, COUNT(*) as count
                    FROM violations
                    WHERE timestamp >= ?
                    GROUP BY hour
                    ORDER BY hour
                """
                cursor.execute(hourly_sql, [(datetime.now() - timedelta(hours=24)).isoformat()])
                hourly = {row['hour']: row['count'] for row in cursor.fetchall()}
                
                # 按天统计
                daily_sql = """
                    SELECT substr(timestamp, 1, 10) as date, COUNT(*) as count
                    FROM violations
                    WHERE timestamp >= ? AND timestamp <= ?
                    GROUP BY date
                    ORDER BY date
                """
                cursor.execute(daily_sql, [start_date.isoformat(), end_date.isoformat()])
                daily = {row['date']: row['count'] for row in cursor.fetchall()}
                
                # 总数量
                total_sql = """
                    SELECT COUNT(*) as total FROM violations
                    WHERE timestamp >= ? AND timestamp <= ?
                """
                total_params = [start_date.isoformat(), end_date.isoformat()]
                if stream_id:
                    total_sql += " AND stream_id = ?"
                    total_params.append(stream_id)
                
                cursor.execute(total_sql, total_params)
                total = cursor.fetchone()['total']
                
                return {
                    "total": total,
                    "by_type": by_type,
                    "by_stream": by_stream,
                    "hourly": hourly,
                    "daily": daily
                }
        except Exception as e:
            logger.error(f"获取违规统计失败: {e}")
            return {"total": 0, "by_type": {}, "by_stream": [], "hourly": {}, "daily": {}}
    
    def get_violation_types(self) -> List[str]:
        """获取所有违规类型"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT violation_type FROM violations")
                return [row['violation_type'] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"获取违规类型失败: {e}")
            return []
    
    # ==================== 日报操作 ====================
    
    def save_daily_report(self, report: DailyReport) -> bool:
        """保存日报"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO daily_reports 
                    (date, total_violations, total_streams, active_streams,
                     violation_types, hourly_stats, stream_stats, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    report.date, report.total_violations, report.total_streams,
                    report.active_streams, report.violation_types,
                    report.hourly_stats, report.stream_stats, report.created_at
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"保存日报失败: {e}")
            return False
    
    def get_daily_report(self, date: str) -> Optional[DailyReport]:
        """获取日报"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM daily_reports WHERE date = ?
                """, (date,))
                row = cursor.fetchone()
                
                if row:
                    return DailyReport(
                        date=row['date'],
                        total_violations=row['total_violations'],
                        total_streams=row['total_streams'],
                        active_streams=row['active_streams'],
                        violation_types=row['violation_types'],
                        hourly_stats=row['hourly_stats'],
                        stream_stats=row['stream_stats'],
                        created_at=row['created_at']
                    )
                return None
        except Exception as e:
            logger.error(f"获取日报失败: {e}")
            return None
    
    def get_report_history(
        self,
        limit: int = 30,
        offset: int = 0
    ) -> Tuple[List[DailyReport], int]:
        """获取历史日报列表"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 总数
                cursor.execute("SELECT COUNT(*) FROM daily_reports")
                total = cursor.fetchone()[0]
                
                # 数据
                cursor.execute("""
                    SELECT * FROM daily_reports
                    ORDER BY date DESC
                    LIMIT ? OFFSET ?
                """, (limit, offset))
                
                rows = cursor.fetchall()
                reports = [
                    DailyReport(
                        date=row['date'],
                        total_violations=row['total_violations'],
                        total_streams=row['total_streams'],
                        active_streams=row['active_streams'],
                        violation_types=row['violation_types'],
                        hourly_stats=row['hourly_stats'],
                        stream_stats=row['stream_stats'],
                        created_at=row['created_at']
                    )
                    for row in rows
                ]
                
                return reports, total
        except Exception as e:
            logger.error(f"获取日报历史失败: {e}")
            return [], 0
    
    # ==================== 系统状态历史 ====================
    
    def add_system_status(
        self,
        cpu_usage: float,
        memory_usage: float,
        disk_usage: float,
        active_streams: int,
        total_violations: int
    ):
        """添加系统状态记录"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO system_status_history 
                    (cpu_usage, memory_usage, disk_usage, active_streams, total_violations)
                    VALUES (?, ?, ?, ?, ?)
                """, (cpu_usage, memory_usage, disk_usage, active_streams, total_violations))
                conn.commit()
        except Exception as e:
            logger.error(f"添加系统状态记录失败: {e}")
    
    def get_system_status_history(self, hours: int = 24) -> List[Dict]:
        """获取系统状态历史"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                start_time = datetime.now() - timedelta(hours=hours)
                
                cursor.execute("""
                    SELECT * FROM system_status_history
                    WHERE timestamp >= ?
                    ORDER BY timestamp DESC
                """, (start_time.isoformat(),))
                
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"获取系统状态历史失败: {e}")
            return []
    
    def cleanup_old_data(self, days: int = 90):
        """清理旧数据"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
                
                # 清理旧违规记录
                cursor.execute("""
                    DELETE FROM violations WHERE timestamp < ?
                """, (cutoff_date,))
                
                # 清理旧系统状态
                cursor.execute("""
                    DELETE FROM system_status_history WHERE timestamp < ?
                """, (cutoff_date,))
                
                conn.commit()
                logger.info(f"清理了 {days} 天前的旧数据")
        except Exception as e:
            logger.error(f"清理旧数据失败: {e}")


# 全局数据库实例
db = Database()
