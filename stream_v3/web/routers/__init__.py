"""
路由模块
"""

from .sites import router as sites_router
from .cameras import router as cameras_router
from .violations import router as violations_router
from .stats import router as stats_router
from .stream import router as stream_router

__all__ = [
    'sites_router',
    'cameras_router', 
    'violations_router',
    'stats_router',
    'stream_router'
]
