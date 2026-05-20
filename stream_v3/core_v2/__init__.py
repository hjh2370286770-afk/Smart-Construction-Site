"""
核心模块

提供视频流处理和监控的核心功能：
- StreamProcessor: 单路视频流处理器
- MultiStreamManager: 多路视频流管理器
"""

from .stream_processor import VideoStreamProcessor, StreamConfig, StreamStats, StreamStatus
from .stream_manager import MultiStreamManager

__all__ = [
    'VideoStreamProcessor',
    'StreamConfig',
    'StreamStats',
    'StreamStatus',
    'MultiStreamManager',
]
