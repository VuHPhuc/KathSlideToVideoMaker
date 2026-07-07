import os
import sys
import json
import wave
import asyncio
from pathlib import Path
from typing import Callable, Dict, Any, List, Optional, Tuple

import requests

# Set event loop policy on Windows to avoid 'Event loop is closed' crash in loops
if sys.platform == 'win32':
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

# Prepend python.exe folder to PATH so pydub/ffmpeg is always found
py_bin_dir = os.path.dirname(sys.executable)
if py_bin_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] = py_bin_dir + os.pathsep + os.environ.get("PATH", "")

# ── Thư mục lưu model ──────────────────────────────────────────────────────
MODELS_DIR = Path(__file__).parent.parent / "models" / "piper"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# ── Hugging Face base URL ───────────────────────────────────────────────────
HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"

VI_MALE_MODELS: Dict[str, Dict[str, Any]] = {
    "Edge-TTS vi-VN-NamMinhNeural (Giọng Nam - Rất hay)": {
        "engine": "edge",
        "voice": "vi-VN-NamMinhNeural",
        "description": "Giọng đọc Neural của Microsoft (Online). Giọng Nam miền Nam, cực kỳ tự nhiên, trôi chảy và chất lượng cao.",
        "multi_speaker": False,
        "default_speaker": 0,
    },
    "Edge-TTS vi-VN-NamMinhNeural (Giọng Nam Trầm - Ấm áp)": {
        "engine": "edge",
        "voice": "vi-VN-NamMinhNeural",
        "pitch": "-4Hz",
        "description": "Giọng đọc Neural của Microsoft với cao độ được hạ thấp nhẹ (-4Hz) tạo cảm giác giọng nam trầm ấm, cuốn hút.",
        "multi_speaker": False,
        "default_speaker": 0,
    },
    "Edge-TTS vi-VN-NamMinhNeural (Giọng Nam Trầm - Dày tiếng)": {
        "engine": "edge",
        "voice": "vi-VN-NamMinhNeural",
        "pitch": "-7Hz",
        "description": "Giọng đọc Neural của Microsoft với cao độ trầm sâu tối đa (-7Hz) tạo cảm giác giọng nam trầm dày, đĩnh đạc.",
        "multi_speaker": False,
        "default_speaker": 0,
    },
    "Edge-TTS vi-VN-HoaiMyNeural (Giọng Nữ - Rất hay)": {
        "engine": "edge",
        "voice": "vi-VN-HoaiMyNeural",
        "description": "Giọng đọc Neural của Microsoft (Online). Giọng Nữ, cực kỳ tự nhiên, trôi chảy và chất lượng cao.",
        "multi_speaker": False,
        "default_speaker": 0,
    },
    "Edge-TTS vi-VN-HoaiMyNeural (Giọng Nữ Trầm - Ấm áp)": {
        "engine": "edge",
        "voice": "vi-VN-HoaiMyNeural",
        "pitch": "-4Hz",
        "description": "Giọng đọc Nữ Neural của Microsoft với cao độ hạ thấp nhẹ (-4Hz) tạo cảm giác giọng nữ ấm áp, dịu dàng.",
        "multi_speaker": False,
        "default_speaker": 0,
    },
    "vi-vais1000-medium (~60 MB, giọng Offline Chất lượng tốt)": {
        "engine": "piper",
        "onnx_url":   f"{HF_BASE}/vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx",
        "config_url": f"{HF_BASE}/vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx.json",
        "onnx_file":   "vi_VN-vais1000-medium.onnx",
        "config_file": "vi_VN-vais1000-medium.onnx.json",
        "multi_speaker": False,
        "default_speaker": 0,
        "description": "Mô hình Piper Offline giọng đọc miền Nam chất lượng tốt (Medium). Đọc tự nhiên, trôi chảy và chạy 100% không cần mạng.",
    },
    "vi-25hours_single-low (~15 MB, giọng Nam Offline)": {
        "engine": "piper",
        "onnx_url":   f"{HF_BASE}/vi/vi_VN/25hours_single/low/vi_VN-25hours_single-low.onnx",
        "config_url": f"{HF_BASE}/vi/vi_VN/25hours_single/low/vi_VN-25hours_single-low.onnx.json",
        "onnx_file":   "vi_VN-25hours_single-low.onnx",
        "config_file": "vi_VN-25hours_single-low.onnx.json",
        "multi_speaker": False,
        "default_speaker": 0,
        "description": "Mô hình Piper Offline giọng Nam miền Nam. Tiết kiệm tài nguyên nhưng chất lượng trung bình.",
    },
    "vi-vivos-x_low  (~30 MB, đa giọng Offline)": {
        "engine": "piper",
        "onnx_url":   f"{HF_BASE}/vi/vi_VN/vivos/x_low/vi_VN-vivos-x_low.onnx",
        "config_url": f"{HF_BASE}/vi/vi_VN/vivos/x_low/vi_VN-vivos-x_low.onnx.json",
        "onnx_file":   "vi_VN-vivos-x_low.onnx",
        "config_file": "vi_VN-vivos-x_low.onnx.json",
        "multi_speaker": True,
        "default_speaker": 0,
        "description": "Mô hình Piper Offline đa giọng (65 người đọc). Hãy thử đổi Speaker ID để tìm giọng Nam ưng ý.",
    },
}



