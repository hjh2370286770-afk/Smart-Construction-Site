"""
车辆清洗记录 SQLite 数据库模块
- 无需安装MySQL，纯Python实现
- 自动创建数据库文件和表
- 进场插入，出场/清洗更新
- 支持查询和统计
"""

import sqlite3
import logging
from typing import Optional, List, Dict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class VehicleWashDB:
    """车辆清洗记录数据库 (SQLite版)"""

    def __init__(self, config: dict):
        self.db_path = config.get('db_path', 'vehicle_wash.db')
        self.table_name = config.get('table_name', 'vehicle_wash_records')
        self.connection = None
        self._connect()
        self._create_table()

    def _connect(self):
        """连接数据库"""
        try:
            self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self.connection.row_factory = sqlite3.Row
            logger.info(f"SQLite数据库连接成功: {self.db_path}")
        except Exception as e:
            raise Exception(f"SQLite数据库连接失败: {e}")

    def _create_table(self):
        """创建车辆记录表"""
        sql = f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id TEXT NOT NULL,
            license_plate TEXT NOT NULL,
            entry_time TEXT NOT NULL,
            exit_time TEXT NULL,
            is_washed INTEGER DEFAULT 0,
            dwell_time REAL DEFAULT 0,
            wash_start_time TEXT NULL,
            wash_duration REAL DEFAULT 0,
            is_reentry INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
        try:
            with self.connection:
                self.connection.execute(sql)
                # 创建索引
                self.connection.execute(f"CREATE INDEX IF NOT EXISTS idx_plate ON {self.table_name}(license_plate)")
                self.connection.execute(f"CREATE INDEX IF NOT EXISTS idx_entry ON {self.table_name}(entry_time)")
            logger.info(f"表 '{self.table_name}' 就绪")
        except Exception as e:
            raise Exception(f"创建表失败: {e}")

    def save_vehicle_record(self, record) -> Optional[int]:
        """保存或更新车辆记录"""
        try:
            if record.db_id is None:
                return self._insert_record(record)
            else:
                self._update_record(record)
                return record.db_id
        except Exception as e:
            logger.error(f"保存记录失败: {e}")
            return None

    def _insert_record(self, record) -> Optional[int]:
        sql = f"""
        INSERT INTO {self.table_name}
        (vehicle_id, license_plate, entry_time, is_washed, is_reentry)
        VALUES (?, ?, ?, ?, ?)
        """
        try:
            with self.connection:
                cursor = self.connection.execute(sql, (
                    record.vehicle_id,
                    record.license_plate,
                    record.entry_time.isoformat(),
                    1 if record.is_washed else 0,
                    1 if getattr(record, 'is_reentry', False) else 0
                ))
            db_id = cursor.lastrowid
            logger.info(f"插入记录: DB_ID={db_id}, 车牌={record.license_plate}")
            return db_id
        except Exception as e:
            logger.error(f"插入记录失败: {e}")
            return None

    def _update_record(self, record):
        sql = f"""
        UPDATE {self.table_name}
        SET exit_time=?, is_washed=?, dwell_time=?, wash_start_time=?, wash_duration=?
        WHERE id=?
        """
        wash_duration = 0.0
        if record.wash_start_time and record.exit_time:
            wash_duration = (record.exit_time - record.wash_start_time).total_seconds()
        elif record.wash_start_time:
            wash_duration = (datetime.now() - record.wash_start_time).total_seconds()

        try:
            with self.connection:
                self.connection.execute(sql, (
                    record.exit_time.isoformat() if record.exit_time else None,
                    1 if record.is_washed else 0,
                    record.dwell_time,
                    record.wash_start_time.isoformat() if record.wash_start_time else None,
                    wash_duration,
                    record.db_id
                ))
            logger.info(f"更新记录: DB_ID={record.db_id}, 车牌={record.license_plate}")
        except Exception as e:
            logger.error(f"更新记录失败: {e}")

    def update_wash_status(self, db_id: int, is_washed: bool, wash_start_time: datetime = None):
        sql = f"UPDATE {self.table_name} SET is_washed=?, wash_start_time=? WHERE id=?"
        try:
            with self.connection:
                self.connection.execute(sql, (1 if is_washed else 0, wash_start_time.isoformat() if wash_start_time else None, db_id))
        except Exception as e:
            logger.error(f"更新清洗状态失败: {e}")

    def get_records(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        sql = f"SELECT * FROM {self.table_name} ORDER BY entry_time DESC LIMIT ? OFFSET ?"
        try:
            with self.connection:
                cursor = self.connection.execute(sql, (limit, offset))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"查询记录失败: {e}")
            return []

    def get_active_records(self) -> List[Dict]:
        sql = f"SELECT * FROM {self.table_name} WHERE exit_time IS NULL ORDER BY entry_time"
        try:
            with self.connection:
                cursor = self.connection.execute(sql)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"查询在场记录失败: {e}")
            return []

    def get_statistics(self) -> Dict:
        try:
            with self.connection:
                total = self.connection.execute(f"SELECT COUNT(*) FROM {self.table_name}").fetchone()[0]
                active = self.connection.execute(f"SELECT COUNT(*) FROM {self.table_name} WHERE exit_time IS NULL").fetchone()[0]
                washed = self.connection.execute(f"SELECT COUNT(*) FROM {self.table_name} WHERE is_washed=1").fetchone()[0]
                exited = self.connection.execute(f"SELECT COUNT(*) FROM {self.table_name} WHERE exit_time IS NOT NULL").fetchone()[0]
                return {
                    'total': total,
                    'active': active,
                    'washed': washed,
                    'exited': exited,
                    'wash_rate': washed / exited if exited > 0 else 0
                }
        except Exception as e:
            logger.error(f"获取统计失败: {e}")
            return {'total': 0, 'active': 0, 'washed': 0, 'exited': 0, 'wash_rate': 0}

    def close(self):
        if self.connection:
            try:
                self.connection.close()
                logger.info("SQLite数据库连接已关闭")
            except Exception:
                pass
