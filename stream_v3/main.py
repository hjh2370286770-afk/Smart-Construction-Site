#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stream V3 后端主程序
多工地安全监控系统 - Web API 版本

功能：
1. 多路视频流并发处理
2. 可配置的多模型检测
3. 违规记录持久化
4. Web API 接口
5. AI 日报生成

启动：
    python main.py
"""

import sys
import io
import asyncio
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict
import json

# 修复 Windows 编码
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

PROJECT_ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

# 导入数据库和日报生成器
from core.database import db, ViolationRecord as DBViolationRecord
from core.report_generator import ReportGenerator

# ============================================================
# WebSocket 连接管理器
# ============================================================

class WebSocketManager:
    """WebSocket 连接管理器 - 管理所有客户端连接并广播事件"""
    
    def __init__(self):
        self.active_connections: Set = set()
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket):
        """接受新连接"""
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(f"WebSocket 客户端连接，当前连接数: {len(self.active_connections)}")
    
    async def disconnect(self, websocket):
        """断开连接"""
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"WebSocket 客户端断开，当前连接数: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """广播消息到所有连接的客户端"""
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

# 全局 WebSocket 管理器实例
ws_manager = WebSocketManager()

# 全局日报生成器
report_generator = ReportGenerator(db, str(PROJECT_ROOT / "storage"))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================
# 数据结构
# ============================================================

@dataclass
class ViolationRecord:
    """违规记录"""
    id: str
    timestamp: str
    camera_id: str
    camera_name: str
    violation_type: str
    severity: str
    description: str
    image_path: Optional[str] = None


# ============================================================
# FastAPI 应用
# ============================================================

from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from io import BytesIO
import uvicorn

app = FastAPI(title="Stream V3 API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件服务
app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "web_frontend")), name="static")

# 注册车辆清洗API路由
from web.routers import vehicle_wash
app.include_router(vehicle_wash.router, prefix="/api")


# ============================================================
# 存储
# ============================================================

violations: List[ViolationRecord] = []
violations_file = PROJECT_ROOT / "storage" / "violations.json"
streams_config: Dict[str, dict] = {}
streams_status: Dict[str, str] = {}
streams_file = PROJECT_ROOT / "storage" / "streams.json"
streams_status_file = PROJECT_ROOT / "storage" / "streams_status.json"


def load_violations():
    """加载违规记录"""
    global violations
    if violations_file.exists():
        try:
            with open(violations_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                violations = [ViolationRecord(**v) for v in data]
            logger.info(f"加载了 {len(violations)} 条违规记录")
        except Exception as e:
            logger.error(f"加载违规记录失败: {e}")


def save_violations():
    """保存违规记录"""
    try:
        violations_file.parent.mkdir(parents=True, exist_ok=True)
        with open(violations_file, 'w', encoding='utf-8') as f:
            json.dump([asdict(v) for v in violations], f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存违规记录失败: {e}")


def load_streams():
    """加载视频流配置 - 合并sites.yaml和streams.json"""
    global streams_config, streams_status
    
    # 先从streams.json加载已有配置（包括前端添加的）
    if streams_file.exists():
        try:
            with open(streams_file, 'r', encoding='utf-8') as f:
                streams_config = json.load(f)
            logger.info(f"从streams.json加载了 {len(streams_config)} 个视频流配置")
        except Exception as e:
            logger.error(f"从streams.json加载失败: {e}")
            streams_config = {}
    
    # 再从sites.yaml加载配置，合并但不覆盖已有配置
    try:
        from utils.config_loader import ConfigManager
        config_mgr = ConfigManager(str(PROJECT_ROOT / "config"))
        config_mgr.load_all()
        
        # 将sites.yaml中的摄像头配置合并到streams_config
        for site in config_mgr.sites:
            for camera in site.cameras:
                if camera.id not in streams_config:
                    # 只有不存在时才添加
                    streams_config[camera.id] = {
                        'name': camera.name,
                        'url': camera.url,
                        'detector_type': camera.models[0] if camera.models else 'ppe_detector',
                        'enabled': camera.enabled,
                        'site_id': site.id,
                        'site_name': site.name,
                        'type': camera.type,
                        'models': camera.models,
                        'rules': camera.rules
                    }
                    streams_status[camera.id] = 'stopped' if camera.enabled else 'disabled'
        
        logger.info(f"从sites.yaml合并后共 {len(streams_config)} 个视频流配置")
        
        # 保存合并后的配置
        save_streams()
        
    except Exception as e:
        logger.error(f"从sites.yaml加载配置失败: {e}")


def save_streams():
    """保存视频流配置和状态"""
    try:
        streams_file.parent.mkdir(parents=True, exist_ok=True)
        with open(streams_file, 'w', encoding='utf-8') as f:
            json.dump(streams_config, f, ensure_ascii=False, indent=2)
        with open(streams_status_file, 'w', encoding='utf-8') as f:
            json.dump(streams_status, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存视频流配置失败: {e}")


load_violations()
load_streams()


# ============================================================
# 视频流管理器
# ============================================================

from core import MultiStreamManager


class SimpleConfigManager:
    """简化配置管理器"""
    def __init__(self):
        self.sites = {}
        self.models = {}
        self.global_config = type('obj', (object,), {'web': {'enabled': False}})()


class SimpleDetectorEngine:
    """简化检测器引擎"""
    def __init__(self):
        self.model_configs = {}


config_manager = SimpleConfigManager()
detector_engine = SimpleDetectorEngine()
stream_manager = MultiStreamManager(
    config_manager=config_manager,
    detector_engine=detector_engine,
    output_base_dir=str(PROJECT_ROOT / "storage")
)


# ============================================================
# 事件处理
# ============================================================

async def on_event(event: Dict):
    """处理违规事件 - 包括保存记录和WebSocket广播"""
    if event.get('type') == 'violation':
        data = event.get('data', {})
        violation_types = data.get('violation_types', [])
        if isinstance(violation_types, list):
            violation_type = ','.join(violation_types)
        else:
            violation_type = str(violation_types)
        
        # 生成记录ID和时间戳
        record_id = f"vio_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{data.get('camera_id', 'unknown')}"
        timestamp = datetime.now().isoformat()
        
        # 保存到内存（兼容旧代码）
        record = ViolationRecord(
            id=record_id,
            timestamp=timestamp,
            camera_id=data.get('camera_id', 'unknown'),
            camera_name=data.get('camera_id', 'unknown'),
            violation_type=violation_type,
            severity='medium',
            description=f"检测到违规: {violation_type}"
        )
        violations.append(record)
        save_violations()
        
        # 保存到数据库
        db_record = DBViolationRecord(
            id=record_id,
            timestamp=timestamp,
            stream_id=data.get('camera_id', 'unknown'),
            stream_name=data.get('camera_id', 'unknown'),
            violation_type=violation_type,
            confidence=data.get('confidence', 0.0),
            image_path=data.get('image_path'),
            location=data.get('location', '')
        )
        db.add_violation(db_record)
        
        logger.info(f"新增违规记录: {record_id}")
        
        # 通过 WebSocket 广播违规事件给所有前端客户端
        await ws_manager.broadcast({
            'type': 'violation',
            'data': {
                'id': record_id,
                'timestamp': timestamp,
                'camera_id': data.get('camera_id', 'unknown'),
                'camera_name': data.get('camera_id', 'unknown'),
                'violation_type': violation_type,
                'severity': 'medium',
                'description': f"检测到违规: {violation_type}",
                'confidence': data.get('confidence', 0.0)
            }
        })
    
    elif event.get('type') == 'status':
        # 广播状态更新
        await ws_manager.broadcast({
            'type': 'status',
            'data': event.get('data', {})
        })


stream_manager.add_event_callback(on_event)


# ============================================================
# 检测器注册
# ============================================================

try:
    from detectors.ppe_detector import PPEDetector
    from detectors.vehicle_detector import VehicleDetector
    from detectors.wall_defect_detector import WallDefectDetector
    from detectors.wall_defect_detector_v2 import WallDefectDetectorV2
    from detectors.vehicle_wash_adapter import VehicleWashDetectorAdapter
    
    detector_engine.model_configs = {
        'ppe_detector': PPEDetector,
        'vehicle_detector': VehicleDetector,
        'wall_detector': WallDefectDetector,
        'wall_detector_v2': WallDefectDetectorV2,
        'vehicle_wash_detector': VehicleWashDetectorAdapter,
    }
    logger.info(f"注册了 {len(detector_engine.model_configs)} 个检测器")
except Exception as e:
    logger.error(f"检测器注册失败: {e}")


# ============================================================
# API 端点
# ============================================================

@app.get("/")
async def root():
    """返回前端页面"""
    return FileResponse(PROJECT_ROOT / "web_frontend" / "index.html")


@app.get("/api/health")
async def health():
    """健康检查"""
    return {"status": "ok"}


@app.get("/api/detectors")
async def get_detectors():
    """获取检测器列表"""
    return [{"id": k, "name": k} for k in detector_engine.model_configs.keys()]


@app.get("/api/streams")
async def get_streams():
    """获取视频流列表"""
    result = []
    for sid, cfg in streams_config.items():
        # 检查处理器是否实际在运行
        actual_status = 'stopped'
        if sid in stream_manager.processors:
            processor = stream_manager.processors[sid]
            if hasattr(processor, 'running') and processor.running:
                actual_status = 'running'
        
        result.append({
            "id": sid,
            "name": cfg.get('name', sid),
            "url": cfg.get('url', ''),
            "detector_type": cfg.get('detector_type', 'ppe_detector'),
            "enabled": cfg.get('enabled', True),
            "status": actual_status
        })
    return result


@app.post("/api/streams")
async def add_stream(stream: dict):
    """添加视频流"""
    sid = stream.get('id', f"stream_{len(streams_config)}")
    streams_config[sid] = {
        'name': stream.get('name', sid),
        'url': stream.get('url', ''),
        'detector_type': stream.get('detector_type', 'ppe_detector'),
        'enabled': True
    }
    streams_status[sid] = 'stopped'
    save_streams()
    return {"success": True, "id": sid}


@app.put("/api/streams/{stream_id}")
async def update_stream(stream_id: str, stream: dict):
    """更新视频流"""
    if stream_id in streams_config:
        streams_config[stream_id].update(stream)
        save_streams()
    return {"success": True}


@app.delete("/api/streams/{stream_id}")
async def delete_stream(stream_id: str):
    """删除视频流"""
    if stream_id in streams_config:
        del streams_config[stream_id]
        del streams_status[stream_id]
        save_streams()
    return {"success": True}


@app.post("/api/streams/{stream_id}/start")
async def start_stream(stream_id: str):
    """启动视频流"""
    if stream_id not in streams_config:
        return {"success": False, "error": "视频流不存在"}
    
    cfg = streams_config[stream_id]
    streams_status[stream_id] = 'running'
    
    from core.stream_processor import StreamConfig, VideoStreamProcessor
    
    stream_config = StreamConfig(
        camera_id=stream_id,
        name=cfg.get('name', stream_id),
        url=cfg.get('url', ''),
        buffer_size=1,
        reconnect_interval=3,
        max_reconnects=100,
        frame_skip=10
    )
    
    detector_class = detector_engine.model_configs.get(cfg.get('detector_type', 'ppe_detector'))
    detector = None
    if detector_class:
        # 构建完整的检测器配置
        detector_config = {
            "conf_threshold": cfg.get('conf_threshold', 0.45),
            "device": cfg.get('device', 'auto'),
            "model_path": cfg.get('model_path', 'yolov8n.pt'),
            "wash_zone": cfg.get('wash_zone', {'x1': 0.1, 'y1': 0.3, 'x2': 0.7, 'y2': 0.8}),
            "wash_stop_time": cfg.get('wash_stop_time', 180),
        }
        detector = detector_class(detector_config)
        
        # 验证车牌检测器是否正确加载
        if hasattr(detector, 'detector') and hasattr(detector.detector, 'plate_detector'):
            if detector.detector.plate_detector is None:
                logger.warning(f"[{stream_id}] 车牌检测器未成功加载，车牌识别功能将不可用")
            else:
                logger.info(f"[{stream_id}] 车牌检测器加载成功")
        else:
            logger.warning(f"[{stream_id}] 检测器结构异常，无法验证车牌检测器状态")
    
    output_dir = PROJECT_ROOT / "storage" / stream_id
    output_dir.mkdir(parents=True, exist_ok=True)
    
    processor = VideoStreamProcessor(
        config=stream_config,
        detector=detector,
        output_dir=output_dir,
        event_callback=on_event
    )
    
    stream_manager.processors[stream_id] = processor
    asyncio.create_task(processor.start())
    
    return {"success": True}


@app.post("/api/streams/{stream_id}/stop")
async def stop_stream(stream_id: str):
    """停止视频流"""
    if stream_id in stream_manager.processors:
        await stream_manager.processors[stream_id].stop()
        del stream_manager.processors[stream_id]
    streams_status[stream_id] = 'stopped'
    return {"success": True}


# 创建全局线程池用于截图操作（避免每次创建线程）
_snapshot_executor = None

def get_snapshot_executor():
    """获取或创建截图线程池"""
    global _snapshot_executor
    if _snapshot_executor is None:
        from concurrent.futures import ThreadPoolExecutor
        _snapshot_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="snapshot_")
    return _snapshot_executor

def _capture_snapshot(url: str, timeout: float = 3.0):
    """
    在独立线程中捕获截图，带超时控制
    
    Args:
        url: 视频流地址
        timeout: 超时时间（秒），默认3秒
        
    Returns:
        JPEG字节数据或None
    """
    import cv2
    import time
    
    cap = None
    try:
        cap = cv2.VideoCapture(url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        if not cap.isOpened():
            return None
        
        # 快速读取帧，最多等待timeout秒
        start_time = time.time()
        ret, frame = None, None
        
        while time.time() - start_time < timeout:
            ret, frame = cap.read()
            if ret and frame is not None:
                break
            # 短暂等待后重试
            time.sleep(0.05)
        
        if not ret or frame is None:
            return None
            
        # 调整分辨率
        frame = cv2.resize(frame, (960, 540))
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        return buffer.tobytes()
        
    except Exception as e:
        logger.warning(f"截图捕获异常: {e}")
        return None
    finally:
        if cap:
            cap.release()


@app.get("/api/streams/{stream_id}/snapshot")
async def get_snapshot(stream_id: str, force: bool = False):
    """
    获取视频流截图
    
    Args:
        stream_id: 视频流ID
        force: 是否强制尝试连接视频流（默认False，停止状态直接返回占位图）
    
    说明：
    - 运行中的视频流：从处理器缓存获取最新帧（带检测框）
    - 停止的视频流：直接返回占位图，不尝试连接视频流地址
    - 这样避免不必要的网络请求和错误日志
    """
    import cv2
    import numpy as np
    
    if stream_id not in streams_config:
        raise HTTPException(status_code=404, detail="视频流不存在")
    
    cfg = streams_config[stream_id]
    
    # 如果视频流未启用或已停止，直接返回占位图
    if not cfg.get('enabled', True) or streams_status.get(stream_id) == 'stopped':
        # 创建占位图
        img = np.zeros((540, 960, 3), dtype=np.uint8)
        img[:] = (30, 30, 30)
        name = cfg.get('name', stream_id)
        cv2.putText(img, f'{name}', (350, 250), 
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (150, 150, 150), 2)
        cv2.putText(img, 'Stream Stopped', (360, 300), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (100, 100, 100), 2)
        cv2.putText(img, 'Click play to start', (370, 350), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (80, 80, 80), 2)
        _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 60])
        return StreamingResponse(BytesIO(buffer.tobytes()), media_type="image/jpeg")
    
    # 如果处理器在运行，优先使用缓存的最新帧（无需额外连接）
    if stream_id in stream_manager.processors:
        processor = stream_manager.processors[stream_id]
        frame = processor.get_latest_frame()
        if frame is not None:
            try:
                frame = cv2.resize(frame, (960, 540))
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                return StreamingResponse(BytesIO(buffer.tobytes()), media_type="image/jpeg")
            except Exception as e:
                logger.warning(f"从缓存帧生成截图失败: {e}")
    
    # 只有在force=true时才尝试新建连接（用于手动刷新预览）
    if force:
        url = cfg.get('url', '')
        try:
            executor = get_snapshot_executor()
            loop = asyncio.get_event_loop()
            image_bytes = await asyncio.wait_for(
                loop.run_in_executor(executor, _capture_snapshot, url, 2.0),
                timeout=3.0
            )
            if image_bytes:
                return StreamingResponse(BytesIO(image_bytes), media_type="image/jpeg")
        except asyncio.TimeoutError:
            logger.debug(f"截图超时: {stream_id}")
        except Exception as e:
            logger.debug(f"截图异常: {e}")
    
    # 默认返回占位图
    img = np.zeros((540, 960, 3), dtype=np.uint8)
    img[:] = (30, 30, 30)
    name = cfg.get('name', stream_id)
    cv2.putText(img, f'{name}', (350, 250), 
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (150, 150, 150), 2)
    cv2.putText(img, 'Stream Unavailable', (320, 300), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (100, 100, 100), 2)
    cv2.putText(img, 'Click play to start', (350, 350), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (80, 80, 80), 2)
    _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 60])
    return StreamingResponse(BytesIO(buffer.tobytes()), media_type="image/jpeg")


def parse_violation_filename(filename: str) -> Optional[dict]:
    """
    从截图文件名解析违规信息
    文件名格式: violation_YYYYMMDD_HHMMSS_ID{id}_{violation_types}.jpg
    例如: violation_20260411_173047_ID1_no_helmet_no_vest_no_mask.jpg
    """
    try:
        # 移除扩展名
        name = filename.replace('.jpg', '')
        parts = name.split('_')
        
        if len(parts) < 5 or parts[0] != 'violation':
            return None
        
        # 解析日期和时间
        date_str = parts[1]  # YYYYMMDD
        time_str = parts[2]  # HHMMSS
        
        # 格式化时间戳
        year = date_str[:4]
        month = date_str[4:6]
        day = date_str[6:8]
        hour = time_str[:2]
        minute = time_str[2:4]
        second = time_str[4:6]
        
        timestamp = f"{year}-{month}-{day}T{hour}:{minute}:{second}"
        
        # 解析ID
        id_part = parts[3]  # ID{id}
        violation_id = id_part.replace('ID', '') if id_part.startswith('ID') else '0'
        
        # 解析违规类型（从第4个部分开始，到末尾）
        violation_types = []
        for i in range(4, len(parts)):
            if parts[i] in ['no', 'helmet', 'vest', 'mask', 'gloves', 'boots']:
                violation_types.append(parts[i])
        
        # 构建违规类型描述
        if 'helmet' in violation_types and 'no' in violation_types:
            type_desc = "未佩戴安全帽"
        elif 'vest' in violation_types and 'no' in violation_types:
            type_desc = "未穿反光背心"
        elif 'mask' in violation_types and 'no' in violation_types:
            type_desc = "未佩戴口罩"
        else:
            type_desc = "违规检测"
        
        # 严重程度判断
        violation_count = violation_types.count('no')
        if violation_count >= 3:
            severity = "critical"
        elif violation_count == 2:
            severity = "high"
        elif violation_count == 1:
            severity = "medium"
        else:
            severity = "low"
        
        return {
            "id": violation_id,
            "timestamp": timestamp,
            "violation_types": violation_types,
            "type_desc": type_desc,
            "severity": severity,
            "filename": filename
        }
    except Exception as e:
        logger.warning(f"解析文件名失败 {filename}: {e}")
        return None


def get_violations_from_files(camera_id: Optional[str] = None) -> List[dict]:
    """从截图文件读取违规记录"""
    results = []
    storage_dir = PROJECT_ROOT / "storage"
    
    # 如果指定了camera_id，只读取该目录
    if camera_id:
        camera_dirs = [storage_dir / camera_id]
    else:
        # 读取所有摄像头目录
        camera_dirs = [d for d in storage_dir.iterdir() if d.is_dir() and d.name not in ['__pycache__']]
    
    for camera_dir in camera_dirs:
        if not camera_dir.exists():
            continue
        
        cam_id = camera_dir.name
        
        # 获取所有截图文件
        image_files = sorted(camera_dir.glob("violation_*.jpg"), reverse=True)
        
        for img_file in image_files:
            parsed = parse_violation_filename(img_file.name)
            if parsed:
                # 使用完整的文件名（不含扩展名）作为唯一ID
                file_stem = img_file.stem  # 例如: violation_20260415_150639_ID5_no_helmet_no_vest_no_mask
                results.append({
                    "id": file_stem,  # 使用完整文件名作为ID，确保唯一性
                    "timestamp": parsed["timestamp"],
                    "camera_id": cam_id,
                    "camera_name": cam_id,
                    "violation_type": parsed["type_desc"],
                    "severity": parsed["severity"],
                    "description": f"检测到违规: {parsed['type_desc']}",
                    "image_path": str(img_file.relative_to(PROJECT_ROOT)),
                    "filename": img_file.name
                })
    
    # 按时间戳降序排序
    results.sort(key=lambda x: x["timestamp"], reverse=True)
    return results


@app.get("/api/violations")
async def get_violations(camera_id: Optional[str] = None, limit: int = 100, page: int = 1):
    """获取违规记录（直接从截图文件读取）"""
    # 从文件读取所有违规记录
    all_violations = get_violations_from_files(camera_id)
    
    # 如果指定了camera_id，过滤
    if camera_id:
        all_violations = [v for v in all_violations if v["camera_id"] == camera_id]
    
    total = len(all_violations)
    
    # 如果limit很大(>1000)，返回所有数据不分页（用于数据分析）
    if limit > 1000:
        return {
            "items": all_violations,
            "total": total,
            "page": 1,
            "page_size": total
        }
    
    # 分页
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    result = all_violations[start_idx:end_idx]
    
    return {
        "items": result,
        "total": total,
        "page": page,
        "page_size": limit
    }


@app.get("/api/violations/stats")
async def get_violation_stats():
    """获取违规统计（从截图文件统计）"""
    all_violations = get_violations_from_files()
    
    by_type = {}
    by_camera = {}
    by_severity = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    
    for v in all_violations:
        vtype = v["violation_type"]
        by_type[vtype] = by_type.get(vtype, 0) + 1
        by_camera[v["camera_id"]] = by_camera.get(v["camera_id"], 0) + 1
        by_severity[v["severity"]] = by_severity.get(v["severity"], 0) + 1
    
    return {
        "total": len(all_violations), 
        "by_type": by_type, 
        "by_camera": by_camera, 
        "by_severity": by_severity
    }


@app.get("/api/violations/{violation_id}/image")
async def get_violation_image(violation_id: str, camera_id: Optional[str] = None):
    """获取违规截图 - 通过完整文件名定位文件
    
    violation_id: 完整的文件名（不含扩展名），例如: violation_20260415_150639_ID5_no_helmet_no_vest_no_mask
    """
    storage_dir = PROJECT_ROOT / "storage"
    
    # 解码URL编码的violation_id
    from urllib.parse import unquote
    violation_id = unquote(violation_id)
    
    # 如果提供了camera_id，直接在该目录查找
    if camera_id:
        camera_dirs = [storage_dir / camera_id]
    else:
        # 否则搜索所有摄像头目录
        camera_dirs = [d for d in storage_dir.iterdir() if d.is_dir() and d.name not in ['__pycache__']]
    
    # 在所有目录中查找匹配的文件
    for camera_dir in camera_dirs:
        if not camera_dir.exists():
            continue
        
        # 直接使用完整的文件名匹配
        img_file = camera_dir / f"{violation_id}.jpg"
        if img_file.exists():
            return FileResponse(str(img_file), media_type="image/jpeg")
        
        # 如果上面的精确匹配没找到，尝试从ID中提取文件名模式
        # 支持旧的ID格式（纯数字）作为兼容
        if violation_id.startswith("violation_"):
            # 已经是完整的文件名格式，但在其他目录
            for img_file in camera_dir.glob(f"{violation_id}.jpg"):
                return FileResponse(str(img_file), media_type="image/jpeg")
    
    # 如果没找到，返回404
    logger.warning(f"截图文件不存在: {violation_id}")
    raise HTTPException(status_code=404, detail="截图文件不存在")


# ============================================================
# MJPEG 实时视频流端点
# ============================================================

@app.get("/api/streams/{stream_id}/live")
async def mjpeg_stream(stream_id: str):
    """
    MJPEG 实时视频流端点
    从stream_processor获取已处理的帧（带检测框），避免重复检测和模型加载
    """
    import cv2
    import numpy as np
    
    if stream_id not in streams_config:
        raise HTTPException(status_code=404, detail="视频流不存在")
    
    cfg = streams_config[stream_id]
    
    async def generate_frames():
        """从processor获取已处理的帧"""
        frame_count = 0
        last_frame = None
        empty_count = 0
        max_empty = 50  # 最多等待5秒
        
        try:
            while True:
                frame = None
                
                # 从processor获取最新帧
                if stream_id in stream_manager.processors:
                    processor = stream_manager.processors[stream_id]
                    frame = processor.get_latest_frame()
                
                if frame is not None:
                    empty_count = 0
                    last_frame = frame.copy()
                    
                    # 调整分辨率
                    if frame.shape[1] != 960 or frame.shape[0] != 540:
                        frame = cv2.resize(frame, (960, 540))
                    
                    # 添加状态信息
                    cv2.putText(frame, f"Stream: {cfg.get('name', stream_id)}", (10, 30), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    
                    # 获取processor状态
                    if stream_id in stream_manager.processors:
                        processor = stream_manager.processors[stream_id]
                        fps = processor.stats.fps if hasattr(processor, 'stats') else 0
                        fps_text = f"FPS: {fps:.1f}"
                        cv2.putText(frame, fps_text, (10, 60), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                else:
                    empty_count += 1
                    if empty_count > max_empty:
                        # 长时间没有帧，返回错误信息
                        frame = np.zeros((540, 960, 3), dtype=np.uint8)
                        frame[:] = (30, 30, 30)
                        cv2.putText(frame, 'Stream Not Running', (320, 270), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (100, 100, 100), 2)
                        cv2.putText(frame, 'Click play to start', (350, 320), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (80, 80, 80), 2)
                    elif last_frame is not None:
                        # 使用最后一帧
                        frame = last_frame.copy()
                        cv2.putText(frame, "Waiting for stream...", (350, 270), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (100, 100, 100), 2)
                    else:
                        # 等待中
                        await asyncio.sleep(0.1)
                        continue
                
                # 编码为 JPEG
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                frame_bytes = buffer.tobytes()
                
                # 发送 MJPEG 帧
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n'
                       b'\r\n' + frame_bytes + b'\r\n')
                
                frame_count += 1
                # 控制帧率 (~15fps)
                await asyncio.sleep(0.066)
                
        except Exception as e:
            logger.error(f"MJPEG 流错误: {e}")
    
    return StreamingResponse(
        generate_frames(),
        media_type='multipart/x-mixed-replace; boundary=frame',
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端点 - 支持实时事件推送和心跳检测"""
    # 必须先接受连接
    await websocket.accept()
    await ws_manager.connect(websocket)
    
    try:
        # 发送连接成功消息
        await websocket.send_json({
            "type": "connected",
            "data": {"message": "Connected to Stream V3"}
        })
        
        # 保持连接，监听客户端消息（心跳等）
        while True:
            try:
                # 接收客户端消息，带超时
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0
                )
                
                # 处理心跳
                if data == "ping":
                    await websocket.send_json({"type": "pong", "data": {}})
                elif data == "get_stats":
                    # 发送当前统计信息
                    await websocket.send_json({
                        "type": "stats",
                        "data": {
                            "total_streams": len(streams_config),
                            "running_streams": sum(1 for s in streams_status.values() if s == 'running'),
                            "total_violations": len(violations)
                        }
                    })
                    
            except asyncio.TimeoutError:
                # 发送心跳保持连接
                try:
                    await websocket.send_json({"type": "ping", "data": {}})
                except Exception:
                    break
            except Exception:
                # 连接已断开
                break
                    
    except Exception as e:
        logger.debug(f"WebSocket 连接异常: {e}")
    finally:
        try:
            await ws_manager.disconnect(websocket)
        except:
            pass


