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
#  SUBTITLE UTILS
# ═══════════════════════════════════════════════════════════════════════════

def split_sentences_into_single_lines(sentences: list, max_chars: int = 45) -> list:
    """
    Tách các câu dài thành các câu phụ đề ngắn có độ dài tối đa max_chars (phù hợp hiển thị 1 dòng).
    Sử dụng thông tin timestamps cấp độ từ (word-level timestamps) từ Whisper nếu có,
    ngược lại nội suy tuyến tính dựa trên vị trí từ.

    Quy tắc bổ sung:
    1. Tự động ngắt dòng ngay sau dấu phẩy (,), dấu chấm phẩy (;), dấu hai chấm (:) hoặc dấu kết câu
       nếu độ dài của phân đoạn hiện tại đã đạt tối thiểu 12 ký tự hoặc có ít nhất 2 từ.
    2. Nếu đoạn văn bản còn lại của câu chỉ còn tối đa 2 từ, gộp tất cả chúng vào phân đoạn hiện tại
       để tránh tạo ra thẻ phụ đề bị mồ côi (chỉ chứa 1 hoặc 2 từ đơn độc ở cuối câu).
    """
    new_sents = []
    idx_counter = 0
    for sent in sentences:
        text = sent.get("text", "").strip()
        start_ms = sent.get("start_ms", 0)
        end_ms = sent.get("end_ms", start_ms + 1000)
        words_ts = sent.get("words", []) # Word timestamps from Whisper
        
        if not text:
            continue
            
        raw_words = text.split()
        if not raw_words:
            continue
            
        # Gom các từ thành các dòng con
        chunks = []
        current_chunk = []
        current_len = 0
        total_raw_words = len(raw_words)
        
        for idx, rw in enumerate(raw_words):
            remaining_words = total_raw_words - idx
            # Nếu chỉ còn lại <= 2 từ trong câu, ép buộc gộp vào dòng hiện tại để tránh từ mồ côi
            force_no_split = (remaining_words <= 2)
            
            add_len = len(rw) + (1 if current_chunk else 0)
            
            # Kiểm tra xem từ trước đó có kết thúc bằng dấu câu đặc biệt không
            prev_ended_with_punctuation = False
            if current_chunk and not force_no_split:
                prev_w = current_chunk[-1]
                clean_prev = prev_w.rstrip('*_"\'')
                # Chỉ ngắt khi dòng đã có độ dài tối thiểu để tránh các từ mồi như "Ví dụ," bị ngắt riêng
                if len(current_chunk) >= 2 or current_len >= 12:
                    if clean_prev.endswith((',', ';', ':', '.', '?', '!')):
                        prev_ended_with_punctuation = True
            
            if (current_len + add_len > max_chars and current_chunk and not force_no_split) or prev_ended_with_punctuation:
                chunks.append(current_chunk)
                current_chunk = [rw]
                current_len = len(rw)
            else:
                current_chunk.append(rw)
                current_len += add_len
                
        if current_chunk:
            chunks.append(current_chunk)
            
        # Gán thời gian bắt đầu và kết thúc cho từng dòng con
        duration = end_ms - start_ms
        
        word_idx = 0
        for chunk in chunks:
            chunk_text = " ".join(chunk)
            num_words = len(chunk)
            
            start_word_idx = word_idx
            end_word_idx = word_idx + num_words - 1
            word_idx += num_words
            
            c_start = start_ms
            c_end = end_ms
            
            if words_ts and len(words_ts) > 0:
                ts_start_idx = min(start_word_idx, len(words_ts) - 1)
                c_start = words_ts[ts_start_idx].get("start_ms", start_ms)
                
                ts_end_idx = min(end_word_idx, len(words_ts) - 1)
                c_end = words_ts[ts_end_idx].get("end_ms", end_ms)
            else:
                c_start = int(start_ms + (start_word_idx / total_raw_words) * duration)
                c_end = int(start_ms + ((end_word_idx + 1) / total_raw_words) * duration)
                
            if c_start < start_ms:
                c_start = start_ms
            if c_end > end_ms:
                c_end = end_ms
            if c_end <= c_start:
                c_end = c_start + 100
                
            new_sents.append({
                "index": idx_counter,
                "text": chunk_text,
                "start_ms": c_start,
                "end_ms": c_end,
                "words": []
            })
            idx_counter += 1
            
    return new_sents


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
    sub_settings: Optional[dict] = None,
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

        _rep(75, "Đang tạo phụ đề…")
        
        # Subtitles logic
        ass_path = ""
        vf_filter = f"fps={fps}"
        
        if sub_settings and sub_settings.get("enabled", True):
            try:
                def ms_to_ass_time(ms: float) -> str:
                    s, ms = divmod(int(ms), 1000)
                    m, s = divmod(s, 60)
                    h, m = divmod(m, 60)
                    cs = ms // 10
                    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

                # Scale font size matching the resolution
                ass_size = int(sub_settings.get("font_size", 20) * (H / 400))
                
                color_map = {
                    "Trắng": "FFFFFF",
                    "Vàng": "00FFFF",
                    "Xanh lá": "00FF00",
                    "Xanh lam": "FF0000"  # BGR
                }
                color_hex = color_map.get(sub_settings.get("color", "Trắng"), "FFFFFF")
                
                style_name = sub_settings.get("style", "Viền đen")
                border_style = 1
                outline = 2
                outline_color_hex = "00000000"
                back_color_hex = "80000000"
                
                if style_name == "Viền đen":
                    border_style = 1
                    outline = 2
                    outline_color_hex = "00000000"
                elif style_name == "Nền đen mờ":
                    border_style = 3
                    outline = 4  # Dùng outline làm độ đệm (padding) cho nền đen mờ
                    outline_color_hex = "5A000000"  # Màu viền trùng với màu nền đen mờ để tạo thành khối đồng nhất
                    back_color_hex = "5A000000"  # AABBGGRR (65% opaque black, matches QColor(0,0,0,165))
                elif style_name == "Không viền":
                    border_style = 1
                    outline = 0
                    outline_color_hex = "00000000"
                    
                # pos=1 → MarginV=0 (sát đáy), pos=2 → H/100, ...
                pos_pct  = sub_settings.get("position", 1)
                margin_v = int(H * (pos_pct - 1) / 100)
                
                # Generate ASS content
                ass_lines = [
                    "[Script Info]",
                    "Title: Subtitles",
                    "ScriptType: v4.00+",
                    "WrapStyle: 0",
                    f"PlayResX: {W}",
                    f"PlayResY: {H}",
                    "ScaledBorderAndShadow: yes",
                    "",
                    "[V4+ Styles]",
                    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
                    f"Style: Default,Arial,{ass_size},&H00{color_hex}&,&H00000000&,&H{outline_color_hex}&,&H{back_color_hex}&,-1,0,0,0,100,100,0,0,{border_style},{outline},0,2,10,10,{margin_v},1",
                    "",
                    "[Events]",
                    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
                ]
                
                sents = json_data.get("sentences", [])
                sents = split_sentences_into_single_lines(sents, max_chars=45)
                for sent in sents:
                    start_ms = sent.get("start_ms", 0)
                    end_ms   = sent.get("end_ms", start_ms + 1000)
                    s_text   = sent.get("text", "").strip()
                    if s_text:
                        start_str = ms_to_ass_time(start_ms)
                        end_str   = ms_to_ass_time(end_ms)
                        # ASS dialogue format
                        ass_lines.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{s_text}")

                ass_path = os.path.join(tmp, "subtitles.ass")
                with open(ass_path, "w", encoding="utf-8") as ass_f:
                    ass_f.write("\n".join(ass_lines))
                
                ass_path_esc = ass_path.replace("\\", "/").replace(":", "\\:")
                vf_filter = f"fps={fps},subtitles='{ass_path_esc}'"
            except Exception as sub_err:
                pass

        _rep(78, "Đang encode video…")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_file,
            "-i", mp3_path,
            "-vf", vf_filter,
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
