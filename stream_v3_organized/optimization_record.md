# 项目优化记录

## 1. 业务流程梳理

### 1.1 核心业务链路

1. 视频源读取  
   `VideoCapture/流地址 -> video_reader_thread -> frame_queue`

2. 车辆检测  
   `vehicle_detection_thread -> detector.detect() -> detect_queue`

3. 跟踪与车牌识别  
   `plate_detection_thread -> vehicle_tracker.update() -> detect_license_plate() -> validate_plate_v2() -> spatial_dedup.add_detection()`

4. 业务判定  
   `EntryExitManager.on_plate_confirmed()/check_missing_vehicles()/check_exits()`

5. 结果输出  
   `result_processing_thread -> display_queue -> display_thread`

6. 扩展能力  
   - HTTP 上报：`ReportClient`
   - SQLite 落库：`VehicleWashDB`
   - FFmpeg 推流：`FFmpegStreamPublisher`

### 1.2 模块依赖关系

- `main/test_full_video_auto_login-v1.0.py`
  - 依赖 `streaming/stream_publisher.py`
  - 依赖 `tracking/vehicle_tracker.py`
  - 依赖 `tracking/spatial_plate_deduplicator.py`
  - 依赖 `tracking/plate_validator_v2.py`
  - 依赖 `database/vehicle_wash_db.py`
- `tests/test_video_file.py`
  - 与主流程共用跟踪、去重、校验模块
- `tools/profile_memory_hotspots.py`
  - 用于复现实测内存/热点基准

## 2. 本轮优化目标

- 不改变原有核心业务判定逻辑
- 降低推流与抓拍相关内存占用
- 减少主流程中的重复计算与阻塞等待
- 补齐线程、Session、数据库、子进程的关闭链路
- 让回归脚本与主流程采用一致的队列/退出语义

## 3. 具体优化项

### 3.1 上报模块优化

**文件**
- `main/test_full_video_auto_login-v1.0.py`

**改动**
- `ReportClient` 从“每次事件创建 daemon 线程”改为固定大小 `ThreadPoolExecutor`
- 增加 `_lock`、`close()`、线程安全统计
- 上报任务改为后台执行，主链路只负责投递任务
- HTTP 响应对象显式 `close()`

**目的**
- 避免上报线程无限增长
- 降低网络抖动时的线程堆积
- 保证程序退出时连接池和后台任务能有序释放

**业务验证**
- 解释器级编译通过
- 上报客户端相关改动未引入静态诊断问题
- 通过主脚本整体语法校验确认可装载

### 3.2 推流模块优化

**文件**
- `streaming/stream_publisher.py`

**改动**
- 推流队列从固定大缓冲改为可配置 `queue_size`，主流程默认接入 `20`
- 队列满时启用“丢弃最旧帧”策略，保证低延迟而不是无限堆积
- 新增 `stderr_thread` 管理
- 统一封装 `_cleanup_process()`、`_drain_frame_queue()`
- `stop()` / `_restart_ffmpeg()` 补齐 `stdin/stdout/stderr` 关闭与线程回收

**目的**
- 显著降低原始帧在内存中的堆积风险
- 避免 FFmpeg 重连后残留管道句柄和监控线程
- 提高推流模块的可回收性和可维护性

**业务验证**
- `python -c` 实例化校验通过
- 队列行为回归：`queue_size=2 tail_values=[1, 2]`，确认满队列后保留最新帧
- 解释器级编译通过

### 3.3 跟踪器与主流程耦合优化

**文件**
- `tracking/vehicle_tracker.py`
- `main/test_full_video_auto_login-v1.0.py`
- `tests/test_video_file.py`

**改动**
- 在 `VehicleTracker.update()` 中保存最近一次 `detection_index -> track_id` 映射
- 主流程和文件模式测试脚本直接复用该映射
- 删除主流程中基于 `bbox == det.bbox` 的二次全量匹配

**目的**
- 减少一轮额外的 O(T*D) 匹配
- 让跟踪和识别之间的数据关系更明确
- 提升代码可读性，降低后续维护成本

**业务验证**
- 冒烟回归：`map1={0: 1} map2={0: 1} active_ids=[1]`
- 说明同一目标在相邻帧中保持同一 track_id

### 3.4 车牌相似度热点优化

**文件**
- `tracking/spatial_plate_deduplicator.py`

