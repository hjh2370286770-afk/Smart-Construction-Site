"""
车辆清洗检测 V3 - 实时模式（集成HTTP上报平台，免登录）
基于 test_full_video_spatial 副本.py 的已验证架构
新增：进出场逻辑 + 清洗判定 + HTTP上报平台(免登录) + 实时播放 + 不生成视频

上报平台配置：
  URL: http://192.168.1.69:8080/deviceRecord
  Method: POST
  Device ID格式: JUNHE_106_01 (公司名_项目名_设备ID)

车牌检测流程（与spatial版本一致）：
  1. 车辆检测（降低分辨率）
  2. 车牌识别（原始分辨率）+ 格式验证
  3. SpatialPlateDeduplicator 空间聚类+投票确认

进出场逻辑：
  - 进场：车牌经空间去重确认后
  - 出场：确认的车辆从画面左侧消失超过1分钟
  - 二次进场：出场后同车牌再次确认

清洗判定：
  - 确认的车辆在清洗区域停止超过3分钟
  - 离开区域或移动则重置计时
"""

import sys
import cv2
import time
import threading
import queue
import base64
import json
import io
import requests
import argparse
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor
import numpy as np

# 导入推流模块 (相对路径)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'streaming'))
from stream_publisher import FFmpegStreamPublisher


# ============================================================
# 命令行参数与配置文件解析
# ============================================================

