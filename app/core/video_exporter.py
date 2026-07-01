"""
video_exporter.py — Kết hợp slide PNG + MP3 → MP4
Dùng ffmpeg để tạo video: mỗi slide hiện đúng thời điểm dựa trên timestamps.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from app.core.slide_processor import SlideInfo


# ═══════════════════════════════════════════════════════════════════════════
#  DATA
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class SlideTimedEntry:
    """Một slide với thời điểm bắt đầu/kết thúc (giây)."""
    slide: SlideInfo
    start_sec: float
    end_sec: float      # = start của slide tiếp theo (hoặc tổng thời lượng)
    duration_sec: float


# ═══════════════════════════════════════════════════════════════════════════
#  CHAR POSITION → TIMESTAMP MAPPING
# ═══════════════════════════════════════════════════════════════════════════

def build_char_to_ms_map(script_text: str, json_data: dict) -> List[tuple[int, int]]:
    """
    Xây dựng danh sách (char_pos, time_ms) để biết từng ký tự
    trong script_text tương ứng với giây nào trong audio.

    Cách tính:
    - script_text được chia thành các câu (giống lúc TTS)
    - JSON có start_ms/end_ms cho từng câu
    - Nội suy tuyến tính: char_pos trong câu → ms tương ứng
    """
    from app.core.mp3_exporter import split_into_sentences

    sentences = split_into_sentences(script_text)
    json_sentences = json_data.get("sentences", [])

    # Build mapping: list of (char_start_in_full_text, start_ms, end_ms)
    mapping: List[tuple[int, int, int]] = []
    char_cursor = 0

    for i, sent_text in enumerate(sentences):
        # Tìm vị trí của câu này trong full text
        char_start = script_text.find(sent_text, char_cursor)
        if char_start == -1:
            char_start = char_cursor
        char_end = char_start + len(sent_text)
        char_cursor = char_end

        # Lấy timing từ JSON
        if i < len(json_sentences):
            start_ms = json_sentences[i].get("start_ms", 0)
            end_ms   = json_sentences[i].get("end_ms", start_ms + 1000)
        else:
            # Fallback: ước tính 150ms/ký tự
            prev_end = mapping[-1][2] if mapping else 0
            start_ms = prev_end + 300
            end_ms   = start_ms + len(sent_text) * 150

        mapping.append((char_start, start_ms, end_ms))

    return mapping


def char_pos_to_ms(char_pos: int, mapping: List[tuple[int, int, int]]) -> float:
    """
    Chuyển character position → milliseconds trong audio.
    Nội suy tuyến tính trong câu.
    """
    if not mapping:
        return 0.0

    # Tìm câu chứa char_pos
    for i, (cs, t_start, t_end) in enumerate(mapping):
        # Lấy char_end từ phần tử tiếp theo
        if i + 1 < len(mapping):
            ce = mapping[i + 1][0]
        else:
            ce = cs + (t_end - t_start)  # ước tính

        if cs <= char_pos < ce:
            # Nội suy tuyến tính
            ratio = (char_pos - cs) / max(1, ce - cs)
            return t_start + ratio * (t_end - t_start)

    # char_pos ngoài range → trả về cuối
    last = mapping[-1]
    return float(last[2])


# ═══════════════════════════════════════════════════════════════════════════
#  BUILD SLIDE TIMELINE
# ═══════════════════════════════════════════════════════════════════════════

def build_slide_timeline(
    slides: List[SlideInfo],
    script_text: str,
    json_data: dict,
) -> List[SlideTimedEntry]:
    """
    Tính thời điểm bắt đầu và kết thúc cho từng slide đã gán.
    Slide chưa gán được bỏ qua.
    Kết quả được sắp xếp theo thời gian.
    """
    total_ms = json_data.get("total_duration_ms", 0)
    if total_ms == 0:
        # Ước tính từ câu cuối
        sents = json_data.get("sentences", [])
        if sents:
            total_ms = sents[-1].get("end_ms", 0)

    mapping = build_char_to_ms_map(script_text, json_data)

    timed: List[SlideTimedEntry] = []
    for slide in slides:
        if not slide.is_assigned:
            continue
        ms = char_pos_to_ms(slide.assigned_pos, mapping)
        timed.append(SlideTimedEntry(
            slide=slide,
            start_sec=ms / 1000.0,
            end_sec=0,
            duration_sec=0,
        ))

    # Sắp xếp theo start_sec
    timed.sort(key=lambda e: e.start_sec)

    # Tính duration cho mỗi slide
    total_sec = total_ms / 1000.0
    for i, entry in enumerate(timed):
        if i + 1 < len(timed):
            entry.end_sec = timed[i + 1].start_sec
        else:
            entry.end_sec = total_sec
        entry.duration_sec = max(0.1, entry.end_sec - entry.start_sec)

    return timed


# ═══════════════════════════════════════════════════════════════════════════
#  FFMPEG VIDEO EXPORT
# ═══════════════════════════════════════════════════════════════════════════

def _check_ffmpeg():
    import shutil
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "Không tìm thấy ffmpeg!\n\n"
            "Tải tại: https://www.gyan.dev/ffmpeg/builds/\n"
            "Giải nén và thêm thư mục /bin vào PATH, rồi khởi động lại ứng dụng."
        )


def export_video(
    slides: List[SlideInfo],
    script_text: str,
    mp3_path: str,
    json_path: str,
    output_path: str,
    resolution: tuple[int, int] = (1280, 720),
    fps: int = 25,
    progress_cb: Optional[Callable[[int, str], None]] = None,
) -> str:
    """
    Xuất video MP4 từ slide PNG + MP3.
    Trả về đường dẫn file output.
    """
    def _rep(pct: int, msg: str):
        if progress_cb:
            progress_cb(pct, msg)

    _check_ffmpeg()

    # Đọc JSON timestamps
    _rep(5, "Đang đọc timestamps…")
    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    # Build timeline
    _rep(10, "Đang tính thời điểm slide…")
    timeline = build_slide_timeline(slides, script_text, json_data)

    if not timeline:
        raise ValueError(
            "Chưa có slide nào được gán vị trí trong kịch bản.\n"
            "Vui lòng gán ít nhất 1 slide trước khi xuất video."
        )

    total_sec = json_data.get("total_duration_ms", 0) / 1000.0
    W, H = resolution

    _rep(15, f"Đang tạo {len(timeline)} phân đoạn slide…")

    with tempfile.TemporaryDirectory(prefix="kath_video_") as tmp:
        concat_lines: List[str] = []

        # Nếu slide đầu không bắt đầu tại 0 → dùng slide đầu tiên từ giây 0
        first_start = timeline[0].start_sec if timeline else 0
        if first_start > 0.1:
            # Kéo dài slide đầu để bao phủ phần mở đầu im lặng
            timeline[0] = SlideTimedEntry(
                slide=timeline[0].slide,
                start_sec=0,
                end_sec=timeline[0].end_sec,
                duration_sec=timeline[0].end_sec,
            )

        for i, entry in enumerate(timeline):
            _rep(15 + int(60 * i / len(timeline)), f"Chuẩn bị slide {i + 1}/{len(timeline)}…")

            slide = entry.slide
            img_path = slide.image_path

            # Scale/pad ảnh về đúng resolution nếu cần
            scaled_path = os.path.join(tmp, f"scaled_{i:04d}.png")
            _scale_image_ffmpeg(img_path, scaled_path, W, H)

            duration = round(entry.duration_sec, 3)
            concat_lines.append(f"file '{scaled_path}'")
            concat_lines.append(f"duration {duration}")

        # ffmpeg concat demuxer cần dòng cuối lặp lại
        if concat_lines:
            last_file_line = concat_lines[-2]  # "file '...'"
            concat_lines.append(last_file_line)

        concat_file = os.path.join(tmp, "concat.txt")
        with open(concat_file, "w", encoding="utf-8") as f:
            f.write("\n".join(concat_lines))

        _rep(78, "Đang encode video…")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_file,
            "-i", mp3_path,
            "-vf", f"fps={fps}",    # Ép framerate cố định (ví dụ 25 fps) để các trình phát video render được hình ảnh
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",          # kết thúc khi audio hết
            "-movflags", "+faststart",
            output_path,
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg thất bại (code {result.returncode}):\n{result.stderr[-1500:]}"
            )

    _rep(100, "✓ Xuất video hoàn thành!")
    return output_path


def _scale_image_ffmpeg(src: str, dst: str, W: int, H: int):
    """Scale ảnh PNG về đúng kích thước W×H, thêm letterbox nếu cần."""
    cmd = [
        "ffmpeg", "-y", "-i", src,
        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
               f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black",
        dst,
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        # Fallback: copy nguyên ảnh
        import shutil
        shutil.copy(src, dst)
