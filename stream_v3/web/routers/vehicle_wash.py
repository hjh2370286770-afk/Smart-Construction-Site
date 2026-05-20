"""
车辆清洗检测路由
提供车辆清洗记录的查询、统计、导出等功能
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import os

from ..models.schemas import BaseModel

router = APIRouter(prefix="/vehicle-wash", tags=["vehicle-wash"])

DB_PATH = "vehicle_wash.db"


# ========== Pydantic 模型 ==========

class VehicleWashRecord(BaseModel):
    """车辆清洗记录"""
    id: int
    vehicle_id: str
    license_plate: str
    entry_time: str
    exit_time: Optional[str] = None
    is_washed: bool
    dwell_time: float
    wash_start_time: Optional[str] = None
    wash_duration: float
    is_reentry: bool
    created_at: str


class VehicleWashStats(BaseModel):
    """车辆清洗统计"""
    total_records: int
    total_entries: int
    total_exits: int
    active_vehicles: int
    washed_count: int
    wash_rate: float
    avg_dwell_time: float
    today_entries: int
    today_exits: int
    today_washed: int


class DailyStatsItem(BaseModel):
    """每日统计项"""
    date: str
    entries: int
    exits: int
    washed: int
    wash_rate: float


class PlateStatsItem(BaseModel):
    """车牌统计项"""
    license_plate: str
    entry_count: int
    wash_count: int
    total_dwell_time: float
    avg_dwell_time: float


class ExportResponse(BaseModel):
    """导出响应"""
    success: bool
    message: str
    file_path: Optional[str] = None
    download_url: Optional[str] = None


# ========== 数据库连接工具 ==========

def get_db_connection():
    """获取数据库连接"""
    if not os.path.exists(DB_PATH):
        raise HTTPException(status_code=404, detail="数据库文件不存在")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ========== API 路由 ==========

@router.get("/records", response_model=List[VehicleWashRecord])
async def get_wash_records(
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    plate: Optional[str] = Query(None, description="车牌号筛选"),
    is_washed: Optional[bool] = Query(None, description="是否已清洗"),
    has_exited: Optional[bool] = Query(None, description="是否已出场"),
    limit: int = Query(100, ge=1, le=1000, description="返回数量限制"),
    offset: int = Query(0, ge=0, description="偏移量")
):
    """
    获取车辆清洗记录列表
    
    支持按日期范围、车牌号、清洗状态、出场状态筛选
    """
    conn = get_db_connection()
    try:
        sql = "SELECT * FROM vehicle_wash_records WHERE 1=1"
        params = []
        
        if start_date:
            sql += " AND entry_time >= ?"
            params.append(f"{start_date} 00:00:00")
        if end_date:
            sql += " AND entry_time <= ?"
            params.append(f"{end_date} 23:59:59")
        if plate:
            sql += " AND license_plate LIKE ?"
            params.append(f"%{plate}%")
        if is_washed is not None:
            sql += " AND is_washed = ?"
            params.append(1 if is_washed else 0)
        if has_exited is not None:
            if has_exited:
                sql += " AND exit_time IS NOT NULL"
            else:
                sql += " AND exit_time IS NULL"
        
        sql += " ORDER BY entry_time DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()
        
        records = []
        for row in rows:
            records.append(VehicleWashRecord(
                id=row['id'],
                vehicle_id=row['vehicle_id'],
                license_plate=row['license_plate'],
                entry_time=row['entry_time'],
                exit_time=row['exit_time'],
                is_washed=bool(row['is_washed']),
                dwell_time=row['dwell_time'] or 0,
                wash_start_time=row['wash_start_time'],
                wash_duration=row['wash_duration'] or 0,
                is_reentry=bool(row['is_reentry']),
                created_at=row['created_at']
            ))
        
        return records
    finally:
        conn.close()


@router.get("/records/{record_id}", response_model=VehicleWashRecord)
async def get_wash_record(record_id: int):
    """获取单条车辆清洗记录详情"""
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM vehicle_wash_records WHERE id = ?",
            (record_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="记录不存在")
        
        return VehicleWashRecord(
            id=row['id'],
            vehicle_id=row['vehicle_id'],
            license_plate=row['license_plate'],
            entry_time=row['entry_time'],
            exit_time=row['exit_time'],
            is_washed=bool(row['is_washed']),
            dwell_time=row['dwell_time'] or 0,
            wash_start_time=row['wash_start_time'],
            wash_duration=row['wash_duration'] or 0,
            is_reentry=bool(row['is_reentry']),
            created_at=row['created_at']
        )
    finally:
        conn.close()


@router.get("/stats", response_model=VehicleWashStats)
async def get_wash_stats():
    """获取车辆清洗统计信息"""
    conn = get_db_connection()
    try:
        # 总体统计
        cursor = conn.execute("SELECT COUNT(*) FROM vehicle_wash_records")
        total_records = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM vehicle_wash_records WHERE exit_time IS NULL")
        active_vehicles = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM vehicle_wash_records WHERE exit_time IS NOT NULL")
        total_exits = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM vehicle_wash_records WHERE is_washed = 1")
        washed_count = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT AVG(dwell_time) FROM vehicle_wash_records WHERE dwell_time > 0")
        avg_dwell = cursor.fetchone()[0] or 0
        
        # 今日统计
        today = datetime.now().strftime('%Y-%m-%d')
        cursor = conn.execute(
            "SELECT COUNT(*) FROM vehicle_wash_records WHERE entry_time LIKE ?",
            (f"{today}%",)
        )
        today_entries = cursor.fetchone()[0]
        
        cursor = conn.execute(
            "SELECT COUNT(*) FROM vehicle_wash_records WHERE exit_time LIKE ?",
            (f"{today}%",)
        )
        today_exits = cursor.fetchone()[0]
        
        cursor = conn.execute(
            "SELECT COUNT(*) FROM vehicle_wash_records WHERE is_washed = 1 AND entry_time LIKE ?",
            (f"{today}%",)
        )
        today_washed = cursor.fetchone()[0]
        
        wash_rate = (washed_count / total_exits * 100) if total_exits > 0 else 0
        
        return VehicleWashStats(
            total_records=total_records,
            total_entries=total_records,
            total_exits=total_exits,
            active_vehicles=active_vehicles,
            washed_count=washed_count,
            wash_rate=round(wash_rate, 1),
            avg_dwell_time=round(avg_dwell, 1),
            today_entries=today_entries,
            today_exits=today_exits,
            today_washed=today_washed
        )
    finally:
        conn.close()


@router.get("/stats/daily", response_model=List[DailyStatsItem])
async def get_daily_stats(
    days: int = Query(7, ge=1, le=30, description="最近N天")
):
    """获取每日统计"""
    conn = get_db_connection()
    try:
        results = []
        for i in range(days - 1, -1, -1):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            
            cursor = conn.execute(
                "SELECT COUNT(*) FROM vehicle_wash_records WHERE entry_time LIKE ?",
                (f"{date}%",)
            )
            entries = cursor.fetchone()[0]
            
            cursor = conn.execute(
                "SELECT COUNT(*) FROM vehicle_wash_records WHERE exit_time LIKE ?",
                (f"{date}%",)
            )
            exits = cursor.fetchone()[0]
            
            cursor = conn.execute(
                "SELECT COUNT(*) FROM vehicle_wash_records WHERE is_washed = 1 AND entry_time LIKE ?",
                (f"{date}%",)
            )
            washed = cursor.fetchone()[0]
            
            wash_rate = (washed / exits * 100) if exits > 0 else 0
            
            results.append(DailyStatsItem(
                date=date,
                entries=entries,
                exits=exits,
                washed=washed,
                wash_rate=round(wash_rate, 1)
            ))
        
        return results
    finally:
        conn.close()


@router.get("/stats/plates", response_model=List[PlateStatsItem])
async def get_plate_stats(
    limit: int = Query(20, ge=1, le=100, description="返回数量")
):
    """获取车牌统计（高频车辆）"""
    conn = get_db_connection()
    try:
        cursor = conn.execute("""
            SELECT 
                license_plate,
                COUNT(*) as entry_count,
                SUM(CASE WHEN is_washed = 1 THEN 1 ELSE 0 END) as wash_count,
                SUM(dwell_time) as total_dwell_time,
                AVG(dwell_time) as avg_dwell_time
            FROM vehicle_wash_records
            GROUP BY license_plate
            ORDER BY entry_count DESC
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        results = []
        for row in rows:
            results.append(PlateStatsItem(
                license_plate=row['license_plate'],
                entry_count=row['entry_count'],
                wash_count=row['wash_count'],
                total_dwell_time=round(row['total_dwell_time'] or 0, 1),
                avg_dwell_time=round(row['avg_dwell_time'] or 0, 1)
            ))
        
        return results
    finally:
        conn.close()