def load_config(config_path: Optional[str] = None) -> dict:
    """加载 YAML/JSON 配置文件，未提供时返回空字典"""
    if not config_path:
        return {}
    p = Path(config_path)
    if not p.exists():
        print(f"[Config] 配置文件不存在: {config_path}")
        return {}
    try:
        if p.suffix.lower() in ('.yaml', '.yml'):
            import yaml
            with open(p, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        elif p.suffix.lower() == '.json':
            with open(p, 'r', encoding='utf-8') as f:
                return json.load(f) or {}
        else:
            print(f"[Config] 不支持的配置文件格式: {p.suffix}")
            return {}
    except Exception as e:
        print(f"[Config] 加载配置文件失败: {e}")
        return {}


def get_nested(config: dict, *keys, default=None):
    """安全读取嵌套配置"""
    cur = config
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur


parser = argparse.ArgumentParser(description='车辆清洗检测 V3 - 多项目配置版')
parser.add_argument('--config', '-c', type=str, default=None,
                    help='项目配置文件路径 (YAML/JSON)')
parser.add_argument('--device-id', type=str, default=None,
                    help='设备/项目标识，如 JUNHE_106_01')
parser.add_argument('--video', type=str, default=None,
                    help='视频源路径或 URL')
parser.add_argument('--stream-url', type=str, default=None,
                    help='推流输出地址')
parser.add_argument('--report-pid', type=int, default=None,
                    help='上报平台 pid')
parser.add_argument('--exit-direction', type=str, default=None,
                    choices=['left', 'right', 'bottom'],
                    help='车辆出场方向: left、right 或 bottom')
parser.add_argument('--exit-leading-edge-threshold', type=float, default=None,
                    help='检测框前缘越线阈值（0~1），默认 0.80')
parser.add_argument('--min-dwell-time', type=int, default=None,
                    help='车辆进场后最短在场时间（秒），默认 5')
parser.add_argument('--no-display', action='store_true',
                    help='不显示 OpenCV 窗口（多实例同时运行时建议开启）')
args = parser.parse_args()

file_config = load_config(args.config)


def cfg(*keys, default=None):
    """优先级：命令行参数 > 配置文件 > 默认值"""
    # 1. 命令行参数（平铺到 args 的键）
    if len(keys) == 1:
        arg_val = getattr(args, keys[0].replace('-', '_'), None)
        if arg_val is not None:
            return arg_val
    # 2. 配置文件
    val = get_nested(file_config, *keys, default=None)
    if val is not None:
        return val
    # 3. 默认值
    return default

# ============================================================
# 上报平台配置（可通过命令行或配置文件覆盖）
# ============================================================
# ============ 修改这里 ============
PROJECT_NAME = cfg('project_name', default='JUNHE_106')
DEVICE_ID = cfg('device_id', default='JUNHE_106_01')  # 公司名_项目名_设备ID
REPORT_URL = cfg('report_url', default='http://47.94.205.19:8080/api/addRecord')
ENABLE_REPORT = cfg('enable_report', default=True)  # 是否启用上报
OSS_UPLOAD_URL = cfg('oss_upload_url', default='http://47.94.205.19:9981/api/upload')
REPORT_PID = cfg('report_pid', default=1)  # 上报平台 pid

# ============ 第二平台上报配置（上海智能建筑） ============
ENABLE_REPORT_2 = cfg('enable_report_2', default=True)  # 是否启用第二平台上报
REPORT_2_LOGIN_URL = cfg('report_2_login_url', default='https://api.shznjz.cn/api/Login')
REPORT_2_API_URL = cfg('report_2_api_url', default='https://api.shznjz.cn/api/AddVehicleManage')
REPORT_2_LOGIN = cfg('report_2_login', default='shebeituisong')
REPORT_2_PWD = cfg('report_2_pwd', default='rh@123')
REPORT_2_DEVICE_ID = cfg('report_2_device_id', default=DEVICE_ID)  # 默认与 DEVICE_ID 相同
REPORT_2_INVERT_ISWASH = cfg('report_2_invert_iswash', default=True)  # 上海平台 iswash 与自有平台相反
# ==========================================================

# ============ 推流配置 ============
ENABLE_STREAMING = cfg('enable_streaming', default=True)  # 是否启用推流
STREAM_OUTPUT_URL = cfg('stream_output_url', default='rtmp://121.199.7.83:1935/live/vehicle_wash')  # 推流地址
STREAM_WIDTH = cfg('stream_width', default=1280)      # 推流分辨率宽
STREAM_HEIGHT = cfg('stream_height', default=720)      # 推流分辨率高
STREAM_FPS = cfg('stream_fps', default=25)          # 推流帧率
STREAM_BITRATE = cfg('stream_bitrate', default='1500k') # 推流码率（降低码率适配云服务器带宽）
STREAM_QUEUE_SIZE = cfg('stream_queue_size', default=20)   # 推流缓存队列，避免原始帧堆积占满内存
# ==================================

# ============ 资源并发配置 ============
REPORT_MAX_WORKERS = cfg('report_max_workers', default=2)   # 上报线程池大小，避免每次事件都创建新线程
# ====================================

# ============ 视频流重连配置 ============
STREAM_RECONNECT_ENABLED = cfg('stream_reconnect_enabled', default=True)   # 是否启用视频流自动重连
STREAM_RECONNECT_MAX_RETRIES = cfg('stream_reconnect_max_retries', default=50)  # 最大重连次数（0=无限）
STREAM_RECONNECT_INTERVAL = cfg('stream_reconnect_interval', default=5.0)   # 重连间隔（秒）
STREAM_RECONNECT_RESET_INTERVAL = cfg('stream_reconnect_reset_interval', default=30.0)  # 成功读取多久后重置重连计数（秒）
# ======================================

# ============ 进出场与清洗配置 ============
EXIT_DIRECTION = cfg('exit_direction', default='left')  # 车辆出场方向：'left' / 'right' / 'bottom'
EXIT_EDGE_THRESHOLD = cfg('exit_edge_threshold', default=0.05)  # 出场边缘阈值（兼容旧逻辑）
EXIT_LEADING_EDGE_THRESHOLD = cfg('exit_leading_edge_threshold', default=0.80)  # 检测框前缘越线阈值（0~1）
EXIT_WAIT_TIME = cfg('exit_wait_time', default=3)  # 前缘持续越线多久才判定出场（秒），新逻辑建议 2~5 秒
MIN_DWELL_TIME = cfg('min_dwell_time', default=5)  # 车辆进场后最短在场时间（秒），防止同时进出场
WASH_STOP_TIME = cfg('wash_stop_time', default=30)  # 清洗停止判定时间（秒）
WASH_ZONE = cfg('wash_zone', default={'x1': 0.1, 'y1': 0.3, 'x2': 0.7, 'y2': 0.8})
PLATE_MERGE_THRESHOLD = cfg('plate_merge_threshold', default=0.60)
# =========================================

# ============ 视频源配置 ============
VIDEO_PATH = cfg('video_path', default='rtmp://rtmp05open.ys7.com:1935/v3/openlive/BK1948130_2_1?expire=1809950641&id=975488750482890752&t=69761f54257288b0df5f7db26a58a8996a6501f7cf1a8475ee42bd6f3ef1f42c&ev=101')
# ==================================

# ============ 运行模式配置 ============
NO_DISPLAY = cfg('no_display', default=False)  # 是否禁用本地显示窗口
# =====================================

# 每个项目使用独立的日志和数据库文件，避免多实例冲突
log_file_path = cfg('log_file', default=f'full_video_test_v3_report_{DEVICE_ID}.log')
log_file = open(log_file_path, 'w', encoding='utf-8')

def log(msg, end='\n'):
    timestamp = datetime.now().strftime('%H:%M:%S')
    line = f"[{timestamp}] {msg}"
    try:
        print(line, end=end, flush=True)
    except:
        print(line.encode('gbk', errors='ignore').decode('gbk'), end=end, flush=True)
    log_file.write(line + end)
    log_file.flush()

# ============================================================
# HTTP上报模块（免登录）
# ============================================================

class ReportClient:
    """车辆进出场数据上报客户端（免登录，直接上报）"""

    def __init__(self, device_id: str, report_url: str, oss_url: str, enable: bool = True):
        self.device_id = device_id
        self.report_url = report_url
        self.oss_url = oss_url
        self.enable = enable
        self.success_count = 0
        self.fail_count = 0
        self._lock = threading.Lock()
        self._closed = False
        self._session = requests.Session()
        self._session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'VehicleWashDetector/1.0'
        })
        self._executor = ThreadPoolExecutor(
            max_workers=REPORT_MAX_WORKERS,
            thread_name_prefix="report-client"
        )

    def _upload_to_oss(self, frame: np.ndarray, license_plate: str, quality: int = 65) -> Optional[str]:
        """将图片上传至OSS，返回URL（上传时不带header，使用独立requests）"""
        try:
            encode_param = [cv2.IMWRITE_JPEG_QUALITY, quality]
            ret, buffer = cv2.imencode('.jpg', frame, encode_param)
            if not ret:
                log(f"[OSS] 图片编码失败: {license_plate}")
                return None

            filename = f"{license_plate}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"

            # 关键修改：用 io.BytesIO 包装 bytes
            files = {
                'file': (filename, io.BytesIO(buffer.tobytes()), 'image/jpeg')
            }

            # 关键修改：用独立 requests.post，不用带 JSON header 的 session
            resp = requests.post(
                self.oss_url,
                files=files,
                timeout=30
            )
            try:
                if resp.status_code == 200:
                    result = resp.json()
                    oss_url = None
                    if isinstance(result, dict) and 'data' in result and isinstance(result['data'], dict):
                        oss_url = result['data'].get('url')
                    if oss_url:
                        log(f"[OSS] ✓ 上传成功: {license_plate}, URL={oss_url[:80]}...")
                        return oss_url
                    else:
                        log(f"[OSS] ✗ 响应中无URL: {result}")
                        return None
                else:
                    log(f"[OSS] ✗ HTTP错误: {resp.status_code}, {resp.text[:200]}")
                    return None
            finally:
                resp.close()

        except requests.exceptions.ConnectionError:
            log(f"[OSS] ✗ 连接失败: 无法连接到 {self.oss_url}")
        except requests.exceptions.Timeout:
            log(f"[OSS] ✗ 请求超时")
        except Exception as e:
            log(f"[OSS] ✗ 异常: {e}")

        return None

    def _mark_success(self):
        with self._lock:
            self.success_count += 1

    def _mark_fail(self):
        with self._lock:
            self.fail_count += 1

    def report(self, license_plate: str, inouttype: int, iswash: int,
               frame: np.ndarray, datatype: int = 0) -> bool:
        """
        上报车辆进出场数据（免登录，直接POST）
        """
        if not self.enable:
            log(f"[Report] 上报已禁用，跳过: {license_plate}")
            return False

        if frame is None:
            log(f"[Report] 无抓拍帧，跳过: {license_plate}")
            self._mark_fail()
            return False

        with self._lock:
            if self._closed:
                log(f"[Report] 客户端已关闭，跳过: {license_plate}")
                self.fail_count += 1
                return False

        try:
            self._executor.submit(
                self._report_worker,
                license_plate,
                inouttype,
                iswash,
                frame,
                datatype
            )
            return True

        except Exception as e:
            log(f"[Report] 构建上报数据失败 {license_plate}: {e}")
            self._mark_fail()
            return False

    def _report_worker(self, license_plate: str, inouttype: int, iswash: int,
                       frame: np.ndarray, datatype: int = 0):
        log(f"[Report] 正在上传图片到OSS: {license_plate}")
        photo_url = self._upload_to_oss(frame, license_plate)

        if not photo_url:
            log(f"[Report] OSS上传失败，跳过上报: {license_plate}")
            self._mark_fail()
            return

        payload = {
            "deviceId": self.device_id,
            "licenseplate": license_plate,
            "inouttype": inouttype,
            "isWash": iswash,
            "photo": photo_url,
            "dataType": datatype,
            "pid": REPORT_PID,
            "createBy": "system",
            "createTime": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        self._do_report(payload, license_plate, inouttype)

    def _do_report(self, payload: dict, license_plate: str, inouttype: int):
        """实际执行HTTP请求"""
        try:
            resp = self._session.post(
                self.report_url,
                json=payload,
                timeout=10
            )
            try:
                if resp.status_code == 200:
                    result = resp.json()
                    # 根据实际接口返回值调整判断逻辑；这里兼容通用成功判断
                    if result.get("Code") == 200 or result.get("code") == 200 or result.get("success") == True:
                        self._mark_success()
                        inout_str = "进场" if inouttype == 0 else "出场"
                        log(f"[Report] ✓ 上报成功: {license_plate} {inout_str}")
                    else:
                        self._mark_fail()
                        log(f"[Report] ✗ 上报失败: {license_plate}, {result}")
                else:
                    self._mark_fail()
                    log(f"[Report] ✗ HTTP错误: {license_plate}, {resp.status_code}")
            finally:
                resp.close()

        except requests.exceptions.ConnectionError:
            self._mark_fail()
            log(f"[Report] ✗ 连接失败: 无法连接到 {self.report_url}")
        except requests.exceptions.Timeout:
            self._mark_fail()
            log(f"[Report] ✗ 请求超时: {license_plate}")
        except Exception as e:
            self._mark_fail()
            log(f"[Report] ✗ 异常: {license_plate}, {e}")

    def get_stats(self) -> dict:
        with self._lock:
            success = self.success_count
            fail = self.fail_count
        return {
            'success': success,
            'fail': fail,
            'total': success + fail
        }

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown(wait=True)
        self._session.close()


class ShznjzReportClient:
    """
    上海智能建筑平台上报客户端

    流程：
    1. 每次上报前调用 /api/Login 获取 token
    2. 将抓拍帧编码为 base64 JPEG
    3. 携带 token Header，POST /api/AddVehicleManage
    """

    def __init__(self,
                 device_id: str,
                 login_url: str,
                 api_url: str,
                 login: str,
                 pwd: str,
                 enable: bool = True,
                 invert_iswash: bool = False):
        self.device_id = device_id
        self.login_url = login_url
        self.api_url = api_url
        self.login = login
        self.pwd = pwd
        self.enable = enable
        self.invert_iswash = invert_iswash
        self.success_count = 0
        self.fail_count = 0
        self._lock = threading.Lock()
        self._closed = False
        self._session = requests.Session()
        self._session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'VehicleWashDetector/1.0'
        })
        self._executor = ThreadPoolExecutor(
            max_workers=REPORT_MAX_WORKERS,
            thread_name_prefix="shznjz-report-client"
        )

    def _encode_frame_to_base64(self, frame: np.ndarray, quality: int = 65) -> Optional[str]:
        """将 OpenCV 帧编码为 base64 字符串"""
        try:
            encode_param = [cv2.IMWRITE_JPEG_QUALITY, quality]
            ret, buffer = cv2.imencode('.jpg', frame, encode_param)
            if not ret:
                log(f"[ShznjzReport] 图片编码失败")
                return None
            return base64.b64encode(buffer.tobytes()).decode('utf-8')
        except Exception as e:
            log(f"[ShznjzReport] base64 编码异常: {e}")
            return None

    def _login(self) -> Optional[str]:
        """登录并返回 token"""
        try:
            resp = self._session.post(
                self.login_url,
                json={"Login": self.login, "pwd": self.pwd},
                timeout=10
            )
            try:
                if resp.status_code == 200:
                    result = resp.json()
                    if result.get("Code") == 1:
                        data = result.get("Data", {})
                        token = data.get("token")
                        if token:
                            log(f"[ShznjzReport] 登录成功，获取 token")
                            return token
                        else:
                            log(f"[ShznjzReport] 登录响应中无 token: {result}")
                    else:
                        log(f"[ShznjzReport] 登录失败: {result.get('Message')}")
                else:
                    log(f"[ShznjzReport] 登录 HTTP 错误: {resp.status_code}")
            finally:
                resp.close()
        except requests.exceptions.ConnectionError:
            log(f"[ShznjzReport] 登录连接失败")
        except requests.exceptions.Timeout:
            log(f"[ShznjzReport] 登录超时")
        except Exception as e:
            log(f"[ShznjzReport] 登录异常: {e}")
        return None

    def _mark_success(self):
        with self._lock:
            self.success_count += 1

    def _mark_fail(self):
        with self._lock:
            self.fail_count += 1

    def report(self, license_plate: str, inouttype: int, iswash: int,
               frame: np.ndarray, datatype: int = 0) -> bool:
        """提交上报任务到线程池"""
        if not self.enable:
            return False
        if frame is None:
            log(f"[ShznjzReport] 无抓拍帧，跳过: {license_plate}")
            self._mark_fail()
            return False
        with self._lock:
            if self._closed:
                self.fail_count += 1
                return False
        try:
            self._executor.submit(
                self._report_worker,
                license_plate,
                inouttype,
                iswash,
                frame,
                datatype
            )
            return True
        except Exception as e:
            log(f"[ShznjzReport] 提交任务失败 {license_plate}: {e}")
            self._mark_fail()
            return False

    def _report_worker(self, license_plate: str, inouttype: int, iswash: int,
                       frame: np.ndarray, datatype: int = 0):
        # 1. 先登录获取 token
        token = self._login()
        if not token:
            log(f"[ShznjzReport] 无法获取 token，跳过上报: {license_plate}")
            self._mark_fail()
            return

        # 2. 图片转 base64
        photo_base64 = self._encode_frame_to_base64(frame)
        if not photo_base64:
            self._mark_fail()
            return

        # 3. 上报（根据配置反转 iswash 含义）
        report_iswash = 1 - iswash if self.invert_iswash else iswash
        payload = [
            {
                "device_id": self.device_id,
                "licenseplate": license_plate,
                "inouttype": inouttype,
                "iswash": report_iswash,
                "photo": photo_base64,
                "datatype": datatype
            }
        ]

        headers = {
            'Content-Type': 'application/json',
            'token': token
        }

        try:
            resp = self._session.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=15
            )
            try:
                if resp.status_code == 200:
                    result = resp.json()
                    if result.get("Code") == 1:
                        self._mark_success()
                        inout_str = "进场" if inouttype == 0 else "出场"
                        log(f"[ShznjzReport] ✓ 上报成功: {license_plate} {inout_str}")
                    else:
                        self._mark_fail()
                        log(f"[ShznjzReport] ✗ 上报失败: {license_plate}, {result}")
                else:
                    self._mark_fail()
                    log(f"[ShznjzReport] ✗ 上报 HTTP 错误: {license_plate}, {resp.status_code}")
            finally:
                resp.close()
        except requests.exceptions.ConnectionError:
            self._mark_fail()
            log(f"[ShznjzReport] ✗ 上报连接失败: {license_plate}")
        except requests.exceptions.Timeout:
            self._mark_fail()
            log(f"[ShznjzReport] ✗ 上报超时: {license_plate}")
        except Exception as e:
            self._mark_fail()
            log(f"[ShznjzReport] ✗ 上报异常: {license_plate}, {e}")

    def get_stats(self) -> dict:
        with self._lock:
            return {
                'success': self.success_count,
                'fail': self.fail_count,
                'total': self.success_count + self.fail_count
            }

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown(wait=True)
        self._session.close()


