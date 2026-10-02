"""
motion_fx.py — Cinematic Ken Burns Motion Engine
Chuyển đổi hình ảnh tĩnh 4K/HD thành video chuyển động máy quay 10s mượt mà bằng FFmpeg.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple


EFFECT_TYPES = [
    ("Phóng to trung tâm (Zoom In)", "zoom_in"),
    ("Thu nhỏ dần (Zoom Out)", "zoom_out"),
    ("Lia máy sang phải (Pan Right)", "pan_left_right"),
    ("Lia máy sang trái (Pan Left)", "pan_right_left"),
    ("Trôi nhẹ điện ảnh (Subtle Drift)", "subtle_drift"),
]


def get_ffmpeg_exe() -> str:
    """Tìm đường dẫn chính xác của file thực thi ffmpeg.exe trên hệ thống."""
    # 1. Tìm trong thư mục Scripts của python (.venv)
    py_dir = Path(sys.executable).parent
    if (py_dir / "ffmpeg.exe").exists():
        return str(py_dir / "ffmpeg.exe")
    if (py_dir / "ffmpeg").exists():
        return str(py_dir / "ffmpeg")
    
    # 2. Tìm qua PATH
    found = shutil.which("ffmpeg")
    if found:
        return found

    # 3. Tìm qua các đường dẫn dự án lân cận
    fallbacks = [
        r"D:\code\KathSldeToVideo\.venv\Scripts\ffmpeg.exe",
        r"D:\code\KathTrimmer\ffmpeg_bin\ffmpeg.exe",
    ]
    for fb in fallbacks:
        if os.path.exists(fb):
            return fb

    return "ffmpeg"


def create_ken_burns_video(
    image_path: str,
    output_video_path: str,
    duration_sec: float = 10.0,
    effect: str = "zoom_in",
    width: int = 1920,
    height: int = 1080,
    fps: int = 25,
    progress_callback: Optional[callable] = None,
) -> Tuple[bool, str]:
    """
    Tạo video MP4 chuyển động camera 10s (hoặc duration_sec) từ 1 file ảnh.
    """
    img_p = Path(image_path)
    if not img_p.exists():
        return False, f"File ảnh không tồn tại: {image_path}"

    out_p = Path(output_video_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg_bin = get_ffmpeg_exe()

    total_frames = int(duration_sec * fps)
    
    # Tính toán zoompan filter phù hợp
    if effect == "zoom_in":
        zoom_step = 0.25 / total_frames
        vf = f"scale=8000:-1,zoompan=z='min(zoom+{zoom_step:.6f},1.25)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps}"
    elif effect == "zoom_out":
        zoom_step = 0.25 / total_frames
        vf = f"scale=8000:-1,zoompan=z='if(lte(zoom,1.0),1.25,max(1.001,zoom-{zoom_step:.6f}))':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps}"
    elif effect == "pan_left_right":
        vf = f"scale=8000:-1,zoompan=z='1.15':d={total_frames}:x='(on/{total_frames})*(iw-iw/zoom)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps}"
    elif effect == "pan_right_left":
        vf = f"scale=8000:-1,zoompan=z='1.15':d={total_frames}:x='(1-on/{total_frames})*(iw-iw/zoom)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps}"
    else:  # subtle_drift
        zoom_step = 0.12 / total_frames
        vf = f"scale=8000:-1,zoompan=z='min(zoom+{zoom_step:.6f},1.12)':d={total_frames}:x='(on/{total_frames})*(iw-iw/zoom)/2':y='(on/{total_frames})*(ih-ih/zoom)/2':s={width}x{height}:fps={fps}"

    # Thêm pix_fmt yuv420p để tương thích tuyệt đối mọi trình phát video
    cmd = [
        ffmpeg_bin, "-y",
        "-loop", "1",
        "-i", str(img_p),
        "-vf", vf,
        "-c:v", "libx264",
        "-t", str(duration_sec),
        "-pix_fmt", "yuv420p",
        "-preset", "veryfast",
        str(out_p)
    ]

    try:
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo,
        )
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            # Fallback đơn giản nếu zoompan lỗi độ phân giải
            fallback_vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps={fps}"
            fallback_cmd = [
                ffmpeg_bin, "-y",
                "-loop", "1",
                "-i", str(img_p),
                "-vf", fallback_vf,
                "-c:v", "libx264",
                "-t", str(duration_sec),
                "-pix_fmt", "yuv420p",
                "-preset", "veryfast",
                str(out_p)
            ]
            fb_proc = subprocess.Popen(
                fallback_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
            )
            fb_proc.communicate()
            if fb_proc.returncode != 0:
                return False, f"FFmpeg error: {stderr.decode('utf-8', errors='ignore')[:300]}"

        return True, str(out_p)
    except Exception as exc:
        return False, str(exc)
