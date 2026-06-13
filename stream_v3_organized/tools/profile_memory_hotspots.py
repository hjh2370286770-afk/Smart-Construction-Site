#!/usr/bin/env python
"""
Micro-benchmarks for the current memory/performance hotspots.

This script does not require model weights or live video input. It measures:
1. Queue memory footprint for buffered frames.
2. Snapshot retention footprint for entry/exit images.
3. Plate similarity hotspot cost with and without cache reuse.

Usage:
    python tools/profile_memory_hotspots.py
"""

import gc
import os
import sys
import time
from queue import Queue

import numpy as np
import psutil


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACKING_DIR = os.path.join(REPO_ROOT, "tracking")
if TRACKING_DIR not in sys.path:
    sys.path.insert(0, TRACKING_DIR)

from spatial_plate_deduplicator import SpatialPlateDeduplicator  # noqa: E402
from plate_utils import levenshtein_distance, plate_similarity  # noqa: E402


def rss_mb() -> float:
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024


def benchmark_frame_queue(frame_count: int = 300, width: int = 1280, height: int = 720) -> float:
    queue_obj = Queue(maxsize=frame_count)
    frames = []
    start = rss_mb()

    for idx in range(frame_count):
        frame = np.full((height, width, 3), idx % 255, dtype=np.uint8)
        queue_obj.put(frame)
        frames.append(frame)

    delta = rss_mb() - start

    del frames
    while not queue_obj.empty():
        queue_obj.get()
    gc.collect()
    time.sleep(0.2)

    return delta


def benchmark_snapshots(vehicle_count: int = 50, width: int = 1920, height: int = 1080) -> float:
    snapshots = []
    start = rss_mb()

    for idx in range(vehicle_count):
        entry_frame = np.full((height, width, 3), idx % 255, dtype=np.uint8)
        exit_frame = np.full((height, width, 3), (idx + 1) % 255, dtype=np.uint8)
        snapshots.append((entry_frame, exit_frame))

    delta = rss_mb() - start

    del snapshots
    gc.collect()
    time.sleep(0.2)

    return delta


def benchmark_similarity(iterations: int = 20000) -> tuple:
    pairs = [
        ("HUA12345", "HUA1234S"),
        ("HAD12345", "HA012345"),
        ("JIB12345", "JIB1234S"),
    ] * iterations

    dedup = SpatialPlateDeduplicator()

    start = time.perf_counter()
    for plate_a, plate_b in pairs:
        dedup._calculate_plate_similarity(plate_a, plate_b)
    plain_secs = time.perf_counter() - start

    levenshtein_distance.cache_clear()
    start = time.perf_counter()
    for plate_a, plate_b in pairs:
        plate_similarity(plate_a, plate_b)
    cached_secs = time.perf_counter() - start

    return plain_secs, cached_secs


def main() -> int:
    baseline = rss_mb()
    queue_delta = benchmark_frame_queue()
    after_queue = rss_mb()
    snapshot_delta = benchmark_snapshots()
    after_snapshots = rss_mb()
    plain_secs, cached_secs = benchmark_similarity()
    speedup = plain_secs / cached_secs if cached_secs else 0.0

    print("=== Memory / Performance Micro Benchmarks ===")
    print(f"baseline_rss_mb={baseline:.1f}")
    print(f"queue_300_720p_delta_mb={queue_delta:.1f}")
    print(f"after_queue_cleanup_rss_mb={after_queue:.1f}")
    print(f"shots_50x2_1080p_delta_mb={snapshot_delta:.1f}")
    print(f"after_shots_cleanup_rss_mb={after_snapshots:.1f}")
    print(f"similarity_plain_secs={plain_secs:.4f}")
    print(f"similarity_cached_secs={cached_secs:.4f}")
    print(f"similarity_speedup_x={speedup:.2f}")
    print()
    print("Recommendations:")
    print("- Reduce frame queue capacity or switch to overwrite/drop-oldest semantics.")
    print("- Store event snapshots as JPEG bytes or ROI instead of full-frame numpy arrays.")
    print("- Reuse cached plate similarity helpers on hot paths.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
