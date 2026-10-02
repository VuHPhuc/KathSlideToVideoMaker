"""
ai_studio_tab.py — Giao diện AI Storyboard Studio (PyQt6, Dark Theme)
Tích hợp toàn diện:
1. Google Gemini API Key & Kết nối Google Flow (flow.google / Veo AI Video).
2. Mở Chrome Google Flow chính thống (Port 9222) đăng nhập không bị Google chặn.
3. Kéo (Pull) 1-Click các video MP4 đã sinh từ Google Flow / Downloads vào Storyboard.
4. Render Slide 1080p chuẩn Gemini / NotebookLM Bento (Stats $67B, Roadmap Timeline).
5. Đồng bộ 1-Click kịch bản & Media sang Timeline.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QSize, QSettings, QTimer,
)
from PyQt6.QtGui import (
    QColor, QDragEnterEvent, QDropEvent, QFont, QPixmap, QIcon,
)
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QSplitter, QStackedWidget, QVBoxLayout, QWidget, QDialog,
    QTableWidget, QTableWidgetItem, QHeaderView,
)

from app.core.ai_engine import GeminiAIEngine, DEFAULT_MODEL, AVAILABLE_MODELS
from app.core.file_reader import read_file
from app.core.pptx_builder import PPTXBuilder, render_slide_to_image
from app.core.google_flow_engine import GoogleFlowEngine
from app.core.tts_engine import TTSEngine
from app.core.mp3_exporter import ExportPipeline


def get_ai_media_output_dir() -> Path:
    """Trả về thư mục lưu trữ media của AI Studio trong thư mục dự án."""
    p = Path(os.getcwd()) / "output" / "AI_Studio_Media"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ═══════════════════════════════════════════════════════════════════════════
#  QUICK DOWNLOADS PICKER DIALOG
# ═══════════════════════════════════════════════════════════════════════════

class DownloadsVideoDialog(QDialog):
    """Hộp thoại hiển thị và chọn nhanh các file Video MP4 vừa tải từ Google Flow."""

    def __init__(self, flow_engine: GoogleFlowEngine, parent=None):
        super().__init__(parent)
        self.flow_engine = flow_engine
        self.selected_file_path = ""
        self.setWindowTitle("📥 Kéo Video từ Downloads (Google Flow)")
        self.resize(650, 380)
        self.setStyleSheet("""
            QDialog { background-color: #0b1320; color: #cbd5e1; }
            QTableWidget { background-color: #111927; border: 1px solid #203354; border-radius: 8px; color: #ffffff; gridline-color: #1e293b; }
            QHeaderView::section { background-color: #162744; color: #38bdf8; font-weight: bold; border: none; padding: 6px; }
            QPushButton { background-color: #1e293b; color: #ffffff; border: 1px solid #334155; border-radius: 6px; padding: 8px 16px; font-weight: 600; }
            QPushButton:hover { background-color: #0284c7; border-color: #38bdf8; }
            QPushButton#primary { background-color: #0284c7; border: none; }
            QPushButton#primary:hover { background-color: #0369a1; }
        """)
        self._init_ui()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        info_lbl = QLabel("Danh sách các file Video MP4 tải về gần đây trong thư mục Downloads của bạn:")
        info_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        lay.addWidget(info_lbl)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Tên Video", "Dung lượng", "Thời gian tải"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.doubleClicked.connect(self._on_select)
        lay.addWidget(self.table)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("🔄 Quét lại Downloads")
        refresh_btn.clicked.connect(self._load_files)
        btn_row.addWidget(refresh_btn)

        btn_row.addStretch()

        choose_btn = QPushButton("✓ Sử dụng Video này")
        choose_btn.setObjectName("primary")
        choose_btn.clicked.connect(self._on_select)
        btn_row.addWidget(choose_btn)

        cancel_btn = QPushButton("Hủy")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        lay.addLayout(btn_row)

        self._load_files()

    def _load_files(self):
        self.files = self.flow_engine.pull_recent_downloads(15)
        self.table.setRowCount(len(self.files))
        for row, f in enumerate(self.files):
            self.table.setItem(row, 0, QTableWidgetItem(f["name"]))
            self.table.setItem(row, 1, QTableWidgetItem(f"{f['size_mb']} MB"))
            self.table.setItem(row, 2, QTableWidgetItem(f["time_str"]))
        if self.files:
            self.table.selectRow(0)

    def _on_select(self):
        cur_row = self.table.currentRow()
        if 0 <= cur_row < len(self.files):
            self.selected_file_path = self.files[cur_row]["path"]
            self.accept()


# ═══════════════════════════════════════════════════════════════════════════
#  WORKER THREADS
# ═══════════════════════════════════════════════════════════════════════════

class AnalyzeDocThread(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, dict, str)

    def __init__(self, ai_engine: GeminiAIEngine, text: str, model_name: str):
        super().__init__()
        self.ai_engine = ai_engine
        self.text = text
        self.model_name = model_name

    def run(self):
        try:
            storyboard = self.ai_engine.analyze_document_to_storyboard(
                document_text=self.text,
                model_name=self.model_name,
                progress_callback=self.progress.emit,
            )
            self.finished.emit(True, storyboard, "")
        except Exception as exc:
            self.finished.emit(False, {}, str(exc))


class SingleGenThread(QThread):
    finished = pyqtSignal(bool, str, str)

    def __init__(self, task_type: str, fn, *args):
        super().__init__()
        self.task_type = task_type
        self.fn = fn
        self.args = args

    def run(self):
        if sys.platform == "win32":
            import asyncio
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed() or not isinstance(loop, asyncio.ProactorEventLoop):
                    loop = asyncio.ProactorEventLoop()
                    asyncio.set_event_loop(loop)
            except Exception:
                loop = asyncio.ProactorEventLoop()
                asyncio.set_event_loop(loop)
        try:
            res = self.fn(*self.args)
            if isinstance(res, tuple):
                success, path_or_err = res
                self.finished.emit(success, path_or_err if success else "", "" if success else str(path_or_err))
            else:
                self.finished.emit(True, str(res), "")
        except Exception as exc:
            self.finished.emit(False, "", str(exc))


class AutoTTSWorker(QThread):
    """Tiến trình tự động tạo file âm thanh MP3 hoàn chỉnh và timestamps Whisper."""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str, str)

    def __init__(self, full_script: str, tts_engine: TTSEngine):
        super().__init__()
        self.full_script = full_script
        self.tts_engine = tts_engine

    def run(self):
        try:
            settings = QSettings("KathTTS", "KathSlideToVideoMaker")
            model_name = settings.value("last_selected_model", "Edge-TTS vi-VN-NamMinhNeural (Giọng Nam TikTok - Trầm ấm Review)")
            try:
                self.tts_engine.load_model(model_name)
            except Exception:
                pass

            # Đọc các thiết lập ngắt nghỉ, tốc độ, giọng đọc trực tiếp từ cấu hình Bước 2
            period_pause_ms = settings.value("last_period_pause_val", None)
            if period_pause_ms is None:
                last_p_text = settings.value("last_period_pause", "Trung bình (0.5s) [Mặc định]")
                map_p = {
                    "Cực ngắn (0.1s)": 100, "Ngắn (0.2s)": 200, "Vừa đủ (0.3s)": 300,
                    "Trung bình (0.5s) [Mặc định]": 500, "Dài (0.8s)": 800, "Rất dài (1.2s)": 1200, "Cực dài (2.0s)": 2000
                }
                period_pause_ms = map_p.get(last_p_text, 500)
            else:
                try: period_pause_ms = int(period_pause_ms)
                except Exception: period_pause_ms = 500

            comma_pause_val = settings.value("last_comma_pause_val", None)
            if comma_pause_val is None:
                last_c_text = settings.value("last_comma_pause", "Ngắn (0.2s) [Mặc định]")
                map_c = {
                    "Đọc bình thường": "normal", "Không dừng (0s)": "none", "Cực ngắn (0.1s)": 100,
                    "Ngắn (0.2s) [Mặc định]": 200, "Trung bình (0.3s)": 300, "Dài (0.5s)": 500
                }
                comma_pause_val = map_c.get(last_c_text, 200)
            else:
                try: comma_pause_val = int(comma_pause_val) if str(comma_pause_val).isdigit() else str(comma_pause_val)
                except Exception: comma_pause_val = 200

            speed_val = settings.value("last_speed_val", None)
            if speed_val is None:
                last_s_text = settings.value("last_selected_speed", "1.15x")
                try: speed_val = float(last_s_text.replace("x", "").split()[0])
                except Exception: speed_val = 1.15
            else:
                try: speed_val = float(speed_val)
                except Exception: speed_val = 1.15

            speaker_id = int(settings.value("last_speaker_id", 0))
            use_whisper = settings.value("last_whisper", "true").lower() == "true" if isinstance(settings.value("last_whisper"), str) else bool(settings.value("last_whisper", True))

            from datetime import datetime
            date_str = datetime.now().strftime("%Y_%m_%d_%H%M%S")
            mp3_filename = f"Audio_{date_str}.mp3"
            json_filename = f"Audio_{date_str}.json"

            # 1. Thư mục output chính của dự án (giống hệt quy trình thủ công)
            project_out = Path(os.getcwd()) / "output"
            project_out.mkdir(parents=True, exist_ok=True)
            main_mp3 = str(project_out / mp3_filename)

            # 2. Thư mục AI_Studio_Media & temp
            ai_dir = get_ai_media_output_dir()
            ai_mp3 = str(ai_dir / mp3_filename)
            temp_dir = Path(tempfile.gettempdir()) / "KathFlow_Export"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_mp3 = str(temp_dir / mp3_filename)

            pipeline = ExportPipeline()
            pipeline.export_audio(
                text=self.full_script,
                engine=self.tts_engine,
                speaker_id=speaker_id,
                output_path=main_mp3,
                use_whisper=use_whisper,
                speed=speed_val,
                period_pause_ms=period_pause_ms,
                comma_pause_val=comma_pause_val,
                progress_callback=lambda p, m: self.progress.emit(p, m),
            )

            main_json = str(Path(main_mp3).with_suffix(".json"))
            if os.path.exists(main_mp3):
                try:
                    shutil.copy2(main_mp3, ai_mp3)
                    shutil.copy2(main_mp3, temp_mp3)
                    # Giữ bản sao tương thích cho legacy references
                    shutil.copy2(main_mp3, str(ai_dir / "voiceover.mp3"))
                    shutil.copy2(main_mp3, str(temp_dir / "voiceover.mp3"))
                    if os.path.exists(main_json):
                        shutil.copy2(main_json, str(ai_dir / json_filename))
                        shutil.copy2(main_json, str(temp_dir / json_filename))
                        shutil.copy2(main_json, str(ai_dir / "voiceover.json"))
                        shutil.copy2(main_json, str(temp_dir / "voiceover.json"))
                except Exception:
                    pass

            self.finished.emit(True, main_mp3, "")
        except Exception as exc:
            self.finished.emit(False, "", str(exc))


class BatchVisualWorker(QThread):
    """Tiến trình sinh Video AI 10s (Google Flow / Veo) và Slide Bento đa phong cách tuần tự."""
    progress = pyqtSignal(int, str)
    scene_finished = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, scenes: List[Dict[str, Any]], ai_engine: GeminiAIEngine, pptx_builder: PPTXBuilder):
        super().__init__()
        self.scenes = scenes
        self.ai_engine = ai_engine
        self.pptx_builder = pptx_builder
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if sys.platform == "win32":
            import asyncio
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed() or not isinstance(loop, asyncio.ProactorEventLoop):
                    loop = asyncio.ProactorEventLoop()
                    asyncio.set_event_loop(loop)
            except Exception:
                loop = asyncio.ProactorEventLoop()
                asyncio.set_event_loop(loop)
        try:
            out_dir = get_ai_media_output_dir()
            total = len(self.scenes)

            for idx, scene in enumerate(self.scenes, 1):
                if self._is_cancelled:
                    break

                scene_id = scene.get("scene_id", idx)
                v_type = scene.get("visual_type", "pptx")
                
                type_label = "Video 10s AI" if v_type == "video" else ("Ảnh AI 4K" if v_type == "image" else "Slide Bento 1080p")
                self.progress.emit(
                    int((idx - 1) / total * 100),
                    f"Đang render {type_label} (Cảnh {scene_id}/{total})..."
                )

                if v_type == "video":
                    vid_path = str(out_dir / f"Scene_{scene_id:02d}_Video_10s.mp4")
                    prompt = scene.get("video_prompt") or scene.get("image_prompt") or scene.get("slide_title", "")
                    
                    success, res_path = self.ai_engine.generate_ai_video_10s(
                        prompt=prompt,
                        output_path=vid_path,
                        progress_callback=lambda p, m: self.progress.emit(int((idx - 1 + p / 100) / total * 100), f"Cảnh {scene_id}: {m}")
                    )
                    
                    if success and os.path.exists(res_path):
                        final_path = res_path
                    else:
                        final_path = str(out_dir / f"Scene_{scene_id:02d}_Slide.png")
                        render_slide_to_image("", scene_id - 1, final_path, scene_data=scene, total_slides=total)
                elif v_type == "image":
                    img_path = str(out_dir / f"Scene_{scene_id:02d}_Art_4K.jpg")
                    prompt = scene.get("image_prompt") or scene.get("video_prompt") or scene.get("slide_title", "")
                    
                    success, res_path = self.ai_engine.generate_image_imagen(
                        prompt=prompt,
                        output_path=img_path,
                        progress_callback=lambda p, m: self.progress.emit(int((idx - 1 + p / 100) / total * 100), f"Cảnh {scene_id}: {m}")
                    )
                    if success and os.path.exists(res_path):
                        final_path = res_path
                        scene["image_path"] = final_path
                    else:
                        final_path = str(out_dir / f"Scene_{scene_id:02d}_Slide.png")
                        render_slide_to_image("", scene_id - 1, final_path, scene_data=scene, total_slides=total)
                else:
                    final_path = str(out_dir / f"Scene_{scene_id:02d}_Slide.png")
                    render_slide_to_image("", scene_id - 1, final_path, scene_data=scene, total_slides=total)

                scene["media_path"] = final_path
                self.scene_finished.emit(scene_id, final_path)

            self.progress.emit(100, f"Đã hoàn tất tạo toàn bộ {total} Slide Bento vào thư mục dự án!")
            self.finished.emit(True, "")
        except Exception as exc:
            self.finished.emit(False, str(exc))


# ═══════════════════════════════════════════════════════════════════════════
#  SCENE CARD WIDGET
# ═══════════════════════════════════════════════════════════════════════════

class SceneCardWidget(QFrame):
    delete_requested = pyqtSignal(int)
    move_up_requested = pyqtSignal(int)
    move_down_requested = pyqtSignal(int)
    data_changed = pyqtSignal()

    def __init__(self, scene_id: int, scene_data: Dict[str, Any], studio_tab: "AIStudioTab", parent=None):
        super().__init__(parent)
        self.scene_id = scene_id
        self.scene_data = scene_data
        self.studio_tab = studio_tab
        self.setObjectName("scene-card")
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet("""
            QFrame#scene-card {
                background-color: #111927;
                border: 1px solid #1f293d;
                border-radius: 12px;
                padding: 12px;
            }
            QFrame#scene-card:hover {
                border-color: #38bdf8;
            }
        """)
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(12, 12, 12, 12)
        main_lay.setSpacing(10)

        # ── Header row ──
        hdr_row = QHBoxLayout()
        self.badge = QLabel(f"🎬  CẢNH {self.scene_id:02d}")
        self.badge.setStyleSheet("""
            background-color: #0284c7;
            color: #ffffff;
            font-weight: 700;
            font-size: 11px;
            padding: 4px 10px;
            border-radius: 6px;
        """)
        hdr_row.addWidget(self.badge)

        self.dur_lbl = QLabel("~8.5 giây đọc")
        self.dur_lbl.setStyleSheet("color: #8b949e; font-size: 11px;")
        hdr_row.addWidget(self.dur_lbl)

        # Layout Badge
        self.layout_badge = QLabel("📊 Layout")
        self.layout_badge.setStyleSheet("""
            background-color: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
            font-weight: 700;
            font-size: 11px;
            padding: 3px 8px;
            border-radius: 4px;
            border: 1px solid rgba(56, 189, 248, 0.3);
        """)
        hdr_row.addWidget(self.layout_badge)

        self.file_tag_lbl = QLabel("")
        self.file_tag_lbl.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 600;")
        hdr_row.addWidget(self.file_tag_lbl)

        hdr_row.addStretch()

        btn_up = QPushButton("▲")
        btn_up.setFixedSize(28, 28)
        btn_up.setToolTip("Dời cảnh lên trên")
        btn_up.setStyleSheet("QPushButton { min-height: 0px; min-width: 0px; padding: 0px; font-size: 11px; font-weight: bold; background-color: #1e293b; color: #c9d1d9; border: 1px solid #334155; border-radius: 4px; } QPushButton:hover { background-color: #334155; color: #ffffff; }")
        btn_up.clicked.connect(lambda: self.move_up_requested.emit(self.scene_id))

        btn_down = QPushButton("▼")
        btn_down.setFixedSize(28, 28)
        btn_down.setToolTip("Dời cảnh xuống dưới")
        btn_down.setStyleSheet("QPushButton { min-height: 0px; min-width: 0px; padding: 0px; font-size: 11px; font-weight: bold; background-color: #1e293b; color: #c9d1d9; border: 1px solid #334155; border-radius: 4px; } QPushButton:hover { background-color: #334155; color: #ffffff; }")
        btn_down.clicked.connect(lambda: self.move_down_requested.emit(self.scene_id))

        btn_del = QPushButton("✕")
        btn_del.setFixedSize(28, 28)
        btn_del.setToolTip("Xóa cảnh này")
        btn_del.setStyleSheet("QPushButton { min-height: 0px; min-width: 0px; padding: 0px; font-size: 12px; font-weight: bold; background-color: #b91c1c; color: #ffffff; border: none; border-radius: 4px; } QPushButton:hover { background-color: #dc2626; }")
        btn_del.clicked.connect(lambda: self.delete_requested.emit(self.scene_id))

        for b in [btn_up, btn_down, btn_del]:
            hdr_row.addWidget(b)

        main_lay.addLayout(hdr_row)

        # ── Body row (2 Columns) ──
        body_row = QHBoxLayout()
        body_row.setSpacing(14)

        # ── Cột trái: Script & Text ──
        left_col = QVBoxLayout()
        left_col.setSpacing(6)

        left_col.addWidget(self._make_label("📝 Tiêu đề slide (Có tiền tố '|'):"))
        self.title_edit = QLineEdit(self.scene_data.get("slide_title", ""))
        self.title_edit.textChanged.connect(self._on_title_changed)
        left_col.addWidget(self.title_edit)

        left_col.addWidget(self._make_label("✦ Chi tiết Bento / Stat / Lộ trình / Điểm nhấn:"))
        self.bullets_edit = QPlainTextEdit()
        self.bullets_edit.setFixedHeight(75)
        bps = self.scene_data.get("bullet_points", [])
        self.bullets_edit.setPlainText("\n".join(bps))
        self.bullets_edit.textChanged.connect(self._on_bullets_changed)
        left_col.addWidget(self.bullets_edit)

        left_col.addWidget(self._make_label("🎙 Đoạn thuyết minh phân cảnh (Voiceover chi tiết):"))
        self.voice_edit = QPlainTextEdit()
        self.voice_edit.setFixedHeight(85)
        self.voice_edit.setPlainText(self.scene_data.get("voiceover_text", ""))
        self.voice_edit.textChanged.connect(self._on_voice_changed)
        left_col.addWidget(self.voice_edit)

        audio_row = QHBoxLayout()
        self.play_audio_btn = QPushButton("▶  Nghe thử giọng đọc cảnh này")
        self.play_audio_btn.setFixedHeight(28)
        self.play_audio_btn.clicked.connect(self._preview_audio)
        audio_row.addWidget(self.play_audio_btn)
        audio_row.addStretch()
        left_col.addLayout(audio_row)

        body_row.addLayout(left_col, 5)

        # ── Cột phải: Visual / Video AI / Style ──
        right_col = QVBoxLayout()
        right_col.setSpacing(6)

        # Row: Format & Layout Selector
        style_row = QHBoxLayout()
        style_row.setSpacing(8)

        style_row.addWidget(self._make_label("Kiểu:"))
        self.layout_combo = QComboBox()
        self.layout_combo.addItem("🌟 Bìa mở đầu (Hero)", "hero_cover")
        self.layout_combo.addItem("📊 Số liệu lớn (Stat)", "stat_metric")
        self.layout_combo.addItem("🏛️ 3 Cột trụ (3 Pillars)", "three_columns")
        self.layout_combo.addItem("🔲 Ma trận 2x2 (Bento Matrix)", "bento_grid_2x2")
        self.layout_combo.addItem("⚡ So sánh VS (Problem vs Solution)", "comparison_vs")
        self.layout_combo.addItem("⏳ Lộ trình (Timeline Roadmap)", "timeline_process")
        self.layout_combo.addItem("🖼️ Sơ đồ Minh họa (Tech Diagram)", "visual_split")
        self.layout_combo.addItem("🎯 Đúc kết (Takeaway)", "key_takeaway_quote")
        self.layout_combo.addItem("🎬 Bìa kết thúc (Ending Outro)", "ending_outro")
        self.layout_combo.addItem("📋 Bento chuẩn (Standard)", "standard")

        cur_layout = self.scene_data.get("layout_type", "stat_metric")
        idx_lay = self.layout_combo.findData(cur_layout)
        if idx_lay >= 0:
            self.layout_combo.setCurrentIndex(idx_lay)
        self.layout_combo.currentIndexChanged.connect(self._on_layout_changed)
        style_row.addWidget(self.layout_combo, 1)

        style_row.addWidget(self._make_label("Màu:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("💎 Sapphire", "sapphire")
        self.theme_combo.addItem("🌿 Emerald", "emerald")
        self.theme_combo.addItem("🔮 Violet", "violet")
        self.theme_combo.addItem("⚡ Amber", "amber")
        self.theme_combo.addItem("🌹 Ruby", "ruby")
        self.theme_combo.addItem("🌊 Cyber Aqua", "cyan")
        self.theme_combo.addItem("🌅 Neon Sunset", "sunset")

        cur_theme = self.scene_data.get("theme_color", "sapphire")
        idx_thm = self.theme_combo.findData(cur_theme)
        if idx_thm >= 0:
            self.theme_combo.setCurrentIndex(idx_thm)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        style_row.addWidget(self.theme_combo, 1)

        right_col.addLayout(style_row)

        # Format visual
        v_type_row = QHBoxLayout()
        v_type_row.addWidget(self._make_label("Định dạng:"))
        self.type_combo = QComboBox()
        self.type_combo.addItem("📊 Slide Bento 1080p (Gemini)", "pptx")
        self.type_combo.addItem("🎨 Ảnh AI 4K (Imagen 3 / Diffusion)", "image")
        self.type_combo.addItem("🎥 Video 10s AI (Google Flow / Veo)", "video")
        cur_type = self.scene_data.get("visual_type", "pptx")
        idx_type = self.type_combo.findData(cur_type)
        if idx_type >= 0:
            self.type_combo.setCurrentIndex(idx_type)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        v_type_row.addWidget(self.type_combo)
        v_type_row.addStretch()
        right_col.addLayout(v_type_row)

        # Preview Thumbnail Box
        self.thumb_lbl = QLabel()
        self.thumb_lbl.setFixedSize(240, 135)
        self.thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.thumb_lbl.setToolTip("Click để mở xem Video 10s / Slide toàn màn hình")
        self.thumb_lbl.mousePressEvent = lambda ev: self._play_media_preview()
        self.thumb_lbl.setStyleSheet("""
            background-color: #0b1320;
            border: 1px dashed #203354;
            border-radius: 8px;
            color: #8b949e;
            font-size: 11px;
        """)
        self.thumb_lbl.setText("Chưa có Visual\n(Click Gen để tạo)")
        right_col.addWidget(self.thumb_lbl)

        # Action buttons row
        vis_act_row = QHBoxLayout()
        self.gen_visual_btn = QPushButton("🔄 Gen lại")
        self.gen_visual_btn.setFixedHeight(28)
        self.gen_visual_btn.setObjectName("primary")
        self.gen_visual_btn.clicked.connect(self._generate_visual)
        vis_act_row.addWidget(self.gen_visual_btn)

        self.pull_dl_btn = QPushButton("📥 Kéo từ Flow")
        self.pull_dl_btn.setFixedHeight(28)
        self.pull_dl_btn.setToolTip("Chọn video vừa tải từ Google Flow trong thư mục Downloads để gán ngay cho Cảnh này")
        self.pull_dl_btn.clicked.connect(self._pick_from_flow_downloads)
        vis_act_row.addWidget(self.pull_dl_btn)

        self.play_vid_btn = QPushButton("▶ Xem")
        self.play_vid_btn.setFixedHeight(28)
        self.play_vid_btn.clicked.connect(self._play_media_preview)
        vis_act_row.addWidget(self.play_vid_btn)

        self.pick_file_btn = QPushButton("📁 Chọn file")
        self.pick_file_btn.setFixedHeight(28)
        self.pick_file_btn.clicked.connect(self._pick_local_media)
        vis_act_row.addWidget(self.pick_file_btn)
        right_col.addLayout(vis_act_row)

        body_row.addLayout(right_col, 4)
        main_lay.addLayout(body_row)

        self._update_duration_estimate()
        self._update_layout_badge()
        self._refresh_thumbnail()

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #8b949e; font-size: 11px; font-weight: 600;")
        return lbl

    def _on_title_changed(self, text: str):
        self.scene_data["slide_title"] = text
        self.data_changed.emit()

    def _on_bullets_changed(self):
        text = self.bullets_edit.toPlainText()
        self.scene_data["bullet_points"] = [line.strip() for line in text.splitlines() if line.strip()]
        self.data_changed.emit()

    def _on_voice_changed(self):
        text = self.voice_edit.toPlainText()
        self.scene_data["voiceover_text"] = text
        self._update_duration_estimate()
        self.data_changed.emit()

    def _on_layout_changed(self, idx: int):
        l_type = self.layout_combo.currentData()
        self.scene_data["layout_type"] = l_type
        self._update_layout_badge()
        self.data_changed.emit()
        # Tự động render lại ảnh slide nếu là pptx
        if self.scene_data.get("visual_type", "pptx") == "pptx":
            self._generate_visual()

    def _on_theme_changed(self, idx: int):
        t_color = self.theme_combo.currentData()
        self.scene_data["theme_color"] = t_color
        self.data_changed.emit()
        if self.scene_data.get("visual_type", "pptx") == "pptx":
            self._generate_visual()

    def _update_layout_badge(self):
        l_type = self.scene_data.get("layout_type", "stat_metric")
        names = {
            "hero_cover": "🌟 Bìa Mở Đầu",
            "stat_metric": "📊 Số Liệu Lớn",
            "three_columns": "🏛️ 3 Cột Trụ",
            "bento_grid_2x2": "🔲 Bento 2x2",
            "comparison_vs": "⚡ So Sánh VS",
            "timeline_process": "⏳ Lộ Trình",
            "visual_split": "🖼️ Sơ Đồ Minh Họa",
            "key_takeaway_quote": "🎯 Đúc Kết Chiến Lược",
            "ending_outro": "🎬 Bìa Kết Thúc",
            "standard": "📋 Bento Chuẩn",
        }
        self.layout_badge.setText(names.get(l_type, "📊 Slide Bento"))

    def _on_type_changed(self, idx: int):
        v_type = self.type_combo.currentData()
        self.scene_data["visual_type"] = v_type
        self.data_changed.emit()

    def _update_duration_estimate(self):
        text = self.voice_edit.toPlainText().strip()
        words = len(text.split())
        est_sec = max(3.0, round(words / 3.0, 1))
        self.dur_lbl.setText(f"~{words} từ ({est_sec}s đọc)")

    def _preview_audio(self):
        text = self.voice_edit.toPlainText().strip()
        if not text:
            return
        self.play_audio_btn.setText("⏳ Đang đọc...")
        self.play_audio_btn.setEnabled(False)
        self.studio_tab.preview_sentence_audio(text, on_done=lambda: self._on_preview_done())

    def _on_preview_done(self):
        self.play_audio_btn.setText("▶  Nghe thử giọng đọc cảnh này")
        self.play_audio_btn.setEnabled(True)

    def _generate_visual(self):
        self.gen_visual_btn.setText("⏳ Đang tạo...")
        self.gen_visual_btn.setEnabled(False)
        self.studio_tab.generate_single_scene_visual(
            self.scene_id,
            self.scene_data,
            on_done=lambda path: self._on_visual_ready(path)
        )

    def _on_visual_ready(self, path: str):
        self.gen_visual_btn.setText("🔄 Gen lại")
        self.gen_visual_btn.setEnabled(True)
        if path:
            self.scene_data["media_path"] = path
            self._refresh_thumbnail()
            self.data_changed.emit()

    def _pick_from_flow_downloads(self):
        dlg = DownloadsVideoDialog(self.studio_tab.flow_engine, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_file_path:
            out_dir = get_ai_media_output_dir()
            dest_file = out_dir / f"Scene_{self.scene_id:02d}_Video_10s.mp4"
            shutil.copy2(dlg.selected_file_path, str(dest_file))
            self.scene_data["media_path"] = str(dest_file)
            self.scene_data["visual_type"] = "video"
            self.type_combo.setCurrentIndex(1)
            self._refresh_thumbnail()
            self.data_changed.emit()

    def _pick_local_media(self):
        settings = QSettings("KathTTS", "KathSlideToVideoMaker")
        last_dir = settings.value("last_media_dir", "")
        if not last_dir or not Path(last_dir).exists():
            last_dir = str(get_ai_media_output_dir())

        fpath, _ = QFileDialog.getOpenFileName(
            self, "Chọn Video 10s hoặc Slide", last_dir, "Media Files (*.mp4 *.avi *.mov *.mkv *.png *.jpg *.jpeg *.webp);;Tất cả (*.*)"
        )
        if fpath:
            settings.setValue("last_media_dir", str(Path(fpath).parent))
            self.scene_data["media_path"] = fpath
            self._refresh_thumbnail()
            self.data_changed.emit()

    def _play_media_preview(self):
        m_path = self.scene_data.get("media_path", "")
        if m_path and os.path.exists(m_path):
            try:
                if sys.platform == "win32":
                    os.startfile(m_path)
                else:
                    subprocess.Popen(["xdg-open", m_path])
            except Exception as e:
                QMessageBox.warning(self, "Không thể mở file", str(e))
        else:
            QMessageBox.information(self, "Chưa có Visual", "Cảnh này chưa được tạo media. Vui lòng bấm 'Gen lại'.")

    def _refresh_thumbnail(self):
        m_path = self.scene_data.get("media_path", "")
        if m_path and os.path.exists(m_path):
            p = Path(m_path)
            is_vid = m_path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))
            if is_vid:
                self.file_tag_lbl.setText(f"✓ Video 10s ({p.name})")
                self.play_vid_btn.setText("▶ Phát")
            else:
                self.file_tag_lbl.setText(f"✓ Slide Bento ({p.name})")
                self.play_vid_btn.setText("🔍 Xem")

            pix = QPixmap()
            if m_path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                pix.load(m_path)
            elif is_vid:
                thumb_tmp = tempfile.mktemp(suffix=".jpg")
                subprocess_cmd = ["ffmpeg", "-y", "-ss", "0.5", "-i", m_path, "-vframes", "1", thumb_tmp]
                try:
                    subprocess.run(subprocess_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                    if os.path.exists(thumb_tmp):
                        pix.load(thumb_tmp)
                except Exception:
                    pass

            if not pix.isNull():
                scaled = pix.scaled(240, 135, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                self.thumb_lbl.setPixmap(scaled)
                return

        self.file_tag_lbl.setText("")
        self.thumb_lbl.setText("Chưa có Visual\n(Click Gen để tạo)")


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN AI STUDIO TAB
# ═══════════════════════════════════════════════════════════════════════════

class AIStudioTab(QWidget):
    storyboard_ready_to_sync = pyqtSignal(dict, str, list)
    script_generated = pyqtSignal(str)

    def __init__(self, tts_engine: TTSEngine, parent=None):
        super().__init__(parent)
        self.tts_engine = tts_engine
        self.ai_engine = GeminiAIEngine()
        self.pptx_builder = PPTXBuilder()
        self.flow_engine = GoogleFlowEngine()
        self.storyboard_data: Dict[str, Any] = {"scenes": []}
        self.card_widgets: List[SceneCardWidget] = []
        self._active_workers: Dict[str, QThread] = {}
        self._generated_mp3_path: str = ""
        self._last_synced_script: str = ""

        self._init_ui()
        self._load_saved_settings()

    def _get_full_script(self) -> str:
        """Lấy toàn bộ văn bản kịch bản thuyết minh được ghép từ tất cả các phân cảnh."""
        scenes = self.storyboard_data.get("scenes", [])
        voiceover_list = []
        for s in scenes:
            v_text = s.get("voiceover_text", "").strip()
            if v_text:
                if not v_text.endswith((".", "!", "?", "...", ":", ";")):
                    v_text += "."
                voiceover_list.append(v_text)
        return " ".join(voiceover_list)

    def is_busy(self) -> bool:
        """Kiểm tra xem AI Studio có đang bận chạy tiến trình nền nào không (phân tích, render slide, đọc MP3)."""
        for k, w in list(self._active_workers.items()):
            if w is not None and w.isRunning():
                return True
        return False

    def _init_ui(self):
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(16, 16, 16, 16)
        root_lay.setSpacing(12)

        # ── TOP CONFIG CARD ──
        top_card = QFrame()
        top_card.setObjectName("card")
        top_lay = QVBoxLayout(top_card)
        top_lay.setContentsMargins(14, 14, 14, 14)
        top_lay.setSpacing(10)

        # Row 1: Gemini API Key & Google Flow Controls
        auth_row = QHBoxLayout()
        auth_row.setSpacing(10)

        key_lbl = QLabel("🔑 Gemini Key:")
        key_lbl.setStyleSheet("font-weight: 700; color: #38bdf8;")
        auth_row.addWidget(key_lbl)

        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("Dán Gemini API Key vào đây...")
        self.key_input.textChanged.connect(self._on_api_key_changed)
        auth_row.addWidget(self.key_input, 2)

        self.test_key_btn = QPushButton("Kiểm tra Key")
        self.test_key_btn.clicked.connect(self._test_api_key)
        auth_row.addWidget(self.test_key_btn)

        self.key_status_badge = QLabel("Chưa kiểm tra")
        self.key_status_badge.setObjectName("badge")
        auth_row.addWidget(self.key_status_badge)

        # Google Flow Direct Chrome Launcher
        self.open_flow_chrome_btn = QPushButton("🌐  Mở Google Flow (Chrome)")
        self.open_flow_chrome_btn.setToolTip("Mở trình duyệt Google Chrome chính thống tới flow.google (đăng nhập mượt mà không bị Google chặn)")
        self.open_flow_chrome_btn.clicked.connect(self._open_chrome_flow)
        auth_row.addWidget(self.open_flow_chrome_btn)

        # Batch Pull from Downloads Button
        self.pull_recent_btn = QPushButton("📥  Kéo Video từ Downloads")
        self.pull_recent_btn.setToolTip("Tự động quét và chọn video MP4 vừa tải từ Google Flow để gán vào các phân cảnh")
        self.pull_recent_btn.clicked.connect(self._open_downloads_picker)
        auth_row.addWidget(self.pull_recent_btn)

        # Copy Prompts Button
        self.copy_prompts_btn = QPushButton("📋  Copy Prompts")
        self.copy_prompts_btn.setToolTip("Sao chép toàn bộ Prompt tiếng Anh của các cảnh để dán nhanh vào Google Flow")
        self.copy_prompts_btn.clicked.connect(self._copy_all_prompts)
        auth_row.addWidget(self.copy_prompts_btn)

        top_lay.addLayout(auth_row)

        # Row 2: Document Input & Model Selection
        doc_row = QHBoxLayout()
        doc_row.setSpacing(12)
        
        self.file_drop_zone = QFrame()
        self.file_drop_zone.setFixedHeight(85)
        self.file_drop_zone.setAcceptDrops(True)
        self.file_drop_zone.setStyleSheet("""
            QFrame {
                background-color: #0b1320;
                border: 2px dashed #203354;
                border-radius: 8px;
            }
            QFrame:hover {
                border-color: #38bdf8;
            }
        """)
        drop_lay = QHBoxLayout(self.file_drop_zone)
        drop_lay.setContentsMargins(14, 8, 14, 8)

        self.file_info_lbl = QLabel("📄  Kéo & thả file (.pdf, .docx, .txt, .md) hoặc click Chọn file...")
        self.file_info_lbl.setStyleSheet("color: #8b949e; font-size: 13px;")
        drop_lay.addWidget(self.file_info_lbl, 1)

        choose_file_btn = QPushButton("Chọn file...")
        choose_file_btn.clicked.connect(self._choose_document_file)
        drop_lay.addWidget(choose_file_btn)

        doc_row.addWidget(self.file_drop_zone, 3)

        act_col = QVBoxLayout()
        act_col.setSpacing(6)

        m_row = QHBoxLayout()
        m_row.addWidget(QLabel("Model Gemini:"))
        self.model_combo = QComboBox()
        for label, val in AVAILABLE_MODELS:
            self.model_combo.addItem(label, val)
        m_row.addWidget(self.model_combo)
        act_col.addLayout(m_row)

        self.analyze_btn = QPushButton("🚀  Phân tích & Tạo Trọn Gói (Slide + MP3)")
        self.analyze_btn.setObjectName("primary")
        self.analyze_btn.setFixedHeight(38)
        self.analyze_btn.setToolTip("Tự động phân tích kịch bản chi tiết, render toàn bộ Slide đa dạng phong cách và xuất file MP3 thuyết minh.")
        self.analyze_btn.clicked.connect(self._start_document_analysis)
        act_col.addWidget(self.analyze_btn)

        doc_row.addLayout(act_col, 2)
        top_lay.addLayout(doc_row)

        self.top_progress = QProgressBar()
        self.top_progress.setFixedHeight(6)
        self.top_progress.setVisible(False)
        top_lay.addWidget(self.top_progress)

        self.status_lbl = QLabel("Sẵn sàng.")
        self.status_lbl.setStyleSheet("color: #8b949e; font-size: 11px;")
        top_lay.addWidget(self.status_lbl)

        root_lay.addWidget(top_card)

        # ── MIDDLE: SCROLLABLE STORYBOARD CARDS ──
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.cards_container = QWidget()
        self.cards_lay = QVBoxLayout(self.cards_container)
        self.cards_lay.setContentsMargins(0, 0, 8, 0)
        self.cards_lay.setSpacing(12)
        self.cards_lay.addStretch()

        self.scroll_area.setWidget(self.cards_container)
        root_lay.addWidget(self.scroll_area, 1)

        # ── BOTTOM ACTION BAR ──
        btm_card = QFrame()
        btm_card.setObjectName("card")
        btm_lay = QHBoxLayout(btm_card)
        btm_lay.setContentsMargins(14, 10, 14, 10)
        btm_lay.setSpacing(10)

        self.summary_badge = QLabel("0 Phân cảnh • Tổng thời lượng: 0s")
        self.summary_badge.setObjectName("badge")
        btm_lay.addWidget(self.summary_badge)

        btm_lay.addStretch()

        self.add_scene_btn = QPushButton("➕  Thêm cảnh")
        self.add_scene_btn.clicked.connect(self._add_new_scene)
        btm_lay.addWidget(self.add_scene_btn)

        self.rebuild_pptx_btn = QPushButton("🔄  Tạo Presentation Bento PPTX")
        self.rebuild_pptx_btn.clicked.connect(self._rebuild_all_pptx)
        btm_lay.addWidget(self.rebuild_pptx_btn)

        self.open_folder_btn = QPushButton("📂  Mở thư mục Media")
        self.open_folder_btn.clicked.connect(self._open_media_folder)
        btm_lay.addWidget(self.open_folder_btn)

        self.gen_all_visuals_btn = QPushButton("🔄  Gen ALL Slide & Video AI")
        self.gen_all_visuals_btn.clicked.connect(self._generate_all_visuals)
        btm_lay.addWidget(self.gen_all_visuals_btn)

        self.sync_pipeline_btn = QPushButton("🚀  Đồng bộ Timeline & Tiếp tục  ➔")
        self.sync_pipeline_btn.setObjectName("success")
        self.sync_pipeline_btn.clicked.connect(self._start_full_pipeline_sync)
        btm_lay.addWidget(self.sync_pipeline_btn)

        root_lay.addWidget(btm_card)

        self.file_drop_zone.dragEnterEvent = self._on_drag_enter
        self.file_drop_zone.dropEvent = self._on_drop
        self._current_doc_text = ""

    def _open_media_folder(self):
        folder = get_ai_media_output_dir()
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as e:
            QMessageBox.warning(self, "Lỗi mở thư mục", str(e))

    def _open_chrome_flow(self):
        """Mở Google Chrome chính thống tới flow.google."""
        self.status_lbl.setText("Đang mở Google Chrome tới flow.google...")
        self.flow_engine.launch_chrome_flow("https://flow.google")

    def _open_downloads_picker(self):
        """Mở hộp thoại chọn video vừa tải từ Google Flow."""
        dlg = DownloadsVideoDialog(self.flow_engine, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_file_path:
            scenes = self.storyboard_data.get("scenes", [])
            if not scenes:
                QMessageBox.warning(self, "Chưa có phân cảnh", "Vui lòng phân tích tài liệu để tạo phân cảnh trước khi kéo video.")
                return

            out_dir = get_ai_media_output_dir()
            target_scene_id = 1
            for s in scenes:
                if not s.get("media_path") or s.get("media_path", "").endswith(".png"):
                    target_scene_id = s.get("scene_id", 1)
                    break

            dest_file = out_dir / f"Scene_{target_scene_id:02d}_Video_10s.mp4"
            shutil.copy2(dlg.selected_file_path, str(dest_file))
            if 0 < target_scene_id <= len(self.card_widgets):
                card = self.card_widgets[target_scene_id - 1]
                card.scene_data["media_path"] = str(dest_file)
                card.scene_data["visual_type"] = "video"
                card.type_combo.setCurrentIndex(1)
                card._refresh_thumbnail()
                card.data_changed.emit()

            QMessageBox.information(self, "Đã kéo Video thành công", f"Đã gán video '{Path(dlg.selected_file_path).name}' vào Cảnh {target_scene_id:02d}!")

    def _copy_all_prompts(self):
        scenes = self.storyboard_data.get("scenes", [])
        if not scenes:
            QMessageBox.warning(self, "Chưa có kịch bản", "Chưa có phân cảnh nào để sao chép Prompt.")
            return

        lines = []
        for s in scenes:
            sid = s.get("scene_id", 1)
            title = s.get("slide_title", "")
            prompt = s.get("video_prompt") or s.get("image_prompt") or title
            lines.append(f"--- CẢNH {sid:02d}: {title} ---\n{prompt}\n")

        full_txt = "\n".join(lines)
        QApplication.clipboard().setText(full_txt)
        QMessageBox.information(self, "Đã sao chép Prompts", f"Đã sao chép danh sách Prompt tiếng Anh của {len(scenes)} phân cảnh vào Clipboard!\nBạn có thể dán vào Google Flow để sinh video nhanh chóng.")

    def _load_saved_settings(self):
        settings = QSettings("KathTTS", "KathSlideToVideoMaker")
        saved_key = settings.value("gemini_api_key", "")
        if saved_key:
            self.key_input.setText(saved_key)
            self.ai_engine.set_api_key(saved_key)

    def _on_api_key_changed(self, text: str):
        self.ai_engine.set_api_key(text)
        settings = QSettings("KathTTS", "KathSlideToVideoMaker")
        settings.setValue("gemini_api_key", text)

    def _test_api_key(self):
        key = self.key_input.text().strip()
        if not key:
            QMessageBox.warning(self, "Chưa nhập Key", "Vui lòng dán Gemini API Key.")
            return
        self.ai_engine.set_api_key(key)
        self.key_status_badge.setText("Đang kiểm tra...")
        valid, msg = self.ai_engine.validate_api_key()
        if valid:
            self.key_status_badge.setText("✓ Đã kết nối")
            self.key_status_badge.setObjectName("badge-green")
            self.key_status_badge.style().unpolish(self.key_status_badge)
            self.key_status_badge.style().polish(self.key_status_badge)

            models = self.ai_engine.list_available_models()
            if models:
                self.model_combo.clear()
                for label, val in models:
                    self.model_combo.addItem(label, val)

            QMessageBox.information(self, "Thành công", msg)
        else:
            self.key_status_badge.setText("✗ Lỗi Key")
            self.key_status_badge.setObjectName("badge-orange")
            self.key_status_badge.style().unpolish(self.key_status_badge)
            self.key_status_badge.style().polish(self.key_status_badge)
            QMessageBox.critical(self, "Lỗi kết nối Gemini", msg)

    def _on_drag_enter(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def _on_drop(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                settings = QSettings("KathTTS", "KathSlideToVideoMaker")
                settings.setValue("last_doc_dir", str(Path(path).parent))
                self._load_document_file(path)

    def _choose_document_file(self):
        settings = QSettings("KathTTS", "KathSlideToVideoMaker")
        last_dir = settings.value("last_doc_dir", "")
        if not last_dir or not Path(last_dir).exists():
            last_dir = settings.value("last_export_dir", "")
            if not last_dir or not Path(last_dir).exists():
                last_dir = str(Path.home() / "Downloads")
                if not Path(last_dir).exists():
                    last_dir = str(Path.home())

        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn tài liệu đầu vào", last_dir, "Tài liệu (*.pdf *.docx *.txt *.md);;Tất cả (*.*)"
        )
        if path:
            settings.setValue("last_doc_dir", str(Path(path).parent))
            settings.setValue("last_export_dir", str(Path(path).parent))
            self._load_document_file(path)

    def _load_document_file(self, file_path: str):
        try:
            text = read_file(file_path)
            if not text.strip():
                QMessageBox.warning(self, "File rỗng", "Tài liệu không có nội dung văn bản.")
                return
            self._current_doc_text = text
            p = Path(file_path)
            self.file_info_lbl.setText(f"📄  {p.name} ({len(text)} ký tự)")
            self.file_info_lbl.setStyleSheet("color: #38bdf8; font-weight: 600;")
            self.status_lbl.setText(f"Đã nạp file: {p.name}")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi đọc file", str(e))

    # ═══════════════════════════════════════════════════════════════════════
    #  3-IN-1 AUTOMATED PIPELINE: Phân tích -> Render Slides -> Tạo MP3
    # ═══════════════════════════════════════════════════════════════════════

    def _start_document_analysis(self):
        if not self._current_doc_text.strip():
            QMessageBox.warning(self, "Chưa có tài liệu", "Vui lòng chọn hoặc kéo thả file tài liệu trước khi phân tích.")
            return

        key = self.key_input.text().strip()
        if not key:
            QMessageBox.warning(self, "Thiếu API Key", "Vui lòng nhập Gemini API Key.")
            return

        self.ai_engine.set_api_key(key)
        model_name = self.model_combo.currentData()

        self.top_progress.setVisible(True)
        self.top_progress.setValue(5)
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.setText("⏳ Đang xử lý trọn gói...")
        self.status_lbl.setText("[1/3] Đang phân tích tài liệu và cấu trúc Slide Bento qua Gemini AI...")

        worker = AnalyzeDocThread(self.ai_engine, self._current_doc_text, model_name)
        self._active_workers["analyze"] = worker
        worker.progress.connect(self._on_analysis_progress)
        worker.finished.connect(self._on_analysis_finished)
        worker.start()

    def _on_analysis_progress(self, val: int, msg: str):
        mapped_val = int(val * 0.3)
        self.top_progress.setValue(mapped_val)
        self.status_lbl.setText(f"[1/3] {msg}")

    def _on_analysis_finished(self, success: bool, data: dict, err: str):
        self._active_workers.pop("analyze", None)

        if not success:
            self.top_progress.setVisible(False)
            self.analyze_btn.setEnabled(True)
            self.analyze_btn.setText("🚀  Phân tích & Tạo Trọn Gói (Slide + MP3)")
            QMessageBox.critical(self, "Lỗi phân tích Gemini", f"Không thể phân tích tài liệu:\n{err}")
            self.status_lbl.setText("Lỗi phân tích.")
            return

        self.storyboard_data = data
        scenes = data.get("scenes", [])
        self.status_lbl.setText(f"✓ Đã tạo {len(scenes)} phân cảnh! [2/3] Bắt đầu tự động render Slide Bento 1080p...")
        self._render_storyboard_cards()

        # Đồng bộ kịch bản ngay sang tab Bước 2 (Tạo MP3)
        full_script = self._get_full_script()
        if full_script:
            self.script_generated.emit(full_script)

        # TỰ ĐỘNG CHẠY TIẾP GIAI ĐOẠN 2: Render toàn bộ Slide Bento 1080p
        self.top_progress.setValue(30)
        worker = BatchVisualWorker(scenes, self.ai_engine, self.pptx_builder)
        self._active_workers["batch_vis"] = worker
        worker.progress.connect(self._on_batch_progress_chained)
        worker.scene_finished.connect(self._on_batch_scene_done)
        worker.finished.connect(self._on_batch_finished_chained)
        worker.start()

    def _on_batch_progress_chained(self, pct: int, msg: str):
        mapped = 30 + int(pct * 0.4) # 30% -> 70%
        self.top_progress.setValue(mapped)
        self.status_lbl.setText(f"[2/3] {msg}")

    def _on_batch_finished_chained(self, success: bool, err: str):
        self._active_workers.pop("batch_vis", None)
        scenes = self.storyboard_data.get("scenes", [])

        # TỰ ĐỘNG CHẠY TIẾP GIAI ĐOẠN 3: Tạo âm thanh MP3 & Timestamps Whisper
        self.top_progress.setValue(70)
        self.status_lbl.setText(f"[3/3] Đang tự động tạo file thuyết minh MP3 (Edge-TTS Nam Minh 1.15x) & Timestamps...")

        full_script = self._get_full_script()

        tts_worker = AutoTTSWorker(full_script, self.tts_engine)
        self._active_workers["auto_tts"] = tts_worker
        tts_worker.progress.connect(self._on_auto_tts_progress)
        tts_worker.finished.connect(self._on_auto_tts_finished)
        tts_worker.start()

    def _on_auto_tts_progress(self, pct: int, msg: str):
        mapped = 70 + int(pct * 0.3) # 70% -> 100%
        self.top_progress.setValue(mapped)
        self.status_lbl.setText(f"[3/3] {msg}")

    def _on_auto_tts_finished(self, success: bool, mp3_path: str, err: str):
        self.top_progress.setVisible(False)
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("🚀  Phân tích & Tạo Trọn Gói (Slide + MP3)")
        self._active_workers.pop("auto_tts", None)

        scenes = self.storyboard_data.get("scenes", [])
        out_dir = get_ai_media_output_dir()

        if success and mp3_path:
            self._generated_mp3_path = mp3_path
            self._last_synced_script = self._get_full_script()
            self.status_lbl.setText(f"✓ Hoàn tất 100%! Đã tạo {len(scenes)} Slide Bento đa phong cách & file MP3 thuyết minh. Đang chuyển sang Bước 3: Đồng bộ Slide...")
            # TỰ ĐỘNG CHUYỂN TIẾP SANG BƯỚC 3 (ĐỒNG BỘ SLIDE & XEM TRƯỚC)
            self._start_full_pipeline_sync()
        else:
            self.status_lbl.setText("Hoàn tất Slide, có cảnh báo về MP3.")
            QMessageBox.warning(self, "Hoàn tất một phần", f"Đã render xong bộ Slide, nhưng quá trình tạo MP3 gặp lỗi:\n{err}")

    def _render_storyboard_cards(self):
        for card in self.card_widgets:
            self.cards_lay.removeWidget(card)
            card.deleteLater()
        self.card_widgets.clear()

        scenes = self.storyboard_data.get("scenes", [])
        for idx, scene in enumerate(scenes, 1):
            scene["scene_id"] = idx
            card = SceneCardWidget(idx, scene, studio_tab=self)
            card.delete_requested.connect(self._delete_scene)
            card.move_up_requested.connect(self._move_scene_up)
            card.move_down_requested.connect(self._move_scene_down)
            card.data_changed.connect(self._update_summary_stats)
            self.cards_lay.insertWidget(self.cards_lay.count() - 1, card)
            self.card_widgets.append(card)

        self._update_summary_stats()

    def _update_summary_stats(self):
        scenes = self.storyboard_data.get("scenes", [])
        total_words = sum(len(s.get("voiceover_text", "").split()) for s in scenes)
        est_sec = max(0, round(total_words / 3.0))
        m = est_sec // 60
        s = est_sec % 60
        self.summary_badge.setText(f"{len(scenes)} Phân cảnh • Thời lượng ước tính: {m:02d}:{s:02d}")

    def _add_new_scene(self):
        scenes = self.storyboard_data.setdefault("scenes", [])
        new_id = len(scenes) + 1
        new_scene = {
            "scene_id": new_id,
            "slide_title": f"| Phân Cảnh Mới {new_id}",
            "layout_type": "three_columns",
            "theme_color": THEME_ORDER[(new_id - 1) % len(THEME_ORDER)],
            "bullet_points": ["Trọng tâm 1: Đổi mới sáng tạo", "Trọng tâm 2: Nâng cao hiệu suất", "Trọng tâm 3: Đảm bảo an toàn"],
            "voiceover_text": "Phân cảnh này tập trung trình bày các mục tiêu chiến lược và giải pháp đổi mới công nghệ, nhằm bảo đảm hiệu quả triển khai tối ưu và an toàn tuyệt đối.",
            "visual_type": "pptx",
            "image_prompt": "Cinematic photography, modern tech landscape",
            "video_prompt": "Smooth forward camera motion 10s",
        }
        scenes.append(new_scene)
        self._render_storyboard_cards()

    def _delete_scene(self, scene_id: int):
        scenes = self.storyboard_data.get("scenes", [])
        if 0 < scene_id <= len(scenes):
            scenes.pop(scene_id - 1)
            self._render_storyboard_cards()

    def _move_scene_up(self, scene_id: int):
        scenes = self.storyboard_data.get("scenes", [])
        idx = scene_id - 1
        if idx > 0:
            scenes[idx], scenes[idx - 1] = scenes[idx - 1], scenes[idx]
            self._render_storyboard_cards()

    def _move_scene_down(self, scene_id: int):
        scenes = self.storyboard_data.get("scenes", [])
        idx = scene_id - 1
        if idx < len(scenes) - 1:
            scenes[idx], scenes[idx + 1] = scenes[idx + 1], scenes[idx]
            self._render_storyboard_cards()

    def preview_sentence_audio(self, text: str, on_done: callable):
        tmp_mp3 = tempfile.mktemp(suffix=".mp3")
        settings = QSettings("KathTTS", "KathSlideToVideoMaker")
        model_name = settings.value("last_selected_model", "Edge-TTS vi-VN-NamMinhNeural (Giọng Nam TikTok - Trầm ấm Review)")
        try:
            self.tts_engine.load_model(model_name)
        except Exception:
            pass

        def run_tts():
            try:
                pipeline = ExportPipeline()
                pipeline.export_audio(
                    text=text,
                    engine=self.tts_engine,
                    speaker_id=0,
                    output_path=tmp_mp3,
                    use_whisper=False,
                    speed=1.15,
                    period_pause_ms=2000,
                    comma_pause_val="normal",
                )
                if sys.platform == "win32" and os.path.exists(tmp_mp3):
                    subprocess.Popen(["powershell", "-c", f'(New-Object Media.SoundPlayer "{tmp_mp3}").PlaySync();'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True, tmp_mp3
            except Exception as e:
                return False, str(e)

        worker = SingleGenThread("tts_preview", run_tts)
        self._active_workers[f"tts_{id(worker)}"] = worker
        def finished_cb(s, p, e):
            self._active_workers.pop(f"tts_{id(worker)}", None)
            on_done()
        worker.finished.connect(finished_cb)
        worker.start()

    def generate_single_scene_visual(self, scene_id: int, scene_data: Dict[str, Any], on_done: callable):
        """Tạo lại media visual (Video hoặc Slide Bento) cho 1 phân cảnh đơn lẻ."""
        self._generate_scene_visual(scene_id, scene_data, on_done)

    def _generate_scene_visual(self, scene_id: int, scene_data: Dict[str, Any], on_done: callable):
        out_dir = get_ai_media_output_dir()
        v_type = scene_data.get("visual_type", "pptx")
        total_sc = len(self.storyboard_data.get("scenes", []))

        def run_gen():
            if v_type == "video":
                vid_path = str(out_dir / f"Scene_{scene_id:02d}_Video_10s.mp4")
                prompt = scene_data.get("video_prompt") or scene_data.get("image_prompt") or scene_data.get("slide_title", "")
                success, path = self.ai_engine.generate_ai_video_10s(prompt, vid_path)
                return (True, path) if success else (False, path)
            elif v_type == "image":
                img_path = str(out_dir / f"Scene_{scene_id:02d}_Art_4K.jpg")
                prompt = scene_data.get("image_prompt") or scene_data.get("video_prompt") or scene_data.get("slide_title", "")
                success, path = self.ai_engine.generate_image_imagen(prompt, img_path)
                if success:
                    scene_data["image_path"] = path
                return (True, path) if success else (False, path)
            else:
                img_path = str(out_dir / f"Scene_{scene_id:02d}_Slide.png")
                render_slide_to_image("", scene_id - 1, img_path, scene_data=scene_data, total_slides=total_sc)
                return True, img_path

        worker = SingleGenThread(f"vis_{scene_id}", run_gen)
        worker_key = f"vis_{scene_id}"
        self._active_workers[worker_key] = worker
        def finished_cb(s, p, e):
            self._active_workers.pop(worker_key, None)
            on_done(p if s else "")
        worker.finished.connect(finished_cb)
        worker.start()

    def _rebuild_all_pptx(self):
        scenes = self.storyboard_data.get("scenes", [])
        if not scenes:
            QMessageBox.warning(self, "Chưa có kịch bản", "Chưa có phân cảnh nào để tạo Presentation.")
            return
        out_dir = get_ai_media_output_dir()
        out_pptx = out_dir / "Presentation_Gemini_Bento.pptx"
        self.pptx_builder.create_presentation(self.storyboard_data, str(out_pptx))
        QMessageBox.information(self, "Thành công", f"Đã xuất bản Presentation chuẩn phong cách Gemini Bento tại:\n{out_pptx}")

    def _generate_all_visuals(self):
        scenes = self.storyboard_data.get("scenes", [])
        if not scenes:
            QMessageBox.warning(self, "Chưa có phân cảnh", "Vui lòng phân tích tài liệu để tạo phân cảnh trước khi sinh Visual.")
            return

        if "batch_vis" in self._active_workers and self._active_workers["batch_vis"].isRunning():
            QMessageBox.information(self, "Đang xử lý", "Hệ thống đang trong quá trình tạo Video & Slide hàng loạt...")
            return

        self.gen_all_visuals_btn.setEnabled(False)
        self.gen_all_visuals_btn.setText("⏳ Đang tạo Video & Slide...")
        self.top_progress.setVisible(True)
        self.top_progress.setValue(0)
        self.status_lbl.setText(f"Đang bắt đầu tạo Video AI 10s & Slide Bento cho {len(scenes)} phân cảnh...")

        worker = BatchVisualWorker(scenes, self.ai_engine, self.pptx_builder)
        self._active_workers["batch_vis"] = worker
        worker.progress.connect(self._on_batch_progress)
        worker.scene_finished.connect(self._on_batch_scene_done)
        worker.finished.connect(self._on_batch_finished)
        worker.start()

    def _on_batch_progress(self, pct: int, msg: str):
        self.top_progress.setValue(pct)
        self.status_lbl.setText(msg)

    def _on_batch_scene_done(self, scene_id: int, path: str):
        if 0 < scene_id <= len(self.card_widgets):
            card = self.card_widgets[scene_id - 1]
            card.scene_data["media_path"] = path
            card._refresh_thumbnail()

    def _on_batch_finished(self, success: bool, err: str):
        self.top_progress.setVisible(False)
        self.gen_all_visuals_btn.setEnabled(True)
        self.gen_all_visuals_btn.setText("🔄  Gen ALL Slide & Video AI")
        self._active_workers.pop("batch_vis", None)

        out_dir = get_ai_media_output_dir()
        if success:
            self.status_lbl.setText("✓ Đã hoàn tất tạo Video 10s AI & Slide Bento cho tất cả các cảnh!")
            reply = QMessageBox.information(
                self, "Hoàn tất Media",
                f"Toàn bộ Video 10s AI và Slide Bento đã được tạo thành công tại:\n{out_dir}\n\nBạn có muốn mở thư mục xem ngay không?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._open_media_folder()
        else:
            self.status_lbl.setText("Lỗi tạo Media.")
            QMessageBox.critical(self, "Lỗi tạo Media", f"Quá trình tạo Media gặp lỗi:\n{err}")

    def _start_full_pipeline_sync(self):
        if self.is_busy():
            self.status_lbl.setText("⏳ Đang tạo âm thanh MP3 & phân tích. Hệ thống sẽ tự động chuyển sang Bước 3 khi hoàn tất...")
            return

        scenes = self.storyboard_data.get("scenes", [])
        if not scenes:
            QMessageBox.warning(self, "Chưa có phân cảnh", "Vui lòng phân tích tài liệu để tạo phân cảnh trước khi đồng bộ.")
            return

        full_script = self._get_full_script()
        out_dir = get_ai_media_output_dir()

        self.status_lbl.setText("Đang chuẩn bị danh sách Media và chuyển sang Timeline...")

        total_sc = len(scenes)
        media_list = []
        for idx, s in enumerate(scenes, 1):
            m_path = s.get("media_path", "")
            candidate = str(out_dir / f"Scene_{idx:02d}_Slide.png")
            if not m_path or not os.path.exists(m_path):
                if os.path.exists(candidate):
                    m_path = candidate
                    s["media_path"] = candidate
                else:
                    m_path = candidate
                    render_slide_to_image("", idx - 1, m_path, scene_data=s, total_slides=total_sc)
                    s["media_path"] = m_path

            is_vid = m_path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))
            media_list.append({
                "type": "video" if is_vid else "slide",
                "path": m_path,
                "title": s.get("slide_title", f"Cảnh {idx}"),
                "voiceover": s.get("voiceover_text", ""),
                "scene_id": idx
            })

        self.status_lbl.setText("✓ Đã chuẩn bị xong media, đang chuyển sang Bước 3: Đồng bộ Slide...")
        self.storyboard_ready_to_sync.emit(self.storyboard_data, full_script, media_list)
