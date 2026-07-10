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


def _get_video_duration(path: str) -> float:
    """Lấy thời lượng (giây) của file video bằng ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1",
             path],
            capture_output=True, text=True,
        )
        return max(0.1, float(r.stdout.strip()))
    except Exception:
        return 5.0


def _make_static_video(img_path: str, dst: str, duration: float,
                       W: int, H: int, fps: int):
    """Tạo video tĩnh từ một ảnh PNG với thời lượng cho trước."""
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-framerate", str(fps), "-i", img_path,
        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
               f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,fps={fps}",
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-an",   # không có audio
        dst,
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg tạo static video thất bại:\n{result.stderr[-800:]}"
        )


def _make_slide_with_gif_video(img_path: str, gifs: list, dst: str, duration: float,
                              W: int, H: int, fps: int):
    """Tạo video từ một ảnh PNG làm hình nền, có đè các hình GIF động (đã được định vị và co giãn)."""
    import os
    import sys
    import shutil
    import subprocess

    ffmpeg_bin = shutil.which("ffmpeg") or os.path.join(os.path.dirname(sys.executable), "ffmpeg.exe")
    if not os.path.exists(ffmpeg_bin):
        ffmpeg_bin = "ffmpeg"

    # Command base
    # Input 0: static background image
    cmd = [
        ffmpeg_bin, "-y",
        "-loop", "1", "-framerate", str(fps), "-i", img_path
    ]

    # Input 1, 2, ...: GIF files
    for gif in gifs:
        cmd.extend(["-ignore_loop", "0", "-i", gif["gif_path"]])

    # Build filter complex
    filters = []
    # Đầu tiên scale và pad hình nền về độ phân giải WxH
    filters.append(f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,fps={fps}[bg_scaled]")
    
    last_output = "[bg_scaled]"
    for idx, gif in enumerate(gifs, start=1):
        x = int(gif["x_rel"] * W)
        y = int(gif["y_rel"] * H)
        w = int(gif["w_rel"] * W)
        h = int(gif["h_rel"] * H)
        
        w = max(1, w)
        h = max(1, h)

        # Scale GIF
        filters.append(f"[{idx}:v]scale={w}:{h}[g{idx}]")
        
        # Overlay GIF
        next_output = f"[tmp{idx}]" if idx < len(gifs) else ""
        shortest_str = ":shortest=1" if idx == len(gifs) else ""
        
        if next_output:
            filters.append(f"{last_output}[g{idx}]overlay={x}:{y}{shortest_str}{next_output}")
            last_output = next_output
        else:
            filters.append(f"{last_output}[g{idx}]overlay={x}:{y}{shortest_str}")

    filter_complex = ";".join(filters)

    cmd.extend([
        "-filter_complex", filter_complex,
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-an",
        dst
    ])

    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg tạo slide video với GIF thất bại:\n{result.stderr.decode('utf-8', errors='ignore')[-800:]}"
        )


def _has_audio(path: str) -> bool:
    """Kiểm tra xem file video có track audio không."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "stream=codec_type",
             "-of", "default=noprint_wrappers=1:nokey=1",
             path],
            capture_output=True, text=True,
        )
        return "audio" in r.stdout
    except Exception:
        return False


