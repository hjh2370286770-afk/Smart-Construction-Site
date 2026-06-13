# Memory and Performance Audit Report

## 1. Scope

- Project type: Python-based vehicle wash recognition and streaming pipeline.
- Audit goal: identify memory leaks, memory retention, invalid memory occupation, and runtime bottlenecks.
- Primary targets:
  - `main/test_full_video_auto_login-v1.0.py`
  - `tests/test_video_file.py`
  - `streaming/stream_publisher.py`
  - `tracking/spatial_plate_deduplicator.py`
  - `tracking/vehicle_tracker.py`
  - `database/vehicle_wash_db.py`

## 2. Method

### 2.1 Static review

- Reviewed thread, queue, snapshot, cache, network, subprocess, database, and tracker lifecycles.
- Focused on heap retention, unbounded object growth, unreleased resources, and repeated heavy computation.

### 2.2 Runtime evidence

- Verified local Python runtime and key dependencies:
  - Python 3.8.0
  - `cv2`, `numpy`, `requests`, `torch`, `yaml`, `psutil` available
- Executed:
  - `python tools/profile_memory_hotspots.py`
  - `$env:PYTHONPATH='tracking'; python tests/test_plate_validator_v2.py`
- Runtime limitation:
  - Full end-to-end live stream reproduction was not completed in this workspace because it depends on external video sources, model weights, ffmpeg runtime behavior, and remote endpoints.
  - The delivered micro-benchmarks are designed to reproduce the dominant memory and CPU pressure points without those external dependencies.

## 3. Key Findings

### P0 - High priority

1. **Full-frame snapshots are retained in long-lived records**
   - `EntryExitManager.set_current_frame()` copies the whole frame into `current_frame`.
   - Entry and exit paths copy the whole frame again into `entry_frame` and `exit_frame`.
   - `self.records` keeps history and does not prune completed records aggressively.
   - Impact:
     - memory grows linearly with vehicle count and frame size.
     - 50 vehicles x 2 retained 1080p snapshots consumed about **593.4 MB** in the local benchmark.

2. **Stream publisher queue is oversized for raw frames**
   - `FFmpegStreamPublisher.frame_queue = queue.Queue(maxsize=300)` stores raw numpy frames.
   - At 1280x720x3, a full queue consumed about **792.2 MB** in the local benchmark.
   - Impact:
     - large idle or backpressure windows translate directly into RAM spikes.
     - GC cannot reduce peak pressure while references stay inside the queue.

3. **Resource shutdown is incomplete**
   - `ReportClient` creates a long-lived `requests.Session()` but does not expose `close()`.
   - Main flow does not call `db.close()`.
   - `FFmpegStreamPublisher.stop()` closes `stdin` only and does not close `stdout` / `stderr`.
   - Impact:
     - sockets, connection pools, process pipes, and SQLite handles can remain open longer than intended.
     - repeated restarts increase leak-like symptoms.

4. **One request creates one thread**
   - `ReportClient.report()` starts a new daemon thread per event.
   - The shared session and success/fail counters are used concurrently without a clear lifecycle boundary.
   - Impact:
     - thread accumulation under network slowdown.
     - more context switching and higher memory overhead.

### P1 - Medium priority

5. **Hot path repeats plate validation and similarity work**
   - Main flow validates plate text before deduplication.
   - `SpatialPlateDeduplicator.add_detection()` validates again.
   - Deduplicator uses its own non-cached Levenshtein path instead of `tracking/plate_utils.py`.
   - Local benchmark showed the cached helper is about **15.23x** faster on repeated similarity pairs.

6. **Per-frame OCR is too expensive**
   - Every detected vehicle can trigger plate detection and OCR again, even for stable tracks.
   - Impact:
     - CPU/GPU time scales with frame count, not meaningful object change.
     - throughput drops first on busy scenes.

7. **Queue stop semantics are fragile**
   - `detect_queue.put(..., block=True)` and `result_queue.put(..., block=True)` can block shutdown.
   - Daemon threads hide incomplete teardown instead of enforcing clean exit.

8. **Extra O(T x D) rematching happens after tracker update**
   - Tracker already computes detection/track association.
   - Main flow performs another bbox-based mapping pass.
   - Impact:
     - avoidable CPU load in dense scenes.

### P2 - Correctness and maintainability risks

9. **Shared mutable state is accessed across threads without a consistent lock strategy**
   - `records`, `current_frame`, and several counters are read and written by different threads.
   - Impact:
     - inconsistent statistics.
     - hard-to-reproduce race behavior during shutdown.

10. **Non-memory residual issue found during runnable test**
    - `tests/test_plate_validator_v2.py` currently reports failures for white and black plate cases.
    - This is not a memory issue, but it should be fixed before using those tests as a release gate.

## 4. Root Cause Summary

