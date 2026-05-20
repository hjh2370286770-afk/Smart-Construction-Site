"""
WebSocket 事件处理模块
"""

import asyncio
import logging
from typing import Set
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    WebSocket 连接管理器
    
    管理所有客户端连接，负责消息广播
    """
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket):
        """接受新连接"""
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(f"WebSocket 客户端连接，当前连接数: {len(self.active_connections)}")
    
    async def disconnect(self, websocket: WebSocket):
        """断开连接"""
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"WebSocket 客户端断开，当前连接数: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """
        广播消息到所有连接的客户端
        
        Args:
            message: 要发送的消息字典，格式: {"type": "violation|status", "data": {...}}
        """
        if not self.active_connections:
            return
        
        disconnected = set()
        
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"发送 WebSocket 消息失败: {e}")
                disconnected.add(connection)
        
        # 清理断开的连接
        if disconnected:
            async with self._lock:
                self.active_connections -= disconnected
    
    async def send_to(self, websocket: WebSocket, message: dict):
        """发送消息到指定客户端"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"发送 WebSocket 消息失败: {e}")
            await self.disconnect(websocket)


# 全局 WebSocket 管理器实例
ws_manager = WebSocketManager()


async def websocket_event_handler(event: dict):
    """
    事件处理器 - 将事件转发到 WebSocket
    
    此函数可作为回调传递给 MultiStreamManager
    
    Args:
        event: 事件字典，格式: {"type": "violation|status", "camera_id": "...", "data": {...}}
    """
    try:
        # 转换事件格式为 WebSocket 消息格式
        ws_message = {
            "type": event.get("type", "unknown"),
            "data": event.get("data", {})
        }
        
        # 如果是违规事件，确保包含 camera_id
        if event.get("type") == "violation":
            ws_message["data"]["camera_id"] = event.get("camera_id")
        
        await ws_manager.broadcast(ws_message)
        
    except Exception as e:
        logger.error(f"WebSocket 事件处理异常: {e}")


async def handle_websocket(websocket: WebSocket):
    """
    处理 WebSocket 连接
    
    客户端连接到 /ws/events 时调用此函数
    """
    await ws_manager.connect(websocket)
    
    try:
        # 发送连接成功消息
        await websocket.send_json({
            "type": "connected",
            "data": {
                "message": "Connected to event stream"
            }
        })
        
        # 保持连接，监听客户端消息（心跳等）
        while True:
            try:
                # 接收客户端消息（可选，用于心跳检测）
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0
                )
                
                # 处理心跳
                if data == "ping":
                    await websocket.send_json({"type": "pong", "data": {}})
                
            except asyncio.TimeoutError:
                # 发送心跳
                try:
                    await websocket.send_json({"type": "ping", "data": {}})
                except Exception:
                    break
            
    except WebSocketDisconnect:
        logger.info("WebSocket 客户端断开连接")
    except Exception as e:
        logger.error(f"WebSocket 处理异常: {e}")
    finally:
        await ws_manager.disconnect(websocket)