# ============================================================
# 进出场 + 清洗判定（集成上报）
# ============================================================

@dataclass
class VehicleRecord:
    vehicle_id: str
    license_plate: str
    entry_time: datetime
    exit_time: Optional[datetime] = None
    is_washed: bool = False
    dwell_time: float = 0.0
    wash_start_time: Optional[datetime] = None
    is_reentry: bool = False
    last_bbox: Optional[Tuple[int, int, int, int]] = None
    last_seen: Optional[datetime] = None
    position_history: List[Tuple[float, float]] = field(default_factory=list)
    db_id: Optional[int] = None
    entry_frame: Optional[np.ndarray] = None  # 进场抓拍帧
    exit_frame: Optional[np.ndarray] = None   # 出场抓拍帧


class EntryExitManager:
    """进出场 + 清洗判定管理器 (方案2: 强车牌合并 + HTTP上报)"""

    def __init__(self, wash_stop_time=180, exit_wait_time=60,
                 exit_left_threshold=0.05, wash_zone=None,
                 plate_merge_threshold=0.60,
                 report_client=None,
                 exit_direction='left',
                 exit_leading_edge_threshold=0.80,
                 min_dwell_time=5):
        self.wash_stop_time = wash_stop_time
        self.exit_wait_time = exit_wait_time
        self.exit_left_threshold = exit_left_threshold
        self.exit_leading_edge_threshold = exit_leading_edge_threshold
        self.min_dwell_time = min_dwell_time
        self.exit_direction = exit_direction.lower() if exit_direction else 'left'
        if self.exit_direction not in ('left', 'right', 'bottom'):
            self.exit_direction = 'left'
        self.wash_zone = wash_zone or {'x1': 0.1, 'y1': 0.3, 'x2': 0.7, 'y2': 0.8}
        self.plate_merge_threshold = plate_merge_threshold

        self.records: Dict[str, VehicleRecord] = {}
        self.exited_plates: Dict[str, datetime] = {}
        self.left_disappear_time: Dict[str, datetime] = {}

        self.next_id = 0
        self.total_entries = 0
        self.total_exits = 0
        self.washed_count = 0

        self.db = None
        # 车牌变体映射: 变体 -> 主车牌
        self.plate_variants: Dict[str, str] = {}
        # 支持单个客户端或客户端列表
        if report_client is None:
            self.report_clients = []
        elif isinstance(report_client, (list, tuple)):
            self.report_clients = [c for c in report_client if c is not None]
        else:
            self.report_clients = [report_client]

        # 当前帧缓存（用于抓拍）
        self.current_frame: Optional[np.ndarray] = None

    def set_current_frame(self, frame: np.ndarray):
        """设置当前帧，用于抓拍上报"""
        # 仅保留引用，真正需要上报时再复制，避免每帧额外产生一份整图副本
        self.current_frame = frame if frame is not None else None

    def set_db(self, db):
        self.db = db

    def _plate_similarity(self, p1: str, p2: str) -> float:
        """计算两个车牌的相似度 (使用统一缓存实现)"""
        from plate_utils import plate_similarity
        return plate_similarity(p1, p2)

    def _find_similar_record(self, plate: str) -> Optional[str]:
        """查找与给定车牌相似的已有记录"""
        # 先检查变体映射
        if plate in self.plate_variants:
            return self.plate_variants[plate]

        best_match = None
        best_sim = self.plate_merge_threshold

        # 与所有在场记录比较
        for existing_plate, record in self.records.items():
            if record.exit_time is not None:
                continue  # 已出场的不再合并
            sim = self._plate_similarity(plate, existing_plate)
            if sim > best_sim:
                best_sim = sim
                best_match = existing_plate

        # 也与已出场记录比较（用于二次进场识别）
        if best_match is None:
            for existing_plate in self.exited_plates:
                sim = self._plate_similarity(plate, existing_plate)
                if sim > best_sim:
                    best_sim = sim
                    best_match = existing_plate

        return best_match

    def on_plate_confirmed(self, plate: str, bbox: Tuple, frame_shape: Tuple):
        """车牌确认后的回调 - 方案2: 强合并 + 上报进场"""
        current_time = datetime.now()
        frame_height, frame_width = frame_shape[:2]
        center_x = (bbox[0] + bbox[2]) / 2
        center_y = (bbox[1] + bbox[3]) / 2

        # 方案2核心: 查找相似记录
        similar_plate = self._find_similar_record(plate)

        if similar_plate and similar_plate in self.records:
            # 合并到已有记录
            record = self.records[similar_plate]

            # 如果当前车牌更"标准"（长度更接近7位），更新主车牌
            if abs(len(plate) - 7) < abs(len(similar_plate) - 7):
                # 迁移记录到新车牌键
                old_plate = similar_plate
                self.records[plate] = record
                record.license_plate = plate
                del self.records[old_plate]

                # 更新变体映射
                self.plate_variants[old_plate] = plate
                self.plate_variants[plate] = plate

                log(f"车牌更新: {old_plate} -> {plate}")
                similar_plate = plate

            # 记录变体映射
            if plate != similar_plate:
                self.plate_variants[plate] = similar_plate
                log(f"车牌合并: {plate} -> {similar_plate} (similarity: {self._plate_similarity(plate, similar_plate):.2f})")

            # 更新位置信息
            record.last_bbox = bbox
            record.last_seen = current_time
            record.position_history.append((center_x, center_y))
            if len(record.position_history) > 60:
                record.position_history = record.position_history[-30:]

            # 清洗判定 - 修复重复重置问题
            if not record.is_washed:
                in_wash_zone = self._is_in_wash_zone(bbox, frame_width, frame_height)
                is_stopped = self._is_vehicle_stopped(similar_plate)

                if in_wash_zone and is_stopped:
                    if record.wash_start_time is None:
                        record.wash_start_time = current_time
                        log(f"车辆进入清洗区域并停止: 车牌={similar_plate}")
                        # 保存清洗开始时间到数据库
                        if self.db:
                            try:
                                self.db.save_vehicle_record(record)
                            except Exception as e:
                                log(f"  数据库保存清洗开始失败: {e}")
                    else:
                        stop_duration = (current_time - record.wash_start_time).total_seconds()
                        if stop_duration >= self.wash_stop_time:
                            record.is_washed = True
                            log(f"★ 车辆清洗完成: 车牌={similar_plate}, 停止时间={stop_duration:.0f}秒")
                            # 保存清洗完成状态到数据库
                            if self.db:
                                try:
                                    self.db.save_vehicle_record(record)
                                    log(f"  数据库已更新清洗状态: {similar_plate}")
                                except Exception as e:
                                    log(f"  数据库保存清洗状态失败: {e}")
                else:
                    # 只有在真正离开区域或移动时才重置
                    if record.wash_start_time is not None:
                        if not in_wash_zone:
                            log(f"车辆离开清洗区域，计时重置: 车牌={similar_plate}")
                            record.wash_start_time = None
                        elif not is_stopped:
                            # 检查是否真的在移动（不是微小抖动）
                            if len(record.position_history) >= 10:
                                recent = record.position_history[-10:]
                                xs = [p[0] for p in recent]
                                ys = [p[1] for p in recent]
                                x_range = max(xs) - min(xs)
                                y_range = max(ys) - min(ys)
                                # 只有移动超过阈值才重置
                                if x_range > 50 or y_range > 50:
                                    log(f"车辆在清洗区域移动，计时重置: 车牌={similar_plate} (移动: {x_range:.0f}, {y_range:.0f})")
                                    record.wash_start_time = None

            # 出场检测（根据配置方向）
            if self._is_near_exit_edge(bbox, frame_width, frame_height):
                if similar_plate not in self.left_disappear_time:
                    self.left_disappear_time[similar_plate] = current_time
                    if self.exit_direction == 'bottom':
                        edge_name = "下方"
                    elif self.exit_direction == 'right':
                        edge_name = "右侧"
                    else:
                        edge_name = "左侧"
                    log(f"车辆到达画面{edge_name}: 车牌={similar_plate}")
            else:
                if similar_plate in self.left_disappear_time:
                    del self.left_disappear_time[similar_plate]

            return record

        # 检查是否是二次进场
        if similar_plate and similar_plate in self.exited_plates:
            is_reentry = True
            del self.exited_plates[similar_plate]
            log(f"车辆二次进场: 车牌={plate} (匹配已出场记录: {similar_plate})")
            # 使用已出场的车牌作为主记录
            plate = similar_plate
        else:
            is_reentry = False

        # 创建新记录
        record = VehicleRecord(
            vehicle_id=str(self.next_id),
            license_plate=plate,
            entry_time=current_time,
            is_reentry=is_reentry,
            last_bbox=bbox,
            last_seen=current_time,
            position_history=[(center_x, center_y)],
            entry_frame=self.current_frame.copy() if self.current_frame is not None else None,
        )
        self.records[plate] = record
        self.next_id += 1
        self.total_entries += 1

        entry_type = "二次进场" if is_reentry else "进场"
        log(f"★ 车辆{entry_type}: ID={record.vehicle_id}, 车牌={plate}")

        # 数据库保存
        if self.db:
            try:
                db_id = self.db.save_vehicle_record(record)
                record.db_id = db_id
            except Exception as e:
                log(f"数据库保存失败: {e}")

        # === 上报进场 ===
        if record.entry_frame is not None:
            for client in self.report_clients:
                client.report(
                    license_plate=plate,
                    inouttype=0,      # 进场
                    iswash=0,         # 刚进场，未洗
                    frame=record.entry_frame,
                    datatype=0
                )
            record.entry_frame = None

        return record

    def check_exits(self, frame_shape: Tuple):
        current_time = datetime.now()
        updated = []

        for plate, disappear_time in list(self.left_disappear_time.items()):
            wait_elapsed = (current_time - disappear_time).total_seconds()
            if wait_elapsed >= self.exit_wait_time:
                record = self.records.get(plate)
                if record and record.exit_time is None:
                    dwell_time = (current_time - record.entry_time).total_seconds()
                    if dwell_time < self.min_dwell_time:
                        # 最短在场时间未满足，继续等待
                        continue
                    record.exit_time = current_time
                    record.dwell_time = (record.exit_time - record.entry_time).total_seconds()
                    record.exit_frame = self.current_frame.copy() if self.current_frame is not None else None

                    self.total_exits += 1
                    if record.is_washed:
                        self.washed_count += 1

                    self.exited_plates[plate] = current_time

                    if self.db:
                        try:
                            self.db.save_vehicle_record(record)
                        except Exception as e:
                            log(f"数据库保存失败: {e}")

                    updated.append(record)
                    log(f"★ 车辆出场: 车牌={plate}, 停留={record.dwell_time:.0f}秒, "
                        f"清洗={'是' if record.is_washed else '否'}")

                    # === 上报出场 ===
                    if record.exit_frame is not None:
                        for client in self.report_clients:
                            client.report(
                                license_plate=plate,
                                inouttype=1,      # 出场
                                iswash=1 if record.is_washed else 0,
                                frame=record.exit_frame,
                                datatype=0
                            )
                        record.exit_frame = None

                    del self.left_disappear_time[plate]

        return updated

    def check_missing_vehicles(self, confirmed_plates: List[str], frame_shape: Tuple):
        current_time = datetime.now()
        frame_height, frame_width = frame_shape[:2]
        confirmed_roots = {
            self.plate_variants.get(cp, cp)
            for cp in confirmed_plates
        }

        for plate, record in self.records.items():
            if record.exit_time is not None:
                continue

            if plate in confirmed_roots:
                continue

            if record.last_bbox and self._is_near_exit_edge(record.last_bbox, frame_width, frame_height):
                if plate not in self.left_disappear_time:
                    self.left_disappear_time[plate] = current_time
                    if self.exit_direction == 'bottom':
                        edge_name = "下方"
                    elif self.exit_direction == 'right':
                        edge_name = "右侧"
                    else:
                        edge_name = "左侧"
                    log(f"车辆从{edge_name}消失: 车牌={plate}")

    def _is_in_wash_zone(self, bbox, frame_width, frame_height):
        x1, y1, x2, y2 = bbox
        center_x = (x1 + x2) / 2 / frame_width
        center_y = (y1 + y2) / 2 / frame_height
        zone = self.wash_zone
        return (zone['x1'] <= center_x <= zone['x2'] and
                zone['y1'] <= center_y <= zone['y2'])

    def _is_vehicle_stopped(self, plate):
        record = self.records.get(plate)
        if not record or len(record.position_history) < 10:
            return False
        recent = record.position_history[-10:]
        xs = [p[0] for p in recent]
        ys = [p[1] for p in recent]
        return (max(xs) - min(xs)) < 30 and (max(ys) - min(ys)) < 30

    def _is_near_exit_edge(self, bbox, frame_width, frame_height):
        """
        前缘越线判定：用检测框朝向出口方向的那条边作为前缘。
        - bottom：车辆向下离开，前缘是 bbox 顶部 y1，y1 > threshold*h 即出场
        - right：车辆向右离开，前缘是 bbox 右侧 x2，x2 > threshold*w 即出场
        - left：车辆向左离开，前缘是 bbox 左侧 x1，x1 < (1-threshold)*w 即出场
        """
        x1, y1, x2, y2 = bbox
        t = self.exit_leading_edge_threshold
        if self.exit_direction == 'bottom':
            return y1 > frame_height * t
        if self.exit_direction == 'right':
            return x2 > frame_width * t
        # 默认左侧出场
        return x1 < frame_width * (1 - t)

    def get_active_records(self):
        return [r for r in self.records.values() if r.exit_time is None]

    def get_completed_records(self):
        return [r for r in self.records.values() if r.exit_time is not None]

    def get_statistics(self):
        return {
            'total_entries': self.total_entries,
            'total_exits': self.total_exits,
            'washed_count': self.washed_count,
            'active_vehicles': sum(1 for r in self.records.values() if r.exit_time is None),
            'pending_exit': len(self.left_disappear_time),
            'wash_rate': self.washed_count / self.total_exits if self.total_exits > 0 else 0,
        }