@router.get("/active-vehicles", response_model=List[VehicleWashRecord])
async def get_active_vehicles():
    """获取当前在场车辆"""
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            "SELECT * FROM vehicle_wash_records WHERE exit_time IS NULL ORDER BY entry_time DESC"
        )
        rows = cursor.fetchall()
        
        records = []
        for row in rows:
            records.append(VehicleWashRecord(
                id=row['id'],
                vehicle_id=row['vehicle_id'],
                license_plate=row['license_plate'],
                entry_time=row['entry_time'],
                exit_time=row['exit_time'],
                is_washed=bool(row['is_washed']),
                dwell_time=row['dwell_time'] or 0,
                wash_start_time=row['wash_start_time'],
                wash_duration=row['wash_duration'] or 0,
                is_reentry=bool(row['is_reentry']),
                created_at=row['created_at']
            ))
        
        return records
    finally:
        conn.close()


@router.post("/export", response_model=ExportResponse)
async def export_records(
    background_tasks: BackgroundTasks,
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期"),
    plate: Optional[str] = Query(None, description="车牌号筛选")
):
    """
    导出车辆清洗记录为Excel
    
    导出完成后返回下载链接
    """
    try:
        from export_db_to_excel import VehicleWashDBExporter
        
        output_filename = f"vehicle_wash_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        output_path = os.path.join("storage", "exports", output_filename)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        exporter = VehicleWashDBExporter(DB_PATH)
        
        # 构建日期筛选参数
        start_param = None
        end_param = None
        if start_date:
            start_param = f"{start_date} 00:00:00"
        if end_date:
            end_param = f"{end_date} 23:59:59"
        
        result_path = exporter.export_to_excel(
            output_path=output_path,
            start_date=start_param,
            end_date=end_param,
            plate_filter=plate
        )
        exporter.close()
        
        if result_path:
            return ExportResponse(
                success=True,
                message="导出成功",
                file_path=result_path,
                download_url=f"/api/vehicle-wash/download?file={output_filename}"
            )
        else:
            return ExportResponse(
                success=False,
                message="没有找到记录"
            )
    except Exception as e:
        return ExportResponse(
            success=False,
            message=f"导出失败: {str(e)}"
        )