# ============================================================
# 新增 API 端点 - 日报系统
# ============================================================

@app.get("/api/reports/daily/{date}")
async def get_daily_report(date: str):
    """获取指定日期的日报"""
    report = report_generator.get_report_summary(date)
    if not report:
        # 尝试生成日报
        db_report = report_generator.generate_daily_report(date)
        if db_report:
            report = report_generator.get_report_summary(date)
    
    if report:
        return report
    raise HTTPException(status_code=404, detail="日报不存在")


@app.post("/api/reports/generate")
async def generate_report(data: dict):
    """生成指定日期的日报"""
    date = data.get('date')
    if not date:
        raise HTTPException(status_code=400, detail="缺少日期参数")
    
    report = report_generator.generate_daily_report(date)
    if report:
        return report_generator.get_report_summary(date)
    raise HTTPException(status_code=500, detail="生成日报失败")


@app.get("/api/reports/history")
async def get_report_history(page: int = 1, page_size: int = 10):
    """获取历史日报列表"""
    offset = (page - 1) * page_size
    reports, total = db.get_report_history(limit=page_size, offset=offset)
    
    items = []
    for r in reports:
        try:
            items.append({
                "date": r.date,
                "total_violations": r.total_violations,
                "total_streams": r.total_streams,
                "active_streams": r.active_streams,
                "created_at": r.created_at
            })
        except:
            pass
    
    return {"items": items, "total": total}