# ============================================================
# 主程序
# ============================================================

log("=" * 70)
log("车辆清洗检测 V3 - 实时模式（集成HTTP上报，免登录）")
log(f"Project: {PROJECT_NAME}, Device ID: {DEVICE_ID}")
log(f"Exit Direction: {EXIT_DIRECTION}")
log(f"Primary Report URL: {REPORT_URL}, PID: {REPORT_PID}, Enabled: {ENABLE_REPORT}")
log(f"Shznjz Report URL: {REPORT_2_API_URL}, Device ID: {REPORT_2_DEVICE_ID}, Enabled: {ENABLE_REPORT_2}")
log(f"Stream Enabled: {ENABLE_STREAMING}")
if ENABLE_STREAMING:
    log(f"Stream URL: {STREAM_OUTPUT_URL}")
    log(f"Stream Resolution: {STREAM_WIDTH}x{STREAM_HEIGHT} @ {STREAM_FPS}fps")
log(f"Log File: {log_file_path}")
log("=" * 70)

# 视频源已在上方的 cfg 中配置
IS_STREAM = VIDEO_PATH.startswith(('rtmp://', 'rtsp://', 'http://', 'https://'))

log(f"\nVideo Source: {VIDEO_PATH}")
if not IS_STREAM:
    video_path = Path(VIDEO_PATH)
    if not video_path.exists():
        log(f"Error: Video file not found: {VIDEO_PATH}")
        log_file.close()
        sys.exit(1)
    log(f"Size: {video_path.stat().st_size / 1024 / 1024:.1f} MB")