def _normalize_video(src: str, dst: str, W: int, H: int, fps: int, duration: Optional[float] = None):
    """Chuẩn hóa video về cùng resolution/fps, giữ audio gốc. Có thể cắt ngắn hoặc kéo dài (atempo/setpts) theo duration."""
    source_dur = _get_video_duration(src)
    has_audio_stream = _has_audio(src)
    
    vf_filters = [
        f"scale={W}:{H}:force_original_aspect_ratio=decrease",
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black",
        f"fps={fps}"
    ]
    af_filters = []
    
    # Nếu duration được yêu cầu lớn hơn duration thực tế của video, dùng setpts và atempo để làm chậm video
    if duration is not None and duration > source_dur and source_dur > 0.1:
        speed_factor = source_dur / duration
        speed_factor = max(0.5, min(2.0, speed_factor))
        vf_filters.append(f"setpts=PTS/{speed_factor:.4f}")
        if has_audio_stream:
            af_filters.append(f"atempo={speed_factor:.4f}")
        
    cmd = [
        "ffmpeg", "-y", "-i", src,
    ]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
        
    cmd += ["-vf", ",".join(vf_filters)]
    
    if has_audio_stream:
        if af_filters:
            cmd += ["-af", ",".join(af_filters)]
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-an"]
        
    cmd += [
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        dst,
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        # Fallback: copy
        import shutil
        shutil.copy(src, dst)


# ═══════════════════════════════════════════════════════════════════════════
#  NEW: EXPORT WITH MEDIA ITEMS + TRANSITIONS + AUDIO MIX
# ═══════════════════════════════════════════════════════════════════════════

def export_video_with_media(
    media_items,          # List[MediaItem]
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
    Xuất video từ List[MediaItem] với hỗ trợ:
    - Bất kỳ MediaItem (slide/video/ảnh) đã gán: timed theo TTS timestamps
    - Video clip: giữ nguyên hoặc cắt theo duration được gán (audio được mix)
    - Ảnh tĩnh: loop theo duration
    - Transition (xfade) giữa bất kỳ cặp clip nào
    - Mix âm lượng TTS + video clip riêng lẻ
    - Subtitle (ASS) — KHÔNG THAY ĐỔI logic
    """
    def _rep(pct: int, msg: str):
        if progress_cb:
            progress_cb(pct, msg)

    _check_ffmpeg()

    W, H = resolution

    # ── Đọc timestamps TTS ───────────────────────────────────────────────
    _rep(5, "Đang đọc timestamps…")
    json_data: dict = {}
    if json_path and Path(json_path).exists():
        with open(json_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)

    # ── Tính TTS timeline cho tất cả items được gán ──────────────────────
    _rep(8, "Đang tính thời điểm xuất hiện…")
    assigned_items = [m for m in media_items if m.is_assigned]

    tts_timeline: List[SlideTimedEntry] = []
    if assigned_items and json_data:
        tts_timeline = build_slide_timeline(assigned_items, script_text, json_data)

    # Map item.id → SlideTimedEntry
    tts_map: dict = {}
    for entry in tts_timeline:
        tts_map[entry.slide.id] = entry

    # ── Tính duration cho từng MediaItem ─────────────────────────────────
    total_ms = json_data.get("total_duration_ms", 0)
    if total_ms == 0:
        sents = json_data.get("sentences", [])
        if sents:
            total_ms = sents[-1].get("end_ms", 0)
    tts_total_sec = total_ms / 1000.0

    # Gán duration cho items từ TTS hoặc tự động lấy từ file gốc
    for m_item in media_items:
        if m_item.media_type == "video" or m_item.path.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
            m_item.duration_sec = _get_video_duration(m_item.path)
        elif m_item.is_assigned:
            entry = tts_map.get(m_item.id)
            if entry:
                m_item.duration_sec = max(0.1, entry.duration_sec)

    _rep(12, f"Đang chuẩn bị {len(media_items)} clip…")

    with tempfile.TemporaryDirectory(prefix="kath_media_") as tmp:

        # ── Bước 1: Tạo clip video trung gian ────────────────────────────
        clip_paths:   List[str]   = []
        has_audio:    List[bool]  = []
        video_vols:   List[float] = []
        tts_vols:     List[float] = []
        clip_durs:    List[float] = []

        for i, m_item in enumerate(media_items):
            _rep(12 + int(35 * i / len(media_items)),
                 f"Clip {i+1}/{len(media_items)}: {m_item.display_name}…")

            clip_out = os.path.join(tmp, f"clip_{i:04d}.mp4")

            # Tính extra_dur nếu clip tiếp theo có transition_in
            extra_dur = 0.0
            if i + 1 < len(media_items):
                next_item = media_items[i + 1]
                next_trans_type = getattr(next_item, "transition_in", "none")
                if next_trans_type != "none":
                    extra_dur = getattr(next_item, "transition_dur", 0.5)

            if m_item.media_type == "video" or m_item.path.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
                # Cắt video đúng thời lượng + phần bù transition
                duration_to_use = m_item.duration_sec + extra_dur
                _normalize_video(m_item.path, clip_out, W, H, fps, duration=duration_to_use)
                has_audio.append(True)
                video_vols.append(m_item.video_volume)
                tts_vols.append(m_item.tts_volume)

            else:  # slide hoặc image
                img_path = m_item.image_path
                if not img_path or not os.path.exists(img_path):
                    # Tạo ảnh đen placeholder
                    placeholder = os.path.join(tmp, f"black_{i}.png")
                    _make_black_image(placeholder, W, H)
                    img_path = placeholder

                dur = max(0.1, m_item.duration_sec) + extra_dur

                # Kiểm tra slide có chứa ảnh GIF động không
                gifs = []
                if m_item.media_type == "slide" and m_item.slide_info:
                    gifs = getattr(m_item.slide_info, "gifs", [])

                if gifs:
                    _make_slide_with_gif_video(img_path, gifs, clip_out, dur, W, H, fps)
                else:
                    _make_static_video(img_path, clip_out, dur, W, H, fps)

                has_audio.append(False)
                video_vols.append(0.0)
                tts_vols.append(1.0)

            clip_paths.append(clip_out)
            clip_durs.append(_get_video_duration(clip_out))

        if not clip_paths:
            raise ValueError("Không có clip nào để xuất!")

        # ── Bước 2: Tạo phụ đề ASS ───────────────────────────────────────
        _rep(50, "Đang tạo phụ đề…")
        ass_path = ""
        sub_vf   = f"fps={fps}"

        if sub_settings and sub_settings.get("enabled", True) and json_data:
            try:
                def ms_to_ass(ms: float) -> str:
                    s, ms_ = divmod(int(ms), 1000)
                    m, s   = divmod(s, 60)
                    h, m   = divmod(m, 60)
                    return f"{h}:{m:02d}:{s:02d}.{ms_//10:02d}"

                ass_size = int(sub_settings.get("font_size", 20) * (H / 400))
                color_map = {
                    "Trắng":    "FFFFFF",
                    "Vàng":     "00FFFF",
                    "Xanh lá":  "00FF00",
                    "Xanh lam": "FF0000",
                }
                color_hex = color_map.get(
                    sub_settings.get("color", "Trắng"), "FFFFFF")

                style_name = sub_settings.get("style", "Viền đen")
                if style_name == "Nền đen mờ":
                    border_style, outline = 3, 4
                    outline_hex = "5A000000"
                    back_hex    = "5A000000"
                elif style_name == "Không viền":
                    border_style, outline = 1, 0
                    outline_hex = "00000000"
                    back_hex    = "80000000"
                else:
                    border_style, outline = 1, 2
                    outline_hex = "00000000"
                    back_hex    = "80000000"

                pos_pct  = sub_settings.get("position", 1)
                margin_v = int(H * (pos_pct - 1) / 100)

                # Tính offset TTS: tổng duration của các items đầu timeline trước khi TTS bắt đầu
                tts_offset_sec = 0.0
                for m_item in media_items:
                    if m_item.is_assigned:
                        break
                    tts_offset_sec += m_item.duration_sec

                ass_lines = [
                    "[Script Info]",
                    "Title: Subtitles", "ScriptType: v4.00+",
                    "WrapStyle: 0",
                    f"PlayResX: {W}", f"PlayResY: {H}",
                    "ScaledBorderAndShadow: yes", "",
                    "[V4+ Styles]",
                    "Format: Name, Fontname, Fontsize, PrimaryColour, "
                    "SecondaryColour, OutlineColour, BackColour, Bold, "
                    "Italic, Underline, StrikeOut, ScaleX, ScaleY, "
                    "Spacing, Angle, BorderStyle, Outline, Shadow, "
                    "Alignment, MarginL, MarginR, MarginV, Encoding",
                    f"Style: Default,Arial,{ass_size},"
                    f"&H00{color_hex}&,&H00000000&,"
                    f"&H{outline_hex}&,&H{back_hex}&,"
                    f"-1,0,0,0,100,100,0,0,{border_style},"
                    f"{outline},0,2,10,10,{margin_v},1", "",
                    "[Events]",
                    "Format: Layer, Start, End, Style, Name, "
                    "MarginL, MarginR, MarginV, Effect, Text",
                ]

                sents = json_data.get("sentences", [])
                sents = split_sentences_into_single_lines(sents, max_chars=45)
                for sent in sents:
                    s_ms = sent.get("start_ms", 0) + tts_offset_sec * 1000
                    e_ms = sent.get("end_ms",   0) + tts_offset_sec * 1000
                    txt  = sent.get("text", "").strip()
                    if txt:
                        ass_lines.append(
                            f"Dialogue: 0,{ms_to_ass(s_ms)},"
                            f"{ms_to_ass(e_ms)},Default,,0,0,0,,{txt}"
                        )

                ass_path_tmp = os.path.join(tmp, "subtitles.ass")
                with open(ass_path_tmp, "w", encoding="utf-8") as f:
                    f.write("\n".join(ass_lines))
                ass_path = ass_path_tmp

                ass_esc = ass_path.replace("\\", "/").replace(":", "\\:")
                sub_vf  = f"fps={fps},subtitles='{ass_esc}'"
            except Exception:
                pass  # subtitle silently skipped on error

        # ── Bước 3: Ghép video với xfade (hoặc concat đơn giản) ──────────
        _rep(60, "Đang ghép video…")
        tmp_video = os.path.join(tmp, "merged_video.mp4")

        has_any_transition = any(
            m.transition_in != "none" for m in media_items[1:]
        )

        if len(clip_paths) == 1:
            # 1 clip — dùng trực tiếp
            import shutil as _shutil
            _shutil.copy(clip_paths[0], tmp_video)
        elif has_any_transition:
            _merge_with_xfade(clip_paths, media_items, clip_durs,
                              tmp_video, sub_vf, fps)
        else:
            _merge_with_concat(clip_paths, tmp_video, sub_vf, fps)

        # ── Bước 4: Mix audio (TTS + video clips) ────────────────────────
        _rep(82, "Đang mix audio…")
        final_output = output_path

        _mix_audio(
            tmp_video, mp3_path, media_items, clip_paths, clip_durs,
            has_audio, video_vols, tts_vols, final_output,
        )

    _rep(100, "✓ Xuất video hoàn thành!")
    return final_output


# ─── Helpers cho export_video_with_media ────────────────────────────────────


def _make_black_image(path: str, W: int, H: int):
    """Tạo ảnh đen placeholder bằng ffmpeg."""
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         f"-i", f"color=black:s={W}x{H}:r=1",
         "-frames:v", "1", path],
        capture_output=True,
    )


def _merge_with_concat(clip_paths: List[str], output: str,
                       vf: str, fps: int):
    """Ghép nhiều clip bằng concat demuxer (không transition)."""
    import tempfile as _tf
    concat_f = output + ".concat.txt"
    with open(concat_f, "w", encoding="utf-8") as f:
        for p in clip_paths:
            f.write(f"file '{p}'\n")
        # ffmpeg concat demuxer cần lặp dòng cuối
        f.write(f"file '{clip_paths[-1]}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_f,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-an",
        output,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg concat thất bại:\n{result.stderr[-1000:]}"
        )
    try:
        os.remove(concat_f)
    except OSError:
        pass


def _merge_with_xfade(clip_paths: List[str], media_items,
                      clip_durs: List[float], output: str,
                      vf: str, fps: int):
    """Ghép clip với xfade transitions."""
    n = len(clip_paths)

    # Build inputs
    inputs: List[str] = []
    for p in clip_paths:
        inputs += ["-i", p]

    # Build filter_complex
    filter_parts: List[str] = []
    cumulative_dur = clip_durs[0]
    in_label = "[0:v]"

    for i in range(1, n):
        trans_type = media_items[i].transition_in if i < len(media_items) else "none"
        trans_dur  = media_items[i].transition_dur if i < len(media_items) else 0.5

        if trans_type == "none":
            trans_dur = 0.0

        out_label = f"[v{i}]" if i < n - 1 else "[vmerged]"

        if trans_type != "none":
            offset = max(0.01, cumulative_dur - trans_dur)
            filter_parts.append(
                f"{in_label}[{i}:v]xfade="
                f"transition={trans_type}:"
                f"duration={trans_dur:.2f}:"
                f"offset={offset:.3f}"
                f"{out_label}"
            )
            cumulative_dur += clip_durs[i] - trans_dur
        else:
            # concat 2 clips: ffmpeg concat filter (n=2)
            filter_parts.append(
                f"{in_label}[{i}:v]concat=n=2:v=1:a=0{out_label}"
            )
            cumulative_dur += clip_durs[i]

        in_label = out_label

    # Last vf step
    final_label = "[vout]"
    filter_parts.append(f"[vmerged]{vf}[vout]")
    filter_complex = ";".join(filter_parts)

    cmd = (
        ["ffmpeg", "-y"] + inputs +
        ["-filter_complex", filter_complex,
         "-map", "[vout]",
         "-c:v", "libx264", "-preset", "fast", "-crf", "23",
         "-pix_fmt", "yuv420p",
         "-an",
         output]
    )

    result = subprocess.run(cmd, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
    if result.returncode != 0:
        # Fallback: concat đơn giản
        _merge_with_concat(clip_paths, output, vf, fps)


def _mix_audio(merged_video: str, mp3_path: str, media_items,
               clip_paths: List[str], clip_durs: List[float], has_audio: List[bool],
               video_vols: List[float], tts_vols: List[float],
               output: str):
    """
    Kết hợp video đã ghép với:
    - TTS audio (delay theo offset của phần slide đầu tiên)
    - Audio gốc của mỗi video clip (delay theo vị trí trong timeline)
    """
    import shutil as _sh

    video_dur = _get_video_duration(merged_video)

    # Tính thời điểm bắt đầu thực tế của từng clip trong video sau khi ghép (có transition)
    clip_start_times = []
    cumulative_dur = 0.0
    for i, m in enumerate(media_items):
        if i == 0:
            clip_start_times.append(0.0)
            cumulative_dur = clip_durs[0]
        else:
            trans_type = getattr(m, "transition_in", "none")
            trans_dur = getattr(m, "transition_dur", 0.5) if trans_type != "none" else 0.0
            start_time = max(0.0, cumulative_dur - trans_dur)
            clip_start_times.append(start_time)
            cumulative_dur = cumulative_dur + clip_durs[i] - trans_dur

    # Tính offset của TTS audio trong final video
    tts_start_sec = 0.0
    for i, m in enumerate(media_items):
        if m.is_assigned:
            tts_start_sec = clip_start_times[i]
            break

    # Thu thập video clips có audio
    video_audio_clips: List[tuple[int, float]] = []  # (media_idx, start_sec)
    for i, m in enumerate(media_items):
        is_vid = m.media_type == "video" or m.path.lower().endswith((".mp4", ".avi", ".mov", ".mkv"))
        if is_vid and has_audio[i]:
            if _has_audio(clip_paths[i]):
                video_audio_clips.append((i, clip_start_times[i]))

    has_tts  = mp3_path and Path(mp3_path).exists()
    has_vids = len(video_audio_clips) > 0

    if not has_tts and not has_vids:
        # Chỉ copy video (không audio)
        cmd = [
            "ffmpeg", "-y", "-i", merged_video,
            "-c:v", "copy", "-an", output,
        ]
        subprocess.run(cmd, capture_output=True)
        return

    # Xây dựng filter_complex cho audio
    inputs: List[str] = ["-i", merged_video]
    filter_parts: List[str] = []
    audio_labels: List[str] = []
    input_idx = 1

    # TTS audio
    if has_tts:
        inputs += ["-i", mp3_path]
        tts_delay_ms = int(tts_start_sec * 1000)
        if tts_delay_ms > 0:
            filter_parts.append(
                f"[{input_idx}:a]adelay={tts_delay_ms}|{tts_delay_ms}[tts_a]"
            )
        else:
            filter_parts.append(f"[{input_idx}:a]anull[tts_a]")
        # Âm lượng TTS — lấy theo clip đang phát (default = 1.0)
        audio_labels.append("[tts_a]")
        input_idx += 1

    # Video clip audio
    for media_idx, start_sec in video_audio_clips:
        delay_ms = int(start_sec * 1000)
        vol      = video_vols[media_idx] if media_idx < len(video_vols) else 0.3
        vid_path = clip_paths[media_idx]  # Dùng file đã chuẩn hóa & tpad cắt đúng thời lượng

        inputs += ["-i", vid_path]
        label   = f"[vid_a{input_idx}]"
        filter_parts.append(
            f"[{input_idx}:a]"
            f"adelay={delay_ms}|{delay_ms},"
            f"volume={vol:.2f}"
            f"{label}"
        )
        audio_labels.append(label)
        input_idx += 1

    # Mix tất cả audio
    n_audio = len(audio_labels)
    if n_audio == 0:
        out_audio = "[0:a]"
    elif n_audio == 1:
        out_audio = audio_labels[0]
    else:
        joined = "".join(audio_labels)
        filter_parts.append(
            f"{joined}amix=inputs={n_audio}:normalize=0[aout]"
        )
        out_audio = "[aout]"

    filter_complex = ";".join(filter_parts) if filter_parts else ""

    cmd = ["ffmpeg", "-y"] + inputs
    if filter_complex:
        cmd += ["-filter_complex", filter_complex,
                "-map", "0:v", "-map", out_audio]
    else:
        cmd += ["-map", "0:v", "-map", out_audio]

    has_video_items = any(
        m.media_type == "video" or m.path.lower().endswith((".mp4", ".avi", ".mov", ".mkv"))
        for m in media_items
    )

    cmd += [
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
    ]
    if has_video_items:
        cmd += ["-t", f"{video_dur:.3f}"]
    else:
        cmd += ["-shortest"]
    cmd += [
        "-movflags", "+faststart",
        output,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
    if result.returncode != 0:
        # Fallback: copy video only
        _sh.copy(merged_video, output)

