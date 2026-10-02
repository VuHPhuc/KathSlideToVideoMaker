"""
video_subtitler.py — Module lõi xử lý phụ đề tự động cho video:
1. Trích xuất âm thanh từ video qua FFmpeg.
2. Nhận diện giọng nói và mốc thời gian (Speech-to-Text & Timestamps) bằng faster-whisper.
3. Dịch phụ đề sang mọi ngôn ngữ (Google Translate miễn phí hoặc Google Gemini AI).
4. Xuất file phụ đề SRT / ASS (hỗ trợ phụ đề đơn hoặc song ngữ).
5. In phụ đề lên video (Hardsub) qua FFmpeg.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import requests


# ── Đảm bảo FFmpeg luôn được tìm thấy ───────────────────────────────────────
def get_ffmpeg_path() -> str:
    """Tìm đường dẫn ffmpeg.exe trong hệ thống hoặc trong thư mục dự án."""
    # 1. Kiểm tra PATH hệ thống
    found = shutil.which("ffmpeg")
    if found:
        return found

    # 2. Kiểm tra trong .venv/Scripts/ffmpeg.exe
    venv_ffmpeg = Path(__file__).resolve().parent.parent.parent / ".venv" / "Scripts" / "ffmpeg.exe"
    if venv_ffmpeg.exists():
        os.environ["PATH"] = str(venv_ffmpeg.parent) + os.pathsep + os.environ.get("PATH", "")
        return str(venv_ffmpeg)

    # 3. Kiểm tra imageio_ffmpeg
    try:
        import imageio_ffmpeg
        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        if ffmpeg_bin and os.path.exists(ffmpeg_bin):
            return ffmpeg_bin
    except Exception:
        pass

    return "ffmpeg"


def get_ffprobe_path() -> str:
    """Tìm đường dẫn ffprobe.exe."""
    found = shutil.which("ffprobe")
    if found:
        return found
    venv_ffprobe = Path(__file__).resolve().parent.parent.parent / ".venv" / "Scripts" / "ffprobe.exe"
    if venv_ffprobe.exists():
        return str(venv_ffprobe)
    return "ffprobe"


# ── Danh sách ngôn ngữ hỗ trợ phổ biến ──────────────────────────────────────
SUPPORTED_LANGUAGES = [
    ("vi", "Tiếng Việt"),
    ("en", "Tiếng Anh (English)"),
    ("ja", "Tiếng Nhật (日本語)"),
    ("ko", "Tiếng Hàn (한국어)"),
    ("zh-CN", "Tiếng Trung Giản Thể (简体中文)"),
    ("zh-TW", "Tiếng Trung Phồn Thể (繁體中文)"),
    ("fr", "Tiếng Pháp (Français)"),
    ("de", "Tiếng Đức (Deutsch)"),
    ("es", "Tiếng Tây Ban Nha (Español)"),
    ("ru", "Tiếng Nga (Русский)"),
    ("th", "Tiếng Thái (ไทย)"),
    ("id", "Tiếng Indonesia"),
    ("pt", "Tiếng Bồ Đào Nha (Português)"),
    ("it", "Tiếng Ý (Italiano)"),
    ("ar", "Tiếng Ả Rập (العربية)"),
    ("hi", "Tiếng Hindi (हिन्दी)"),
]

WHISPER_MODELS = [
    ("small", "⚖️ Small (Khuyên dùng)", "Cân bằng tốc độ & độ chính xác cao"),
    ("base", "⚡ Base (Nhanh & Nhẹ)", "Chạy nhanh, phù hợp máy cấu hình bình thường"),
    ("medium", "🎯 Medium (Chuẩn xác)", "Chính xác cao, phù hợp video phức tạp"),
    ("tiny", "🚀 Tiny (Siêu tốc)", "Cực nhanh, độ chính xác cơ bản"),
]


# ── Lấy thông tin video qua FFprobe ─────────────────────────────────────────
def get_video_info(video_path: str) -> Dict:
    """Lấy thời lượng (giây), độ phân giải (W, H) và fps của video."""
    ffprobe = get_ffprobe_path()
    cmd = [
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration:stream=width,height,r_frame_rate",
        "-of", "json",
        video_path
    ]
    info = {"duration": 0.0, "width": 1280, "height": 720, "fps": 25.0}
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        if "format" in data and "duration" in data["format"]:
            info["duration"] = float(data["format"]["duration"])
        streams = data.get("streams", [])
        for s in streams:
            if "width" in s and "height" in s:
                info["width"] = int(s["width"])
                info["height"] = int(s["height"])
                r_fps = s.get("r_frame_rate", "25/1")
                if "/" in r_fps:
                    num, den = r_fps.split("/")
                    info["fps"] = round(float(num) / max(float(den), 1.0), 2)
                break
    except Exception:
        pass
    return info


# ── 1. Trích xuất âm thanh từ video ─────────────────────────────────────────
def extract_audio_from_video(video_path: str, output_wav: str) -> bool:
    """Tách âm thanh từ video sang file WAV 16kHz mono phục vụ Whisper."""
    ffmpeg = get_ffmpeg_path()
    cmd = [
        ffmpeg, "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        output_wav
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode == 0 and os.path.exists(output_wav)


# ── 2. Whisper Speech-to-Text ──────────────────────────────────────────────
def transcribe_video_audio(
    audio_path: str,
    model_size: str = "base",
    language: Optional[str] = None,
    progress_cb: Optional[Callable[[int, str], None]] = None,
) -> Tuple[List[Dict], str, float]:
    """
    Nhận diện lời thoại và sinh timestamps từng câu.
    Trả về: (segments, detected_language, probability)
    Mỗi segment: {"start": float, "end": float, "text": str, "orig_text": str}
    """
    if progress_cb:
        progress_cb(10, f"Đang khởi động AI Whisper ({model_size})...")

    from faster_whisper import WhisperModel

    whisper_cache = Path(__file__).resolve().parent.parent / "models" / "whisper"
    whisper_cache.mkdir(parents=True, exist_ok=True)

    # Tự động phát hiện GPU CUDA, nếu không có fallback sang CPU
    device = "cpu"
    compute_type = "int8"
    try:
        import torch
        if torch.cuda.is_available():
            device = "cuda"
            compute_type = "float16"
    except Exception:
        pass

    model = WhisperModel(
        model_size,
        device=device,
        compute_type=compute_type,
        download_root=str(whisper_cache),
    )

    if progress_cb:
        progress_cb(30, "Đang nhận diện giọng nói & phân tích timestamps...")

    lang_param = None if (not language or language == "auto") else language
    segments_iter, info = model.transcribe(
        audio_path,
        language=lang_param,
        beam_size=5,
        word_timestamps=True,
        vad_filter=True,
    )

    detected_lang = info.language
    detected_prob = info.language_probability

    segments = []
    seg_list = list(segments_iter)
    total_segs = max(len(seg_list), 1)

    for idx, s in enumerate(seg_list):
        cleaned_text = s.text.strip()
        if not cleaned_text:
            continue
        segments.append({
            "id": idx + 1,
            "start": round(s.start, 3),
            "end": round(s.end, 3),
            "orig_text": cleaned_text,
            "text": cleaned_text,  # Mặc định lúc đầu chưa dịch thì bằng orig_text
            "translated_text": "",
        })
        if progress_cb and idx % 5 == 0:
            pct = 30 + int((idx / total_segs) * 55)
            progress_cb(pct, f"Đã nhận diện {idx + 1}/{total_segs} câu...")

    if progress_cb:
        progress_cb(85, f"Hoàn tất nhận diện {len(segments)} câu lời thoại!")

    return segments, detected_lang, detected_prob


# ── 3. Dịch thuật (Google Translate & Gemini) ──────────────────────────────
def translate_google(text: str, target_lang: str, source_lang: str = "auto") -> str:
    """Dịch đoạn văn bản miễn phí qua Google Translate (dùng POST để tránh giới hạn URL)."""
    if not text.strip():
        return ""
    # Nếu ngôn ngữ nguồn trùng ngôn ngữ đích (hoặc do Whisper nhận diện nhầm), ép auto để Google tự nhận diện
    if source_lang and target_lang and source_lang.lower().split("-")[0] == target_lang.lower().split("-")[0]:
        source_lang = "auto"

    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "gtx",
        "sl": source_lang or "auto",
        "tl": target_lang,
        "dt": "t",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    resp = requests.post(url, params=params, data={"q": text}, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    result = []
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
        for item in data[0]:
            if isinstance(item, list) and len(item) > 0 and item[0]:
                result.append(item[0])
    return "".join(result).strip()


def translate_with_gemini(
    texts: List[str],
    target_lang: str,
    api_key: str,
    source_lang_name: str = "",
) -> List[str]:
    """Dịch danh sách các câu qua Google Gemini AI để có văn phong mượt mà nhất."""
    from app.core.ai_engine import GEMINI_API_HOST, API_VERSIONS, DEFAULT_MODEL

    target_lang_name = dict(SUPPORTED_LANGUAGES).get(target_lang, target_lang)
    prompt = (
        f"Bạn là chuyên gia dịch thuật phụ đề phim và video chuyên nghiệp.\n"
        f"Hãy dịch danh sách các câu thoại sau từ ngôn ngữ gốc sang: {target_lang_name}.\n"
        f"Yêu cầu:\n"
        f"1. Dịch tự nhiên, đúng ngữ cảnh hội thoại, súc tích phù hợp hiển thị phụ đề.\n"
        f"2. Giữ nguyên số lượng dòng ({len(texts)} dòng). Không gộp dòng hoặc tự ý tách thêm dòng.\n"
        f"3. Trả về đúng định dạng JSON: {{\"translations\": [\"câu 1\", \"câu 2\", ...]}}\n\n"
        f"Dữ liệu cần dịch:\n"
        f"{json.dumps(texts, ensure_ascii=False)}"
    )

    url = f"{GEMINI_API_HOST}/v1beta/models/{DEFAULT_MODEL}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}
    }
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    res_data = resp.json()
    content_text = res_data["candidates"][0]["content"]["parts"][0]["text"]
    parsed = json.loads(content_text)
    translations = parsed.get("translations", [])
    if len(translations) == len(texts):
        return translations
    raise ValueError("Gemini trả về số lượng dòng không khớp.")


def batch_translate_segments(
    segments: List[Dict],
    target_lang: str,
    source_lang: str = "auto",
    engine: str = "google",
    gemini_api_key: str = "",
    progress_cb: Optional[Callable[[int, str], None]] = None,
) -> List[Dict]:
    """
    Dịch toàn bộ danh sách phụ đề sang ngôn ngữ đích.
    Lưu kết quả vào trường 'translated_text' và 'text' của mỗi segment.
    """
    total = len(segments)
    if total == 0:
        return segments

    # Đảm bảo source_lang không trùng target_lang khiến Google/Gemini trả về nguyên gốc
    if source_lang and target_lang and source_lang.lower().split("-")[0] == target_lang.lower().split("-")[0]:
        source_lang = "auto"

    if progress_cb:
        target_name = dict(SUPPORTED_LANGUAGES).get(target_lang, target_lang)
        progress_cb(10, f"Đang chuẩn bị dịch {total} câu sang {target_name}...")

    # 1. Nếu dùng Gemini AI
    if engine == "gemini" and gemini_api_key:
        try:
            batch_size = 30
            for i in range(0, total, batch_size):
                batch = segments[i:i + batch_size]
                orig_texts = [s["orig_text"] for s in batch]
                translated_batch = translate_with_gemini(orig_texts, target_lang, gemini_api_key)
                for s, tr in zip(batch, translated_batch):
                    s["translated_text"] = tr.strip()
                    s["text"] = tr.strip()
                if progress_cb:
                    pct = int(((i + len(batch)) / total) * 100)
                    progress_cb(pct, f"Gemini đã dịch {min(i + len(batch), total)}/{total} câu...")
            return segments
        except Exception as e:
            # Fallback sang Google Translate nếu Gemini gặp lỗi
            if progress_cb:
                progress_cb(20, f"Lỗi Gemini ({str(e)[:40]}), tự động chuyển sang Google Dịch...")

    # 2. Dịch qua Google Translate (chia batch nhỏ gộp bằng ký tự phân cách)
    batch_size = 20
    for i in range(0, total, batch_size):
        chunk = segments[i:i + batch_size]
        combined = "\n###--###\n".join(s["orig_text"] for s in chunk)
        try:
            translated_combined = translate_google(combined, target_lang=target_lang, source_lang=source_lang)
            # Dùng regex để bóc tách kể cả khi Google tự ý thêm khoảng trắng thành ### -- ###
            tr_lines = [p.strip() for p in re.split(r'\s*#+\s*[-–—]+\s*#+\s*', translated_combined) if p.strip()]
            if len(tr_lines) == len(chunk):
                for s, tr in zip(chunk, tr_lines):
                    s["translated_text"] = tr
                    s["text"] = tr
            else:
                # Nếu chia dòng lệch, dịch từng câu đơn lẻ
                for s in chunk:
                    tr = translate_google(s["orig_text"], target_lang=target_lang, source_lang=source_lang)
                    s["translated_text"] = tr.strip()
                    s["text"] = tr.strip()
        except Exception:
            for s in chunk:
                try:
                    tr = translate_google(s["orig_text"], target_lang=target_lang, source_lang=source_lang)
                    s["translated_text"] = tr.strip()
                    s["text"] = tr.strip()
                except Exception:
                    pass

        if progress_cb:
            pct = int(((i + len(chunk)) / total) * 100)
            progress_cb(pct, f"Đã dịch {min(i + len(chunk), total)}/{total} câu...")

    # Kiểm tra xem có dịch được câu nào không
    translated_count = sum(1 for s in segments if s.get("translated_text") and s["translated_text"].strip() != s.get("orig_text", "").strip())
    if total > 0 and translated_count == 0:
        raise RuntimeError(f"Không thể dịch phụ đề sang ngôn ngữ đã chọn. Vui lòng kiểm tra lại kết nối mạng hoặc thử công cụ dịch khác.")

    return segments


# ── 4. Định dạng thời gian cho SRT & ASS ────────────────────────────────────
def sec_to_srt_time(sec: float) -> str:
    """Chuyển số giây sang định dạng SRT: HH:MM:SS,mmm"""
    total_ms = int(round(sec * 1000))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    m = (total_s // 60) % 60
    h = total_s // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def sec_to_ass_time(sec: float) -> str:
    """Chuyển số giây sang định dạng ASS: H:MM:SS.cc (centiseconds)"""
    total_cs = int(round(sec * 100))
    cs = total_cs % 100
    total_s = total_cs // 100
    s = total_s % 60
    m = (total_s // 60) % 60
    h = total_s // 3600
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


# ── 5. Chia nhỏ câu thành các câu đơn 1 dòng ───────────────────────────────
def split_segment_into_single_lines(seg: Dict, text: str, max_chars: int = 38) -> List[Dict]:
    """
    Tách 1 câu dài thành các câu đơn ngắn hơn hiển thị tuần tự từng dòng một,
    chia đều mốc thời gian start -> end theo tỷ lệ độ dài câu.
    Đảm bảo phụ đề luôn luôn chỉ có 1 dòng duy nhất, không bao giờ bị 2 dòng chen chúc.
    """
    clean_text = text.replace("\r", " ").replace("\n", " ").strip()
    clean_text = re.sub(r"\s+", " ", clean_text)
    if not clean_text:
        return []

    dur = max(0.1, seg["end"] - seg["start"])
    if len(clean_text) <= max_chars or dur < 1.2:
        res = dict(seg)
        res["display_text"] = clean_text
        return [res]

    words = clean_text.split()
    chunks = []
    curr = []
    for w in words:
        cand = " ".join(curr + [w])
        if len(cand) > max_chars and curr:
            chunks.append(" ".join(curr))
            curr = [w]
        else:
            curr.append(w)
    if curr:
        chunks.append(" ".join(curr))

    if len(chunks) <= 1:
        res = dict(seg)
        res["display_text"] = clean_text
        return [res]

    total_len = sum(len(c) for c in chunks)
    result = []
    curr_t = seg["start"]
    for idx, c in enumerate(chunks):
        c_dur = dur * (len(c) / total_len)
        c_end = curr_t + c_dur if idx < len(chunks) - 1 else seg["end"]
        sub_seg = dict(seg)
        sub_seg["start"] = round(curr_t, 3)
        sub_seg["end"] = round(c_end, 3)
        sub_seg["display_text"] = c
        result.append(sub_seg)
        curr_t = c_end

    return result


# ── 6. Xuất file SRT ────────────────────────────────────────────────────────
def export_srt_file(
    segments: List[Dict],
    output_path: str,
    mode: str = "translated",  # 'translated', 'original'
) -> bool:
    """
    Xuất danh sách phụ đề ra file .srt chuẩn (tự động tách câu đơn 1 dòng duy nhất).
    """
    try:
        single_line_segments = []
        for s in segments:
            orig = s.get("orig_text", "").strip()
            trans = s.get("translated_text", "").strip() or s.get("text", "").strip()
            raw_text = orig if (mode == "original" or not trans) else trans
            parts = split_segment_into_single_lines(s, raw_text, max_chars=40)
            single_line_segments.extend(parts)

        # Khử trùng thời gian để không chồng lấn
        for i in range(len(single_line_segments) - 1):
            if single_line_segments[i]["end"] > single_line_segments[i + 1]["start"]:
                single_line_segments[i]["end"] = max(
                    single_line_segments[i]["start"] + 0.1,
                    round(single_line_segments[i + 1]["start"] - 0.02, 3)
                )

        lines = []
        for idx, s in enumerate(single_line_segments, start=1):
            start_str = sec_to_srt_time(s["start"])
            end_str = sec_to_srt_time(s["end"])
            sub_text = s.get("display_text", "").strip()
            lines.append(f"{idx}\n{start_str} --> {end_str}\n{sub_text}\n")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return True
    except Exception:
        return False


# ── 7. Xuất file ASS với định dạng thẩm mỹ cao ──────────────────────────────
def export_ass_file(
    segments: List[Dict],
    output_path: str,
    video_w: int = 1280,
    video_h: int = 720,
    mode: str = "translated",
    font_name: str = "Arial",
    font_size: int = 20,
    color_hex: str = "FFE500",     # Mặc định Vàng nổi bật chống lóa
    outline_color_hex: str = "000000",
    margin_v: int = 14,
    box_style: str = "box",        # "box" (hộp đen mờ vuông vắn), "outline" (viền nét), "shadow" (đổ bóng)
) -> bool:
    """
    Xuất file .ass đảm bảo 100% CHỈ 1 DÒNG DUY NHẤT, hộp nền đen vuông vắn chuẩn Netflix/YouTube,
    không bao giờ bị gãy 2 dòng hay xếp chồng lên nhau.
    """
    try:
        # Tự động cân đối cỡ chữ theo chiều cao video
        actual_font_size = font_size
        if video_h <= 480 and actual_font_size > 20:
            actual_font_size = 18
        elif video_h >= 1080 and actual_font_size < 26:
            actual_font_size = 28

        # Chuyển RRGGBB sang định dạng ASS: &H00BBGGRR&
        r, g, b = color_hex[:2], color_hex[2:4], color_hex[4:6]
        ass_color = f"&H00{b}{g}{r}&"

        out_r, out_g, out_b = outline_color_hex[:2], outline_color_hex[2:4], outline_color_hex[4:6]

        if box_style == "box":
            # Hộp đen mờ vuông vắn, thẳng tắp, padding đều đặn
            border_style = 3
            ass_outline = "&H40000000&"
            ass_back = "&H40000000&"
            outline_val = 4.5
            shadow_val = 0
            bold_val = 1
        elif box_style == "shadow":
            border_style = 1
            ass_outline = f"&H00{out_b}{out_g}{out_r}&"
            ass_back = "&H80000000&"
            outline_val = 1.5
            shadow_val = 2.5
            bold_val = 1
        else:
            # Viền đen nét truyền thống
            border_style = 1
            ass_outline = f"&H00{out_b}{out_g}{out_r}&"
            ass_back = "&H80000000&"
            outline_val = 2.5
            shadow_val = 0.5
            bold_val = 1

        ass_lines = [
            "[Script Info]",
            "Title: Auto Subtitle",
            "ScriptType: v4.00+",
            "WrapStyle: 2",     # BẮT BUỘC: Cấm tự ngắt 2 dòng, chỉ hiển thị 1 dòng duy nhất!
            f"PlayResX: {video_w}",
            f"PlayResY: {video_h}",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Default,{font_name},{actual_font_size},{ass_color},&H000000FF&,{ass_outline},{ass_back},{bold_val},0,0,0,100,100,0,0,{border_style},{outline_val},{shadow_val},2,20,20,{margin_v},1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]

        # 1. Chuyển đổi và tách câu đảm bảo 100% CHỈ 1 DÒNG DUY NHẤT
        single_line_segments = []
        max_line_chars = 38 if video_w <= 640 else (46 if video_w <= 1280 else 54)

        for s in segments:
            orig = s.get("orig_text", "").strip()
            trans = s.get("translated_text", "").strip() or s.get("text", "").strip()

            if mode == "original" or not trans:
                raw_text = orig
            else:
                raw_text = trans

            parts = split_segment_into_single_lines(s, raw_text, max_chars=max_line_chars)
            single_line_segments.extend(parts)

        # 2. Khử trùng lặp thời gian tuyệt đối (chống libass xếp chồng 2 dòng lên nhau)
        for i in range(len(single_line_segments) - 1):
            if single_line_segments[i]["end"] > single_line_segments[i + 1]["start"]:
                single_line_segments[i]["end"] = max(
                    single_line_segments[i]["start"] + 0.1,
                    round(single_line_segments[i + 1]["start"] - 0.02, 3)
                )

        # 3. Sinh các dòng Events trong file ASS
        for s in single_line_segments:
            start_str = sec_to_ass_time(s["start"])
            end_str = sec_to_ass_time(s["end"])
            txt = s.get("display_text", "").strip()
            if not txt:
                continue

            # Thêm đệm khoảng trắng không ngắt \h hai bên để hộp nền đen vuông vắn, không bị sát chữ
            if box_style == "box":
                txt = f"\\h {txt} \\h"

            ass_lines.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{txt}")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(ass_lines))
        return True
    except Exception:
        return False


# ── 7. Gắn phụ đề vào Video (Hardsub) qua FFmpeg ─────────────────────────────
def burn_subtitles_to_video(
    video_path: str,
    ass_path: str,
    output_video_path: str,
    progress_cb: Optional[Callable[[int, str], None]] = None,
) -> Tuple[bool, str]:
    """
    Render gắn chết phụ đề (hardsub) vào video.
    Tự động kích hoạt GPU NVENC để render siêu tốc khi máy có hỗ trợ.
    """
    ffmpeg = get_ffmpeg_path()
    info = get_video_info(video_path)
    total_dur = info.get("duration", 0.0)

    # Escape đường dẫn Windows cho bộ lọc subtitles của FFmpeg
    ass_escaped = os.path.abspath(ass_path).replace("\\", "/").replace(":", "\\:")

    # Kiểm tra xem có thể dùng GPU NVIDIA NVENC không
    test_nvenc = subprocess.run(
        [ffmpeg, "-f", "lavfi", "-i", "nullsrc=s=640x480:d=1", "-c:v", "h264_nvenc", "-f", "null", "-"],
        capture_output=True
    )
    vcodec = "h264_nvenc" if test_nvenc.returncode == 0 else "libx264"
    # Giữ nguyên 100% độ phân giải, tỷ lệ khung hình gốc (không scale/kéo giãn)
    vf_arg = f"subtitles='{ass_escaped}'"

    cmd = [
        ffmpeg, "-y",
        "-i", video_path,
        "-vf", vf_arg,
        "-c:v", vcodec,
        "-pix_fmt", "yuv420p",
    ]
    if vcodec == "h264_nvenc":
        # Chuẩn chất lượng cao nguyên bản: Preset P7 cao nhất, CQ 14 cực nét, không trần bitrate
        cmd.extend([
            "-preset", "p7",
            "-tune", "hq",
            "-rc", "vbr",
            "-cq", "14",
            "-b:v", "0",
            "-spatial-aq", "1",
            "-temporal-aq", "1",
        ])
    else:
        # Fallback CPU: CRF 15 chuẩn near-lossless
        cmd.extend(["-preset", "slow", "-crf", "15", "-tune", "film"])

    # Giữ nguyên 100% âm thanh gốc, không nén lại
    cmd.extend(["-c:a", "copy", output_video_path])

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        time_pattern = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")

        for line in proc.stdout:
            match = time_pattern.search(line)
            if match and total_dur > 0:
                hours = int(match.group(1))
                mins = int(match.group(2))
                secs = float(match.group(3))
                current_time = hours * 3600 + mins * 60 + secs
                pct = min(99, int((current_time / total_dur) * 100))
                if progress_cb:
                    progress_cb(pct, f"Đang xuất video có phụ đề: {pct}%")

        proc.wait()
        if proc.returncode == 0 and os.path.exists(output_video_path):
            if progress_cb:
                progress_cb(100, "✓ Xuất video hoàn tất thành công!")
            return True, ""
        else:
            return False, f"FFmpeg trả về mã lỗi {proc.returncode}"
    except Exception as e:
        return False, str(e)
