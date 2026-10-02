"""
auto_subtitle_tab.py — Giao diện Tab Độc Lập: Tạo & Dịch Phụ Đề Video (AI Subtitle Studio)
Các chức năng:
1. Kéo thả file video vào nhận diện tức thì.
2. Tự động trích xuất âm thanh và dùng Whisper nhận diện giọng nói + timestamps.
3. Hộp thoại thông minh hỏi có cần dịch sang ngôn ngữ khác (cho phép chọn bất kỳ ngôn ngữ nào).
4. Dịch phụ đề tự động (Google Translate miễn phí tức thì hoặc Google Gemini AI).
5. Màn hình bảng xem trước và chỉnh sửa từng dòng phụ đề (Start, End, Gốc, Dịch).
6. Tùy chỉnh phong cách phụ đề (Cỡ chữ, Màu sắc, Song ngữ/Đơn ngữ).
7. Xuất file .SRT hoặc Render gắn phụ đề trực tiếp vào video (Hardsub MP4).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.core.video_subtitler import (
    SUPPORTED_LANGUAGES,
    WHISPER_MODELS,
    batch_translate_segments,
    burn_subtitles_to_video,
    export_ass_file,
    export_srt_file,
    extract_audio_from_video,
    get_video_info,
    sec_to_srt_time,
    transcribe_video_audio,
)


# ═══════════════════════════════════════════════════════════════════════════
#  WORKER THREADS
# ═══════════════════════════════════════════════════════════════════════════

class TranscribeVideoWorker(QThread):
    """Tiến trình tách audio & chạy Whisper Speech-to-Text."""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, list, str, float, str)  # success, segments, lang, prob, err

    def __init__(self, video_path: str, model_size: str, language: Optional[str] = None):
        super().__init__()
        self.video_path = video_path
        self.model_size = model_size
        self.language = language

    def run(self):
        tmp_dir = tempfile.mkdtemp(prefix="kath_sub_")
        wav_path = os.path.join(tmp_dir, "extracted_audio.wav")
        try:
            self.progress.emit(5, "Đang tách âm thanh từ video...")
            ok = extract_audio_from_video(self.video_path, wav_path)
            if not ok:
                self.finished.emit(False, [], "", 0.0, "Không thể trích xuất âm thanh từ video qua FFmpeg.")
                return

            self.progress.emit(15, f"Bắt đầu nạp Whisper AI ({self.model_size})...")
            segments, detected_lang, prob = transcribe_video_audio(
                wav_path,
                model_size=self.model_size,
                language=self.language,
                progress_cb=self.progress.emit,
            )
            self.finished.emit(True, segments, detected_lang, prob, "")
        except Exception as e:
            self.finished.emit(False, [], "", 0.0, str(e))
        finally:
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass


class TranslateWorker(QThread):
    """Tiến trình dịch toàn bộ phụ đề sang ngôn ngữ đích."""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, list, str)  # success, segments, err

    def __init__(self, segments: list, target_lang: str, source_lang: str = "auto", engine: str = "google", gemini_api_key: str = ""):
        super().__init__()
        self.segments = segments
        self.target_lang = target_lang
        self.source_lang = source_lang
        self.engine = engine
        self.gemini_api_key = gemini_api_key

    def run(self):
        try:
            res_segs = batch_translate_segments(
                self.segments,
                target_lang=self.target_lang,
                source_lang=self.source_lang,
                engine=self.engine,
                gemini_api_key=self.gemini_api_key,
                progress_cb=self.progress.emit,
            )
            self.finished.emit(True, res_segs, "")
        except Exception as e:
            self.finished.emit(False, self.segments, str(e))


class ExportVideoWorker(QThread):
    """Tiến trình render tạo video có phụ đề."""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str, str)  # success, out_path, err

    def __init__(self, video_path: str, segments: list, out_path: str, style_opts: dict):
        super().__init__()
        self.video_path = video_path
        self.segments = segments
        self.out_path = out_path
        self.style_opts = style_opts

    def run(self):
        tmp_dir = tempfile.mkdtemp(prefix="kath_render_")
        ass_path = os.path.join(tmp_dir, "subtitles.ass")
        try:
            info = get_video_info(self.video_path)
            orig_w = info.get("width", 1280)
            orig_h = info.get("height", 720)
            # Giữ nguyên 100% độ phân giải và tỷ lệ khung hình gốc của video import
            w = orig_w
            h = orig_h

            ok_ass = export_ass_file(
                segments=self.segments,
                output_path=ass_path,
                video_w=w,
                video_h=h,
                mode=self.style_opts.get("mode", "translated"),
                font_name=self.style_opts.get("font_name", "Arial"),
                font_size=self.style_opts.get("font_size", 24),
                color_hex=self.style_opts.get("color_hex", "FFFFFF"),
                outline_color_hex="000000",
                margin_v=self.style_opts.get("margin_v", 12),
                box_style=self.style_opts.get("box_style", "box"),
            )
            if not ok_ass:
                self.finished.emit(False, "", "Không thể khởi tạo file định dạng phụ đề ASS.")
                return

            self.progress.emit(10, "Bắt đầu gắn phụ đề vào video bằng FFmpeg...")
            ok_burn, err = burn_subtitles_to_video(
                video_path=self.video_path,
                ass_path=ass_path,
                output_video_path=self.out_path,
                progress_cb=self.progress.emit,
            )
            if ok_burn:
                self.finished.emit(True, self.out_path, "")
            else:
                self.finished.emit(False, "", err or "FFmpeg render thất bại.")
        except Exception as e:
            self.finished.emit(False, "", str(e))
        finally:
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════════
#  DROP ZONE CHO VIDEO
# ═══════════════════════════════════════════════════════════════════════════

class VideoDropZone(QFrame):
    """Vùng kéo thả file video hỗ trợ đa định dạng."""
    video_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("videoDropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(115)
        self.setStyleSheet("""
            QFrame#videoDropZone {
                background-color: #161b22;
                border: 2px dashed #30363d;
                border-radius: 10px;
                padding: 10px;
            }
            QFrame#videoDropZone:hover {
                border-color: #8b5cf6;
                background-color: #1c182a;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._icon_lbl = QLabel("🎬")
        self._icon_lbl.setStyleSheet("font-size: 32px; background: transparent;")
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._text_lbl = QLabel("Kéo & thả file Video vào đây (.mp4, .mkv, .mov, .avi, .webm)")
        self._text_lbl.setStyleSheet("color: #8b949e; font-size: 13px; font-weight: 500; background: transparent;")
        self._text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._choose_btn = QPushButton("📂  Chọn Video từ máy tính…")
        self._choose_btn.setFixedHeight(30)
        self._choose_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._choose_btn.clicked.connect(self._browse_file)
        btn_row.addWidget(self._choose_btn)

        layout.addWidget(self._icon_lbl)
        layout.addWidget(self._text_lbl)
        layout.addLayout(btn_row)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            for url in e.mimeData().urls():
                ext = Path(url.toLocalFile()).suffix.lower()
                if ext in (".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv", ".m4v"):
                    e.acceptProposedAction()
                    return
        e.ignore()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            path = url.toLocalFile()
            ext = Path(path).suffix.lower()
            if ext in (".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv", ".m4v"):
                self.video_selected.emit(path)
                e.acceptProposedAction()
                return

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn file Video",
            "",
            "Video files (*.mp4 *.mkv *.mov *.avi *.webm *.flv *.wmv *.m4v);;Tất cả (*.*)",
        )
        if path:
            self.video_selected.emit(path)