@router.get("/download")
async def download_export(file: str):
    """下载导出的Excel文件"""
    file_path = Path("storage/exports") / file
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    return FileResponse(
        str(file_path),
        filename=file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@router.get("/realtime")
async def get_realtime_status():
    """获取实时状态（当前在场车辆数、今日统计等）"""
    conn = get_db_connection()
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        
        # 当前在场
        cursor = conn.execute("SELECT COUNT(*) FROM vehicle_wash_records WHERE exit_time IS NULL")
        active_count = cursor.fetchone()[0]
        
        # 今日进场
        cursor = conn.execute(
            "SELECT COUNT(*) FROM vehicle_wash_records WHERE entry_time LIKE ?",
            (f"{today}%",)
        )
        today_entries = cursor.fetchone()[0]
        
        # 今日出场
        cursor = conn.execute(
            "SELECT COUNT(*) FROM vehicle_wash_records WHERE exit_time LIKE ?",
            (f"{today}%",)
        )
        today_exits = cursor.fetchone()[0]
        
        # 今日清洗
        cursor = conn.execute(
            "SELECT COUNT(*) FROM vehicle_wash_records WHERE is_washed = 1 AND entry_time LIKE ?",
            (f"{today}%",)
        )
        today_washed = cursor.fetchone()[0]
        
        # 在场车辆详情
        cursor = conn.execute(
            "SELECT license_plate, entry_time, is_washed FROM vehicle_wash_records WHERE exit_time IS NULL ORDER BY entry_time DESC LIMIT 10"
        )
        active_vehicles = []
        for row in cursor.fetchall():
            entry_dt = datetime.fromisoformat(row['entry_time'])
            elapsed = (datetime.now() - entry_dt).total_seconds()
            active_vehicles.append({
                "license_plate": row['license_plate'],
                "entry_time": row['entry_time'],
                "elapsed_minutes": round(elapsed / 60, 1),
                "is_washed": bool(row['is_washed'])
            })
        
        return {
            "active_count": active_count,
            "today_entries": today_entries,
            "today_exits": today_exits,
            "today_washed": today_washed,
            "active_vehicles": active_vehicles,
            "timestamp": datetime.now().isoformat()
        }
    finally:
        conn.close()