- The pipeline is frame-centric, so expensive work is repeated every frame instead of every meaningful object state change.
- Large numpy images are copied and retained as business objects.
- Queues favor buffering over bounded latency and memory safety.
- Long-lived resources lack a unified shutdown contract.
- Some hot-path helpers bypass the already optimized shared utility implementation.

## 5. Optimization Plan

### 5.1 Memory reduction

1. **Replace full-frame retention with compact event snapshots**
   - Keep only:
     - vehicle ROI, or
     - plate ROI, or
     - JPEG bytes, or
     - a path to an asynchronously persisted image file
   - Do not store raw full-frame numpy arrays in `VehicleRecord`.

2. **Prune historical records**
   - Keep active records in memory.
   - Move completed records to DB and lightweight summaries.
   - Retain only the latest N exited records in RAM for re-entry matching.

3. **Shrink streaming queue**
   - Reduce `frame_queue` from 300 to a small bounded range such as 10-30.
   - Prefer drop-oldest or overwrite semantics over unlimited backlog growth.

4. **Explicit close contract**
   - Add `close()` / `release()` to:
     - `ReportClient`
     - detector wrappers
     - stream publisher
     - main runtime orchestration

5. **Add memory threshold alarms**
   - Log RSS and queue size every 30s.
   - Trigger warnings when:
     - RSS exceeds a configurable threshold
     - stream queue occupancy exceeds 70%
     - active record count exceeds a safe cap

### 5.2 Throughput improvement

1. **Track-level OCR throttling**
   - Re-run plate OCR only when:
     - a track is new,
     - bbox size changes significantly,
     - image quality improves,
     - or the last OCR result is stale.

2. **Single validation pass**
   - Keep validation in one layer only.
   - Pass the cleaned plate text downstream.

3. **Reuse cached similarity helper**
   - Replace the deduplicator's local distance implementation with `plate_utils.plate_similarity`.

4. **Return association map from tracker**
   - Modify tracker update to return `det_idx -> track_id`.
   - Remove the second rematching loop in the main thread.

5. **Reduce duplicate resize/copy work**
   - Reuse one resized frame for display and publishing when possible.
   - Skip visualization work completely in headless mode.

6. **Use a bounded worker pool for reporting**
   - Replace "one event, one thread" with `ThreadPoolExecutor(max_workers=2..4)` and a small queue.

### 5.3 Stability and lifecycle

1. **Use timeout-aware queue operations**
   - All producer and consumer queue operations should honor `stop_event`.
   - Prevent indefinite blocking on shutdown.

2. **Use non-daemon workers where cleanup matters**
   - Signal stop.
   - Drain queues or stop accepting work.
   - Join workers.
   - Release resources in deterministic order.

3. **Close subprocess pipes fully**
   - Close `stdin`, `stdout`, and `stderr`.
   - Join the stderr monitor thread.

## 6. Code Change Examples

### 6.1 Replace retained numpy snapshots with JPEG bytes

Target: `main/test_full_video_auto_login-v1.0.py`

```python
from dataclasses import dataclass, field
from typing import Optional
import cv2


def encode_snapshot(frame, quality=70):
    if frame is None:
        return None
    ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buffer.tobytes() if ok else None


@dataclass
class VehicleRecord:
    vehicle_id: str
    license_plate: str
    entry_snapshot_jpg: Optional[bytes] = None
    exit_snapshot_jpg: Optional[bytes] = None
```

```python
# on entry
record.entry_snapshot_jpg = encode_snapshot(vehicle_roi_or_frame)

# on exit
record.exit_snapshot_jpg = encode_snapshot(vehicle_roi_or_frame)

# after successful upload
record.entry_snapshot_jpg = None
record.exit_snapshot_jpg = None
```

Expected gain:
- event memory falls from raw frame size to compressed JPEG size.
- for 1080p frames, practical footprint often drops by 80% to 95% depending on content.

### 6.2 Add deterministic close() to ReportClient

Target: `main/test_full_video_auto_login-v1.0.py`

```python
from concurrent.futures import ThreadPoolExecutor
import threading


class ReportClient:
    def __init__(self, device_id, report_url, oss_url, enable=True):
        self.device_id = device_id
        self.report_url = report_url
        self.oss_url = oss_url
        self.enable = enable
        self.success_count = 0
        self.fail_count = 0
        self._lock = threading.Lock()
        self._session = requests.Session()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="report")

    def report(self, license_plate, inouttype, iswash, frame, datatype=0):
        if not self.enable:
            return False
        payload = self._build_payload(license_plate, inouttype, iswash, frame, datatype)
        if not payload:
            return False
        self._pool.submit(self._do_report, payload, license_plate, inouttype)
        return True

    def _mark_success(self):
        with self._lock:
            self.success_count += 1

    def _mark_fail(self):
        with self._lock:
            self.fail_count += 1

    def close(self):
        self._pool.shutdown(wait=True, cancel_futures=False)
        self._session.close()
```