cap = cv2.VideoCapture(VIDEO_PATH)
if not cap.isOpened():
    log("Error: Cannot open video source")
    log_file.close()
    sys.exit(1)

fps = cap.get(cv2.CAP_PROP_FPS)
frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

# 流模式下fps可能为0，使用默认值
if fps <= 0:
    fps = 25.0
    log("[Stream] FPS not provided by source, using default 25.0")

frame_interval = 1.0 / fps

log(f"Video Info:")
log(f"  Resolution: {width}x{height}")
log(f"  FPS: {fps:.1f}")
if not IS_STREAM and frame_count > 0:
    log(f"  Total frames: {frame_count}")
    log(f"  Duration: {frame_count/fps:.1f}s")
else:
    log(f"  Mode: Live stream")

report_client = None
db = None
stream_publisher = None

DETECT_WIDTH = 1280
DETECT_HEIGHT = int(height * DETECT_WIDTH / width)
detect_scale = width / DETECT_WIDTH

log(f"\nDetection Settings:")
log(f"  Vehicle detection: {DETECT_WIDTH}x{DETECT_HEIGHT}")
log(f"  Plate detection: Original ({width}x{height})")

# ============================================================
# 加载检测器（与 spatial 副本版本一致）
# ============================================================

log("\nLoading detector...")
try:
    # 添加 detectors 和 tracking 路径
    detectors_path = str(Path(__file__).parent.parent / 'detectors')
    tracking_path = str(Path(__file__).parent.parent / 'tracking')
    if detectors_path not in sys.path:
        sys.path.insert(0, detectors_path)
    if tracking_path not in sys.path:
        sys.path.insert(0, tracking_path)
    
    from vehicle_wash_detector import VehicleWashDetector
    from spatial_plate_deduplicator import SpatialPlateDeduplicator
    from plate_validator_v2 import validate_plate_v2
    from vehicle_tracker import VehicleTracker
    log("  Import OK")

    # 模型路径改为相对 organized 目录
    model_path = str(Path(__file__).parent.parent / 'models' / 'yolov8n.pt')
    detector_config = {
        'path': model_path,
        'device': 'cuda',
        'conf_threshold': 0.35,
        'iou_threshold': 0.45,
        'img_size': 640,
    }

    detector = VehicleWashDetector(detector_config)
    log("  Detector OK")

    if detector.plate_detector is not None:
        log("  YOLOv8 plate model loaded")
    else:
        log("  WARNING: Plate detector not loaded!")

    spatial_dedup = SpatialPlateDeduplicator(
        spatial_threshold=80.0,
        time_window=12.0,
        min_detections=10,
        min_plate_agreement=0.80,
        plate_similarity_threshold=0.90
    )
    log("  Spatial dedup: spatial=80px, min_detections=10, agreement=0.80, similarity=0.90")

    # 初始化上报客户端（免登录）
    report_client = ReportClient(
        device_id=DEVICE_ID,
        report_url=REPORT_URL,
        oss_url=OSS_UPLOAD_URL,
        enable=ENABLE_REPORT
    )
    log(f"  Report client OK (no login)")

    # 初始化第二平台上报客户端（上海智能建筑）
    report_client_2 = ShznjzReportClient(
        device_id=REPORT_2_DEVICE_ID,
        login_url=REPORT_2_LOGIN_URL,
        api_url=REPORT_2_API_URL,
        login=REPORT_2_LOGIN,
        pwd=REPORT_2_PWD,
        enable=ENABLE_REPORT_2,
        invert_iswash=REPORT_2_INVERT_ISWASH
    )
    log(f"  Shznjz report client OK (login first)")

    report_clients = [c for c in [report_client, report_client_2] if c is not None]

    entry_exit_mgr = EntryExitManager(
        wash_stop_time=WASH_STOP_TIME,
        exit_wait_time=EXIT_WAIT_TIME,
        exit_left_threshold=EXIT_EDGE_THRESHOLD,
        wash_zone=WASH_ZONE,
        plate_merge_threshold=PLATE_MERGE_THRESHOLD,
        report_client=report_clients,
        exit_direction=EXIT_DIRECTION,
        exit_leading_edge_threshold=EXIT_LEADING_EDGE_THRESHOLD,
        min_dwell_time=MIN_DWELL_TIME
    )
    log(f"  Entry/Exit: direction={EXIT_DIRECTION}, leading_edge={EXIT_LEADING_EDGE_THRESHOLD}, "
        f"exit_wait={EXIT_WAIT_TIME}s, min_dwell={MIN_DWELL_TIME}s, wash_stop={WASH_STOP_TIME}s, "
        f"plate_merge={PLATE_MERGE_THRESHOLD} (with {len(report_clients)} report clients)")

    vehicle_tracker = VehicleTracker(
        iou_threshold=0.3,
        max_miss_frames=5,
        exit_left_threshold=EXIT_EDGE_THRESHOLD,
        exit_wait_time=EXIT_WAIT_TIME,
        exit_direction=EXIT_DIRECTION,
        exit_leading_edge_threshold=EXIT_LEADING_EDGE_THRESHOLD,
        min_dwell_time=MIN_DWELL_TIME,
    )
    log(f"  Vehicle Tracker: IOU=0.3, max_miss=5 frames, direction={EXIT_DIRECTION}, "
        f"leading_edge={EXIT_LEADING_EDGE_THRESHOLD}, exit_wait={EXIT_WAIT_TIME}s, min_dwell={MIN_DWELL_TIME}s")

    db_file = cfg('db_path', default=f'vehicle_wash_{DEVICE_ID}.db')
    db_config = {
        'enabled': cfg('db_enabled', default=True),
        'db_path': db_file,
        'table_name': cfg('db_table_name', default='vehicle_wash_records'),
    }
    if db_config.get('enabled', False):
        try:
            # 添加 database 路径
            db_path = str(Path(__file__).parent.parent / 'database')
            if db_path not in sys.path:
                sys.path.insert(0, db_path)
            from vehicle_wash_db import VehicleWashDB
            # 使用配置中的数据库路径（支持每个项目独立数据库）
            db_config['db_path'] = str(Path(__file__).parent.parent / db_config['db_path'])
            db = VehicleWashDB(db_config)
            entry_exit_mgr.set_db(db)
            log("  SQLite database connected")
        except Exception as e:
            log(f"  Database failed: {e}")

    # 初始化推流器
    stream_publisher = None
    if ENABLE_STREAMING:
        try:
            stream_publisher = FFmpegStreamPublisher(
                output_url=STREAM_OUTPUT_URL,
                width=STREAM_WIDTH,
                height=STREAM_HEIGHT,
                fps=STREAM_FPS,
                bitrate=STREAM_BITRATE,
                preset="ultrafast",
                queue_size=STREAM_QUEUE_SIZE
            )
            stream_publisher.start()
            log("  Stream publisher started")
        except Exception as e:
            log(f"  Stream publisher failed: {e}")
            stream_publisher = None

except Exception as e:
    log(f"Error: {e}")
    import traceback
    traceback.print_exc()
    log_file.close()
    sys.exit(1)

# ============================================================
# 多线程架构（与 spatial 副本版本一致 + 实时模式）
# ============================================================

frame_queue = queue.Queue(maxsize=30)
detect_queue = queue.Queue(maxsize=30)
result_queue = queue.Queue(maxsize=30)

stop_event = threading.Event()
frame_idx = 0
processed_frames = 0
lock = threading.Lock()

stats = {
    'total_frames': 0,
    'start_time': time.time(),
    'total_detections': 0,
    'valid_plates': 0,
    'invalid_plates': 0,
    'confirmed_vehicles': set(),
}

def queue_put_with_stop(target_queue, item, timeout=0.2) -> bool:
    """在可停止语义下向队列写入，避免线程在退出阶段永久阻塞"""
    while not stop_event.is_set():
        try:
            target_queue.put(item, block=True, timeout=timeout)
            return True
        except queue.Full:
            continue
    return False