class TTSEngine:
    """Wrapper cho Piper TTS và Edge TTS với hỗ trợ on-demand download."""

    def __init__(self):
        self._voice = None
        self._current_model_name: Optional[str] = None

    # ── Download ────────────────────────────────────────────────────────────

    def is_model_downloaded(self, model_name: str) -> bool:
        info = VI_MALE_MODELS[model_name]
        if info.get("engine") == "edge":
            return True
        onnx_path   = MODELS_DIR / info["onnx_file"]
        config_path = MODELS_DIR / info["config_file"]
        return onnx_path.exists() and config_path.exists()

    def download_model(
        self,
        model_name: str,
        progress_callback: Callable[[int, str], None] = None,
    ) -> None:
        """Tải ONNX model và config từ Hugging Face."""
        info = VI_MALE_MODELS[model_name]
        if info.get("engine") == "edge":
            if progress_callback:
                progress_callback(100, "Giọng đọc online (Edge-TTS) — Sẵn sàng!")
            return

        files_to_download = [
            (info["onnx_url"],   info["onnx_file"]),
            (info["config_url"], info["config_file"]),
        ]
        total_files = len(files_to_download)

        for idx, (url, filename) in enumerate(files_to_download):
            dest = MODELS_DIR / filename
            if dest.exists():
                if progress_callback:
                    pct = int((idx + 1) / total_files * 100)
                    progress_callback(pct, f"{filename} (đã có sẵn)")
                continue

            if progress_callback:
                progress_callback(
                    int(idx / total_files * 100),
                    f"Đang tải {filename}..."
                )

            tmp_path = dest.with_suffix(".tmp")
            try:
                response = requests.get(url, stream=True, timeout=60)
                response.raise_for_status()

                total_bytes = int(response.headers.get("content-length", 0))
                downloaded  = 0

                with open(tmp_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback and total_bytes:
                                file_pct   = downloaded / total_bytes
                                global_pct = int((idx + file_pct) / total_files * 100)
                                progress_callback(global_pct, f"Đang tải {filename}...")

                tmp_path.rename(dest)

            except Exception as exc:
                if tmp_path.exists():
                    tmp_path.unlink()
                raise RuntimeError(f"Không thể tải '{filename}': {exc}") from exc

        if progress_callback:
            progress_callback(100, "Tải model xong!")

    # ── Load ────────────────────────────────────────────────────────────────

    def load_model(self, model_name: str) -> None:
        """Load model vào bộ nhớ (bỏ qua nếu đã load rồi)."""
        if self._current_model_name == model_name:
            # Nếu là Edge hoặc đã có model, không cần load lại
            info = VI_MALE_MODELS[model_name]
            if info.get("engine") == "edge" or self._voice is not None:
                return

        info = VI_MALE_MODELS[model_name]
        if info.get("engine") == "edge":
            self._voice = None
            self._current_model_name = model_name
            return

        # Piper load
        try:
            from piper.voice import PiperVoice
        except ImportError as exc:
            raise ImportError(
                "Thiếu thư viện piper-tts.\n"
                "Chạy: pip install piper-tts"
            ) from exc

        onnx_path   = str(MODELS_DIR / info["onnx_file"])
        config_path = str(MODELS_DIR / info["config_file"])

        self._voice = PiperVoice.load(onnx_path, config_path=config_path)
        self._current_model_name = model_name

    # ── Synthesize ──────────────────────────────────────────────────────────

    def synthesize(
        self,
        text: str,
        output_wav_path: str,
        speaker_id: int = 0,
        speed: float = 1.0,
    ) -> None:
        """Tổng hợp giọng nói từ text, lưu ra file WAV."""
        # Kiểm tra nếu text không có ký tự chữ hoặc số nào (ví dụ chỉ có dấu câu)
        if not any(c.isalnum() for c in text):
            from pydub import AudioSegment
            silence = AudioSegment.silent(duration=200)
            silence.export(output_wav_path, format="wav")
            return

        if not self._current_model_name:
            raise RuntimeError("Model chưa được load. Gọi load_model() trước.")

        info = VI_MALE_MODELS[self._current_model_name]

        if info.get("engine") == "edge":
            import asyncio
            import edge_tts
            from pydub import AudioSegment
            import os
            import time

            voice = info["voice"]
            temp_mp3 = output_wav_path + ".temp.mp3"

            # Ánh xạ tốc độ đọc (ví dụ: speed = 1.3 -> +30%)
            rate_pct = round((speed - 1.0) * 100)
            rate_str = f"+{rate_pct}%" if rate_pct >= 0 else f"{rate_pct}%"
            pitch_str = info.get("pitch", None)

            async def run_edge():
                # Chỉ truyền tham số pitch nếu có cấu hình trầm
                if pitch_str:
                    communicate = edge_tts.Communicate(text, voice, rate=rate_str, pitch=pitch_str)
                else:
                    communicate = edge_tts.Communicate(text, voice, rate=rate_str)
                await communicate.save(temp_mp3)

            # Thêm độ trễ nhỏ để tránh bị rate limit từ máy chủ Edge (tăng lên 0.5s để đảm bảo ổn định)
            time.sleep(0.5)

            success = False
            last_err = None
            backoffs = [1, 2, 2, 3, 3, 4, 5, 5, 5, 5]  # Tăng lên 10 lần thử với tổng thời gian chờ lớn hơn
            for attempt, delay in enumerate(backoffs):
                try:
                    # Chạy coroutine đồng bộ
                    asyncio.run(run_edge())
                    success = True
                    break
                except Exception as e:
                    last_err = e
                    print(f"[THÔNG BÁO] Kết nối Edge-TTS bị chậm/lỗi nhẹ (Đang tự động thử lại lần {attempt+1}/{len(backoffs)} sau {delay}s)...")
                    time.sleep(delay)

            if not success:
                # Không được tự ý thay thế bằng khoảng lặng nữa, bắt buộc phải lấy được tiếng
                raise RuntimeError(
                    f"Không thể kết nối đến máy chủ Edge-TTS để lấy âm thanh sau 10 lần thử.\n"
                    f"Chi tiết lỗi: {last_err}\n"
                    f"Văn bản câu lỗi: \"{text}\"\n\n"
                    f"Vui lòng kiểm tra lại kết nối mạng Internet hoặc thử lại sau."
                )

            try:
                # Chuyển đổi sang WAV
                audio = AudioSegment.from_mp3(temp_mp3)
                audio.export(output_wav_path, format="wav")
            finally:
                if os.path.exists(temp_mp3):
                    try:
                        os.remove(temp_mp3)
                    except Exception:
                        pass
            return

        # Piper Synthesis
        if self._voice is None:
            raise RuntimeError("Model chưa được load. Gọi load_model() trước.")

        from piper.config import SynthesisConfig
        # Ánh xạ tốc độ đọc sang length_scale (speed = 1.3 -> length_scale = 1.0 / 1.3 = 0.77)
        length_scale = 1.0 / max(0.1, speed)
        syn_config = SynthesisConfig(speaker_id=speaker_id, length_scale=length_scale)
        with wave.open(output_wav_path, "wb") as wav_file:
            self._voice.synthesize_wav(text, wav_file, syn_config=syn_config)

    # ── Speaker info ────────────────────────────────────────────────────────

    def get_speakers(self, model_name: str) -> List[Tuple[str, int]]:
        """
        Trả về danh sách (tên, speaker_id) từ file config.
        Nếu chưa tải model, trả về [(Nam 0, 0)].
        """
        info = VI_MALE_MODELS.get(model_name, {})
        if info.get("engine") == "edge":
            return [("Giọng đọc Neural (Mặc định)", 0)]

        config_path = MODELS_DIR / info.get("config_file", "")

        if not config_path.exists():
            return [("Người đọc 0", 0)]

        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)

            speaker_map: dict = config.get("speaker_id_map", {})
            if speaker_map:
                # Sắp xếp theo speaker_id
                return sorted(
                    ((name, sid) for name, sid in speaker_map.items()),
                    key=lambda x: x[1],
                )
            else:
                return [("Người đọc 0", 0)]

        except Exception:
            return [("Người đọc 0", 0)]