```python
try:
    ...
finally:
    stop_event.set()
    for t in threads:
        t.join(timeout=5.0)
    if stream_publisher:
        stream_publisher.stop()
    if db:
        db.close()
    if report_client:
        report_client.close()
    cap.release()
    log_file.close()
```

Expected gain:
- eliminates unbounded background thread growth.
- avoids session/socket leakage across long runs and restarts.

### 6.3 Reduce stream queue memory pressure

Target: `streaming/stream_publisher.py`

```python
self.frame_queue = queue.Queue(maxsize=20)
```

```python
def write_frame(self, frame: np.ndarray):
    if self.stop_event.is_set() or self.ffmpeg_process is None:
        return
    try:
        self.frame_queue.put(frame, block=False)
    except queue.Full:
        try:
            _ = self.frame_queue.get_nowait()
        except queue.Empty:
            pass
        try:
            self.frame_queue.put_nowait(frame)
        except queue.Full:
            self.stats["frames_dropped"] += 1
```

Expected gain:
- peak queue RAM falls by more than 90% when queue size drops from 300 to 20.

### 6.4 Replace local similarity logic with cached shared helper

Target: `tracking/spatial_plate_deduplicator.py`

```python
from plate_utils import plate_similarity


def _calculate_plate_similarity(self, plate1: str, plate2: str) -> float:
    return plate_similarity(plate1, plate2)
```

Expected gain:
- repeated similarity checks become much cheaper.
- local benchmark measured about 15x acceleration on repeated pairs.

### 6.5 Track-level OCR throttling

Target: `main/test_full_video_auto_login-v1.0.py`

```python
last_ocr_state = {}


def should_run_ocr(track_id, bbox, frame_idx, every_n_frames=6):
    prev = last_ocr_state.get(track_id)
    if prev is None:
        last_ocr_state[track_id] = (bbox, frame_idx)
        return True

    old_bbox, old_idx = prev
    if frame_idx - old_idx >= every_n_frames:
        last_ocr_state[track_id] = (bbox, frame_idx)
        return True

    old_area = max(1, (old_bbox[2] - old_bbox[0]) * (old_bbox[3] - old_bbox[1]))
    new_area = max(1, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
    if abs(new_area - old_area) / old_area > 0.25:
        last_ocr_state[track_id] = (bbox, frame_idx)
        return True

    return False
```

Expected gain:
- OCR frequency becomes proportional to track changes instead of raw frame rate.
- this is the most important throughput optimization candidate.

## 7. Validation Plan

### 7.1 Required metrics

- RSS memory:
  - average
  - peak
  - 30-minute drift
- GC:
  - collection frequency
  - pause duration
- Queue health:
  - max occupancy
  - average occupancy
  - dropped frame count
- Throughput:
  - end-to-end FPS
  - vehicle detection latency
  - plate OCR latency
  - publish latency
- CPU:
  - process CPU
  - hottest thread CPU
- Stability:
  - restart success rate
  - clean shutdown success

### 7.2 Test procedure

1. **Baseline run**
   - Run current code for at least 30 minutes on:
     - low traffic video
     - medium traffic video
     - worst-case dense traffic video
   - Sample RSS, CPU, queue occupancy every 5s.

2. **Micro-benchmark run**
   - Execute `python tools/profile_memory_hotspots.py`.
   - Record queue memory delta, snapshot memory delta, and similarity benchmark time.

3. **After each optimization phase**
   - Repeat the same video workload and the same micro-benchmark.
   - Compare against baseline on identical resolution, FPS, and model settings.

4. **Shutdown test**
   - Trigger Ctrl+C.
   - Confirm no stuck queue, no orphan worker, no ffmpeg process, no open DB lock.

### 7.3 Acceptance targets

- Memory:
  - peak RSS reduced by **30% or more**
  - no monotonic growth during a 30-minute steady-state run
- Throughput:
  - core scenario FPS or response speed improved by **25% or more**
- Stability:
  - clean shutdown in all tested modes
  - no new resource leakage symptoms after repeated restart tests

## 8. Recommended Delivery Order

### Phase 1 - Immediate

- Shrink stream queue.
- Replace retained snapshots with JPEG bytes or ROI.
- Add `close()` for report client, DB, and publisher.
- Make queue operations timeout-aware.

### Phase 2 - High ROI

- Add track-level OCR throttling.
- Remove duplicate validation.
- Replace local similarity logic with cached shared helper.
- Remove second track mapping loop.

### Phase 3 - Hardening

- Add memory / queue alarms.
- Add periodic metric logging.
- Add repeatable performance regression scripts for CI or release checks.

## 9. Deliverables

- This report: `memory_performance_audit_report.md`
- Runnable hotspot benchmark: `tools/profile_memory_hotspots.py`

