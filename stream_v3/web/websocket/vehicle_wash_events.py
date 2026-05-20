"""
车辆清洗检测 WebSocket 事件发布模块

将车辆清洗检测的实时事件推送到前端
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional
from .events import ws_manager

logger = logging.getLogger(__name__)


class VehicleWashEventPublisher:
    """
    车辆清洗事件发布器
    
    将车辆进场、出场、清洗等事件通过WebSocket推送到前端
    """
    
    @staticmethod
    async def publish_entry(plate: str, entry_time: datetime, vehicle_id: str):
        """发布车辆进场事件"""
        await ws_manager.broadcast({
            "type": "vehicle_wash_entry",
            "data": {
                "license_plate": plate,
                "entry_time": entry_time.isoformat(),
                "vehicle_id": vehicle_id,
                "timestamp": datetime.now().isoformat()
            }
        })
        logger.info(f"WebSocket推送: 车辆进场 {plate}")
    
    @staticmethod
    async def publish_exit(plate: str, exit_time: datetime, dwell_time: float, is_washed: bool):
        """发布车辆出场事件"""
        await ws_manager.broadcast({
            "type": "vehicle_wash_exit",
            "data": {
                "license_plate": plate,
                "exit_time": exit_time.isoformat(),
                "dwell_time": dwell_time,
                "is_washed": is_washed,
                "timestamp": datetime.now().isoformat()
            }
        })
        logger.info(f"WebSocket推送: 车辆出场 {plate}")
    
    @staticmethod
    async def publish_wash_start(plate: str, wash_start_time: datetime):
        """发布清洗开始事件"""
        await ws_manager.broadcast({
            "type": "vehicle_wash_start",
            "data": {
                "license_plate": plate,
                "wash_start_time": wash_start_time.isoformat(),
                "timestamp": datetime.now().isoformat()
            }
        })
        logger.info(f"WebSocket推送: 清洗开始 {plate}")
    
    @staticmethod
    async def publish_wash_complete(plate: str, wash_duration: float):
        """发布清洗完成事件"""
        await ws_manager.broadcast({
            "type": "vehicle_wash_complete",
            "data": {
                "license_plate": plate,
                "wash_duration": wash_duration,
                "timestamp": datetime.now().isoformat()
            }
        })
        logger.info(f"WebSocket推送: 清洗完成 {plate}")
    
    @staticmethod
    async def publish_realtime_status(
        active_count: int,
        today_entries: int,
        today_exits: int,
        today_washed: int,
        active_vehicles: list
    ):
        """发布实时状态更新"""
        await ws_manager.broadcast({
            "type": "vehicle_wash_status",
            "data": {
                "active_count": active_count,
                "today_entries": today_entries,
                "today_exits": today_exits,
                "today_washed": today_washed,
                "active_vehicles": active_vehicles,
                "timestamp": datetime.now().isoformat()
            }
        })


# 全局事件发布器实例
vehicle_wash_publisher = VehicleWashEventPublisher()


# 兼容同步调用的辅助函数（用于从非异步上下文调用）
def publish_entry_sync(plate: str, entry_time: datetime, vehicle_id: str):
    """同步方式发布进场事件（用于从检测线程调用）"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(vehicle_wash_publisher.publish_entry(plate, entry_time, vehicle_id))
        else:
            loop.run_until_complete(vehicle_wash_publisher.publish_entry(plate, entry_time, vehicle_id))
    except Exception as e:
        logger.debug(f"WebSocket推送进场事件失败（可能无连接）: {e}")


def publish_exit_sync(plate: str, exit_time: datetime, dwell_time: float, is_washed: bool):
    """同步方式发布出场事件"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(vehicle_wash_publisher.publish_exit(plate, exit_time, dwell_time, is_washed))
        else:
            loop.run_until_complete(vehicle_wash_publisher.publish_exit(plate, exit_time, dwell_time, is_washed))
    except Exception as e:
        logger.debug(f"WebSocket推送出场事件失败（可能无连接）: {e}")


def publish_wash_complete_sync(plate: str, wash_duration: float):
    """同步方式发布清洗完成事件"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(vehicle_wash_publisher.publish_wash_complete(plate, wash_duration))
        else:
            loop.run_until_complete(vehicle_wash_publisher.publish_wash_complete(plate, wash_duration))
    except Exception as e:
        logger.debug(f"WebSocket推送清洗事件失败（可能无连接）: {e}")