# ============================================================
# 新增 API 端点 - 违规记录（数据库版本）
# ============================================================

@app.get("/api/violations/new")
async def get_violations_new(
    stream_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    violation_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20
):
    """从数据库获取违规记录（支持分页和筛选）"""
    offset = (page - 1) * page_size
    
    violations_list, total = db.get_violations(
        stream_id=stream_id,
        start_date=start_date,
        end_date=end_date,
        violation_type=violation_type,
        limit=page_size,
        offset=offset
    )
    
    items = [{
        "id": v.id,
        "timestamp": v.timestamp,
        "stream_id": v.stream_id,
        "stream_name": v.stream_name,
        "type": v.violation_type,
        "confidence": v.confidence,
        "image_url": f"/api/violations/{v.id}/image" if v.image_path else None,
        "location": v.location
    } for v in violations_list]
    
    return {"items": items, "total": total}


@app.get("/api/violations/types")
async def get_violation_types():
    """获取所有违规类型"""
    types = db.get_violation_types()
    return types


@app.get("/api/violations/stats/new")
async def get_violation_stats_new(days: int = 7, stream_id: Optional[str] = None):
    """获取违规统计（数据库版本）"""
    return db.get_violation_stats(days=days, stream_id=stream_id)


# ============================================================
# 新增 API 端点 - 系统状态
# ============================================================

