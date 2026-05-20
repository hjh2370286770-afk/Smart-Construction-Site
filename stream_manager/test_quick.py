import subprocess
import tempfile
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
sys.path.insert(0, str(Path.cwd() / 'detectors'))

import cv2
from detectors.ppe_detector import PPEDetector

stream_url = 'rtmp://rtmp05open.ys7.com:1935/v3/openlive/G49745764_1_1?expire=1805439206&id=956566417183907840&t=c08663468482dadc8848af79d473a956f8d8aa105fca33609790d99a2816e19e&ev=101'

print('=' * 70)
print('单帧 PPE 检测测试')
print('=' * 70)

# 下载一帧
print('\n[1/3] 下载视频帧...')
temp_path = tempfile.mktemp(suffix='.jpg')

cmd = [
    'ffmpeg',
    '-i', stream_url,
    '-ss', '00:00:02',
    '-vframes', '1',
    '-q:v', '2',
    '-y',
    temp_path
]

try:
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode != 0 or not os.path.exists(temp_path):
        print('[X] 下载失败')
        print('FFmpeg错误:', result.stderr.decode('utf-8', errors='ignore')[:500])
        exit(1)
except Exception as e:
    print(f'[X] FFmpeg错误: {e}')
    exit(1)

print('[OK] 帧下载成功')

# 加载图像
print('\n[2/3] 加载图像...')
frame = cv2.imread(temp_path)
os.remove(temp_path)

if frame is None:
    print('[X] 无法加载图像')
    exit(1)

print(f'[OK] 图像尺寸: {frame.shape[1]}x{frame.shape[0]}')

# 保存原图
output_original = 'test_g49745764_original.jpg'
cv2.imwrite(output_original, frame)
print(f'[OK] 原图已保存: {output_original}')

# 初始化检测器
print('\n[3/3] PPE 检测...')
detector = PPEDetector(conf_threshold=0.3)
detections = detector.detect(frame)

print(f'[OK] 检测到 {len(detections)} 个人员')

# 打印详情
for i, det in enumerate(detections):
    helmet_status = '[OK] 已戴' if det.has_helmet else '[X] 未戴'
    vest_status = '[OK] 已穿' if det.has_vest else '[X] 未穿'
    mask_status = '[OK] 已戴' if det.has_mask else '[X] 未戴'
    compliant_status = '[OK] 是' if det.is_compliant else '[X] 否'
    
    print(f'\n  人员 {i+1} (ID: {det.track_id}):')
    print(f'    安全帽: {helmet_status}')
    print(f'    反光衣: {vest_status}')
    print(f'    口罩: {mask_status}')
    print(f'    合规: {compliant_status}')

# 绘制结果
result_img = detector.draw_results(frame, detections)
output_result = 'test_g49745764_ppe_result.jpg'
cv2.imwrite(output_result, result_img)
print(f'\n[OK] 结果已保存: {output_result}')

print('\n' + '=' * 70)
print('测试完成')
print('=' * 70)
