"""
视频流推流模块
使用 ffmpeg 将 OpenCV 帧推流到 RTMP/RTSP 服务器
支持多协议输出：RTMP、RTSP、SRT
"""

import cv2
import numpy as np
import subprocess
import threading
import queue
import time
import shlex
import os


def log(msg):
    """简单日志函数"""
    timestamp = time.strftime('%H:%M:%S')
    print(f"[{timestamp}] [StreamPublisher] {msg}", flush=True)


class FFmpegStreamPublisher:
    """
    使用 ffmpeg 将 OpenCV 帧推流到 RTMP/RTSP 服务器

    使用方式:
        publisher = FFmpegStreamPublisher("rtmp://localhost:1935/live/stream")
        publisher.start()

        # 在处理循环中
        publisher.write_frame(frame)

        publisher.stop()
    """

    def __init__(self,
                 output_url: str,
                 width: int = 1280,
                 height: int = 720,
                 fps: int = 25,
                 bitrate: str = "3000k",
                 preset: str = "ultrafast",
                 gop_size: int = None,
                 queue_size: int = 30,
                 drop_oldest_on_full: bool = True):
        """
        Args:
            output_url: 推流地址
                - RTMP: rtmp://host:port/app/stream
                - RTSP: rtsp://host:port/path
                - SRT:  srt://host:port?mode=caller
            width: 输出宽度
            height: 输出高度
            fps: 输出帧率
            bitrate: 视频码率 (如 "3000k", "5M")
            preset: x264 编码预设 (ultrafast/superfast/veryfast/faster/fast/medium)
            gop_size: GOP 大小，默认 fps*2
        """
        self.output_url = output_url
        self.width = width
        self.height = height
        self.fps = fps
        self.bitrate = bitrate
        self.preset = preset
        self.gop_size = gop_size or (fps * 2)
        self.queue_size = max(1, int(queue_size))
        self.drop_oldest_on_full = drop_oldest_on_full

        self.frame_queue = queue.Queue(maxsize=self.queue_size)
        self.stop_event = threading.Event()
        self.ffmpeg_process = None
        self.publish_thread = None
        self.stderr_thread = None
        self.stats = {
            'frames_written': 0,
            'frames_dropped': 0,
            'frames_reconnected': 0,
            'start_time': None,
        }
        # 自动重连配置
        self.auto_reconnect = True
        self.max_reconnect_attempts = 5
        self.reconnect_interval = 3  # 秒

    def _build_command(self) -> list:
        """构建 ffmpeg 命令"""
        is_rtmp = self.output_url.startswith('rtmp://')
        is_rtsp = self.output_url.startswith('rtsp://')
        is_srt = self.output_url.startswith('srt://')

        # 基础输入参数
        command = [
            'ffmpeg',
            '-y',                           # 覆盖输出文件
            '-loglevel', 'warning',         # 只显示警告和错误
            '-nostats',                      # 不显示进度统计
            '-f', 'rawvideo',               # 输入格式
            '-vcodec', 'rawvideo',          # 输入编码
            '-pix_fmt', 'bgr24',            # OpenCV 默认格式
            '-s', f'{self.width}x{self.height}',
            '-r', str(self.fps),
            '-thread_queue_size', '512',    # 输入队列大小
            '-i', '-',                      # 从 stdin 读取
        ]

        # 视频编码参数
        command.extend([
            '-c:v', 'libx264',
            '-pix_fmt', 'yuv420p',
            '-preset', self.preset,
            '-tune', 'zerolatency',
            '-b:v', self.bitrate,
            '-maxrate', self.bitrate,
            '-bufsize', '2000k',
            '-g', str(self.gop_size),
            '-keyint_min', str(self.fps),
            '-sc_threshold', '0',
        ])

        # 输出格式
        if is_rtmp:
            command.extend(['-f', 'flv'])
        elif is_rtsp:
            command.extend([
                '-f', 'rtsp',
                '-rtsp_transport', 'tcp',
            ])
        elif is_srt:
            command.extend(['-f', 'mpegts'])

        command.append(self.output_url)
        return command

    def start(self):
        """启动推流进程"""
        if self.ffmpeg_process is not None:
            log("Publisher already started")
            return
        self.stop_event.clear()

        command = self._build_command()
        log(f"Starting ffmpeg: {' '.join(command)}")

        # Windows 下需要特殊处理
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        try:
            self.ffmpeg_process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                startupinfo=startupinfo,
                bufsize=10**8,
            )
        except FileNotFoundError:
            log("ERROR: ffmpeg not found! Please install ffmpeg and add to PATH")
            raise

        # 启动错误监控线程
        self.stderr_thread = threading.Thread(
            target=self._monitor_stderr,
            args=(self.ffmpeg_process,),
            daemon=True,
            name="FFmpegStderrMonitor"
        )
        self.stderr_thread.start()

        self.stats['start_time'] = time.time()
        self.publish_thread = threading.Thread(target=self._publish_loop, daemon=True)
        self.publish_thread.start()

        log(f"Stream publisher started: {self.output_url}")
        log(f"Output resolution: {self.width}x{self.height} @ {self.fps}fps, bitrate={self.bitrate}")

    def _monitor_stderr(self, process):
        """监控 ffmpeg stderr，只打印真正的错误"""
        while not self.stop_event.is_set() and process:
            try:
                line = process.stderr.readline()
                if not line:
                    break
                line = line.decode('utf-8', errors='ignore').strip()
                
                # 跳过进度信息（包含 frame= fps= size= 等）
                if any(x in line for x in ['frame=', 'fps=', 'size=', 'time=', 'bitrate=', 'speed=']):
                    continue
                
                # 只保留真正的错误/警告
                if any(x in line.lower() for x in ['error', 'warning', 'failed', 'cannot', 'unable', 'broken', 'connection']):
                    log(f"[ffmpeg] {line}")
            except Exception:
                break

    def _close_pipe(self, pipe):
        try:
            if pipe:
                pipe.close()
        except Exception:
            pass

    def _drain_frame_queue(self):
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break

    def _cleanup_process(self, wait_timeout: float = 2.0):
        process = self.ffmpeg_process
        if not process:
            return

        self._close_pipe(process.stdin)
        self._close_pipe(process.stdout)
        self._close_pipe(process.stderr)

        try:
            process.wait(timeout=wait_timeout)
        except subprocess.TimeoutExpired:
            try:
                process.terminate()
                process.wait(timeout=2.0)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

        if self.stderr_thread and self.stderr_thread.is_alive():
            self.stderr_thread.join(timeout=1.0)
        self.stderr_thread = None
        self.ffmpeg_process = None

    def _restart_ffmpeg(self):
        """重启 ffmpeg 进程（用于断线重连）"""
        log("Restarting ffmpeg...")
        
        # 关闭旧进程
        if self.ffmpeg_process:
            try:
                self.ffmpeg_process.terminate()
            except Exception:
                pass
            self._cleanup_process(wait_timeout=2.0)
        
        # 清空队列（避免积压太久）
        self._drain_frame_queue()
        
        # 重新启动
        command = self._build_command()
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        try:
            self.ffmpeg_process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                startupinfo=startupinfo,
                bufsize=10**8,
            )
            self.stderr_thread = threading.Thread(
                target=self._monitor_stderr,
                args=(self.ffmpeg_process,),
                daemon=True,
                name="FFmpegStderrMonitor"
            )
            self.stderr_thread.start()
            log("FFmpeg restarted successfully")
            return True
        except Exception as e:
            log(f"Failed to restart ffmpeg: {e}")
            return False

    def _publish_loop(self):
        """推流主循环（带自动重连）"""
        log("Publish loop started")
        reconnect_attempts = 0

        while not self.stop_event.is_set():
            try:
                frame = self.frame_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            # 确保尺寸正确
            if frame.shape[1] != self.width or frame.shape[0] != self.height:
                frame = cv2.resize(frame, (self.width, self.height),
                                   interpolation=cv2.INTER_LINEAR)

            try:
                if self.ffmpeg_process is None or self.ffmpeg_process.poll() is not None:
                    # ffmpeg 已退出，尝试重启
                    if self.auto_reconnect and reconnect_attempts < self.max_reconnect_attempts:
                        reconnect_attempts += 1
                        log(f"FFmpeg disconnected, reconnecting ({reconnect_attempts}/{self.max_reconnect_attempts})...")
                        time.sleep(self.reconnect_interval)
                        if self._restart_ffmpeg():
                            reconnect_attempts = 0
                            self.stats['frames_reconnected'] += 1
                        else:
                            log("Reconnect failed, continuing...")
                    else:
                        log("Max reconnect attempts reached or reconnect disabled")
                        break
                
                self.ffmpeg_process.stdin.write(frame.tobytes())
                self.ffmpeg_process.stdin.flush()
                self.stats['frames_written'] += 1
                
                # 重置重连计数（成功写入后重置）
                if reconnect_attempts > 0:
                    reconnect_attempts = 0
                    
            except BrokenPipeError:
                log("FFmpeg pipe broken")
                if self.auto_reconnect and reconnect_attempts < self.max_reconnect_attempts:
                    reconnect_attempts += 1
                    time.sleep(self.reconnect_interval)
                    if self._restart_ffmpeg():
                        reconnect_attempts = 0
                        self.stats['frames_reconnected'] += 1
                else:
                    break
            except Exception as e:
                log(f"Write error: {e}")
                break

        log("Publish loop stopped")

    def write_frame(self, frame: np.ndarray):
        """
        写入一帧到推流队列（非阻塞）

        Args:
            frame: BGR 格式的 numpy 数组 (H, W, 3)
        """
        if self.stop_event.is_set() or self.ffmpeg_process is None:
            return

        try:
            self.frame_queue.put(frame, block=False)
        except queue.Full:
            self.stats['frames_dropped'] += 1
            if not self.drop_oldest_on_full:
                return
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                return
            try:
                self.frame_queue.put_nowait(frame)
            except queue.Full:
                pass

    def get_stats(self) -> dict:
        """获取推流统计"""
        elapsed = time.time() - self.stats['start_time'] if self.stats['start_time'] else 0
        return {
            **self.stats,
            'fps': self.stats['frames_written'] / elapsed if elapsed > 0 else 0,
            'queue_size': self.frame_queue.qsize(),
            'is_running': self.ffmpeg_process is not None and self.ffmpeg_process.poll() is None,
        }

    def stop(self):
        """停止推流"""
        log("Stopping stream publisher...")
        self.stop_event.set()

        if self.publish_thread:
            self.publish_thread.join(timeout=3.0)
            self.publish_thread = None

        if self.ffmpeg_process:
            self._cleanup_process(wait_timeout=5.0)
        self._drain_frame_queue()
        log("Stream publisher stopped")


