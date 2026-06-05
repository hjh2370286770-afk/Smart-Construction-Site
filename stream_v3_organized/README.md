# Vehicle Wash Recognition System

## Project Overview
YOLOv8-based vehicle detection + license plate recognition system with entry/exit management, wash determination, and RTMP/RTSP streaming.

---

## Directory Structure

```
stream_v3_organized/
├── main/                          # Main program entry
│   └── test_full_video_auto_login-v1.0.py
│
├── detectors/                     # Detector modules
│   ├── __init__.py
│   ├── base_detector.py           # Base detector class
│   ├── vehicle_wash_detector.py   # Vehicle + plate detector
│   └── plate_detector.py          # Plate detector (YOLOv8)
│
├── plate_recognition/             # Plate recognition submodule
│   ├── plate_rec.py               # Core recognition logic
│   ├── plateNet.py                # Recognition network
│   └── double_plate_split_merge.py # Double-layer plate handling
│
├── tracking/                      # Tracking & deduplication
│   ├── vehicle_tracker.py         # IOU-based vehicle tracking
│   ├── spatial_plate_deduplicator.py # Spatial plate deduplication
│   ├── plate_validator_v2.py      # Plate validation v2 (color-based)
│   └── plate_utils.py             # Plate utilities
│
├── database/                      # Data storage
│   └── vehicle_wash_db.py         # SQLite database operations
│
├── streaming/                     # Streaming module
│   └── stream_publisher.py        # FFmpeg RTMP/RTSP publisher
│
├── models/                        # Model files
│   ├── yolov8n.pt                 # Vehicle detection model (~6MB)
│   ├── yolov8s.pt                 # Plate detection model (~22MB)
│   └── plate_rec_color.pth        # Plate recognition model (~30MB)
│
├── config/                        # Configuration files
│   ├── vehicle_wash_config.yaml
│   ├── models.yaml
│   ├── sites.yaml
│   └── mediamtx.yml
│
├── tools/                         # Utility scripts
│   ├── export_db_to_excel.py
│   ├── extract_frame.py
│   ├── check_gpu.py
│   └── install_gpu_pytorch.py
│
└── tests/                         # Test files
    ├── test_video_file.py
    ├── test_single_plate.py
    ├── test_plate_validator_v2.py
    ├── test_detector.py
    ├── test_paddleocr.py
    └── test_ocr.py
```

---

## Path Configuration

All paths are configured to be relative to the `stream_v3_organized/` directory:

| Resource | Path |
|----------|------|
| Vehicle model | `models/yolov8n.pt` |
| Plate detection model | `models/yolov8s.pt` |
| Plate recognition model | `models/plate_rec_color.pth` |
| Database | `vehicle_wash.db` (created at runtime) |
| Config files | `config/*.yaml` |

---

## How to Run

```bash
cd stream_v3_organized
python main/test_full_video_auto_login-v1.0.py
```

---

## Dependencies

```bash
pip install ultralytics torch torchvision opencv-python numpy requests
```

---

## Key Modifications for Organized Structure

1. **Import paths**: Changed from `from detectors.xxx` to direct imports with `sys.path` insertion
2. **Model paths**: All model paths now point to `models/`
3. **Database path**: Set to project root (`vehicle_wash.db`)
4. **Plate recognition imports**: Updated to use `plate_recognition/` directly