def video_reader_thread():
    global frame_idx, cap
    log("[Video Reader] Started (REALTIME)")
    next_frame_time = time.time()
    consecutive_failures = 0
    reconnect_count = 0
    last_success_time = time.time()

    while not stop_event.is_set():
        ret, frame = cap.read()
        if not ret:
            consecutive_failures += 1

            # 检查是否需要重连（仅对网络流）
            if IS_STREAM and STREAM_RECONNECT_ENABLED:
                # 检查是否超过最大重连次数
                if STREAM_RECONNECT_MAX_RETRIES > 0 and reconnect_count >= STREAM_RECONNECT_MAX_RETRIES:
                    log(f"[Video Reader] Max reconnect attempts ({STREAM_RECONNECT_MAX_RETRIES}) reached, giving up")
                    break

                # 尝试重连
                if consecutive_failures >= 10:
                    reconnect_count += 1
                    log(f"[Video Reader] Stream disconnected, reconnecting ({reconnect_count}/{STREAM_RECONNECT_MAX_RETRIES if STREAM_RECONNECT_MAX_RETRIES > 0 else '∞'})...")

                    # 释放旧连接
                    try:
                        cap.release()
                    except:
                        pass

                    # 等待后重新连接
                    time.sleep(STREAM_RECONNECT_INTERVAL)

                    # 创建新的 VideoCapture
                    cap = cv2.VideoCapture(VIDEO_PATH)
                    if cap.isOpened():
                        log("[Video Reader] Stream reconnected successfully")
                        consecutive_failures = 0
                        # 重置帧率相关参数
                        new_fps = cap.get(cv2.CAP_PROP_FPS)
                        if new_fps > 0:
                            global frame_interval
                            frame_interval = 1.0 / new_fps
                        continue
                    else:
                        log("[Video Reader] Reconnect failed, will retry...")
                        continue
                else:
                    # 还没达到10次失败，先简单重试
                    log(f"[Video Reader] Frame read failed ({consecutive_failures}/10), retrying...")
                    time.sleep(0.5)
                    continue
            else:
                # 非网络流或重连禁用
                if IS_STREAM:
                    log("[Video Reader] Stream disconnected, reconnect disabled")
                else:
                    log("[Video Reader] Video ended")
                break

        # 成功读取帧
        consecutive_failures = 0
        last_success_time = time.time()

        # 检查是否需要重置重连计数（长时间成功读取后）
        if reconnect_count > 0 and (time.time() - last_success_time) > STREAM_RECONNECT_RESET_INTERVAL:
            log(f"[Video Reader] Connection stable for {STREAM_RECONNECT_RESET_INTERVAL}s, reset reconnect counter")
            reconnect_count = 0

        try:
            frame_queue.put((frame_idx, frame), block=True, timeout=1.0)
        except queue.Full:
            log("[Video Reader] Frame queue full, dropping frame")
            continue

        with lock:
            frame_idx += 1
            stats['total_frames'] = frame_idx

        next_frame_time += frame_interval
        sleep_time = next_frame_time - time.time()
        if sleep_time > 0:
            time.sleep(sleep_time)

    log("[Video Reader] Stopped")

def vehicle_detection_thread():
    log("[Vehicle Detector] Started")

    while not stop_event.is_set():
        if stop_event.is_set():
            break

        try:
            idx, original_frame = frame_queue.get(timeout=0.2)
        except queue.Empty:
            if stop_event.is_set():
                break
            continue

        start_time = time.time()

        detect_frame = cv2.resize(
            original_frame, (DETECT_WIDTH, DETECT_HEIGHT),
            interpolation=cv2.INTER_LINEAR
        )

        detections = detector.detect(detect_frame)
        detect_time = time.time() - start_time

        for det in detections:
            x1, y1, x2, y2 = det.bbox
            det.bbox = (
                int(x1 * detect_scale),
                int(y1 * detect_scale),
                int(x2 * detect_scale),
                int(y2 * detect_scale)
            )

        with lock:
            stats['total_detections'] += len(detections)

        if not queue_put_with_stop(
            detect_queue,
            (idx, original_frame, detections, detect_time)
        ):
            break

    log("[Vehicle Detector] Stopped")

def plate_detection_worker(args):
    original_frame, detection, idx = args
    x1, y1, x2, y2 = detection.bbox
    vehicle_roi = original_frame[y1:y2, x1:x2]

    if vehicle_roi.size == 0 or vehicle_roi.shape[0] < 20 or vehicle_roi.shape[1] < 50:
        return None

    plate_result = detector.detect_license_plate(original_frame, detection.bbox)

    if plate_result and plate_result[0]:
        plate_text, plate_bbox, plate_color, color_conf = plate_result

        # 使用V2验证器（基于颜色）- 只使用V2验证，不再使用V1后备
        is_valid, cleaned, reason = validate_plate_v2(plate_text, plate_color, color_conf)

        if is_valid and cleaned:
            confirmed_vehicle = spatial_dedup.add_detection(
                frame_idx=idx,
                bbox=detection.bbox,
                plate_text=cleaned,
                plate_bbox=plate_bbox,
                confidence=detection.confidence,
                plate_color=plate_color,
                color_conf=color_conf
            )

            if confirmed_vehicle:
                return {
                    'detection': detection,
                    'plate_text': confirmed_vehicle['plate_number'],
                    'plate_bbox': plate_bbox,
                    'vehicle_id': confirmed_vehicle['vehicle_id'],
                    'confidence': confirmed_vehicle['confidence'],
                    'is_confirmed': True,
                    'plate_color': plate_color,
                    'color_conf': color_conf
                }
            else:
                return {
                    'detection': detection,
                    'plate_text': cleaned,
                    'plate_bbox': plate_bbox,
                    'vehicle_id': None,
                    'confidence': 0,
                    'is_confirmed': False,
                    'plate_color': plate_color,
                    'color_conf': color_conf
                }

    return None

def plate_detection_thread():
    log("[Plate Detector] Started (with tracking + spatial deduplication)")

    with ThreadPoolExecutor(max_workers=4) as executor:
        while not stop_event.is_set():
            if stop_event.is_set():
                break

            try:
                idx, frame, detections, detect_time = detect_queue.get(timeout=0.2)
            except queue.Empty:
                if stop_event.is_set():
                    break
                continue

            start_time = time.time()

            # === 更新当前帧到 EntryExitManager（用于抓拍上报）===
            entry_exit_mgr.set_current_frame(frame)

            # === 步骤1: 更新车辆跟踪（所有检测到的车辆，不依赖车牌）===
            tracked_objects = []
            if detections:
                tracked_objects = vehicle_tracker.update(detections, idx, frame.shape)

            # === 步骤2: 车牌识别（只处理有车牌的）===
            plate_results = []
            confirmed_plates_this_frame = []
            valid_count = 0
            invalid_count = 0

            det_to_track = vehicle_tracker.get_last_detection_mapping()

            if detections:
                futures = []
                det_indices = []
                for i, det in enumerate(detections):
                    future = executor.submit(plate_detection_worker, (frame, det, idx))
                    futures.append(future)
                    det_indices.append(i)

                for future, det_idx in zip(futures, det_indices):
                    try:
                        result = future.result(timeout=10.0)

                        if result:
                            # 关联车牌到跟踪ID
                            track_id = det_to_track.get(det_idx)
                            if track_id and result.get('plate_text'):
                                vehicle_tracker.associate_plate(
                                    track_id, result['plate_text'],
                                    result.get('confidence', 0)
                                )

                            if result['is_confirmed']:
                                plate_results.append(result)
                                valid_count += 1
                                confirmed_plates_this_frame.append(result['plate_text'])

                                with lock:
                                    if result['plate_text'] not in stats['confirmed_vehicles']:
                                        stats['confirmed_vehicles'].add(result['plate_text'])
                                        color_info = f""
                                        if result.get('plate_color'):
                                            color_info = f", 颜色:{result['plate_color']}"
                                        log(f"[Vehicle ✓#{result['vehicle_id']}] Confirmed: {result['plate_text']} "
                                            f"(conf: {result['confidence']:.1%}{color_info})")

                                entry_exit_mgr.on_plate_confirmed(
                                    result['plate_text'], result['detection'].bbox, frame.shape
                                )
                            else:
                                invalid_count += 1

                    except Exception as e:
                        log(f"[Plate Detection] Error: {e}")

                with lock:
                    stats['valid_plates'] += valid_count
                    stats['invalid_plates'] += invalid_count

            # === 步骤3: 检查出场（基于跟踪器）===
            exited_tracks = vehicle_tracker.get_exited_tracks()
            for track in exited_tracks:
                if track.plate_text and track.plate_text in entry_exit_mgr.records:
                    record = entry_exit_mgr.records[track.plate_text]
                    if record.exit_time is None:
                        # 增加最短在场时间校验，避免车辆刚进即出
                        from datetime import datetime
                        now = datetime.now()
                        dwell_time = (now - record.entry_time).total_seconds()
                        if dwell_time < entry_exit_mgr.min_dwell_time:
                            continue
                        # 标记出场
                        record.exit_time = now
                        record.dwell_time = dwell_time
                        record.exit_frame = entry_exit_mgr.current_frame.copy() if entry_exit_mgr.current_frame is not None else None
                        entry_exit_mgr.total_exits += 1
                        if record.is_washed:
                            entry_exit_mgr.washed_count += 1
                        entry_exit_mgr.exited_plates[track.plate_text] = record.exit_time
                        log(f"★ 车辆出场(跟踪): 车牌={track.plate_text}, 跟踪ID={track.track_id}, 停留={dwell_time:.0f}秒")
                        # 跟踪器出场也上报
                        if record.exit_frame is not None:
                            for client in report_clients:
                                client.report(
                                    license_plate=track.plate_text,
                                    inouttype=1,
                                    iswash=1 if record.is_washed else 0,
                                    frame=record.exit_frame,
                                    datatype=0
                                )
                            record.exit_frame = None

            entry_exit_mgr.check_missing_vehicles(confirmed_plates_this_frame, frame.shape)
            entry_exit_mgr.check_exits(frame.shape)

            plate_time = time.time() - start_time

            # === 传递所有跟踪对象到显示线程 ===
            if not queue_put_with_stop(
                result_queue,
                (idx, frame, plate_results, detect_time, plate_time, tracked_objects)
            ):
                break

    log("[Plate Detector] Stopped")

