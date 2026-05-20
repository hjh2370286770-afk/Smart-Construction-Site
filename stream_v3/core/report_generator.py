#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
日报生成器 - 自动生成每日监控报告
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path
import calendar

from core.database import Database, DailyReport

logger = logging.getLogger(__name__)


class ReportGenerator:
    """日报生成器"""
    
    def __init__(self, db: Database, storage_dir: str = "storage"):
        self.db = db
        self.storage_dir = Path(storage_dir)
    
    def _get_violations_from_files(self, date: Optional[str] = None) -> List[Dict]:
        """从截图文件读取指定日期的违规记录"""
        results = []
        
        # 遍历所有摄像头目录
        for camera_dir in self.storage_dir.iterdir():
            if not camera_dir.is_dir() or camera_dir.name.startswith('__'):
                continue
            
            # 获取所有截图文件
            for img_file in camera_dir.glob("violation_*.jpg"):
                # 从文件名解析日期
                # 文件名格式: violation_YYYYMMDD_HHMMSS_ID{id}_{types}.jpg
                try:
                    parts = img_file.stem.split('_')
                    if len(parts) < 5:
                        continue
                    
                    file_date = parts[1]  # YYYYMMDD
                    file_time = parts[2]  # HHMMSS
                    
                    # 格式化日期
                    year = file_date[:4]
                    month = file_date[4:6]
                    day = file_date[6:8]
                    
                    hour = file_time[:2]
                    minute = file_time[2:4]
                    second = file_time[4:6]
                    
                    timestamp = f"{year}-{month}-{day}T{hour}:{minute}:{second}"
                    
                    # 如果指定了日期，只返回该日期的记录
                    if date:
                        record_date = f"{year}-{month}-{day}"
                        if record_date != date:
                            continue
                    
                    # 解析违规类型（从文件名中提取所有违规类型组合）
                    # 文件名格式: violation_YYYYMMDD_HHMMSS_ID{id}_{type combinations}.jpg
                    # 例如: violation_20260415_171033_ID65_no_helmet_no_vest_no_mask.jpg
                    
                    # 提取所有违规类型标记
                    has_helmet = 'no_helmet' in img_file.name
                    has_vest = 'no_vest' in img_file.name  
                    has_mask = 'no_mask' in img_file.name
                    
                    # 构建违规类型描述（组合形式）
                    violation_parts = []
                    if has_helmet:
                        violation_parts.append("未佩戴安全帽")
                    if has_vest:
                        violation_parts.append("未穿反光背心")
                    if has_mask:
                        violation_parts.append("未佩戴口罩")
                    
                    if violation_parts:
                        type_desc = " + ".join(violation_parts)
                    else:
                        type_desc = "违规检测"
                    
                    results.append({
                        "timestamp": timestamp,
                        "date": f"{year}-{month}-{day}",
                        "hour": hour,
                        "stream_id": camera_dir.name,
                        "stream_name": camera_dir.name,
                        "violation_type": type_desc,
                        "has_helmet": has_helmet,
                        "has_vest": has_vest,
                        "has_mask": has_mask,
                        "filename": img_file.name
                    })
                    
                except Exception as e:
                    logger.warning(f"解析文件名失败 {img_file.name}: {e}")
                    continue
        
        # 按时间戳降序排序
        results.sort(key=lambda x: x["timestamp"], reverse=True)
        return results
    
    def generate_daily_report(self, date: Optional[str] = None) -> Optional[DailyReport]:
        """生成指定日期的日报"""
        if date is None:
            date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        logger.info(f"开始生成 {date} 的日报")
        
        try:
            # 从截图文件读取违规记录
            violations = self._get_violations_from_files(date)
            total_count = len(violations)
            
            logger.info(f"找到 {total_count} 条违规记录")
            
            # 按类型统计
            type_stats: Dict[str, int] = {}
            for v in violations:
                type_stats[v["violation_type"]] = type_stats.get(v["violation_type"], 0) + 1
            
            # 按小时统计（只统计实际有数据的小时）
            hourly_stats: Dict[str, int] = {}
            for v in violations:
                hour_key = f"{v['hour']}:00"
                hourly_stats[hour_key] = hourly_stats.get(hour_key, 0) + 1
            
            # 按视频流统计
            stream_stats: Dict[str, Dict] = {}
            for v in violations:
                sid = v["stream_id"]
                if sid not in stream_stats:
                    stream_stats[sid] = {
                        "stream_id": sid,
                        "stream_name": v["stream_name"],
                        "violation_count": 0
                    }
                stream_stats[sid]["violation_count"] += 1
            
            report = DailyReport(
                date=date,
                total_violations=total_count,
                total_streams=len(stream_stats),
                active_streams=len(stream_stats),
                violation_types=json.dumps([
                    {"type": k, "label": k, "count": v}
                    for k, v in sorted(type_stats.items(), key=lambda x: x[1], reverse=True)
                ], ensure_ascii=False),
                hourly_stats=json.dumps([
                    {"hour": k, "count": v}
                    for k, v in sorted(hourly_stats.items())
                ], ensure_ascii=False),
                stream_stats=json.dumps(list(stream_stats.values()), ensure_ascii=False),
                created_at=datetime.now().isoformat()
            )
            
            self.db.save_daily_report(report)
            logger.info(f"日报生成完成: {date}, 违规总数: {total_count}")
            return report
            
        except Exception as e:
            logger.error(f"生成日报失败: {e}")
            return None
    
    def get_report_summary(self, date: str) -> Optional[Dict]:
        """获取日报摘要"""
        report = self.db.get_daily_report(date)
        if not report:
            return None
        
        try:
            return {
                "date": report.date,
                "total_violations": report.total_violations,
                "total_streams": report.total_streams,
                "active_streams": report.active_streams,
                "violation_types": json.loads(report.violation_types),
                "hourly_stats": json.loads(report.hourly_stats),
                "stream_stats": json.loads(report.stream_stats),
                "created_at": report.created_at
            }
        except:
            return None
    
    def generate_weekly_report(self, end_date: Optional[str] = None) -> Optional[Dict]:
        """生成周报"""
        if end_date is None:
            end_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        end = datetime.strptime(end_date, '%Y-%m-%d')
        start = end - timedelta(days=6)
        
        daily_reports = []
        current = start
        while current <= end:
            summary = self.get_report_summary(current.strftime('%Y-%m-%d'))
            if summary:
                daily_reports.append(summary)
            current += timedelta(days=1)
        
        if not daily_reports:
            return None
        
        total_violations = sum(r['total_violations'] for r in daily_reports)
        
        type_stats: Dict[str, int] = {}
        for r in daily_reports:
            for t in r.get('violation_types', []):
                type_stats[t['type']] = type_stats.get(t['type'], 0) + t['count']
        
        stream_stats: Dict[str, Dict] = {}
        for r in daily_reports:
            for s in r.get('stream_stats', []):
                sid = s['stream_id']
                if sid not in stream_stats:
                    stream_stats[sid] = {'stream_id': sid, 'stream_name': s['stream_name'], 'violation_count': 0}
                stream_stats[sid]['violation_count'] += s['violation_count']
        
        return {
            "start_date": start.strftime('%Y-%m-%d'),
            "end_date": end_date,
            "total_violations": total_violations,
            "daily_average": round(total_violations / len(daily_reports), 1),
            "violation_types": [{"type": k, "count": v} for k, v in sorted(type_stats.items(), key=lambda x: x[1], reverse=True)],
            "stream_stats": list(stream_stats.values()),
            "daily_reports": daily_reports
        }
    
    def generate_monthly_report(self, year: int, month: int) -> Optional[Dict]:
        """生成月报"""
        _, last_day = calendar.monthrange(year, month)
        daily_reports = []
        
        for day in range(1, last_day + 1):
            summary = self.get_report_summary(f"{year}-{month:02d}-{day:02d}")
            if summary:
                daily_reports.append(summary)
        
        if not daily_reports:
            return None
        
        total_violations = sum(r['total_violations'] for r in daily_reports)
        
        type_stats: Dict[str, int] = {}
        for r in daily_reports:
            for t in r.get('violation_types', []):
                type_stats[t['type']] = type_stats.get(t['type'], 0) + t['count']
        
        stream_stats: Dict[str, Dict] = {}
        for r in daily_reports:
            for s in r.get('stream_stats', []):
                sid = s['stream_id']
                if sid not in stream_stats:
                    stream_stats[sid] = {'stream_id': sid, 'stream_name': s['stream_name'], 'violation_count': 0}
                stream_stats[sid]['violation_count'] += s['violation_count']
        
        return {
            "year": year,
            "month": month,
            "total_violations": total_violations,
            "daily_average": round(total_violations / len(daily_reports), 1),
            "violation_types": [{"type": k, "count": v} for k, v in sorted(type_stats.items(), key=lambda x: x[1], reverse=True)],
            "stream_stats": list(stream_stats.values()),
            "daily_reports": daily_reports
        }
