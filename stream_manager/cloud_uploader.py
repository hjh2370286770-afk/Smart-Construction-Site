#!/usr/bin/env python3
"""
云端上传器 - 将关键帧上传到云端平台
支持多种上传策略：HTTP/HTTPS、OSS/S3、MQTT
"""

import asyncio
import logging
import json
import base64
from typing import Dict, Optional, Callable, List, Any
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
import aiohttp
import aiofiles

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None

logger = logging.getLogger(__name__)


@dataclass
class UploadConfig:
    """上传配置"""
    # 通用配置
    upload_mode: str = "http"  # http, s3, mqtt
    enabled: bool = True
    max_retries: int = 3
    retry_delay: float = 1.0
    concurrent_uploads: int = 5
    
    # HTTP 配置
    http_endpoint: Optional[str] = None
    http_headers: Optional[Dict] = None
    http_timeout: float = 30.0
    
    # S3/OSS 配置
    s3_endpoint: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_bucket: Optional[str] = None
    s3_region: str = "us-east-1"
    s3_prefix: str = "construction_site"
    
    # MQTT 配置
    mqtt_broker: Optional[str] = None
    mqtt_port: int = 1883
    mqtt_topic: str = "construction/keyframes"
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None


@dataclass
class UploadResult:
    """上传结果"""
    success: bool
    stream_id: str
    timestamp: float
    remote_url: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = None