# ═══════════════════════════════════════════════════════════════════════════
#  TAB GIAO DIỆN CHÍNH
# ═══════════════════════════════════════════════════════════════════════════

class AutoSubtitleTab(QWidget):
    """Tab riêng biệt hoàn toàn: Nhận diện giọng nói từ video, Dịch phụ đề & Xuất video."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._video_path: str = ""
        self._segments: List[Dict] = []
        self._detected_language: str = ""

        self._transcribe_worker: Optional[TranscribeVideoWorker] = None
        self._translate_worker: Optional[TranslateWorker] = None
        self._export_worker: Optional[ExportVideoWorker] = None

        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 14, 18, 14)
        main_layout.setSpacing(12)

        # ── 1. Thẻ Top: Chọn Video & Cấu hình Nhận diện Whisper ──────────
        top_card = QFrame()
        top_card.setObjectName("card")
        top_card_lay = QVBoxLayout(top_card)
        top_card_lay.setContentsMargins(14, 12, 14, 12)
        top_card_lay.setSpacing(10)

        # Dropzone
        self._drop_zone = VideoDropZone()
        self._drop_zone.video_selected.connect(self._on_video_loaded)
        top_card_lay.addWidget(self._drop_zone)

        # Thanh thông tin video sau khi chọn
        self._video_info_bar = QFrame()
        self._video_info_bar.setStyleSheet("background-color: #0d1117; border-radius: 6px; padding: 6px;")
        self._video_info_bar.setVisible(False)
        info_lay = QHBoxLayout(self._video_info_bar)
        info_lay.setContentsMargins(8, 4, 8, 4)

        self._file_name_lbl = QLabel("🎥 Chưa chọn video")
        self._file_name_lbl.setStyleSheet("font-weight: 700; color: #58a6ff;")
        self._file_meta_lbl = QLabel("")
        self._file_meta_lbl.setStyleSheet("color: #8b949e;")

        info_lay.addWidget(self._file_name_lbl)
        info_lay.addSpacing(16)
        info_lay.addWidget(self._file_meta_lbl)
        info_lay.addStretch()

        self._reselect_btn = QPushButton("Đổi video khác")
        self._reselect_btn.setFixedHeight(26)
        self._reselect_btn.clicked.connect(self._drop_zone._browse_file)
        info_lay.addWidget(self._reselect_btn)

        top_card_lay.addWidget(self._video_info_bar)

        # Hàng điều khiển Whisper
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(10)

        # Model Whisper
        lbl_model = QLabel("Mô hình Whisper:")
        lbl_model.setStyleSheet("color: #c9d1d9; font-weight: 600;")
        ctrl_row.addWidget(lbl_model)

        self._model_combo = QComboBox()
        for idx, item in enumerate(WHISPER_MODELS):
            m_id = item[0]
            m_name = item[1]
            m_tip = item[2] if len(item) > 2 else ""
            self._model_combo.addItem(m_name, m_id)
            if m_tip:
                self._model_combo.setItemData(idx, m_tip, Qt.ItemDataRole.ToolTipRole)
        self._model_combo.setCurrentIndex(0)  # Mặc định 'small' (Khuyên dùng)
        self._model_combo.setMinimumWidth(230)
        self._model_combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        ctrl_row.addWidget(self._model_combo)

        # Ngôn ngữ trong video
        lbl_src_lang = QLabel("Ngôn ngữ video:")
        lbl_src_lang.setStyleSheet("color: #c9d1d9; font-weight: 600;")
        ctrl_row.addWidget(lbl_src_lang)

        self._src_lang_combo = QComboBox()
        self._src_lang_combo.addItem("🌐 Tự động nhận diện (Auto)", "auto")
        for code, name in SUPPORTED_LANGUAGES:
            self._src_lang_combo.addItem(name, code)
        self._src_lang_combo.setMinimumWidth(210)
        self._src_lang_combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        ctrl_row.addWidget(self._src_lang_combo)

        ctrl_row.addStretch()

        # Nút Bắt đầu nghe
        self._start_transcribe_btn = QPushButton("🎧  AI Nghe & Bóc Tách Script")
        self._start_transcribe_btn.setObjectName("primary")
        self._start_transcribe_btn.setFixedHeight(34)
        self._start_transcribe_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._start_transcribe_btn.clicked.connect(self._start_transcribe)
        self._start_transcribe_btn.setEnabled(False)
        ctrl_row.addWidget(self._start_transcribe_btn)

        top_card_lay.addLayout(ctrl_row)
        main_layout.addWidget(top_card)

        # ── 2. Thẻ Dịch thuật thông minh & Hộp thoại gợi ý ───────────────
        self._trans_card = QFrame()
        self._trans_card.setObjectName("card")
        self._trans_card.setStyleSheet("""
            QFrame#card {
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 8px;
            }
        """)
        trans_lay = QHBoxLayout(self._trans_card)
        trans_lay.setContentsMargins(14, 10, 14, 10)
        trans_lay.setSpacing(12)

        self._trans_status_badge = QLabel("🌍 Dịch Phụ Đề:")
        self._trans_status_badge.setStyleSheet("font-weight: 700; color: #a371f7;")
        trans_lay.addWidget(self._trans_status_badge)

        # Chọn Ngôn ngữ ĐÍCH (Target Language)
        trans_lay.addWidget(QLabel("Dịch sang:"))
        self._target_lang_combo = QComboBox()
        for code, name in SUPPORTED_LANGUAGES:
            self._target_lang_combo.addItem(name, code)
        self._target_lang_combo.setCurrentIndex(0)  # Mặc định Tiếng Việt
        self._target_lang_combo.setMinimumWidth(180)
        self._target_lang_combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        trans_lay.addWidget(self._target_lang_combo)

        # Chọn Công cụ dịch
        trans_lay.addWidget(QLabel("Bằng công cụ:"))
        self._engine_combo = QComboBox()
        self._engine_combo.addItem("⚡ Google Dịch (Miễn phí)", "google")
        self._engine_combo.addItem("🧠 Gemini AI (Thông minh)", "gemini")
        self._engine_combo.setMinimumWidth(190)
        self._engine_combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        trans_lay.addWidget(self._engine_combo)

        # Kiểu phụ đề
        trans_lay.addWidget(QLabel("Hiển thị:"))
        self._sub_mode_combo = QComboBox()
        self._sub_mode_combo.addItem("Đơn ngữ (Bản dịch)", "translated")
        self._sub_mode_combo.addItem("Song ngữ (Gốc + Dịch)", "bilingual")
        self._sub_mode_combo.addItem("Tiếng gốc (Không dịch)", "original")
        self._sub_mode_combo.setMinimumWidth(185)
        self._sub_mode_combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        self._sub_mode_combo.currentIndexChanged.connect(lambda: self._populate_table(self._segments))
        trans_lay.addWidget(self._sub_mode_combo)

        trans_lay.addStretch()

        # Nút Dịch phụ đề
        self._translate_btn = QPushButton("🌍  Dịch Phụ Đề Ngay")
        self._translate_btn.setFixedHeight(30)
        self._translate_btn.setStyleSheet("""
            QPushButton {
                background-color: #238636;
                color: #ffffff;
                font-weight: 600;
                border-radius: 6px;
                padding: 0 14px;
            }
            QPushButton:hover { background-color: #2ea043; }
            QPushButton:disabled { background-color: #21262d; color: #484f58; }
        """)
        self._translate_btn.setEnabled(False)
        self._translate_btn.clicked.connect(self._start_translation)
        trans_lay.addWidget(self._translate_btn)

        main_layout.addWidget(self._trans_card)

        # ── 3. Bảng Editor Xem & Sửa Phụ Đề (Interactive Table) ──────────
        table_container = QFrame()
        table_container.setObjectName("card")
        table_lay = QVBoxLayout(table_container)
        table_lay.setContentsMargins(12, 12, 12, 12)
        table_lay.setSpacing(8)

        # Header bảng
        tb_hdr = QHBoxLayout()
        self._sub_count_lbl = QLabel("BẢNG PHỤ ĐỀ (0 câu)")
        self._sub_count_lbl.setObjectName("heading")
        tb_hdr.addWidget(self._sub_count_lbl)

        tb_hdr.addStretch()

        # Ô tìm kiếm trong bảng
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("🔍 Tìm từ khóa...")
        self._search_input.setFixedWidth(180)
        self._search_input.textChanged.connect(self._on_search_text)
        tb_hdr.addWidget(self._search_input)

        # Nút thêm/xóa dòng
        self._add_row_btn = QPushButton("➕ Thêm dòng")
        self._add_row_btn.setFixedHeight(26)
        self._add_row_btn.clicked.connect(self._on_add_row)
        tb_hdr.addWidget(self._add_row_btn)

        self._del_row_btn = QPushButton("➖ Xóa dòng")
        self._del_row_btn.setFixedHeight(26)
        self._del_row_btn.clicked.connect(self._on_delete_row)
        tb_hdr.addWidget(self._del_row_btn)

        table_lay.addLayout(tb_hdr)

        # Bảng TableWidget
        self._sub_table = QTableWidget(0, 5)
        self._sub_table.setHorizontalHeaderLabels([
            "#", "Bắt đầu", "Kết thúc", "Lời thoại gốc (Original)", "Bản dịch / Phụ đề hiển thị (Bấm để sửa)"
        ])
        self._sub_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._sub_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._sub_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._sub_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self._sub_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._sub_table.setColumnWidth(3, 300)
        self._sub_table.verticalHeader().setVisible(False)
        self._sub_table.setStyleSheet("""
            QTableWidget {
                background-color: #0d1117;
                border: 1px solid #30363d;
                gridline-color: #21262d;
                color: #e6edf3;
                selection-background-color: #2d1f4d;
                selection-color: #ffffff;
            }
            QHeaderView::section {
                background-color: #161b22;
                color: #8b949e;
                font-weight: 700;
                font-size: 11px;
                border: 1px solid #21262d;
                padding: 6px;
            }
        """)
        self._sub_table.itemChanged.connect(self._on_table_item_changed)
        table_lay.addWidget(self._sub_table, 1)

        main_layout.addWidget(table_container, 1)

        # ── 4. Thanh Tiến Trình & Trạng Thái ─────────────────────────────
        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setVisible(False)
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #21262d;
                border-radius: 4px;
                border: none;
            }
            QProgressBar::chunk {
                background-color: #8b5cf6;
                border-radius: 4px;
            }
        """)
        main_layout.addWidget(self._progress_bar)

        # ── 5. Thẻ Đáy: Tùy chỉnh Kiểu dáng & Nút Xuất Video ─────────────
        bot_card = QFrame()
        bot_card.setObjectName("card")
        bot_card_lay = QVBoxLayout(bot_card)
        bot_card_lay.setContentsMargins(14, 10, 14, 10)
        bot_card_lay.setSpacing(8)

        # Hàng 1: Tùy chỉnh kiểu dáng phụ đề (Cỡ chữ, màu sắc, khung nền, khoảng cách)
        style_row = QHBoxLayout()
        style_row.setSpacing(10)

        style_row.addWidget(QLabel("🎨 Cỡ chữ:"))
        self._font_size_combo = QComboBox()
        for sz in [18, 20, 22, 24, 26, 28, 32, 36]:
            self._font_size_combo.addItem(f"{sz}px", sz)
        self._font_size_combo.setCurrentIndex(2)  # 22px
        self._font_size_combo.setFixedWidth(80)
        style_row.addWidget(self._font_size_combo)

        style_row.addWidget(QLabel("Màu chữ:"))
        self._color_combo = QComboBox()
        self._color_combo.addItem("Trắng sáng", "FFFFFF")
        self._color_combo.addItem("Vàng nổi bật ⭐", "FFE500")
        self._color_combo.addItem("Xanh Cyan mát", "00FFFF")
        self._color_combo.addItem("Xanh lá tươi", "00FF66")
        self._color_combo.setCurrentIndex(1)  # Vàng nổi bật
        self._color_combo.setMinimumWidth(140)
        self._color_combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        style_row.addWidget(self._color_combo)

        style_row.addWidget(QLabel("Kiểu nền:"))
        self._box_style_combo = QComboBox()
        self._box_style_combo.addItem("📦 Hộp đen mờ (YouTube)", "box")
        self._box_style_combo.addItem("🔤 Viền đen nét", "outline")
        self._box_style_combo.addItem("🌓 Đổ bóng mềm", "shadow")
        self._box_style_combo.setCurrentIndex(0)  # Mặc định: Hộp đen mờ
        self._box_style_combo.setMinimumWidth(170)
        self._box_style_combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        style_row.addWidget(self._box_style_combo)

        style_row.addWidget(QLabel("Cách đáy:"))
        self._margin_combo = QComboBox()
        self._margin_combo.addItem("12px (Sát đáy)", 12)
        self._margin_combo.addItem("25px (Tiêu chuẩn)", 25)
        self._margin_combo.addItem("45px (Cao)", 45)
        self._margin_combo.addItem("70px (Rất cao)", 70)
        self._margin_combo.setCurrentIndex(0)  # Mặc định 12px sát đáy
        self._margin_combo.setMinimumWidth(130)
        self._margin_combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)
        style_row.addWidget(self._margin_combo)

        style_row.addStretch()

        # Nút Xuất file .SRT
        self._export_srt_btn = QPushButton("💾  Lưu File .SRT")
        self._export_srt_btn.setFixedHeight(30)
        self._export_srt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_srt_btn.clicked.connect(self._export_srt_dialog)
        self._export_srt_btn.setEnabled(False)
        style_row.addWidget(self._export_srt_btn)

        bot_card_lay.addLayout(style_row)

        # Hàng 2: Trạng thái chi tiết & Nút Xuất Video lớn
        act_row = QHBoxLayout()
        act_row.setSpacing(12)

        self._status_lbl = QLabel("Sẵn sàng. Kéo thả file video để bắt đầu.")
        self._status_lbl.setStyleSheet("color: #7d8590; font-size: 13px; font-weight: 500;")
        act_row.addWidget(self._status_lbl, 1)

        self._export_video_btn = QPushButton("🎬  XUẤT VIDEO CÓ PHỤ ĐỀ  ➔")
        self._export_video_btn.setObjectName("success")
        self._export_video_btn.setFixedHeight(36)
        self._export_video_btn.setMinimumWidth(230)
        self._export_video_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_video_btn.clicked.connect(self._export_video_dialog)
        self._export_video_btn.setEnabled(False)
        act_row.addWidget(self._export_video_btn)

        bot_card_lay.addLayout(act_row)

        main_layout.addWidget(bot_card)

    # ═══════════════════════════════════════════════════════════════════
    #  SỰ KIỆN XỬ LÝ VIDEO & BÓC TÁCH SCRIPT
    # ═══════════════════════════════════════════════════════════════════

    def _on_video_loaded(self, path: str):
        """Khi người dùng kéo thả hoặc chọn 1 file video."""
        self._video_path = path
        p = Path(path)
        self._drop_zone.setVisible(False)
        self._video_info_bar.setVisible(True)

        self._file_name_lbl.setText(f"🎥 {p.name}")

        info = get_video_info(path)
        dur = info.get("duration", 0.0)
        mins = int(dur // 60)
        secs = int(dur % 60)
        w = info.get("width", 0)
        h = info.get("height", 0)
        size_mb = p.stat().st_size / (1024 * 1024)

        self._file_meta_lbl.setText(f"Thời lượng: {mins:02d}:{secs:02d} | Phân giải: {w}x{h} | Dung lượng: {size_mb:.1f} MB")
        self._start_transcribe_btn.setEnabled(True)
        self._status_lbl.setText("Đã nạp video. Bấm 'AI Nghe & Bóc Tách Script' để bắt đầu.")

    def _start_transcribe(self):
        """Khởi chạy Whisper để nghe và nhận diện giọng nói."""
        if not self._video_path or not os.path.exists(self._video_path):
            QMessageBox.warning(self, "Chưa có video", "Vui lòng chọn hoặc kéo thả 1 file video hợp lệ.")
            return

        model_size = self._model_combo.currentData()
        src_lang = self._src_lang_combo.currentData()

        self._start_transcribe_btn.setEnabled(False)
        self._translate_btn.setEnabled(False)
        self._export_srt_btn.setEnabled(False)
        self._export_video_btn.setEnabled(False)

        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(5)
        self._status_lbl.setText("Đang khởi động AI Whisper...")

        self._transcribe_worker = TranscribeVideoWorker(
            video_path=self._video_path,
            model_size=model_size,
            language=src_lang,
        )
        self._transcribe_worker.progress.connect(self._on_progress_update)
        self._transcribe_worker.finished.connect(self._on_transcribe_finished)
        self._transcribe_worker.start()

    def _on_progress_update(self, pct: int, msg: str):
        self._progress_bar.setValue(pct)
        self._status_lbl.setText(msg)

    def _on_transcribe_finished(self, success: bool, segments: list, detected_lang: str, prob: float, err: str):
        self._progress_bar.setVisible(False)
        self._start_transcribe_btn.setEnabled(True)

        if not success:
            QMessageBox.critical(self, "Lỗi nhận diện giọng nói", f"Không thể bóc tách phụ đề:\n{err}")
            self._status_lbl.setText("Nhận diện thất bại.")
            return

        self._segments = segments
        self._detected_language = detected_lang
        self._populate_table(self._segments)

        self._translate_btn.setEnabled(True)
        self._export_srt_btn.setEnabled(True)
        self._export_video_btn.setEnabled(True)

        # Lấy tên ngôn ngữ phát hiện được
        lang_dict = dict(SUPPORTED_LANGUAGES)
        lang_name = lang_dict.get(detected_lang, detected_lang.upper())
        self._status_lbl.setText(f"✓ Hoàn tất! Phát hiện {len(segments)} câu lời thoại ({lang_name} - {int(prob*100)}%).")

        # ── HỎI NGƯỜI DÙNG CÓ CẦN DỊCH KHÔNG ──────────────────────────
        self._prompt_translation_dialog(lang_name, detected_lang)

    def _prompt_translation_dialog(self, lang_name: str, detected_lang: str):
        """Hộp thoại thông minh hỏi người dùng có cần dịch phụ đề không."""
        # Nếu ngôn ngữ video khác Tiếng Việt (hoặc người dùng muốn dịch sang bất kỳ tiếng nào)
        reply = QMessageBox.question(
            self,
            "🌍 Hỏi Dịch Phụ Đề Tự Động",
            f"AI đã nhận diện thành công {len(self._segments)} câu lời thoại!\n\n"
            f"Ngôn ngữ phát hiện trong video: 【 {lang_name} 】\n\n"
            f"Bạn có muốn dịch phụ đề sang ngôn ngữ khác (ví dụ: {self._target_lang_combo.currentText()}) ngay bây giờ không?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._start_translation()

    # ═══════════════════════════════════════════════════════════════════
    #  DỊCH THUẬT PHỤ ĐỀ
    # ═══════════════════════════════════════════════════════════════════

    def _start_translation(self):
        """Khởi chạy tiến trình dịch phụ đề sang ngôn ngữ đích."""
        if not self._segments:
            QMessageBox.information(self, "Chưa có phụ đề", "Vui lòng cho AI nghe video trước khi dịch.")
            return

        target_lang = self._target_lang_combo.currentData()
        engine = self._engine_combo.currentData()

        # Kiểm tra API Key nếu chọn Gemini
        gemini_key = ""
        if engine == "gemini":
            from PyQt6.QtCore import QSettings
            settings = QSettings("KathTTS", "KathSlideToVideoMaker")
            gemini_key = settings.value("gemini_api_key", "").strip() or os.getenv("GEMINI_API_KEY", "")
            if not gemini_key:
                QMessageBox.warning(
                    self, "Thiếu Gemini API Key",
                    "Chưa tìm thấy Gemini API Key trong cài đặt ứng dụng.\n"
                    "Hệ thống sẽ tự động chuyển sang Google Dịch miễn phí siêu tốc!"
                )
                engine = "google"

        self._translate_btn.setEnabled(False)
        self._export_video_btn.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(10)

        target_name = self._target_lang_combo.currentText()
        self._status_lbl.setText(f"Đang dịch {len(self._segments)} câu sang {target_name}...")

        # Tự động phát hiện & tránh lỗi cùng ngôn ngữ nguồn - đích khiến Google/Gemini bỏ qua
        src_lang = (self._detected_language or "auto").strip()
        if src_lang.lower().split("-")[0] == target_lang.lower().split("-")[0]:
            src_lang = "auto"

        self._translate_worker = TranslateWorker(
            segments=self._segments,
            target_lang=target_lang,
            source_lang=src_lang,
            engine=engine,
            gemini_api_key=gemini_key,
        )
        self._translate_worker.progress.connect(self._on_progress_update)
        self._translate_worker.finished.connect(self._on_translate_finished)
        self._translate_worker.start()

    def _on_translate_finished(self, success: bool, segments: list, err: str):
        self._progress_bar.setVisible(False)
        self._translate_btn.setEnabled(True)
        self._export_video_btn.setEnabled(True)

        if not success:
            QMessageBox.critical(self, "Lỗi dịch thuật", f"Không thể dịch phụ đề:\n{err}")
            self._status_lbl.setText("Dịch thất bại.")
            return

        self._segments = segments
        self._populate_table(self._segments)
        target_name = self._target_lang_combo.currentText()
        self._status_lbl.setText(f"✓ Đã dịch xong toàn bộ {len(segments)} câu sang {target_name}!")
        QMessageBox.information(
            self, "Dịch hoàn tất",
            f"Đã dịch thành công sang {target_name}!\n\n"
            "Bạn có thể xem lại hoặc bấm vào bảng để sửa trực tiếp câu chữ trước khi xuất video."
        )

    # ═══════════════════════════════════════════════════════════════════
    #  HIỂN THỊ & CHỈNH SỬA BẢNG PHỤ ĐỀ
    # ═══════════════════════════════════════════════════════════════════

    def _populate_table(self, segments: list):
        """Đổ dữ liệu phụ đề vào TableWidget theo chế độ hiển thị."""
        self._sub_table.blockSignals(True)
        self._sub_table.setRowCount(len(segments))
        sub_mode = self._sub_mode_combo.currentData() if hasattr(self, "_sub_mode_combo") else "translated"

        for row, s in enumerate(segments):
            # Cột 0: STT
            item_id = QTableWidgetItem(str(row + 1))
            item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_id.setFlags(item_id.flags() & ~Qt.ItemFlag.ItemIsEditable)

            # Cột 1: Start
            item_start = QTableWidgetItem(sec_to_srt_time(s["start"]))
            item_start.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Cột 2: End
            item_end = QTableWidgetItem(sec_to_srt_time(s["end"]))
            item_end.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Cột 3: Tiếng gốc
            orig = s.get("orig_text", "").strip()
            item_orig = QTableWidgetItem(orig)
            item_orig.setForeground(QColor("#8b949e"))

            # Cột 4: Phụ đề hiển thị / Bản dịch (tương ứng với chế độ Đơn ngữ / Song ngữ / Tiếng gốc)
            trans = s.get("translated_text", "").strip() or s.get("text", "").strip()
            if sub_mode == "bilingual" and orig and trans and orig != trans:
                display_text = f"{orig}\n{trans}"
            elif sub_mode == "original" or not trans:
                display_text = orig
            else:
                display_text = trans

            item_trans = QTableWidgetItem(display_text)
            item_trans.setForeground(QColor("#ffffff"))
            item_trans.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))

            self._sub_table.setItem(row, 0, item_id)
            self._sub_table.setItem(row, 1, item_start)
            self._sub_table.setItem(row, 2, item_end)
            self._sub_table.setItem(row, 3, item_orig)
            self._sub_table.setItem(row, 4, item_trans)

        self._sub_table.blockSignals(False)
        self._sub_count_lbl.setText(f"BẢNG PHỤ ĐỀ ({len(segments)} câu)")

    def _on_table_item_changed(self, item: QTableWidgetItem):
        """Khi người dùng sửa trực tiếp một ô trong bảng phụ đề."""
        row = item.row()
        col = item.column()
        if 0 <= row < len(self._segments):
            if col == 4:
                # Cập nhật bản dịch
                new_text = item.text().strip()
                self._segments[row]["translated_text"] = new_text
                self._segments[row]["text"] = new_text
            elif col == 3:
                # Cập nhật tiếng gốc
                self._segments[row]["orig_text"] = item.text().strip()

    def _on_search_text(self, text: str):
        """Lọc nhanh câu thoại trong bảng theo từ khóa."""
        text_lower = text.strip().lower()
        for row in range(self._sub_table.rowCount()):
            if not text_lower:
                self._sub_table.setRowHidden(row, False)
                continue
            orig_item = self._sub_table.item(row, 3)
            trans_item = self._sub_table.item(row, 4)
            orig = orig_item.text().lower() if orig_item else ""
            trans = trans_item.text().lower() if trans_item else ""
            matches = (text_lower in orig or text_lower in trans)
            self._sub_table.setRowHidden(row, not matches)

    def _on_add_row(self):
        """Thêm 1 câu phụ đề mới ở cuối."""
        new_start = self._segments[-1]["end"] if self._segments else 0.0
        new_end = new_start + 3.0
        new_seg = {
            "id": len(self._segments) + 1,
            "start": round(new_start, 3),
            "end": round(new_end, 3),
            "orig_text": "Câu thoại mới",
            "text": "Câu thoại mới",
            "translated_text": "Câu thoại mới",
        }
        self._segments.append(new_seg)
        self._populate_table(self._segments)

    def _on_delete_row(self):
        """Xóa câu phụ đề đang chọn."""
        curr_row = self._sub_table.currentRow()
        if 0 <= curr_row < len(self._segments):
            del self._segments[curr_row]
            self._populate_table(self._segments)

    # ═══════════════════════════════════════════════════════════════════
    #  XUẤT FILE PHỤ ĐỀ SRT & XUẤT VIDEO HARDSUB
    # ═══════════════════════════════════════════════════════════════════

    def _export_srt_dialog(self):
        """Lưu phụ đề ra file .SRT."""
        if not self._segments:
            return
        default_name = f"{Path(self._video_path).stem}_subtitles.srt" if self._video_path else "subtitles.srt"
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Lưu file phụ đề SRT", default_name, "SRT Subtitle (*.srt);;Tất cả (*.*)"
        )
        if save_path:
            mode = self._sub_mode_combo.currentData()
            ok = export_srt_file(self._segments, save_path, mode=mode)
            if ok:
                QMessageBox.information(self, "Lưu thành công", f"Đã xuất file phụ đề tại:\n{save_path}")
            else:
                QMessageBox.critical(self, "Lỗi", "Không thể ghi file phụ đề.")

    def _export_video_dialog(self):
        """Lưu video mới đã được gắn phụ đề hoàn chỉnh."""
        if not self._video_path or not self._segments:
            QMessageBox.warning(self, "Chưa sẵn sàng", "Vui lòng chọn video và tạo phụ đề trước khi xuất.")
            return

        default_name = f"{Path(self._video_path).stem}_subtitled.mp4"
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Chọn nơi lưu Video có phụ đề", default_name, "MP4 Video (*.mp4);;Tất cả (*.*)"
        )
        if not save_path:
            return

        style_opts = {
            "mode": self._sub_mode_combo.currentData(),
            "font_size": self._font_size_combo.currentData(),
            "color_hex": self._color_combo.currentData(),
            "margin_v": self._margin_combo.currentData(),
            "box_style": self._box_style_combo.currentData(),
            "font_name": "Arial",
        }

        self._export_video_btn.setEnabled(False)
        self._export_srt_btn.setEnabled(False)
        self._translate_btn.setEnabled(False)
        self._start_transcribe_btn.setEnabled(False)

        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(5)
        self._status_lbl.setText("Đang khởi tạo tiến trình xuất video...")

        self._export_worker = ExportVideoWorker(
            video_path=self._video_path,
            segments=self._segments,
            out_path=save_path,
            style_opts=style_opts,
        )
        self._export_worker.progress.connect(self._on_progress_update)
        self._export_worker.finished.connect(self._on_export_video_finished)
        self._export_worker.start()

    def _on_export_video_finished(self, success: bool, out_path: str, err: str):
        self._progress_bar.setVisible(False)
        self._export_video_btn.setEnabled(True)
        self._export_srt_btn.setEnabled(True)
        self._translate_btn.setEnabled(True)
        self._start_transcribe_btn.setEnabled(True)

        if not success:
            QMessageBox.critical(self, "Lỗi xuất Video", f"Không thể xuất video có phụ đề:\n{err}")
            self._status_lbl.setText("Xuất video thất bại.")
            return

        self._status_lbl.setText(f"✓ Đã xuất thành công: {Path(out_path).name}")
        reply = QMessageBox.information(
            self,
            "🎉 Xuất Video Thành Công!",
            f"Video có phụ đề đã được tạo thành công tại:\n{out_path}\n\n"
            "Bạn có muốn mở thư mục chứa video không?",
            QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Open,
        )
        if reply == QMessageBox.StandardButton.Open:
            try:
                import subprocess
                subprocess.run(["explorer", "/select,", os.path.normpath(out_path)])
            except Exception:
                pass