class StreamServer:
    """
    简易流媒体服务器封装
    支持启动 Node Media Server 或 MediaMTX
    """

    @staticmethod
    def start_mediamtx(path: str = None):
        """
        启动 MediaMTX 服务器

        Args:
            path: mediamtx.exe 的路径，默认在当前目录查找
        """
        if path is None:
            path = "mediamtx.exe"

        if not os.path.exists(path):
            log(f"MediaMTX not found at {path}")
            log("Please download from: https://github.com/bluenviron/mediamtx/releases")
            return None

        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        try:
            proc = subprocess.Popen(
                [path],
                startupinfo=startupinfo,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            log(f"MediaMTX started (PID: {proc.pid})")
            log("RTSP: rtsp://localhost:8554/live/stream")
            log("RTMP: rtmp://localhost:1935/live/stream")
            return proc
        except Exception as e:
            log(f"Failed to start MediaMTX: {e}")
            return None

    @staticmethod
    def create_nms_config(output_path: str = "nms_config.js"):
        """生成 Node Media Server 配置文件"""
        config = '''const NodeMediaServer = require('node-media-server');

const config = {
  rtmp: {
    port: 1935,
    chunk_size: 60000,
    gop_cache: true,
    ping: 30,
    ping_timeout: 60
  },
  http: {
    port: 8000,
    allow_origin: '*',
    mediaroot: './media'
  },
  trans: {
    ffmpeg: 'ffmpeg',
    tasks: [
      {
        app: 'live',
        hls: true,
        hlsFlags: '[hls_time=2:hls_list_size=3:hls_flags=delete_segments]',
        dash: true,
        dashFlags: '[f=dash:window_size=3:extra_window_size=5]'
      }
    ]
  }
};

var nms = new NodeMediaServer(config);
nms.run();
console.log('Node Media Server started');
console.log('RTMP: rtmp://121.199.7.83:1935/live/stream');
console.log('HLS:  http://121.199.7.83:8000/live/stream/index.m3u8');
console.log('DASH: http://121.199.7.83:8000/live/stream/index.mpd');
'''
        with open(output_path, 'w') as f:
            f.write(config)
        log(f"Node Media Server config written to {output_path}")
        log("Run: npm install node-media-server && node nms_config.js")
