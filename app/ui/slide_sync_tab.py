"""
slide_sync_tab.py — Tab "Đồng bộ Media / Timeline"
Cho phép import PPTX/PDF/Video/Ảnh, xây dựng timeline ngang kiểu Clipchamp,
thêm transition giữa các clip, và gán slide vào vị trí văn bản TTS.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import (
    Qt, QThread, QSize, pyqtSignal, QPropertyAnimation, QEasingCurve, QRect, QTimer,
)
from PyQt6.QtGui import (
    QColor, QFont, QPixmap, QTextCharFormat, QTextCursor, QPainter,
    QTextDocument,
)
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSizePolicy, QSplitter, QVBoxLayout, QWidget, QProgressBar,
    QToolButton, QGridLayout, QTextEdit, QCheckBox, QComboBox,
    QSlider, QSpinBox, QDoubleSpinBox, QDialog,
)

from app.core.slide_processor import (
    SlideInfo, load_pptx, load_pdf, mapping_to_dict, apply_mapping_from_dict,
    SlideProcessorError,
)
from app.models.media_item import MediaItem, TRANSITION_TYPES
from app.ui.timeline_widget import TimelineWidget


# ═══════════════════════════════════════════════════════════════════════════
#  SLIDE SCRIPT EDITOR (custom painter for pill badges — KHÔNG THAY ĐỔI)
# ═══════════════════════════════════════════════════════════════════════════

class SlideScriptEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._tag_ranges = []  # list of (start, end, is_selected, slide_num)

    def set_tag_ranges(self, ranges):
        self._tag_ranges = ranges
        self.viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for start, end, is_selected, slide_num in self._tag_ranges:
            c_start = QTextCursor(self.document())
            c_start.setPosition(start)
            c_end = QTextCursor(self.document())
            c_end.setPosition(end)

            rect_start = self.cursorRect(c_start)
            rect_end   = self.cursorRect(c_end)

            if rect_start.top() == rect_end.top():
                tag_width  = rect_end.left() - rect_start.left()
                tag_height = rect_start.height()
                if tag_width > 0:
                    rect = QRect(
                        rect_start.left() - 4,
                        rect_start.top()  + 1,
                        tag_width + 8,
                        tag_height - 2,
                    )
                    bg_color = QColor("#db2777") if is_selected else QColor("#7c3aed")
                    painter.setBrush(bg_color)
                    painter.setPen(Qt.PenStyle.NoPen)
                    radius = rect.height() / 2.0
                    painter.drawRoundedRect(rect, radius, radius)

                    painter.setPen(QColor("#ffffff"))
                    font = self.font()
                    font.setBold(True)
                    if font.pointSize() > 0:
                        font.setPointSize(font.pointSize() - 1)
                    elif font.pixelSize() > 0:
                        font.setPixelSize(font.pixelSize() - 1)
                    painter.setFont(font)
                    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                                     f"[Slide {slide_num}]")


# ═══════════════════════════════════════════════════════════════════════════
#  WORKER THREADS
# ═══════════════════════════════════════════════════════════════════════════

class SlideLoadThread(QThread):
    progress  = pyqtSignal(int, str)
    finished  = pyqtSignal(bool, list, str)   # success, slides, error

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            ext = Path(self.path).suffix.lower()
            if ext == ".pdf":
                slides = load_pdf(self.path, self.progress.emit)
            else:
                slides = load_pptx(self.path, self.progress.emit)
            self.finished.emit(True, slides, "")
        except Exception as exc:
            self.finished.emit(False, [], str(exc))


class MediaImportThread(QThread):
    """Thread nhập video/ảnh: tạo thumbnail và lấy duration."""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, object, str)  # success, MediaItem, error

    def __init__(self, path: str, media_type: str, parent=None):
        super().__init__(parent)
        self.path       = path
        self.media_type = media_type   # "video" | "image"

    def run(self):
        try:
            import shutil
            item = MediaItem(media_type=self.media_type, path=self.path)

            if self.media_type == "video":
                self.progress.emit(20, f"Đang phân tích video: {Path(self.path).name}…")

                # Lấy duration qua ffprobe
                if shutil.which("ffprobe"):
                    r = subprocess.run(
                        ["ffprobe", "-v", "error",
                         "-show_entries", "format=duration",
                         "-of", "default=noprint_wrappers=1:nokey=1",
                         self.path],
                        capture_output=True, text=True,
                    )
                    try:
                        item.duration_sec = max(0.5, float(r.stdout.strip()))
                    except ValueError:
                        item.duration_sec = 5.0

                # Tạo thumbnail
                self.progress.emit(50, "Đang tạo thumbnail…")
                tmp_thumb = tempfile.NamedTemporaryFile(
                    suffix=".png", delete=False,
                    prefix="kath_thumb_"
                )
                tmp_thumb.close()
                if shutil.which("ffmpeg"):
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", self.path,
                         "-ss", "00:00:01", "-vframes", "1",
                         "-vf", "scale=320:-1",
                         tmp_thumb.name],
                        capture_output=True,
                    )
                    if os.path.exists(tmp_thumb.name) and os.path.getsize(tmp_thumb.name) > 0:
                        item.thumbnail_path = tmp_thumb.name

            else:  # image
                item.duration_sec  = 5.0
                item.thumbnail_path = self.path  # dùng trực tiếp

            self.progress.emit(100, "Xong!")
            self.finished.emit(True, item, "")

        except Exception as exc:
            self.finished.emit(False, None, str(exc))


# ═══════════════════════════════════════════════════════════════════════════
#  DROP ZONE (mở rộng hỗ trợ PPTX/PDF/Video/Ảnh)
# ═══════════════════════════════════════════════════════════════════════════

_SLIDE_EXTS  = (".pptx", ".pdf")
_VIDEO_EXTS  = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv")
_IMAGE_EXTS  = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")
_ALL_EXTS    = _SLIDE_EXTS + _VIDEO_EXTS + _IMAGE_EXTS


class MediaDropZone(QFrame):
    """Drop zone nhận PPTX/PDF/Video/Ảnh — phát tín hiệu (path, media_type)."""
    file_dropped = pyqtSignal(str, str)  # path, media_type

    _IDLE = """QFrame#mediaDropZone {
        background-color: #161b22; border: 2px dashed #30363d; border-radius: 10px;
    }"""
    _HOVER = """QFrame#mediaDropZone {
        background-color: #1a0e36; border: 2px dashed #7c3aed; border-radius: 10px;
    }"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("mediaDropZone")
        self.setAcceptDrops(True)
        self.setFixedHeight(38)
        self.setStyleSheet(self._IDLE)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 2, 12, 2)
        lay.setSpacing(10)

        self._lbl = QLabel("Kéo & thả media vào đây hoặc:")
        self._lbl.setStyleSheet("color:#7d8590; font-size:11px; background:transparent;")
        lay.addWidget(self._lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        buttons = [
            ("Import PPTX",  "*.pptx",                "slide"),
            ("Import PDF",   "*.pdf",                  "slide"),
            ("Import Video", " ".join(f"*{e}" for e in _VIDEO_EXTS), "video"),
            ("Import Ảnh",   " ".join(f"*{e}" for e in _IMAGE_EXTS), "image"),
        ]
        for label, filt, mtype in buttons:
            btn = QPushButton(label)
            btn.setFixedHeight(22)
            btn.setStyleSheet(
                "QPushButton{font-size:10px;padding:1px 6px;}"
            )
            btn.clicked.connect(
                lambda _, f=filt, m=mtype: self._open_dialog(f, m)
            )
            btn_row.addWidget(btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

    def _open_dialog(self, filt: str, media_type: str):
        from PyQt6.QtCore import QSettings
        settings = QSettings("KathTTS", "KathSlideToVideoMaker")
        last_dir = settings.value("last_export_dir", None)
        if not last_dir:
            last_dir = str(Path.home() / "Downloads")
            if not Path(last_dir).exists():
                last_dir = str(Path.home())

        label_map = {
            "slide": "Slide (PPTX / PDF)",
            "video": "Video",
            "image": "Ảnh",
        }
        ext_label = label_map.get(media_type, media_type)
        # Cho phép chọn NHIỀU file cùng lúc
        paths, _ = QFileDialog.getOpenFileNames(
            self, f"Mở {ext_label}", last_dir,
            f"{ext_label} ({filt});;Tất cả (*.*)"
        )
        for path in paths:
            self.file_dropped.emit(path, media_type)
        if paths:
            settings.setValue("last_export_dir", str(Path(paths[0]).parent))

    def _classify(self, path: str) -> Optional[str]:
        ext = Path(path).suffix.lower()
        if ext in _SLIDE_EXTS:  return "slide"
        if ext in _VIDEO_EXTS:  return "video"
        if ext in _IMAGE_EXTS:  return "image"
        return None

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            # Chấp nhận nếu ÍT NHẤT 1 file hợp lệ
            for url in event.mimeData().urls():
                if self._classify(url.toLocalFile()):
                    event.acceptProposedAction()
                    self.setStyleSheet(self._HOVER)
                    n = len(event.mimeData().urls())
                    self._lbl.setText(
                        f"Thả {n} file vào đây ✓" if n > 1 else "Thả file vào đây ✓"
                    )
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self._IDLE)
        self._lbl.setText("Kéo & thả  PPTX · PDF · Video · Ảnh  vào đây")

    def dropEvent(self, event):
        self.setStyleSheet(self._IDLE)
        self._lbl.setText("Kéo & thả  PPTX · PDF · Video · Ảnh  vào đây")
        # Xử lý TẤT CẢ files được thả vào
        for url in event.mimeData().urls():
            path  = url.toLocalFile()
            mtype = self._classify(path)
            if mtype:
                self.file_dropped.emit(path, mtype)


# ═══════════════════════════════════════════════════════════════════════════
#  AUDIO MIX PANEL (hiện khi chọn video clip)
# ═══════════════════════════════════════════════════════════════════════════

class AudioMixPanel(QFrame):
    """Panel nhỏ điều chỉnh âm lượng của clip video đang chọn."""
    changed = pyqtSignal()
    apply_video_vol_all = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._item: Optional[MediaItem] = None
        self._last_tts_vol = 100
        self._last_vid_vol = 30
        
        self.setStyleSheet("""
            QFrame { background:#12161c; border:1px solid #21262d; border-radius:6px; }
            QLabel { background:transparent; color:#8b949e; font-size:10px; }
            QToolButton {
                background: transparent;
                border: none;
                color: #8b949e;
                font-size: 10px;
                font-weight: bold;
                padding: 2px 6px;
            }
            QToolButton:hover {
                color: #ffffff;
                background: #21262d;
                border-radius: 4px;
            }
        """)
        self.setFixedHeight(56)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(14)

        # TTS volume
        self._tts_mute_btn = QToolButton()
        self._tts_mute_btn.setText("🎙 TTS:")
        self._tts_mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tts_mute_btn.clicked.connect(self._toggle_tts_mute)
        lay.addWidget(self._tts_mute_btn)

        self._tts_slider = QSlider(Qt.Orientation.Horizontal)
        self._tts_slider.setRange(0, 100)
        self._tts_slider.setValue(100)
        self._tts_slider.setFixedWidth(80)
        self._tts_slider.setStyleSheet(
            "QSlider::groove:horizontal{height:3px;background:#30363d;border-radius:2px;}"
            "QSlider::handle:horizontal{width:10px;height:10px;margin:-4px 0;"
            "background:#7c3aed;border-radius:5px;}"
            "QSlider::sub-page:horizontal{background:#6d28d9;border-radius:2px;}"
        )
        self._tts_lbl = QLabel("100%")
        self._tts_lbl.setFixedWidth(34)
        self._tts_slider.valueChanged.connect(self._on_tts_changed)
        lay.addWidget(self._tts_slider)
        lay.addWidget(self._tts_lbl)

        lay.addSpacing(6)

        # Video volume
        self._vid_mute_btn = QToolButton()
        self._vid_mute_btn.setText("🎬 Video:")
        self._vid_mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._vid_mute_btn.clicked.connect(self._toggle_vid_mute)
        lay.addWidget(self._vid_mute_btn)

        self._vid_slider = QSlider(Qt.Orientation.Horizontal)
        self._vid_slider.setRange(0, 100)
        self._vid_slider.setValue(30)
        self._vid_slider.setFixedWidth(80)
        self._vid_slider.setStyleSheet(
            "QSlider::groove:horizontal{height:3px;background:#30363d;border-radius:2px;}"
            "QSlider::handle:horizontal{width:10px;height:10px;margin:-4px 0;"
            "background:#0891b2;border-radius:5px;}"
            "QSlider::sub-page:horizontal{background:#0e7490;border-radius:2px;}"
        )
        self._vid_lbl = QLabel("30%")
        self._vid_lbl.setFixedWidth(34)
        self._vid_slider.valueChanged.connect(self._on_vid_changed)
        lay.addWidget(self._vid_slider)
        lay.addWidget(self._vid_lbl)

        lay.addSpacing(6)

        # Mute all button
        self._mute_all_btn = QToolButton()
        self._mute_all_btn.setText("🔇 Tắt tất cả")
        self._mute_all_btn.setToolTip("Tắt tiếng tất cả các clip video trong timeline")
        self._mute_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mute_all_btn.clicked.connect(lambda: self.apply_video_vol_all.emit(0.0))
        self._mute_all_btn.setStyleSheet(
            "QToolButton{"
            "  color:#f85149; background:transparent; border:none;"
            "  font-size:10px; font-weight:bold; padding:2px 6px;"
            "}"
            "QToolButton:hover{"
            "  color:#ff7b72; background:#2c1515; border-radius:4px;"
            "}"
        )
        lay.addWidget(self._mute_all_btn)

        # Set 30% button
        self._vol30_all_btn = QToolButton()
        self._vol30_all_btn.setText("🔉 Video 30% tất cả")
        self._vol30_all_btn.setToolTip("Đặt âm lượng video là 30% cho tất cả các clip")
        self._vol30_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._vol30_all_btn.clicked.connect(lambda: self.apply_video_vol_all.emit(0.3))
        self._vol30_all_btn.setStyleSheet(
            "QToolButton{"
            "  color:#58a6ff; background:transparent; border:none;"
            "  font-size:10px; font-weight:bold; padding:2px 6px;"
            "}"
            "QToolButton:hover{"
            "  color:#79c0ff; background:#15233c; border-radius:4px;"
            "}"
        )
        lay.addWidget(self._vol30_all_btn)

        lay.addStretch()

    def set_item(self, item: Optional[MediaItem]):
        self._item = item
        if item and item.media_type == "video":
            self._tts_slider.blockSignals(True)
            self._vid_slider.blockSignals(True)
            self._tts_slider.setValue(int(item.tts_volume  * 100))
            self._vid_slider.setValue(int(item.video_volume * 100))
            self._tts_lbl.setText(f"{int(item.tts_volume*100)}%")
            self._vid_lbl.setText(f"{int(item.video_volume*100)}%")
            self._tts_slider.blockSignals(False)
            self._vid_slider.blockSignals(False)
            self._update_mute_states()
            self.setVisible(True)
        else:
            self.setVisible(False)

    def _update_mute_states(self):
        tts_val = self._tts_slider.value()
        vid_val = self._vid_slider.value()
        self._tts_mute_btn.setText("🔇 TTS:" if tts_val == 0 else "🎙 TTS:")
        self._vid_mute_btn.setText("🔇 Video:" if vid_val == 0 else "🎬 Video:")

    def _toggle_tts_mute(self):
        curr = self._tts_slider.value()
        if curr > 0:
            self._last_tts_vol = curr
            self._tts_slider.setValue(0)
        else:
            self._tts_slider.setValue(self._last_tts_vol if getattr(self, "_last_tts_vol", 100) > 0 else 100)

    def _toggle_vid_mute(self):
        curr = self._vid_slider.value()
        if curr > 0:
            self._last_vid_vol = curr
            self._vid_slider.setValue(0)
        else:
            self._vid_slider.setValue(self._last_vid_vol if getattr(self, "_last_vid_vol", 30) > 0 else 30)

    def _on_tts_changed(self, v: int):
        self._tts_lbl.setText(f"{v}%")
        self._update_mute_states()
        if self._item:
            self._item.tts_volume = v / 100.0
        self.changed.emit()

    def _on_vid_changed(self, v: int):
        self._vid_lbl.setText(f"{v}%")
        self._update_mute_states()
        if self._item:
            self._item.video_volume = v / 100.0
        self.changed.emit()


# ═══════════════════════════════════════════════════════════════════════════
#  TRANSITION SELECTION DIALOG
# ═══════════════════════════════════════════════════════════════════════════

class TransitionSelectionDialog(QDialog):
    """Dialog cho phép người dùng chọn loại và thời lượng chuyển cảnh tự động."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chọn Transition")
        self.setMinimumWidth(320)
        self.setStyleSheet("""
            QDialog {
                background: #161b22;
                color: #c9d1d9;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                font-size: 13px;
                color: #8b949e;
                font-weight: 500;
            }
            QComboBox {
                background: #0d1117;
                color: #c9d1d9;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QDoubleSpinBox {
                background: #0d1117;
                color: #c9d1d9;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QPushButton {
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: 13px;
            }
            QPushButton#ok_btn {
                background: #6d28d9;
                color: white;
                border: none;
            }
            QPushButton#ok_btn:hover {
                background: #7c3aed;
            }
            QPushButton#cancel_btn {
                background: #21262d;
                color: #c9d1d9;
                border: 1px solid #30363d;
            }
            QPushButton#cancel_btn:hover {
                background: #30363d;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Loại chuyển cảnh
        layout.addWidget(QLabel("Loại chuyển cảnh:"))
        self.type_combo = QComboBox()
        
        from app.models.media_item import TRANSITION_TYPES
        for display, key in TRANSITION_TYPES:
            display_name = display
            if not display_name.startswith("✦"):
                display_name = f"✦  {display_name}"
            self.type_combo.addItem(display_name, key)
            
        # Chọn fade theo mặc định
        index = self.type_combo.findData("fade")
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
            
        layout.addWidget(self.type_combo)

        # Thời lượng
        layout.addWidget(QLabel("Thời lượng (giây):"))
        self.dur_spin = QDoubleSpinBox()
        self.dur_spin.setRange(0.1, 10.0)
        self.dur_spin.setSingleStep(0.1)
        self.dur_spin.setValue(0.5)
        self.dur_spin.setDecimals(2)
        self.dur_spin.setSuffix(" s")
        layout.addWidget(self.dur_spin)

        layout.addSpacing(10)

        # Buttons (OK bên trái, Cancel bên phải giống mockup)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.ok_btn = QPushButton("OK")
        self.ok_btn.setObjectName("ok_btn")
        self.ok_btn.clicked.connect(self.accept)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancel_btn")
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def get_values(self) -> tuple[str, float]:
        return self.type_combo.currentData(), self.dur_spin.value()


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN SLIDE SYNC TAB
# ═══════════════════════════════════════════════════════════════════════════

