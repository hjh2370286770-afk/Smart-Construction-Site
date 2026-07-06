"""
多项目启动器
在单台电脑上同时启动多个车辆清洗检测实例，每个实例使用独立配置。

用法：
    python main/run_all_projects.py

说明：
    - 每个项目以独立进程运行，拥有独立的日志、数据库和显示窗口。
    - 多进程会各自加载一次检测模型，对 GPU 显存要求较高；
      如果显存不足，可考虑关闭部分项目的显示窗口（no_display: true）或只运行关键项目。
    - 按 Ctrl+C 可统一停止所有项目。
"""

import subprocess
import sys
import time
import signal
from pathlib import Path


PROJECTS = [
    {
        'name': 'JUNHE_106_01',
        'config': 'config/project_JUNHE_106_01.yaml',
        'display': True,
    },
    {
        'name': 'JUNHE_CHENJIA_02',
        'config': 'config/project_JUNHE_CHENJIA_02.yaml',
        'display': False,
    },
]

MAIN_SCRIPT = Path(__file__).parent / 'test_full_video_auto_login-v1.0.py'


def start_projects():
    """启动所有项目进程"""
    processes = []
    for p in PROJECTS:
        cmd = [
            sys.executable,
            str(MAIN_SCRIPT),
            '--config', p['config'],
        ]
        if not p.get('display', True):
            cmd.append('--no-display')

        print(f"[Launcher] 启动项目 {p['name']}: {' '.join(cmd)}")
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=Path(__file__).parent.parent,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0,
            )
            processes.append((p['name'], proc))
        except Exception as e:
            print(f"[Launcher] 启动项目 {p['name']} 失败: {e}")

    return processes


def stop_projects(processes):
    """停止所有项目进程"""
    print("\n[Launcher] 正在停止所有项目...")
    for name, proc in processes:
        if proc.poll() is None:
            print(f"[Launcher] 停止 {name} (PID {proc.pid})")
            try:
                if sys.platform == 'win32':
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    proc.send_signal(signal.SIGINT)
            except Exception as e:
                print(f"[Launcher] 发送停止信号失败: {e}")

    # 等待进程退出
    for name, proc in processes:
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            print(f"[Launcher] {name} 未在 10s 内退出，强制终止")
            proc.kill()


def main():
    print("=" * 70)
    print("车辆清洗检测 - 多项目启动器")
    print(f"主程序: {MAIN_SCRIPT}")
    print(f"项目数: {len(PROJECTS)}")
    print("=" * 70)

    processes = start_projects()
    print(f"\n[Launcher] 已启动 {len(processes)} 个项目")
    for name, proc in processes:
        print(f"  - {name}: PID {proc.pid}")
    print("[Launcher] 按 Ctrl+C 统一停止\n")

    try:
        while True:
            # 检查是否有进程异常退出
            for name, proc in list(processes):
                ret = proc.poll()
                if ret is not None:
                    print(f"[Launcher] 项目 {name} 已退出，返回码: {ret}")
                    processes.remove((name, proc))

            if not processes:
                print("[Launcher] 所有项目均已退出")
                break

            time.sleep(2)
    except KeyboardInterrupt:
        stop_projects(processes)

    print("[Launcher] 已退出")


if __name__ == '__main__':
    main()