**改动**
- `_calculate_plate_similarity()` 改为统一复用 `plate_utils.plate_similarity`

**目的**
- 消除重复实现
- 直接复用带缓存的公共热点路径
- 降低去重阶段重复编辑距离计算的开销

**业务验证**
- `tools/profile_memory_hotspots.py` 重新执行通过
- 优化后当前“普通路径”和“缓存路径”耗时接近，说明热点已复用到缓存实现

### 3.5 主流程内存与退出语义优化

**文件**
- `main/test_full_video_auto_login-v1.0.py`
- `tests/test_video_file.py`

**改动**
- `EntryExitManager.set_current_frame()` 改为保留引用，不再每帧复制整图
- 进/出场上报提交后立刻释放 `entry_frame/exit_frame`
- `check_missing_vehicles()` 改为根车牌集合判断，减少逐项重复比较
- `get_statistics()` 改为生成器计数，避免频繁创建中间列表
- 新增 `queue_put_with_stop()`，统一 `detect_queue/result_queue` 的可停止写入语义
- 清理阶段补齐线程 `join`、`db.close()`、`report_client.close()`、`cap.release()`、`log_file.close()`

**目的**
- 避免每帧多余的整图拷贝
- 避免抓拍图片在内存中长期驻留
- 防止队列阻塞导致线程在退出时卡死
- 让主流程和测试流程都具备更稳定的资源回收路径

**业务验证**
- 主脚本静态诊断通过
- 文件模式脚本静态诊断通过
- `python -m py_compile ...` 全部通过

## 4. 回归测试记录

### 4.1 已执行

1. **解释器编译回归**
   - 命令：
     `python -m py_compile main/test_full_video_auto_login-v1.0.py streaming/stream_publisher.py tracking/vehicle_tracker.py tracking/spatial_plate_deduplicator.py tests/test_video_file.py tools/profile_memory_hotspots.py`
   - 结果：通过

2. **内存/热点基准回归**
   - 命令：
     `python tools/profile_memory_hotspots.py`
   - 结果：通过
   - 观察：
     - `queue_300_720p_delta_mb=792.2`
     - `shots_50x2_1080p_delta_mb=593.4`
     - 当前相似度热点已走统一缓存路径

3. **跟踪映射回归**
   - 命令：内联 Python 冒烟脚本
   - 结果：通过
   - 观察：相邻帧同一目标维持同一 `track_id`

4. **推流队列策略回归**
   - 命令：内联 Python 冒烟脚本
   - 结果：通过
   - 观察：队列满时淘汰旧帧，保留最新两帧

5. **现有规则测试回归**
   - 命令：
     `$env:PYTHONPATH='tracking'; python tests/test_plate_validator_v2.py`
   - 结果：脚本可运行，但原有白牌/黑牌相关断言仍失败
   - 说明：该失败为项目既有规则覆盖缺口，不是本轮性能优化引入

### 4.2 未完成的端到端验证项

- `main/test_full_video_auto_login-v1.0.py` 的真实端到端视频跑测
- `tests/test_video_file.py` 的本地视频完整跑测
- 真实 HTTP 上报链路联调
- 真实 FFmpeg 推流链路联调

**原因**
- 当前工作区缺少稳定可复用的模型文件、视频样本、外部流地址可用性保证和真实服务端联调环境。

## 5. 业务影响评估

### 保持不变

- 车辆检测、车牌识别、空间去重、进出场判定、清洗判定的核心业务规则未被重写
- SQLite 落库流程未改表结构
- 推流输出协议和主参数接口保持兼容
- 现有多线程流水线结构保持不变

### 改善点

- 主流程在高并发上报和推流积压时更稳定
- 退出阶段更不容易出现资源残留
- 跟踪到识别的链路更直接
- 相似度热点和统计路径更轻量

## 6. 下一步建议

1. 结合真实视频样本执行 30 分钟稳定性跑测
2. 对主脚本和文件模式脚本分别采集：
   - RSS 峰值
   - 平均 FPS
   - 推流队列占用
   - 上报成功率
3. 补充白牌/黑牌规则测试，避免测试基线本身不稳定
4. 若继续推进，可在下一轮引入：
   - track 级 OCR 节流
   - 抓拍 ROI/JPEG 化替代整帧缓存
   - 端到端性能指标自动采集脚本