# 显示队列 - 用于线程间传递显示帧
display_queue = queue.Queue(maxsize=2)

def display_thread():
    """独立显示线程 - 不阻塞主处理流水线"""
    log("[Display] Started")
    window_name = f"Vehicle Wash V3 ({DEVICE_ID})"

    if NO_DISPLAY:
        log("[Display] 本地显示已禁用（no_display=true）")
        # 仍保持线程存活，以便接收 stop_event，但不创建窗口
        while not stop_event.is_set():
            time.sleep(0.1)
        log("[Display] Stopped")
        return

    while not stop_event.is_set():
        # 先检查stop_event，避免不必要的队列等待
        if stop_event.is_set():
            break

        try:
            display_frame = display_queue.get(timeout=0.05)
        except queue.Empty:
            # 队列为空时仍然处理waitKey，让OpenCV有机会处理窗口事件
            if stop_event.is_set():
                break
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                log("[Display] User pressed Q")
                stop_event.set()
                break
            continue

        # 再次检查stop_event，避免在显示已停止的帧
        if stop_event.is_set():
            break

        cv2.imshow(window_name, display_frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            log("[Display] User pressed Q")
            stop_event.set()
            break
        elif key == ord('p'):
            cv2.waitKey(0)

    # 确保窗口关闭
    try:
        cv2.destroyWindow(window_name)
    except:
        pass
    cv2.destroyAllWindows()
    for _ in range(10):
        cv2.waitKey(1)
    log("[Display] Stopped")


def result_processing_thread():
    global processed_frames
    log("[Result Processor] Started (display separated)")

    frame_count = 0
    last_log_time = time.time()
    tracked_confirmed = {}
    skipped_frames = 0

    while not stop_event.is_set():
        # 快速检查stop_event
        if stop_event.is_set():
            break

        try:
            item = result_queue.get(timeout=0.2)
            # 兼容旧格式和新格式
            if len(item) == 5:
                idx, frame, plate_results, detect_time, plate_time = item
                tracked_objects = []
            else:
                idx, frame, plate_results, detect_time, plate_time, tracked_objects = item
        except queue.Empty:
            # 如果stop_event已设置且队列为空，退出循环
            if stop_event.is_set():
                break
            continue

        # 队列积压检测 - 如果显示队列满或禁用显示，跳过绘制直接处理
        skip_drawing = display_queue.full() or NO_DISPLAY
        if skip_drawing:
            skipped_frames += 1
            result_frame = frame  # 不复制，直接使用原帧
        else:
            result_frame = frame.copy()

        h, w = result_frame.shape[:2]

        # 只在需要显示时才绘制
        if not skip_drawing:
            zone = entry_exit_mgr.wash_zone
            zx1, zy1 = int(zone['x1'] * w), int(zone['y1'] * h)
            zx2, zy2 = int(zone['x2'] * w), int(zone['y2'] * h)
            cv2.rectangle(result_frame, (zx1, zy1), (zx2, zy2), (255, 255, 0), 2)
            cv2.putText(result_frame, "WASH ZONE", (zx1 + 5, zy1 + 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

            t = entry_exit_mgr.exit_leading_edge_threshold
            if entry_exit_mgr.exit_direction == 'bottom':
                exit_y = int(h * t)
                cv2.line(result_frame, (0, exit_y), (w, exit_y), (0, 0, 255), 2)
                cv2.putText(result_frame, "EXIT", (w - 80, h - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            elif entry_exit_mgr.exit_direction == 'right':
                exit_x = int(w * t)
                cv2.line(result_frame, (exit_x, 0), (exit_x, h), (0, 0, 255), 2)
                cv2.putText(result_frame, "EXIT", (w - 80, h - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            else:
                exit_x = int(w * (1 - t))
                cv2.line(result_frame, (exit_x, 0), (exit_x, h), (0, 0, 255), 2)
                cv2.putText(result_frame, "EXIT", (5, h - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

            # === 绘制所有跟踪的车辆检测框 ===
            for track in tracked_objects:
                x1, y1, x2, y2 = track.bbox

                # 根据状态选择颜色
                if track.exit_detected:
                    color = (128, 128, 128)  # 灰色: 已出场
                    label = f"T{track.track_id}: EXITED"
                elif track.plate_text:
                    # 有车牌确认的车辆
                    if track.plate_text not in tracked_confirmed:
                        hash_val = hash(track.plate_text) % 0xFFFFFF
                        r = (hash_val >> 16) & 0xFF
                        g = (hash_val >> 8) & 0xFF
                        b = hash_val & 0xFF
                        color = (max(r, 80), max(g, 80), max(b, 80))
                        tracked_confirmed[track.plate_text] = color
                    else:
                        color = tracked_confirmed[track.plate_text]

                    record = entry_exit_mgr.records.get(track.plate_text)
                    if record:
                        if record.is_washed:
                            color = (0, 200, 255)
                        elif record.wash_start_time:
                            color = (0, 255, 255)

                    label = f"T{track.track_id}: {track.plate_text}"
                    if record and record.is_washed:
                        label += " WASHED"
                    elif record and record.wash_start_time:
                        elapsed = (datetime.now() - record.wash_start_time).total_seconds()
                        label += f" Wash:{elapsed:.0f}s"
                else:
                    # 未识别到车牌的车辆 - 使用青色显示
                    color = (0, 255, 255)
                    label = f"T{track.track_id}: {track.class_name}"

                cv2.rectangle(result_frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(result_frame, label, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            # === 绘制车牌识别结果（在车辆框内显示车牌框）===
            for result in plate_results:
                det = result['detection']
                if result.get('plate_bbox'):
                    px1, py1, px2, py2 = result['plate_bbox']
                    cv2.rectangle(result_frame, (px1, py1), (px2, py2), (0, 0, 255), 2)

            mgr_stats = entry_exit_mgr.get_statistics()
            tracker_stats = vehicle_tracker.get_statistics()
            video_elapsed = idx / fps
            video_min = int(video_elapsed // 60)
            video_sec = video_elapsed % 60

            with lock:
                unique_vehicles = len(stats['confirmed_vehicles'])

            info_text = [
                f"Video: {video_min:02d}:{video_sec:05.2f}",
                f"FPS: {processed_frames / max(1, time.time() - stats['start_time']):.1f}",
                f"Tracks: {tracker_stats['total_active']}",
                f"Confirmed: {unique_vehicles}",
                f"Entries: {mgr_stats['total_entries']}",
                f"Exits: {mgr_stats['total_exits']}",
                f"Washed: {mgr_stats['washed_count']}",
                f"Active: {mgr_stats['active_vehicles']}",
            ]
            y_offset = 30
            for text in info_text:
                cv2.putText(result_frame, text, (w - 300, y_offset),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                y_offset += 25

            # 每3帧发送一次到显示队列
            if frame_count % 1 == 0:
                try:
                    display_frame = cv2.resize(result_frame, (1280, 720))
                    display_queue.put(display_frame, block=False)
                except queue.Full:
                    pass  # 显示队列满，丢弃此帧

            # === 推流 ===
            if stream_publisher is not None:
                # 复用已 resize 好的 display_frame，或重新 resize
                if 'display_frame' in dir():
                    stream_frame = display_frame
                else:
                    stream_frame = cv2.resize(result_frame, (STREAM_WIDTH, STREAM_HEIGHT))
                stream_publisher.write_frame(stream_frame)

        frame_count += 1
        with lock:
            processed_frames += 1

        current_time = time.time()
        if current_time - last_log_time >= 5.0:
            with lock:
                total = stats['total_frames']
                proc = processed_frames
                elapsed = current_time - stats['start_time']
                avg_fps = proc / elapsed if elapsed > 0 else 0
                total_det = stats['total_detections']
                valid = stats['valid_plates']
                invalid = stats['invalid_plates']
                unique = len(stats['confirmed_vehicles'])
                mgr_stats = entry_exit_mgr.get_statistics()
                tracker_stats = vehicle_tracker.get_statistics()

            log(f"[Stats] Frames: {proc}/{total} ({proc/total*100:.1f}%), "
                f"FPS: {avg_fps:.1f}, "
                f"Video: {video_min:02d}:{video_sec:05.2f}, "
                f"Detections: {total_det}, Valid: {valid}, Invalid: {invalid}, "
                f"Tracks: {tracker_stats['total_active']}, "
                f"Confirmed: {unique}, "
                f"Entries: {mgr_stats['total_entries']}, "
                f"Exits: {mgr_stats['total_exits']}, "
                f"Washed: {mgr_stats['washed_count']}")

            # 上报统计
            if report_clients:
                stats_parts = []
                for client in report_clients:
                    rpt_stats = client.get_stats()
                    label = "Shznjz" if isinstance(client, ShznjzReportClient) else "Primary"
                    stats_parts.append(f"{label}:成功{rpt_stats['success']}/失败{rpt_stats['fail']}")
                log(f"[Report] {' | '.join(stats_parts)}")

            # 推流统计
            if stream_publisher is not None:
                pub_stats = stream_publisher.get_stats()
                reconnect_info = f", 重连:{pub_stats.get('frames_reconnected', 0)}次" if pub_stats.get('frames_reconnected', 0) > 0 else ""
                log(f"[Stream] 已推流:{pub_stats['frames_written']}帧, "
                    f"丢帧:{pub_stats['frames_dropped']}, "
                    f"推流FPS:{pub_stats['fps']:.1f}, "
                    f"队列:{pub_stats['queue_size']}{reconnect_info}")

            if skip_drawing and skipped_frames > 0:
                log(f"[Warning] Skipped {skipped_frames} frames due to display backlog")
                skipped_frames = 0
            if stats['confirmed_vehicles']:
                log(f"[Plates] {', '.join(sorted(stats['confirmed_vehicles']))}")
            for r in entry_exit_mgr.get_active_records():
                wash_info = ""
                if r.is_washed:
                    wash_info = " WASHED"
                elif r.wash_start_time:
                    elapsed_w = (datetime.now() - r.wash_start_time).total_seconds()
                    wash_info = f" Wash:{elapsed_w:.0f}s/{entry_exit_mgr.wash_stop_time}s"
                re_tag = " [RE]" if r.is_reentry else ""
                log(f"  Active: {r.license_plate}{wash_info}{re_tag}")
            last_log_time = current_time

    log("[Result Processor] Stopped")

# ============================================================
# 启动
# ============================================================

log("\nStarting threads (REALTIME)...")
log(f"  Frame interval: {frame_interval*1000:.1f}ms ({fps:.1f}fps)")

threads = [
    threading.Thread(target=video_reader_thread, name="VideoReader"),
    threading.Thread(target=vehicle_detection_thread, name="VehicleDetector"),
    threading.Thread(target=plate_detection_thread, name="PlateDetector"),
    threading.Thread(target=result_processing_thread, name="ResultProcessor"),
    threading.Thread(target=display_thread, name="Display"),
]

for t in threads:
    t.daemon = True
    t.start()

log("All threads started (5 threads)")
log("-" * 70)

try:
    if IS_STREAM:
        # 流模式：持续运行，等待用户中断
        log("[Main] Stream mode - running continuously. Press Ctrl+C to stop.")
        while True:
            time.sleep(1)
            if stop_event.is_set():
                break
    else:
        # 文件模式：等视频播放完
        threads[0].join(timeout=300.0)
        if threads[0].is_alive():
            log("[Main] VideoReader did not exit in time")

        if not stop_event.is_set():
            log("[Main] Video ended, signaling all threads to stop...")
            stop_event.set()

        for t in threads[1:]:
            t.join(timeout=5.0)
            if t.is_alive():
                log(f"[Main] Thread {t.name} did not exit in time")

except KeyboardInterrupt:
    log("\nUser interrupted")
    stop_event.set()

# 给所有线程一点时间处理停止信号
time.sleep(0.5)

for t in threads:
    t.join(timeout=5.0)
    if t.is_alive():
        log(f"[Main] Thread {t.name} did not exit in time during cleanup")

# 停止推流
if stream_publisher is not None:
    log("[Main] Stopping stream publisher...")
    stream_publisher.stop()

if db is not None:
    db.close()

for client in report_clients:
    if client is not None:
        client.close()

# 强制关闭所有OpenCV窗口
cv2.destroyAllWindows()
for i in range(10):
    cv2.waitKey(1)

log("[Main] All windows closed")

# ============================================================
# 最终统计
# ============================================================

log("\n" + "=" * 70)
log("PROCESSING COMPLETED!")
log("=" * 70)

with lock:
    total_frames = frame_idx
    processed = processed_frames
    elapsed = time.time() - stats['start_time']
    total_det = stats['total_detections']
    valid = stats['valid_plates']
    invalid = stats['invalid_plates']
    confirmed_list = stats['confirmed_vehicles']

dedup_stats = spatial_dedup.get_statistics()
confirmed_vehicles_detail = spatial_dedup.get_confirmed_vehicles()
mgr_stats = entry_exit_mgr.get_statistics()

log(f"\nPerformance:")
log(f"  Total frames: {total_frames}")
if total_frames > 0:
    log(f"  Processed: {processed} ({processed/total_frames*100:.1f}%)")
if elapsed > 0:
    log(f"  Average FPS: {processed/elapsed:.1f}")
log(f"  Video duration: {total_frames/fps:.1f}s")
log(f"  Processing time: {elapsed:.1f}s")

log(f"\nDetection Results:")
log(f"  Total vehicle detections: {total_det}")
log(f"  Valid plates detected: {valid}")
log(f"  Invalid plates filtered: {invalid}")

log(f"\nSpatial Deduplication Statistics:")
log(f"  Tracks created: {dedup_stats['tracks_created']}")
log(f"  Active tracks: {dedup_stats['active_tracks']}")
log(f"  Vehicles confirmed: {len(confirmed_vehicles_detail)}")
log(f"  Plates merged: {dedup_stats['plates_merged']}")

log(f"\nFinal Confirmed Vehicles ({len(confirmed_vehicles_detail)}):")
if confirmed_vehicles_detail:
    for i, vehicle in enumerate(confirmed_vehicles_detail, 1):
        plate_num = vehicle['plate_number']
        # 获取车牌颜色和类型信息
        from plate_validator_v2 import PlateValidatorV2
        plate_info = PlateValidatorV2.get_plate_info(plate_num)
        color_str = plate_info.get('plate_color', '未知')
        type_str = plate_info.get('plate_type', '未知')

        log(f"  {i}. [ID:{vehicle['vehicle_id']}] {plate_num}")
        log(f"     颜色: {color_str}, 类型: {type_str}, 长度: {len(plate_num)}位")
        log(f"     Detections: {vehicle['detection_count']}, "
            f"Confidence: {vehicle['confidence']:.1%}")
        if vehicle.get('merged'):
            log(f"     Candidates: {vehicle.get('candidate_plates', {})}")
else:
    log("  No vehicles confirmed")

log(f"\nEntry/Exit Statistics:")
log(f"  Total entries: {mgr_stats['total_entries']}")
log(f"  Total exits: {mgr_stats['total_exits']}")
log(f"  Washed: {mgr_stats['washed_count']}")
log(f"  Wash rate: {mgr_stats['wash_rate']:.1%}")
log(f"  Active vehicles: {mgr_stats['active_vehicles']}")

if report_clients:
    log(f"\nHTTP Report Statistics:")
    for client in report_clients:
        rpt_stats = client.get_stats()
        label = "Shznjz" if isinstance(client, ShznjzReportClient) else "Primary"
        log(f"  [{label}] Success: {rpt_stats['success']}, Fail: {rpt_stats['fail']}, Total: {rpt_stats['total']}")

if entry_exit_mgr.get_completed_records():
    log(f"\nCompleted Records:")
    for i, r in enumerate(entry_exit_mgr.get_completed_records(), 1):
        re_tag = " [二次进场]" if r.is_reentry else ""
        log(f"  {i}. {r.license_plate} - 停留{r.dwell_time:.0f}秒, "
            f"清洗={'是' if r.is_washed else '否'}{re_tag}")

if entry_exit_mgr.get_active_records():
    log(f"\nActive Records:")
    for i, r in enumerate(entry_exit_mgr.get_active_records(), 1):
        wash_info = ""
        if r.is_washed:
            wash_info = ", 已清洗"
        elif r.wash_start_time:
            elapsed_w = (datetime.now() - r.wash_start_time).total_seconds()
            wash_info = f", 清洗中:{elapsed_w:.0f}s"
        re_tag = " [二次进场]" if r.is_reentry else ""
        log(f"  {i}. {r.license_plate} - 在场{(datetime.now() - r.entry_time).total_seconds():.0f}秒"
            f"{wash_info}{re_tag}")

log("=" * 70)

cap.release()
log_file.close()
