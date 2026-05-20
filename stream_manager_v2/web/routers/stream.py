"""
视频流代理模块
提供 MJPEG 流和 HTTP-FLV 流转换
"""

import asyncio
import cv2
import logging
from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse
import io

from ..dependencies import get_stream_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stream", tags=["stream"])


@router.get("/{camera_id}/mjpeg")
async def mjpeg_stream(camera_id: str):
    """
    MJPEG 视频流
    
    直接返回 Motion JPEG 流，浏览器原生支持
    """
    stream_manager = get_stream_manager()
    
    if not stream_manager or camera_id not in stream_manager.processors:
        return Response(content="Camera not found", status_code=404)
    
    processor = stream_manager.processors[camera_id]
    
    async def generate_frames():
        """生成 MJPEG 帧"""
        cap = None
        try:
            # 打开视频流
            cap = cv2.VideoCapture(processor.config.url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            if not cap.isOpened():
                logger.error(f"无法打开视频流: {camera_id}")
                return
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    await asyncio.sleep(0.1)
                    continue
                
                # 调整分辨率
                if frame.shape[1] != 960 or frame.shape[0] != 540:
                    frame = cv2.resize(frame, (960, 540))
                
                # 绘制检测框（如果有）
                if processor.last_detection:
                    try:
                        frame = processor.detector.draw_results(frame, processor.last_detection)
                    except Exception as e:
                        logger.warning(f"绘制检测框失败: {e}")
                
                # 编码为 JPEG
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                frame_bytes = buffer.tobytes()
                
                # 发送 MJPEG 帧
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n'
                       b'Content-Length: ' + str(len(frame_bytes)).encode() + b'\r\n'
                       b'\r\n' + frame_bytes + b'\r\n')
                
                # 控制帧率 (~15fps)
                await asyncio.sleep(0.066)
                
        except Exception as e:
            logger.error(f"MJPEG 流错误: {e}")
        finally:
            if cap:
                cap.release()
    
    return StreamingResponse(
        generate_frames(),
        media_type='multipart/x-mixed-replace; boundary=frame',
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
    )


@router.get("/{camera_id}/snapshot")
async def camera_snapshot(camera_id: str):
    """
    获取当前帧截图
    """
    stream_manager = get_stream_manager()
    
    if not stream_manager or camera_id not in stream_manager.processors:
        return Response(content="Camera not found", status_code=404)
    
    processor = stream_manager.processors[camera_id]
    
    try:
        # 打开视频流获取一帧
        cap = cv2.VideoCapture(processor.config.url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        if not cap.isOpened():
            return Response(content="Cannot open stream", status_code=500)
        
        ret, frame = cap.read()
        cap.release()
        
        if not ret or frame is None:
            return Response(content="Cannot read frame", status_code=500)
        
        # 调整分辨率
        if frame.shape[1] != 960 or frame.shape[0] != 540:
            frame = cv2.resize(frame, (960, 540))
        
        # 绘制检测框（如果有）
        if processor.last_detection:
            try:
                frame = processor.detector.draw_results(frame, processor.last_detection)
            except Exception as e:
                logger.warning(f"绘制检测框失败: {e}")
        
        # 编码为 JPEG
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        
        return Response(
            content=buffer.tobytes(),
            media_type="image/jpeg",
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache'
            }
        )
        
    except Exception as e:
        logger.error(f"截图失败: {e}")
        return Response(content=f"Error: {str(e)}", status_code=500)
