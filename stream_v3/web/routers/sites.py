"""
工地路由
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List

from ..models import SiteResponse
from ..dependencies import get_config_manager

router = APIRouter(prefix="/sites", tags=["sites"])


@router.get("", response_model=List[SiteResponse])
async def get_all_sites():
    """
    获取所有工地信息
    """
    config_manager = get_config_manager()
    if not config_manager:
        raise HTTPException(status_code=503, detail="配置管理器未初始化")
    
    sites = []
    for site in config_manager.sites:
        sites.append(SiteResponse(
            id=site.id,
            name=site.name,
            location=site.location,
            description=site.description,
            camera_count=len(site.cameras)
        ))
    
    return sites
