"""
FastAPI 主应用
"""

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import logging

from .routers import sites, cameras, violations, stats, stream, vehicle_wash
from .websocket.events import handle_websocket
from .dependencies import set_stream_manager, set_config_manager

logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(
    title="Stream Manager V2 API",
    description="工地安全监控系统 Web API",
    version="2.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制为前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(sites.router, prefix="/api")
app.include_router(cameras.router, prefix="/api")
app.include_router(violations.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(stream.router)
app.include_router(vehicle_wash.router, prefix="/api")


@app.websocket("/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 事件端点"""
    await handle_websocket(websocket)


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "version": "2.0.0"}


# 静态文件服务（前端构建文件）
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """服务单页应用"""
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"message": "Frontend not built. Run 'npm run build' in web_frontend."}


def create_app(stream_manager=None, config_manager=None):
    """
    创建应用实例（用于集成模式）
    
    Args:
        stream_manager: MultiStreamManager 实例
        config_manager: ConfigManager 实例
    """
    if stream_manager:
        set_stream_manager(stream_manager)
    if config_manager:
        set_config_manager(config_manager)
    
    return app


if __name__ == "__main__":
    import uvicorn
    
    # 独立运行模式
    uvicorn.run(app, host="0.0.0.0", port=8000)
