"""
配置加载模块
支持 YAML 配置文件加载和验证
"""

import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class CameraConfig:
    """摄像头配置"""
    id: str
    name: str
    url: str
    type: str = "rtmp"
    enabled: bool = True
    models: List[str] = field(default_factory=list)
    rules: List[Dict] = field(default_factory=list)
    roi: Optional[List[List[int]]] = None


@dataclass
class SiteConfig:
    """工地配置"""
    id: str
    name: str
    location: str
    description: str = ""
    cameras: List[CameraConfig] = field(default_factory=list)


@dataclass
class ModelConfig:
    """模型配置"""
    name: str
    description: str
    type: str
    path: str
    version: str
    classes: List[Dict] = field(default_factory=list)
    violation_rules: List[Dict] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GlobalConfig:
    """全局配置"""
    stream: Dict[str, Any] = field(default_factory=dict)
    detection: Dict[str, Any] = field(default_factory=dict)
    output: Dict[str, Any] = field(default_factory=dict)
    memory: Dict[str, Any] = field(default_factory=dict)
    web: Dict[str, Any] = field(default_factory=dict)


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_dir: str = "./config"):
        self.config_dir = Path(config_dir)
        self.sites: List[SiteConfig] = []
        self.models: Dict[str, ModelConfig] = {}
        self.global_config: GlobalConfig = GlobalConfig()
        
    def load_all(self):
        """加载所有配置"""
        self._load_sites()
        self._load_models()
        logger.info("配置加载完成")
        
    def _load_sites(self):
        """加载工地配置"""
        sites_file = self.config_dir / "sites.yaml"
        if not sites_file.exists():
            logger.warning(f"站点配置文件不存在: {sites_file}")
            return
            
        with open(sites_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            
        # 解析全局配置
        if 'global' in data:
            self.global_config = GlobalConfig(**data['global'])
            
        # 解析站点配置
        for site_data in data.get('sites', []):
            cameras = []
            for cam_data in site_data.get('cameras', []):
                cameras.append(CameraConfig(**cam_data))
            
            site = SiteConfig(
                id=site_data['id'],
                name=site_data['name'],
                location=site_data['location'],
                description=site_data.get('description', ''),
                cameras=cameras
            )
            self.sites.append(site)
            
        logger.info(f"加载了 {len(self.sites)} 个站点")
        
    def _load_models(self):
        """加载模型配置"""
        models_file = self.config_dir / "models.yaml"
        if not models_file.exists():
            logger.warning(f"模型配置文件不存在: {models_file}")
            return
            
        with open(models_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            
        for model_id, model_data in data.get('models', {}).items():
            self.models[model_id] = ModelConfig(**model_data)
            
        logger.info(f"加载了 {len(self.models)} 个模型")
        
    def get_site(self, site_id: str) -> Optional[SiteConfig]:
        """获取指定站点配置"""
        for site in self.sites:
            if site.id == site_id:
                return site
        return None
        
    def get_model(self, model_id: str) -> Optional[ModelConfig]:
        """获取指定模型配置"""
        return self.models.get(model_id)
        
    def get_enabled_cameras(self) -> List[tuple]:
        """获取所有启用的摄像头"""
        cameras = []
        for site in self.sites:
            for camera in site.cameras:
                if camera.enabled:
                    cameras.append((site, camera))
        return cameras


# 全局配置实例
_config_manager: Optional[ConfigManager] = None


def get_config(config_dir: str = "./config") -> ConfigManager:
    """获取配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_dir)
        _config_manager.load_all()
    return _config_manager


def reload_config():
    """重新加载配置"""
    global _config_manager
    if _config_manager:
        _config_manager.load_all()


if __name__ == "__main__":
    # 测试配置加载
    logging.basicConfig(level=logging.INFO)
    config = get_config("../config")
    
    print("\n=== 站点配置 ===")
    for site in config.sites:
        print(f"\n站点: {site.name} ({site.id})")
        print(f"  位置: {site.location}")
        for cam in site.cameras:
            print(f"  摄像头: {cam.name}")
            print(f"    模型: {cam.models}")
            print(f"    规则: {[r['type'] for r in cam.rules]}")
    
    print("\n=== 模型配置 ===")
    for model_id, model in config.models.items():
        print(f"\n模型: {model.name} ({model_id})")
        print(f"  类型: {model.type}")
        print(f"  类别: {[c['name'] for c in model.classes]}")
