"""
mp3_exporter.py — Pipeline: Text → WAV (Piper) → Word timestamps (Whisper) → MP3 + JSON
"""

import json
import re
import tempfile
from pathlib import Path
from typing import Callable, Dict, Any, List, Optional

from pydub import AudioSegment


# ── Whisper model cache dir ─────────────────────────────────────────────────
WHISPER_CACHE = Path(__file__).parent.parent / "models" / "whisper"
WHISPER_CACHE.mkdir(parents=True, exist_ok=True)


# ── Text splitting ──────────────────────────────────────────────────────────

def split_into_sentences(text: str) -> List[str]:
    """
    Chia văn bản thành danh sách câu để TTS từng câu riêng.
    Mỗi câu sẽ có timestamps riêng biệt trong output JSON.
    """
    # Chuẩn hóa line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Tách theo đoạn (double newline) trước
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    sentences: List[str] = []
    for para in paragraphs:
        # Thay single newline bằng space trong mỗi đoạn
        para = re.sub(r"\n", " ", para)
        # Tách theo dấu câu kết thúc câu
        parts = re.split(r"(?<=[.!?…])\s+", para)
        for part in parts:
            part = part.strip()
            if part:
                sentences.append(part)

    return sentences


# ── Export Pipeline ─────────────────────────────────────────────────────────

class ExportPipeline:
    """
    Pipeline xuất MP3 + JSON timestamps:
    1. Piper TTS → WAV từng câu
    2. Ghép WAV + thêm khoảng lặng giữa câu
    3. faster-whisper → word-level timestamps
    4. pydub → MP3 192kbps
    5. Lưu JSON timestamps
    """

    SILENCE_BETWEEN_SENTENCES_MS = 150   # ms lặng ngắn giữa các câu để có điểm dừng nhẹ
    SILENCE_BETWEEN_PARAGRAPHS_MS = 250  # ms lặng ngắn giữa đoạn văn

    def __init__(self):
        self._whisper_model = None

    def _ensure_ffmpeg(self) -> None:
        """Kiểm tra ffmpeg có trong PATH không."""
        import shutil
        if not shutil.which("ffmpeg"):
            raise RuntimeError(
                "Không tìm thấy ffmpeg!\n\n"
                "Cài ffmpeg:\n"
                "  1. Tải tại: https://www.gyan.dev/ffmpeg/builds/\n"
                "  2. Giải nén và thêm thư mục bin vào PATH.\n"
                "  3. Khởi động lại ứng dụng."
            )

    def _load_whisper(self, progress_callback: Optional[Callable] = None) -> None:
        """Load faster-whisper model (tải lần đầu ~75MB)."""
        if self._whisper_model is not None:
            return

        if progress_callback:
            progress_callback(0, "Đang tải Whisper model (lần đầu ~75MB)...")

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ImportError(
                "Thiếu thư viện faster-whisper.\n"
                "Chạy: pip install faster-whisper"
            ) from exc

        self._whisper_model = WhisperModel(
            "tiny",
            device="cpu",
            compute_type="int8",
            download_root=str(WHISPER_CACHE),
        )

    def run(
        self,
        text: str,
        tts_engine,
        speaker_id: int,
        output_mp3: str,
        progress_callback: Callable[[int, str], None] = None,
        use_whisper_align: bool = True,
        speed: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Chạy toàn bộ pipeline.
        Trả về dict JSON timestamps.
        Ném exception nếu có lỗi.
        """
        self._ensure_ffmpeg()

        sentences = split_into_sentences(text)
        if not sentences:
            raise ValueError("Văn bản trống — không có câu nào để xử lý.")

        def _prog(pct: int, msg: str):
            if progress_callback:
                progress_callback(pct, msg)

        # ── Bước 1: TTS từng câu → WAV ──────────────────────────────────────
        wav_segments: List[AudioSegment] = []
        sentence_durations_ms: List[int] = []

        n = len(sentences)
        with tempfile.TemporaryDirectory() as tmp_dir:

            for i, sentence in enumerate(sentences):
                pct_start = int(i / n * 55)          # TTS chiếm 0–55%
                _prog(pct_start, f"Đang đọc câu {i + 1}/{n}...")

                wav_path = f"{tmp_dir}/seg_{i:04d}.wav"
                tts_engine.synthesize(sentence, wav_path, speaker_id, speed=speed)

                seg = AudioSegment.from_wav(wav_path)
                wav_segments.append(seg)
                sentence_durations_ms.append(len(seg))

            # ── Bước 2: Ghép audio + thêm lặng ─────────────────────────────
            _prog(56, "Đang ghép audio...")

            pause = AudioSegment.silent(duration=self.SILENCE_BETWEEN_SENTENCES_MS)
            combined = AudioSegment.empty()
            for i, seg in enumerate(wav_segments):
                combined += seg
                if i < len(wav_segments) - 1:
                    combined += pause

            # Tính sentence timestamps chính xác từ độ dài WAV riêng lẻ
            sentence_data: List[Dict[str, Any]] = []
            cursor_ms = 0
            for i, (sentence, dur_ms) in enumerate(zip(sentences, sentence_durations_ms)):
                sentence_data.append({
                    "index":    i,
                    "text":     sentence,
                    "start_ms": cursor_ms,
                    "end_ms":   cursor_ms + dur_ms,
                    "words":    [],
                })
                cursor_ms += dur_ms + self.SILENCE_BETWEEN_SENTENCES_MS

            # ── Bước 3: Whisper word-level alignment ────────────────────────
            if use_whisper_align:
                _prog(60, "Đang tải Whisper model...")
                self._load_whisper(progress_callback)

                full_wav_path = f"{tmp_dir}/full.wav"
                combined.export(full_wav_path, format="wav")

                _prog(65, "Đang phân tích timestamps từng từ (Whisper)...")
                segments_iter, _ = self._whisper_model.transcribe(
                    full_wav_path,
                    language="vi",
                    word_timestamps=True,
                )

                all_words: List[Dict[str, Any]] = []
                for seg in segments_iter:
                    if seg.words:
                        for w in seg.words:
                            all_words.append({
                                "word":     w.word.strip(),
                                "start_ms": int(w.start * 1000),
                                "end_ms":   int(w.end * 1000),
                            })

                _prog(85, "Đang gán từ vào câu...")

                # Gán words vào đúng sentence theo thời gian
                for sent in sentence_data:
                    sent["words"] = [
                        w for w in all_words
                        if sent["start_ms"] <= w["start_ms"] < sent["end_ms"]
                    ]

            # ── Bước 4: Xuất MP3 ────────────────────────────────────────────
            _prog(90, "Đang xuất MP3...")
            combined.export(output_mp3, format="mp3", bitrate="192k")

        # ── Bước 5: Lưu JSON ────────────────────────────────────────────────
        _prog(97, "Đang ghi file timestamps JSON...")

        result: Dict[str, Any] = {
            "version":           "1.0",
            "total_duration_ms": len(combined),
            "sentence_count":    len(sentence_data),
            "sentences":         sentence_data,
        }

        json_path = str(Path(output_mp3).with_suffix(".json"))
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        _prog(100, "✓ Hoàn thành!")
        return result