import psutil

@app.get("/api/system/status")
async def get_system_status():
    """获取系统状态"""
    try:
        cpu_usage = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        active_streams = sum(1 for s in streams_status.values() if s == 'running')
        total_violations = len(violations)
        
        # 记录到数据库
        db.add_system_status(
            cpu_usage=cpu_usage,
            memory_usage=memory.percent,
            disk_usage=disk.percent,
            active_streams=active_streams,
            total_violations=total_violations
        )
        
        return {
            "cpu_usage": cpu_usage,
            "memory_usage": memory.percent,
            "disk_usage": disk.percent,
            "active_streams": active_streams,
            "total_violations": total_violations,
            "uptime": 0  # TODO: 实现运行时间统计
        }
    except Exception as e:
        logger.error(f"获取系统状态失败: {e}")
        return {
            "cpu_usage": 0,
            "memory_usage": 0,
            "disk_usage": 0,
            "active_streams": 0,
            "total_violations": len(violations),
            "uptime": 0
        }


@app.get("/api/system/config")
async def get_system_config():
    """获取系统配置"""
    return {
        "detection": {
            "model_path": "models/ppe_best.pt",
            "confidence_threshold": 0.45,
            "iou_threshold": 0.45,
            "device": "cuda" if hasattr(detector_engine, 'model_configs') else "cpu",
            "classes": ["person", "helmet", "vest", "gloves", "boots"]
        },
        "notification": {
            "enabled": True,
            "webhooks": [],
            "emails": [],
            "min_confidence": 0.5,
            "cooldown_minutes": 5
        }
    }


# ============================================================
# 主入口
# ============================================================

if __name__ == "__main__":
    logger.info("=" * 70)
    logger.info("Stream V3 后端服务启动")
    logger.info("=" * 70)
    uvicorn.run(app, host="0.0.0.0", port=8000)