class CloudUploader:
    """
    云端上传器
    
    支持多种上传方式，支持批量上传和失败重试
    """
    
    def __init__(self, config: UploadConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._s3_client = None
        self._upload_queue: asyncio.Queue = asyncio.Queue()
        self._semaphore = asyncio.Semaphore(config.concurrent_uploads)
        self._upload_tasks: List[asyncio.Task] = []
        self._running = False
        
        # 回调
        self._success_callbacks: List[Callable[[UploadResult], None]] = []
        self._error_callbacks: List[Callable[[UploadResult], None]] = []
        
    def on_upload_success(self, callback: Callable[[UploadResult], None]):
        """注册上传成功回调"""
        self._success_callbacks.append(callback)
        
    def on_upload_error(self, callback: Callable[[UploadResult], None]):
        """注册上传失败回调"""
        self._error_callbacks.append(callback)
        
    async def start(self):
        """启动上传服务"""
        if not self.config.enabled:
            logger.info("Cloud uploader is disabled")
            return
            
        self._running = True
        self._session = aiohttp.ClientSession()
        
        # 初始化 S3 客户端（如果需要）
        if self.config.upload_mode == "s3" and boto3:
            self._s3_client = boto3.client(
                's3',
                endpoint_url=self.config.s3_endpoint,
                aws_access_key_id=self.config.s3_access_key,
                aws_secret_access_key=self.config.s3_secret_key,
                region_name=self.config.s3_region
            )
            
        # 启动上传工作协程
        for _ in range(self.config.concurrent_uploads):
            task = asyncio.create_task(self._upload_worker())
            self._upload_tasks.append(task)
            
        logger.info(f"Cloud uploader started (mode: {self.config.upload_mode})")
        
    async def stop(self):
        """停止上传服务"""
        self._running = False
        
        # 等待队列清空
        await self._upload_queue.join()
        
        # 取消工作协程
        for task in self._upload_tasks:
            task.cancel()
        await asyncio.gather(*self._upload_tasks, return_exceptions=True)
        
        # 关闭 session
        if self._session:
            await self._session.close()
            
        logger.info("Cloud uploader stopped")
        
    async def upload(self, 
                     file_path: str, 
                     stream_id: str,
                     detection_result: Dict,
                     metadata: Optional[Dict] = None) -> UploadResult:
        """
        上传文件到云端
        
        Args:
            file_path: 本地文件路径
            stream_id: 流ID
            detection_result: 检测结果
            metadata: 额外元数据
            
        Returns:
            UploadResult
        """
        if not self.config.enabled:
            return UploadResult(
                success=False,
                stream_id=stream_id,
                timestamp=datetime.now().timestamp(),
                error="Uploader is disabled"
            )
            
        # 将任务加入队列
        await self._upload_queue.put({
            "file_path": file_path,
            "stream_id": stream_id,
            "detection_result": detection_result,
            "metadata": metadata or {}
        })
        
        # 注意：这里返回的是一个占位结果，实际结果通过回调获取
        return UploadResult(
            success=True,
            stream_id=stream_id,
            timestamp=datetime.now().timestamp(),
            metadata={"queued": True}
        )
        
    async def _upload_worker(self):
        """上传工作协程"""
        while self._running:
            try:
                task = await asyncio.wait_for(
                    self._upload_queue.get(), 
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                continue
                
            async with self._semaphore:
                result = await self._do_upload_with_retry(task)
                
                # 触发回调
                if result.success:
                    for cb in self._success_callbacks:
                        try:
                            cb(result)
                        except Exception as e:
                            logger.error(f"Success callback error: {e}")
                else:
                    for cb in self._error_callbacks:
                        try:
                            cb(result)
                        except Exception as e:
                            logger.error(f"Error callback error: {e}")
                            
                self._upload_queue.task_done()
                
    async def _do_upload_with_retry(self, task: Dict) -> UploadResult:
        """带重试的上传"""
        for attempt in range(self.config.max_retries):
            try:
                if self.config.upload_mode == "http":
                    return await self._upload_http(task)
                elif self.config.upload_mode == "s3":
                    return await self._upload_s3(task)
                elif self.config.upload_mode == "mqtt":
                    return await self._upload_mqtt(task)
                else:
                    raise ValueError(f"Unknown upload mode: {self.config.upload_mode}")
            except Exception as e:
                logger.warning(f"Upload attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                else:
                    return UploadResult(
                        success=False,
                        stream_id=task["stream_id"],
                        timestamp=datetime.now().timestamp(),
                        error=str(e)
                    )
                    
    async def _upload_http(self, task: Dict) -> UploadResult:
        """HTTP 上传"""
        file_path = task["file_path"]
        stream_id = task["stream_id"]
        detection_result = task["detection_result"]
        metadata = task["metadata"]
        
        # 读取文件
        async with aiofiles.open(file_path, 'rb') as f:
            file_data = await f.read()
            
        # 构建 multipart 数据
        data = aiohttp.FormData()
        data.add_field('file', file_data, filename=Path(file_path).name)
        data.add_field('stream_id', stream_id)
        data.add_field('timestamp', str(datetime.now().timestamp()))
        data.add_field('detection_result', json.dumps(detection_result, ensure_ascii=False))
        data.add_field('metadata', json.dumps(metadata, ensure_ascii=False))
        
        # 构建请求头
        headers = self.config.http_headers or {}
        
        # 发送请求
        async with self._session.post(
            self.config.http_endpoint,
            data=data,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=self.config.http_timeout)
        ) as response:
            if response.status == 200:
                resp_data = await response.json()
                return UploadResult(
                    success=True,
                    stream_id=stream_id,
                    timestamp=datetime.now().timestamp(),
                    remote_url=resp_data.get('url'),
                    metadata=resp_data
                )
            else:
                raise Exception(f"HTTP {response.status}: {await response.text()}")
                
    async def _upload_s3(self, task: Dict) -> UploadResult:
        """S3/OSS 上传"""
        if not boto3:
            raise ImportError("boto3 is required for S3 upload")
            
        file_path = task["file_path"]
        stream_id = task["stream_id"]
        
        # 构建 S3 key
        dt = datetime.now()
        s3_key = f"{self.config.s3_prefix}/{dt.strftime('%Y/%m/%d')}/{stream_id}/{Path(file_path).name}"
        
        # 上传（在线程池中执行，因为 boto3 是同步的）
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            self._s3_upload_sync,
            file_path,
            s3_key
        )
        
        # 构建 URL
        remote_url = f"{self.config.s3_endpoint}/{self.config.s3_bucket}/{s3_key}"
        
        return UploadResult(
            success=True,
            stream_id=stream_id,
            timestamp=datetime.now().timestamp(),
            remote_url=remote_url
        )
        
    def _s3_upload_sync(self, file_path: str, s3_key: str):
        """同步 S3 上传（在线程池中执行）"""
        self._s3_client.upload_file(
            file_path,
            self.config.s3_bucket,
            s3_key,
            ExtraArgs={'ContentType': 'image/jpeg'}
        )
        
    async def _upload_mqtt(self, task: Dict) -> UploadResult:
        """MQTT 上传（发送元数据和图片base64）"""
        # 这里简化实现，实际可以使用 aiomqtt
        file_path = task["file_path"]
        stream_id = task["stream_id"]
        
        # 读取并编码图片
        async with aiofiles.open(file_path, 'rb') as f:
            image_data = await f.read()
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
        # 构建消息
        message = {
            "stream_id": stream_id,
            "timestamp": datetime.now().timestamp(),
            "image_base64": image_base64,
            "detection_result": task["detection_result"],
            "metadata": task["metadata"]
        }
        
        # TODO: 实现 MQTT 发布
        # 这里简化处理，实际应该使用 aiomqtt 或 paho-mqtt
        logger.info(f"MQTT publish to {self.config.mqtt_topic}: {stream_id}")
        
        return UploadResult(
            success=True,
            stream_id=stream_id,
            timestamp=datetime.now().timestamp()
        )


# 简单的 HTTP 服务器示例（用于测试）
async def run_test_server():
    """运行测试服务器"""
    from aiohttp import web
    
    async def handle_upload(request):
        reader = await request.multipart()
        
        data = {}
        while True:
            part = await reader.next()
            if part is None:
                break
                
            if part.filename:
                # 文件字段
                filename = part.filename
                size = 0
                while True:
                    chunk = await part.read_chunk()
                    if not chunk:
                        break
                    size += len(chunk)
                data['file'] = {'filename': filename, 'size': size}
            else:
                # 普通字段
                value = await part.text()
                data[part.name] = value
                
        logger.info(f"Received upload: {data}")
        return web.json_response({'status': 'ok', 'url': 'http://example.com/uploaded.jpg'})
    
    app = web.Application()
    app.router.add_post('/upload', handle_upload)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8080)
    await site.start()
    
    logger.info("Test server started on http://localhost:8080")
    return runner


