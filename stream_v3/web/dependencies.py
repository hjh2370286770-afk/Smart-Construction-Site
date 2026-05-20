"""
依赖注入模块
"""

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core import MultiStreamManager
    from utils.config_loader import ConfigManager

# 全局依赖（将在启动时注入）
_stream_manager: Optional["MultiStreamManager"] = None
_config_manager: Optional["ConfigManager"] = None


def set_stream_manager(manager: "MultiStreamManager"):
    """设置流管理器"""
    global _stream_manager
    _stream_manager = manager


def get_stream_manager() -> Optional["MultiStreamManager"]:
    """获取流管理器"""
    return _stream_manager


def set_config_manager(manager: "ConfigManager"):
    """设置配置管理器"""
    global _config_manager
    _config_manager = manager


def get_config_manager() -> Optional["ConfigManager"]:
    """获取配置管理器"""
    return _config_manager