class SlideSyncTab(QWidget):
    """
    Tab đồng bộ media: trái = kịch bản văn bản, phải = timeline ngang.
    """
    request_back   = pyqtSignal()
    request_export = pyqtSignal(list)   # pass media_items

    def __init__(self, parent=None):
        super().__init__(parent)

        # ── State ─────────────────────────────────────────────────────────
        self._media_items:   List[MediaItem] = []
        self._selected_id:   Optional[str]   = None
        self._script_text:   str             = ""
        self._mp3_path:      str             = ""
        self._json_path:     str             = ""
        self._load_thread:   Optional[SlideLoadThread]   = None
        self._import_thread: Optional[MediaImportThread] = None
        self._import_queue:  List[tuple[str, str]]        = []  # [(path, media_type)]

        self._sub_settings = {
            "enabled":   True,
            "font_size": 20,
            "color":     "Trắng",
            "style":     "Viền đen",
            "position":  3,
        }

        self._build_ui()

    # ──────────────────────────────────────────────────────────────────────
    #  PUBLIC API
    # ──────────────────────────────────────────────────────────────────────

    def load_context(self, script_text: str, mp3_path: str,
                     has_json: bool = True):
        """Được gọi từ MainWindow khi chuyển sang tab này."""
        self._script_text = script_text
        self._mp3_path    = mp3_path
        self._json_path   = str(Path(mp3_path).with_suffix(".json"))

        self._editor.setPlainText(script_text)

        mp3_name = Path(mp3_path).name
        self._mp3_lbl.setText(f"🎵  {mp3_name}")

        if has_json:
            self._warn_lbl.setText("")
            self._json_ok_lbl.setText("✓ timestamps .json có sẵn")
            self._json_ok_lbl.setVisible(True)
        else:
            self._json_ok_lbl.setVisible(False)
            self._warn_lbl.setText(
                "⚠️ Thiếu .json timestamps — slide timing sẽ không chính xác"
            )

        self._update_stats()

    # ──────────────────────────────────────────────────────────────────────
    #  UI BUILD
    # ──────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_info_bar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([480, 580])
        root.addWidget(splitter, 1)

        root.addWidget(self._build_action_bar())

    # ── Info bar ──────────────────────────────────────────────────────────

    def _build_info_bar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(38)
        bar.setStyleSheet(
            "QFrame{background:#12161c;border-bottom:1px solid #21262d;}"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(20)

        self._mp3_lbl = QLabel("🎵  Chưa có file MP3")
        self._mp3_lbl.setStyleSheet(
            "color:#8b949e; font-size:11px; background:transparent;"
        )

        self._json_ok_lbl = QLabel("✓ timestamps .json có sẵn")
        self._json_ok_lbl.setStyleSheet(
            "color:#3fb950; font-size:11px; background:transparent;"
        )
        self._json_ok_lbl.setVisible(False)

        self._stats_lbl = QLabel("0 item · 0 slide đã gán")
        self._stats_lbl.setStyleSheet(
            "color:#8b949e; font-size:11px; background:transparent;"
        )

        self._warn_lbl = QLabel("")
        self._warn_lbl.setStyleSheet(
            "color:#f0883e; font-size:11px; background:transparent;"
        )

        lay.addWidget(self._mp3_lbl)
        lay.addWidget(self._json_ok_lbl)
        lay.addWidget(self._stats_lbl)
        lay.addStretch()
        lay.addWidget(self._warn_lbl)
        return bar

    # ── Left panel ────────────────────────────────────────────────────────

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#0d1117;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 14, 8, 14)
        lay.setSpacing(8)

        # Header
        hdr = QHBoxLayout()
        lbl = QLabel("📄  KỊCH BẢN")
        lbl.setObjectName("heading")
        self._cursor_lbl = QLabel("Nhấp vào văn bản để đặt vị trí")
        self._cursor_lbl.setStyleSheet(
            "color:#484f58; font-size:11px; background:transparent;"
        )
        hdr.addWidget(lbl)
        hdr.addStretch()
        hdr.addWidget(self._cursor_lbl)
        lay.addLayout(hdr)

        # Script editor
        self._editor = SlideScriptEditor()
        self._editor.setReadOnly(False)
        self._editor.setPlaceholderText(
            "Kịch bản sẽ được tải tự động từ bước tạo MP3.\n\n"
            "Bạn có thể chọn vị trí bất kỳ rồi nhấn 'Gán Slide' ở bên phải."
        )
        self._editor.setStyleSheet(
            "QPlainTextEdit{font-size:13px;line-height:1.7;"
            "selection-background-color:#4c1d95;}"
        )
        self._editor.cursorPositionChanged.connect(self._on_cursor_changed)
        self._editor.textChanged.connect(self._on_text_changed)
        lay.addWidget(self._editor, 1)

        # Assign buttons
        assign_row = QHBoxLayout()
        self._assign_btn = QPushButton("⬅  Gán Slide đang chọn")
        self._assign_btn.setObjectName("primary")
        self._assign_btn.setMinimumHeight(38)
        self._assign_btn.setEnabled(False)
        self._assign_btn.clicked.connect(self._assign_slide)

        self._auto_btn = QPushButton("⚡  Tự động gán tất cả")
        self._auto_btn.setObjectName("success")
        self._auto_btn.setMinimumHeight(38)
        self._auto_btn.setEnabled(False)
        self._auto_btn.clicked.connect(self._auto_assign_slides)

        assign_row.addWidget(self._assign_btn, 1)
        assign_row.addWidget(self._auto_btn, 1)
        lay.addLayout(assign_row)

        self._assign_hint = QLabel("← Chọn 1 slide bên phải trước")
        self._assign_hint.setStyleSheet(
            "color:#484f58; font-size:11px; background:transparent;"
        )
        lay.addWidget(self._assign_hint)

        # ── Subtitle Settings ─────────────────────────────────────────────
        self._sub_frame = QFrame()
        self._sub_frame.setStyleSheet("""
            QFrame{background:#161b22;border:1px solid #30363d;border-radius:8px;}
            QLabel{color:#8b949e;font-size:11px;font-weight:600;border:none;}
            QComboBox,QCheckBox{
                background:#0d1117;border:1px solid #30363d;
                border-radius:4px;padding:3px 6px;color:#e6edf3;font-size:12px;
            }
        """)
        sf_lay = QVBoxLayout(self._sub_frame)
        sf_lay.setContentsMargins(10, 6, 10, 6)
        sf_lay.setSpacing(4)

        # Row 1
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self._sub_enable_cb = QCheckBox("Hiển thị phụ đề")
        self._sub_enable_cb.setChecked(self._sub_settings.get("enabled", True))
        self._sub_enable_cb.stateChanged.connect(self._on_sub_settings_changed)
        row1.addWidget(self._sub_enable_cb)

        row1.addWidget(QLabel("Cỡ:"))
        self._sub_size_combo = QComboBox()
        self._sub_size_combo.addItems(
            ["14","16","18","20","22","24","26","28","32"]
        )
        self._sub_size_combo.setCurrentText(
            str(self._sub_settings.get("font_size", 20))
        )
        self._sub_size_combo.setFixedWidth(52)
        self._sub_size_combo.currentTextChanged.connect(
            self._on_sub_settings_changed
        )
        row1.addWidget(self._sub_size_combo)

        row1.addWidget(QLabel("Màu:"))
        self._sub_color_combo = QComboBox()
        self._sub_color_combo.addItems(["Trắng","Vàng","Xanh lá","Xanh lam"])
        self._sub_color_combo.setCurrentText(
            self._sub_settings.get("color","Trắng")
        )
        self._sub_color_combo.setFixedWidth(72)
        self._sub_color_combo.currentTextChanged.connect(
            self._on_sub_settings_changed
        )
        row1.addWidget(self._sub_color_combo)

        row1.addWidget(QLabel("Kiểu:"))
        self._sub_style_combo = QComboBox()
        self._sub_style_combo.addItems(["Viền đen","Nền đen mờ","Không viền"])
        self._sub_style_combo.setCurrentText(
            self._sub_settings.get("style","Viền đen")
        )
        self._sub_style_combo.setFixedWidth(90)
        self._sub_style_combo.currentTextChanged.connect(
            self._on_sub_settings_changed
        )
        row1.addWidget(self._sub_style_combo)
        row1.addStretch()
        sf_lay.addLayout(row1)

        # Row 2
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        row2.addWidget(QLabel("Vị trí (% đáy):"))
        self._sub_pos_slider = QSlider(Qt.Orientation.Horizontal)
        self._sub_pos_slider.setMinimum(1)
        self._sub_pos_slider.setMaximum(60)
        self._sub_pos_slider.setValue(self._sub_settings.get("position",1))
        self._sub_pos_slider.setStyleSheet(
            "QSlider::groove:horizontal{height:4px;background:#30363d;border-radius:2px;}"
            "QSlider::handle:horizontal{width:12px;height:12px;margin:-4px 0;"
            "background:#7c3aed;border-radius:6px;}"
            "QSlider::sub-page:horizontal{background:#6d28d9;border-radius:2px;}"
        )
        self._sub_pos_spin = QSpinBox()
        self._sub_pos_spin.setMinimum(1)
        self._sub_pos_spin.setMaximum(60)
        self._sub_pos_spin.setValue(self._sub_settings.get("position",1))
        self._sub_pos_spin.setFixedWidth(48)
        self._sub_pos_slider.valueChanged.connect(self._sub_pos_spin.setValue)
        self._sub_pos_spin.valueChanged.connect(self._sub_pos_slider.setValue)
        self._sub_pos_slider.valueChanged.connect(self._on_sub_settings_changed)
        row2.addWidget(self._sub_pos_slider, 1)
        row2.addWidget(self._sub_pos_spin)
        sf_lay.addLayout(row2)

        lay.addWidget(self._sub_frame)
        return w

    # ── Right panel ───────────────────────────────────────────────────────

    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background:#0d1117;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 10, 16, 8)
        lay.setSpacing(6)

        # Header
        hdr = QHBoxLayout()
        lbl = QLabel("🖼  MEDIA")
        lbl.setObjectName("heading")
        self._item_count_lbl = QLabel("0 item")
        self._item_count_lbl.setObjectName("badge")
        hdr.addWidget(lbl)
        hdr.addWidget(self._item_count_lbl)
        hdr.addStretch()

        clear_btn = QPushButton("🗑  Xóa tất cả")
        clear_btn.setObjectName("danger")
        clear_btn.setFixedHeight(22)
        clear_btn.setStyleSheet("QPushButton{font-size:10px; padding:2px 8px; font-weight:bold;}")
        clear_btn.clicked.connect(self._clear_all)

        auto_trans_btn = QPushButton("✦  Tự động chuyển cảnh")
        auto_trans_btn.setFixedHeight(22)
        auto_trans_btn.setStyleSheet("QPushButton{font-size:10px; padding:2px 8px; font-weight:bold; background:#1e0f4a; border:1px solid #7c3aed; color:#c4b5fd;}")
        auto_trans_btn.clicked.connect(self._auto_assign_transitions)

        hdr.addWidget(auto_trans_btn)
        hdr.addWidget(clear_btn)
        lay.addLayout(hdr)

        # Drop zone
        self._drop_zone = MediaDropZone()
        self._drop_zone.file_dropped.connect(self._on_file_dropped)
        lay.addWidget(self._drop_zone)

        # Progress
        self._import_progress = QProgressBar()
        self._import_progress.setFixedHeight(4)
        self._import_progress.setVisible(False)
        self._import_status = QLabel("")
        self._import_status.setStyleSheet(
            "color:#8b949e; font-size:10px; background:transparent;"
        )
        self._import_status.setVisible(False)
        self._import_status.setFixedHeight(14)
        lay.addWidget(self._import_progress)
        lay.addWidget(self._import_status)

        # Large preview — flexible height (co giãn với cửa sổ)
        preview_frame = QFrame()
        preview_frame.setObjectName("card")
        preview_frame.setMinimumHeight(100)
        preview_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        p_lay = QVBoxLayout(preview_frame)
        p_lay.setContentsMargins(6, 4, 6, 4)

        self._preview_lbl = QLabel("Chọn một item để xem trước")
        self._preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_lbl.setStyleSheet(
            "color:#484f58; font-size:12px; background:transparent;"
        )
        self._preview_lbl.setScaledContents(False)
        p_lay.addWidget(self._preview_lbl, 1)

        self._preview_title = QLabel("")
        self._preview_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_title.setStyleSheet(
            "color:#c9d1d9; font-size:10px; font-weight:600; background:transparent;"
        )
        p_lay.addWidget(self._preview_title)
        # Stretch factor = 1 → preview nhận toàn bộ không gian thừa
        lay.addWidget(preview_frame, 1)

        # Audio mix panel (chỉ hiện khi chọn video)
        self._audio_mix = AudioMixPanel()
        self._audio_mix.setVisible(False)
        self._audio_mix.apply_video_vol_all.connect(self._on_apply_video_vol_all)
        lay.addWidget(self._audio_mix)   # stretch=0, fixed 56px khi hiện

        self._timeline = TimelineWidget()
        self._timeline.clip_selected.connect(self._on_clip_selected)
        self._timeline.clip_removed.connect(self._on_clip_removed)
        self._timeline.transition_changed.connect(self._on_transition_changed)
        self._timeline.reordered.connect(self._on_timeline_reordered)
        lay.addWidget(self._timeline)   # stretch=0 → fixed height từ bên trong

        # Slide count info & Clear button in a single row
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        
        self._slide_count_lbl = QLabel("")
        self._slide_count_lbl.setStyleSheet(
            "color:#484f58; font-size:10px; background:transparent;"
        )
        self._slide_count_lbl.setFixedHeight(24)
        bottom_row.addWidget(self._slide_count_lbl)
        bottom_row.addStretch()

        pass
        
        lay.addLayout(bottom_row)

        return w

    # ── Action bar ────────────────────────────────────────────────────────

    def _build_action_bar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(56)
        bar.setStyleSheet(
            "QFrame{background:#161b22;border-top:1px solid #21262d;}"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(10)

        back_btn = QPushButton("← Quay lại tạo MP3")
        back_btn.clicked.connect(self.request_back.emit)

        save_btn = QPushButton("💾  Lưu dự án")
        save_btn.clicked.connect(self._save_project)

        self._action_stats = QLabel("")
        self._action_stats.setStyleSheet(
            "color:#7d8590; font-size:12px; background:transparent;"
        )
        self._action_stats.setAlignment(Qt.AlignmentFlag.AlignCenter)

        preview_btn = QPushButton("▶  Xem trước Video")
        preview_btn.clicked.connect(self._preview_video)

        self._next_btn = QPushButton("Tiếp tục → Xuất Video")
        self._next_btn.setObjectName("success")
        self._next_btn.setMinimumHeight(38)
        self._next_btn.setMinimumWidth(180)
        self._next_btn.clicked.connect(self._go_export)

        lay.addWidget(back_btn)
        lay.addWidget(save_btn)
        lay.addStretch()
        lay.addWidget(self._action_stats)
        lay.addStretch()
        lay.addWidget(preview_btn)
        lay.addWidget(self._next_btn)
        return bar

    # ──────────────────────────────────────────────────────────────────────
    #  FILE DROP / IMPORT
    # ──────────────────────────────────────────────────────────────────────

    def _on_file_dropped(self, path: str, media_type: str):
        self._import_queue.append((path, media_type))
        self._process_import_queue()

    def _process_import_queue(self):
        # Nếu có thread nào đang chạy thì đợi nó xong
        if self._load_thread and self._load_thread.isRunning():
            return
        if self._import_thread and self._import_thread.isRunning():
            return

        if not self._import_queue:
            return

        path, media_type = self._import_queue.pop(0)

        self._import_progress.setVisible(True)
        self._import_progress.setValue(0)
        self._import_status.setVisible(True)

        if media_type == "slide":
            self._import_status.setText(f"Đang tải: {Path(path).name}…")
            self._load_thread = SlideLoadThread(path, parent=self)
            self._load_thread.progress.connect(self._on_import_progress)
            self._load_thread.finished.connect(self._on_slides_loaded)
            self._load_thread.start()
        else:
            self._import_status.setText(f"Đang xử lý: {Path(path).name}…")
            self._import_thread = MediaImportThread(path, media_type, parent=self)
            self._import_thread.progress.connect(self._on_import_progress)
            self._import_thread.finished.connect(self._on_media_loaded)
            self._import_thread.start()

    def _on_import_progress(self, pct: int, msg: str):
        self._import_progress.setValue(pct)
        self._import_status.setText(msg)

    def _on_slides_loaded(self, success: bool, slides: list, error: str):
        self._import_progress.setVisible(False)
        self._import_status.setVisible(False)
        if not success:
            QMessageBox.critical(self, "Lỗi import", error)
            self._process_import_queue()
            return

        # Thêm các slide vào cuối timeline
        existing_nums = {
            item.display_number
            for item in self._media_items
            if item.media_type == "slide"
        }
        for slide in slides:
            p = getattr(slide, "video_path", "") or getattr(slide, "image_path", "") or ""
            item = MediaItem(
                media_type="slide",
                path=p,
                slide_info=slide,
                duration_sec=5.0,
            )
            if getattr(slide, "video_path", ""):
                item.thumbnail_path = slide.image_path
            self._media_items.append(item)

        self._rebuild_timeline()
        self._load_saved_mapping()
        self._refresh_editor_from_slides()
        self._update_stats()
        self._process_import_queue()

    def _on_media_loaded(self, success: bool, item: object, error: str):
        self._import_progress.setVisible(False)
        self._import_status.setVisible(False)
        if not success:
            QMessageBox.critical(self, "Lỗi import", error)
            self._process_import_queue()
            return
        self._media_items.append(item)
        self._rebuild_timeline()
        self._update_stats()
        self._process_import_queue()

    # ──────────────────────────────────────────────────────────────────────
    #  TIMELINE MANAGEMENT
    # ──────────────────────────────────────────────────────────────────────

    def _rebuild_timeline(self):
        # Thiết lập display_number trước để các label hiển thị đúng chỉ số!
        for n, item in enumerate(self._media_items, start=1):
            item._display_number = n

        self._timeline.set_items(self._media_items)
        total = len(self._media_items)
        slides = self._slide_items
        self._item_count_lbl.setText(f"{total} item")
        self._slide_count_lbl.setText(
            f"{len(slides)} slide  ·  "
            f"{sum(1 for s in slides if s.is_assigned)} đã gán"
        )

    def _on_clip_selected(self, item_id: str):
        self._selected_id = item_id
        item = self._find_item(item_id)
        if item is None:
            return

        # Update large preview
        img_path = item.image_path
        if img_path and os.path.exists(img_path):
            pix = QPixmap(img_path)
            self._preview_lbl.setPixmap(
                pix.scaled(
                    self._preview_lbl.width() - 4, 110,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self._preview_lbl.setText("")
        else:
            icons = {"slide": "📊", "video": "🎬", "image": "🖼️"}
            self._preview_lbl.setPixmap(QPixmap())
            self._preview_lbl.setText(
                icons.get(item.media_type, "?") + "  " + item.display_name
            )

        self._preview_title.setText(item.display_name)

        # Audio mix panel
        self._audio_mix.set_item(item)

        # Assign button — có thể gán bất kỳ loại media nào (slide, video, ảnh)
        can_assign = True
        self._assign_btn.setEnabled(can_assign)
        self._assign_hint.setText(
            f"'{item.display_name}' đã chọn  •  "
            "Nhấp vào văn bản bên trái rồi nhấn Gán"
        )

        self._draw_markers()

    def _on_apply_video_vol_all(self, vol: float):
        count = 0
        for item in self._media_items:
            if item.media_type == "video":
                item.video_volume = vol
                count += 1
        if self._selected_id:
            curr_item = self._find_item(self._selected_id)
            if curr_item:
                self._audio_mix.set_item(curr_item)
        QMessageBox.information(
            self, "✓ Hoàn thành",
            f"Đã đặt âm lượng Video thành {int(vol * 100)}% cho tất cả {count} clip video!"
        )

    def _on_clip_removed(self, item_id: str):
        self._media_items = [i for i in self._media_items if i.id != item_id]
        if self._selected_id == item_id:
            self._selected_id = None
            self._preview_lbl.setPixmap(QPixmap())
            self._preview_lbl.setText("Chọn một item để xem trước")
            self._preview_title.setText("")
            self._audio_mix.setVisible(False)
            self._assign_btn.setEnabled(False)
        self._rebuild_timeline()
        self._refresh_editor_from_slides()
        self._update_stats()

    def _on_transition_changed(self, index: int, trans_type: str,
                               trans_dur: float):
        # Đã được cập nhật trực tiếp vào MediaItem trong TimelineWidget
        pass
 
    def _on_timeline_reordered(self):
        # Cập nhật số thứ tự hiển thị
        for n, item in enumerate(self._media_items, start=1):
            item._display_number = n
        # Đồng bộ nhãn kịch bản theo thứ tự mới
        self._refresh_editor_from_slides()
        self._update_stats()

    def _auto_assign_transitions(self):
        if len(self._media_items) < 2:
            QMessageBox.information(self, "Thông báo", "Cần ít nhất 2 clip để gán chuyển cảnh.")
            return

        dlg = TransitionSelectionDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            trans_type, trans_dur = dlg.get_values()

            for item in self._media_items[1:]:
                item.transition_in = trans_type
                item.transition_dur = trans_dur

            self._rebuild_timeline()
            
            from app.models.media_item import TRANSITION_TYPES
            display_name = trans_type
            for display, key in TRANSITION_TYPES:
                if key == trans_type:
                    display_name = display
                    break

            QMessageBox.information(
                self, "✓ Hoàn thành",
                f"Đã tự động gán chuyển cảnh '{display_name}' ({trans_dur:.2f}s) cho tất cả phân đoạn!"
            )

    def _clear_all(self):
        if not self._media_items:
            return
        if QMessageBox.question(
            self, "Xác nhận", "Xóa toàn bộ media đã import?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self._media_items.clear()
            self._selected_id = None
            self._rebuild_timeline()
            self._editor.blockSignals(True)
            self._editor.setPlainText(self._script_text)
            self._editor.blockSignals(False)
            self._on_text_changed()
            self._update_stats()

    # ──────────────────────────────────────────────────────────────────────
    #  SLIDE ASSIGNMENT (KHÔNG THAY ĐỔI LOGIC CỐT LÕI)
    # ──────────────────────────────────────────────────────────────────────

    def _on_cursor_changed(self):
        cursor = self._editor.textCursor()
        pos    = cursor.position()
        block  = cursor.blockNumber() + 1
        col    = cursor.columnNumber() + 1
        self._cursor_lbl.setText(f"Dòng {block}, Cột {col}  (vị trí {pos})")

    def parse_editor_text(
        self, editor_text: str
    ) -> tuple[str, dict[int, tuple[int, str]]]:
        pattern = re.compile(r"\[Slide (\d+)\]")
        matches = list(pattern.finditer(editor_text))

        clean_parts    = []
        last_idx       = 0
        total_tag_len  = 0
        assignments    = {}

        for match in matches:
            clean_parts.append(editor_text[last_idx:match.start()])
            clean_pos  = match.start() - total_tag_len
            slide_num  = int(match.group(1))
            slide_idx  = slide_num - 1
            assignments[slide_idx] = clean_pos
            last_idx       = match.end()
            total_tag_len += match.end() - match.start()

        clean_parts.append(editor_text[last_idx:])
        clean_text = "".join(clean_parts)

        final = {}
        for idx, clean_pos in assignments.items():
            snip_end = min(len(clean_text), clean_pos + 45)
            snippet  = clean_text[max(0, clean_pos):snip_end].replace("\n"," ").strip()
            final[idx] = (clean_pos, snippet)

        return clean_text, final

    def _on_text_changed(self):
        raw_text = self._editor.toPlainText()
        clean_text, assignments = self.parse_editor_text(raw_text)
        self._script_text = clean_text

        slide_items = self._slide_items
        for item in slide_items:
            item.assigned_pos  = -1
            item.assigned_text = ""

        for slide_idx, (pos, snippet) in assignments.items():
            if 0 <= slide_idx < len(slide_items):
                slide_items[slide_idx].assigned_pos  = pos
                slide_items[slide_idx].assigned_text = snippet

        self._draw_markers()
        self._update_stats()

    def _refresh_editor_from_slides(self):
        slide_items = [i for i in self._slide_items if i.is_assigned]
        slide_items.sort(key=lambda s: (s.assigned_pos, s.display_number),
                         reverse=True)

        chars = list(self._script_text)
        for item in slide_items:
            pos = min(len(chars), max(0, item.assigned_pos))
            tag = f"[Slide {item.display_number}]"
            chars.insert(pos, tag)

        new_text = "".join(chars)
        self._editor.blockSignals(True)
        self._editor.setPlainText(new_text)
        self._editor.blockSignals(False)
        self._on_text_changed()

    def _draw_markers(self):
        extra_selections = []
        text    = self._editor.toPlainText()
        pattern = re.compile(r"\[Slide (\d+)\]")
        ranges  = []

        slide_items = self._slide_items

        for match in pattern.finditer(text):
            slide_num = int(match.group(1))
            slide_idx = slide_num - 1

            # Tìm selected slide
            sel_item = self._find_item(self._selected_id)
            is_sel = (
                sel_item is not None
                and sel_item.media_type == "slide"
                and sel_item.display_number == slide_num
            )
            ranges.append((match.start(), match.end(), is_sel, slide_num))

            fmt = QTextCharFormat()
            fmt.setForeground(QColor("#0d1117"))
            fmt.setBackground(QColor("#0d1117"))
            fmt.setToolTip(f"Slide #{slide_num}")

            sel = QTextEdit.ExtraSelection()
            sel.format = fmt
            cursor = self._editor.textCursor()
            cursor.setPosition(match.start())
            cursor.setPosition(match.end(), QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = cursor
            extra_selections.append(sel)

        self._editor.set_tag_ranges(ranges)
        self._editor.setExtraSelections(extra_selections)

    def _assign_slide(self):
        item = self._find_item(self._selected_id)
        if item is None:
            return

        tag_str = f"[Slide {item.display_number}]"
        self._editor.blockSignals(True)
        cursor = self._editor.textCursor()
        doc = self._editor.document()
        find_cursor = doc.find(tag_str)
        if not find_cursor.isNull():
            find_cursor.removeSelectedText()
        cursor = self._editor.textCursor()
        cursor.insertText(tag_str)
        self._editor.blockSignals(False)

        self._on_text_changed()

        orig = self._assign_btn.text()
        self._assign_btn.setText("✓  Đã gán!")
        self._assign_btn.setEnabled(False)
        QTimer.singleShot(800, lambda: (
            self._assign_btn.setText(orig),
            self._assign_btn.setEnabled(True),
        ))

    def _auto_assign_slides(self):
        slide_items = self._slide_items
        if not slide_items:
            return

        reply = QMessageBox.question(
            self, "⚡ Tự động gán Slide",
            "Hệ thống sẽ tự động phân bổ tất cả slide vào kịch bản.\n"
            "Các gán cũ sẽ bị ghi đè.\n\nTiếp tục?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        text     = self._script_text
        n        = len(slide_items)
        text_len = len(text)

        if n == 1:
            slide_items[0].assigned_pos = 0
            self._refresh_editor_from_slides()
            return

        last_dot = text.rfind(".")
        if last_dot == -1:
            last_dot = text_len

        from app.core.mp3_exporter import split_into_sentences
        sentences = split_into_sentences(text)

        sentence_starts = []
        char_cursor = 0
        for sent in sentences:
            char_start = text.find(sent, char_cursor)
            if char_start == -1:
                char_start = char_cursor
            sentence_starts.append(char_start)
            char_cursor = char_start + len(sent)

        valid_starts = [p for p in sentence_starts if p < last_dot]

        for item in slide_items:
            item.assigned_pos  = -1
            item.assigned_text = ""

        slide_items[0].assigned_pos = 0
        for i in range(1, n - 1):
            if len(valid_starts) >= n - 1:
                sent_idx = int(i * len(valid_starts) / (n - 1))
                pos = valid_starts[sent_idx]
            else:
                pos = int(i * last_dot / (n - 1))
                while pos > 0 and not text[pos - 1].isspace():
                    pos -= 1
                pos = min(pos, last_dot)
            slide_items[i].assigned_pos = pos

        slide_items[-1].assigned_pos = last_dot
        self._refresh_editor_from_slides()

    # ──────────────────────────────────────────────────────────────────────
    #  HELPERS
    # ──────────────────────────────────────────────────────────────────────

    @property
    def _slide_items(self) -> List[MediaItem]:
        """Trả về tất cả MediaItem trong timeline để gán vào kịch bản."""
        # Đánh lại display_number theo thứ tự xuất hiện
        for n, item in enumerate(self._media_items, start=1):
            item._display_number = n
        return self._media_items

    def _find_item(self, item_id: Optional[str]) -> Optional[MediaItem]:
        if not item_id:
            return None
        for item in self._media_items:
            if item.id == item_id:
                return item
        return None

    def _load_saved_mapping(self):
        """Tải mapping đã lưu từ .slides.json nếu có."""
        if not self._mp3_path:
            return
        slides_json = Path(self._mp3_path).with_suffix(".slides.json")
        if slides_json.exists():
            try:
                with open(slides_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                slide_infos = [i.slide_info for i in self._media_items
                               if i.slide_info]
                apply_mapping_from_dict(slide_infos, data)
                # Đồng bộ lại assigned_pos vào MediaItem
                for item in self._media_items:
                    if item.slide_info:
                        item.assigned_pos  = getattr(
                            item.slide_info, "assigned_pos", -1)
                        item.assigned_text = getattr(
                            item.slide_info, "assigned_text", "")
            except Exception:
                pass

    # ──────────────────────────────────────────────────────────────────────
    #  STATS
    # ──────────────────────────────────────────────────────────────────────

    def _update_stats(self):
        total     = len(self._media_items)
        slides    = self._slide_items
        assigned  = sum(1 for s in slides if s.is_assigned)
        unassigned= len(slides) - assigned

        self._stats_lbl.setText(
            f"{total} item · {assigned}/{len(slides)} slide đã gán"
        )
        self._item_count_lbl.setText(f"{total} item")
        self._slide_count_lbl.setText(
            f"{len(slides)} slide  ·  {assigned} đã gán"
        )

        if unassigned > 0:
            self._action_stats.setText(
                f"✅ {assigned} đã gán  •  ⚠️ {unassigned} slide chưa gán"
            )
        else:
            self._action_stats.setText(
                f"✅ Tất cả {len(slides)} slide đã gán" if slides
                else f"🎬 {total} media trong timeline"
            )

        self._auto_btn.setEnabled(
            bool(slides) and bool(self._editor.toPlainText().strip())
        )

        if unassigned > 0:
            self._warn_lbl.setText(f"⚠  Còn {unassigned} slide chưa gán vị trí")
        else:
            self._warn_lbl.setText("")

    # ──────────────────────────────────────────────────────────────────────
    #  SUBTITLE SETTINGS
    # ──────────────────────────────────────────────────────────────────────

    def _on_sub_settings_changed(self):
        self._sub_settings["enabled"]   = self._sub_enable_cb.isChecked()
        self._sub_settings["font_size"] = int(self._sub_size_combo.currentText())
        self._sub_settings["color"]     = self._sub_color_combo.currentText()
        self._sub_settings["style"]     = self._sub_style_combo.currentText()
        self._sub_settings["position"]  = self._sub_pos_slider.value()

    def _sync_sub_controls(self):
        for w in [self._sub_enable_cb, self._sub_size_combo,
                  self._sub_color_combo, self._sub_style_combo,
                  self._sub_pos_slider, self._sub_pos_spin]:
            w.blockSignals(True)

        self._sub_enable_cb.setChecked(
            self._sub_settings.get("enabled", True))
        self._sub_size_combo.setCurrentText(
            str(self._sub_settings.get("font_size", 20)))
        self._sub_color_combo.setCurrentText(
            self._sub_settings.get("color", "Trắng"))
        self._sub_style_combo.setCurrentText(
            self._sub_settings.get("style", "Viền đen"))
        self._sub_pos_slider.setValue(
            self._sub_settings.get("position", 5))
        self._sub_pos_spin.setValue(
            self._sub_settings.get("position", 5))

        for w in [self._sub_enable_cb, self._sub_size_combo,
                  self._sub_color_combo, self._sub_style_combo,
                  self._sub_pos_slider, self._sub_pos_spin]:
            w.blockSignals(False)

    # ──────────────────────────────────────────────────────────────────────
    #  SAVE / PREVIEW / EXPORT
    # ──────────────────────────────────────────────────────────────────────

    def _save_project(self):
        if not self._mp3_path:
            QMessageBox.warning(self, "Chưa có MP3",
                                "Cần xuất MP3 trước khi lưu dự án.")
            return

        slide_infos = [i.slide_info for i in self._media_items
                       if i.slide_info]
        data = mapping_to_dict(slide_infos)
        data["script_text"] = self._script_text
        data["mp3_path"]    = self._mp3_path

        default_path = str(Path(self._mp3_path).with_suffix(".slides.json"))
        path, _ = QFileDialog.getSaveFileName(
            self, "Lưu dự án", default_path,
            "JSON Project (*.slides.json *.json)"
        )
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        QMessageBox.information(self, "✓ Đã lưu", f"Dự án lưu tại:\n{path}")

    def _preview_video(self):
        if not self._media_items:
            QMessageBox.warning(self, "Chưa có media",
                                "Vui lòng import media trước.")
            return
        if not self._mp3_path:
            QMessageBox.warning(self, "Chưa có MP3", "Chưa có file audio.")
            return

        # Lấy slides (backward compat với dialog cũ)
        slides = [i.slide_info for i in self._media_items if i.slide_info]

        from app.ui.video_export_dialog import PreviewVideoDialog
        dlg = PreviewVideoDialog(
            slides=slides,
            script_text=self._script_text,
            mp3_path=self._mp3_path,
            json_path=self._json_path,
            sub_settings=self._sub_settings,
            media_items=self._media_items,
            parent=self,
        )
        dlg.exec()
        self._sync_sub_controls()

    def _go_export(self):
        if not self._media_items:
            QMessageBox.warning(self, "Chưa có media",
                                "Vui lòng import media trước.")
            return
        if not self._mp3_path:
            QMessageBox.warning(self, "Chưa có MP3", "Chưa có file audio.")
            return

        slide_items = self._slide_items
        unassigned  = [s for s in slide_items if not s.is_assigned]
        if unassigned:
            reply = QMessageBox.question(
                self, "Còn slide chưa gán",
                f"Có {len(unassigned)} slide chưa gán vị trí.\n"
                "Những slide này sẽ được bỏ qua khi xuất video.\n\nTiếp tục?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                return

        from app.ui.video_export_dialog import ExportVideoDialog
        # Lấy slides để truyền cho dialog (backward compat)
        slides = [i.slide_info for i in self._media_items if i.slide_info]

        dlg = ExportVideoDialog(
            slides=slides,
            script_text=self._script_text,
            mp3_path=self._mp3_path,
            json_path=self._json_path,
            sub_settings=self._sub_settings,
            media_items=self._media_items,    # NEW: truyền cả media_items
            parent=self,
        )
        dlg.exec()