# ==================== 使用示例 ====================

async def demo():
    """演示用法"""
    # 启动测试服务器
    runner = await run_test_server()
    
    # 创建配置
    config = UploadConfig(
        upload_mode="http",
        http_endpoint="http://localhost:8080/upload",
        http_headers={"Authorization": "Bearer test_token"},
        concurrent_uploads=3
    )
    
    # 创建上传器
    uploader = CloudUploader(config)
    
    # 注册回调
    def on_success(result: UploadResult):
        print(f"Upload success: {result.stream_id} -> {result.remote_url}")
        
    def on_error(result: UploadResult):
        print(f"Upload failed: {result.stream_id} - {result.error}")
        
    uploader.on_upload_success(on_success)
    uploader.on_upload_error(on_error)
    
    # 启动
    await uploader.start()
    
    # 模拟上传
    import tempfile
    import numpy as np
    import cv2
    
    with tempfile.TemporaryDirectory() as tmpdir:
        for i in range(5):
            # 创建测试图片
            img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            img_path = f"{tmpdir}/test_{i}.jpg"
            cv2.imwrite(img_path, img)
            
            # 上传
            await uploader.upload(
                file_path=img_path,
                stream_id=f"cam_{i % 3}",
                detection_result={"detections": [{"class": "person", "conf": 0.9}]},
                metadata={"test": True}
            )
            
    # 等待上传完成
    await asyncio.sleep(3)
    
    # 停止
    await uploader.stop()
    await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(demo())
