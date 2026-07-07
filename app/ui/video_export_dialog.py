"""
video_export_dialog.py — Dialog xuất video MP4 và xem trước slide timeline.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal, QUrl
from PyQt6.QtGui import QPixmap, QColor, QPainter, QFont, QFontMetrics, QTextLayout
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
    QComboBox, QCheckBox, QSlider, QSpinBox, QGridLayout,
)

from app.core.slide_processor import SlideInfo


# ═══════════════════════════════════════════════════════════════════════════
#  EXPORT WORKER THREAD
# ═══════════════════════════════════════════════════════════════════════════

class OutlinedLabel(QLabel):
    """Label vẽ chữ có viền mờ (outline) hoặc nền đen mờ sát chữ."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.outline_enabled = True
        self.outline_color = QColor("#000000")
        self.text_color = QColor("#ffffff")
        # True = chỉ wrap background sát chữ (không outline)
        self.tight_bg = False
        self.tight_bg_color = QColor(0, 0, 0, 165)  # semi-transparent black

    def paintEvent(self, event):
        text = self.text()
        if not text:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = self.font()
        painter.setFont(font)
        rect = self.contentsRect()
        
        # Căn lề sát đáy và căn giữa ngang để dán sát viền dưới
        flags = Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap

        if self.tight_bg:
            # Vẽ nền đen mờ bao sát chữ
            metrics = QFontMetrics(font)
            br = metrics.boundingRect(rect, flags, text)
            
            # Để tránh clipping phần đệm (padding) ở đáy khi nhãn neo sát đáy,
            # dịch chuyển vùng vẽ chữ lên trên một khoảng pad_y
            pad_x, pad_y = 10, 5
            br.translate(0, -pad_y)
            bg_rect = br.adjusted(-pad_x, -pad_y, pad_x, pad_y)
            
            painter.setBrush(self.tight_bg_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(bg_rect, 4, 4)
            painter.setPen(self.text_color)
            painter.drawText(rect.translated(0, -pad_y), flags, text)
            return

        if not self.outline_enabled:
            painter.setPen(self.text_color)
            # Dịch nhẹ lên 2px để tránh dính sát sạt viền quá nếu không có nền
            painter.drawText(rect.translated(0, -2), flags, text)
            return

        # 8 directions outline (viền đen)
        painter.setPen(self.outline_color)
        offsets = [(-1, -1), (1, -1), (-1, 1), (1, 1),
                   (-1, 0), (1, 0), (0, -1), (0, 1)]
        for dx, dy in offsets:
            painter.drawText(rect.translated(dx, dy - 2), flags, text)

        painter.setPen(self.text_color)
        painter.drawText(rect.translated(0, -2), flags, text)


class ExportVideoThread(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)   # success, error/path

    def __init__(self, slides, script_text, mp3_path, json_path,
                 output_path, resolution, sub_settings=None,
                 media_items=None, parent=None):
        super().__init__(parent)
        self.slides       = slides
        self.script_text  = script_text
        self.mp3_path     = mp3_path
        self.json_path    = json_path
        self.output_path  = output_path
        self.resolution   = resolution
        self.sub_settings = sub_settings
        self.media_items  = media_items  # None → dùng export_video cũ

    def run(self):
        try:
            if self.media_items:
                from app.core.video_exporter import export_video_with_media
                out = export_video_with_media(
                    self.media_items,
                    self.script_text,
                    self.mp3_path,
                    self.json_path,
                    self.output_path,
                    resolution=self.resolution,
                    sub_settings=self.sub_settings,
                    progress_cb=self.progress.emit,
                )
            else:
                from app.core.video_exporter import export_video
                out = export_video(
                    self.slides,
                    self.script_text,
                    self.mp3_path,
                    self.json_path,
                    self.output_path,
                    resolution=self.resolution,
                    sub_settings=self.sub_settings,
                    progress_cb=self.progress.emit,
                )
            self.finished.emit(True, out)
        except Exception as exc:
            self.finished.emit(False, str(exc))


# ═══════════════════════════════════════════════════════════════════════════
#  EXPORT DIALOG
# ═══════════════════════════════════════════════════════════════════════════

class ExportVideoDialog(QDialog):
    """Dialog cấu hình và xuất video MP4."""

    def __init__(
        self,
        slides: List[SlideInfo],
        script_text: str,
        mp3_path: str,
        json_path: str,
        sub_settings: dict = None,
        media_items=None,    # List[MediaItem] — dùng export mới khi có
        parent=None,
    ):
        super().__init__(parent)
        self.slides       = slides
        self.script_text  = script_text
        self.mp3_path     = mp3_path
        self.json_path    = json_path
        self.sub_settings = sub_settings
        self.media_items  = media_items
        self._thread: Optional[ExportVideoThread] = None

        self.setWindowTitle("Xuất Video MP4")
        self.setMinimumWidth(560)
        self.setStyleSheet("""
            QDialog { background-color: #0d1117; color: #e6edf3; }
            QLabel  { background: transparent; }
            QLineEdit {
                background: #161b22; border: 1px solid #30363d;
                border-radius: 6px; color: #e6edf3; padding: 6px 10px;
            }
            QComboBox {
                background: #161b22; border: 1px solid #30363d;
                border-radius: 6px; color: #e6edf3; padding: 6px 10px;
            }
            QPushButton {
                background: #21262d; color: #c9d1d9;
                border: 1px solid #30363d; border-radius: 6px;
                padding: 7px 16px; font-weight: 600;
            }
            QPushButton:hover { background: #30363d; }
            QPushButton#primary {
                background: #6d28d9; color: #fff; border: none;
            }
            QPushButton#primary:hover { background: #7c3aed; }
            QPushButton#primary:disabled { background: #3b1a6e; color: #7d5ba5; }
            QPushButton#success {
                background: #1a7f37; color: #fff; border: none;
                font-size: 14px; font-weight: 700;
                padding: 10px 20px; min-height: 40px;
            }
            QPushButton#success:hover { background: #238636; }
            QPushButton#success:disabled { background: #0d3318; color: #3fb950; }
            QProgressBar {
                background: #21262d; border: none; border-radius: 4px; height: 8px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #6d28d9, stop:1 #9333ea);
                border-radius: 4px;
            }
        """)
        self._build_ui()
        self._auto_fill_output()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(14)
        lay.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("🎬  Xuất Video MP4")
        title.setStyleSheet("font-size:16px; font-weight:700; color:#e6edf3;")
        lay.addWidget(title)

        # Stats
        assigned = sum(1 for s in self.slides if s.is_assigned)
        stats = QLabel(
            f"📊  {len(self.slides)} slide  ·  {assigned} đã gán vị trí  ·  "
            f"Audio: {Path(self.mp3_path).name}"
        )
        stats.setStyleSheet("color:#7d8590; font-size:12px;")
        lay.addWidget(stats)

        # JSON warning
        has_json = Path(self.json_path).exists() if self.json_path else False
        if not has_json:
            warn = QLabel(
                "⚠️  Không có file timestamps JSON — slide sẽ được phân bổ đều theo thời lượng audio"
            )
            warn.setStyleSheet("color:#f0883e; font-size:11px;")
            warn.setWordWrap(True)
            lay.addWidget(warn)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background:#21262d; border:none; max-height:1px;")
        lay.addWidget(sep)

        # Output path
        lay.addWidget(self._lbl("Lưu file video (.mp4):"))
        out_row = QHBoxLayout()
        self._out_edit = QLineEdit()
        self._out_edit.setPlaceholderText("Chọn đường dẫn lưu…")
        browse = QPushButton("…")
        browse.setFixedWidth(36)
        browse.clicked.connect(self._browse_output)
        out_row.addWidget(self._out_edit, 1)
        out_row.addWidget(browse)
        lay.addLayout(out_row)

        # Resolution
        lay.addWidget(self._lbl("Độ phân giải:"))
        self._res_combo = QComboBox()
        for label in ["1920 × 1080  (Full HD)", "1280 × 720  (HD)", "854 × 480  (SD)"]:
            self._res_combo.addItem(label)
        lay.addWidget(self._res_combo)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("background:#21262d; border:none; max-height:1px;")
        lay.addWidget(sep2)

        # Progress
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color:#8b949e; font-size:11px;")
        self._status_lbl.setVisible(False)
        lay.addWidget(self._progress)
        lay.addWidget(self._status_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Huỷ")
        cancel_btn.clicked.connect(self.reject)

        self._export_btn = QPushButton("🎬  Xuất Video")
        self._export_btn.setObjectName("success")
        self._export_btn.clicked.connect(self._start_export)

        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._export_btn)
        lay.addLayout(btn_row)

    def _lbl(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#8b949e; font-size:12px;")
        return lbl

    def _auto_fill_output(self):
        default = str(Path(self.mp3_path).with_suffix(".mp4"))
        self._out_edit.setText(default)

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Lưu file video", self._out_edit.text(),
            "MP4 Video (*.mp4);;Tất cả (*.*)"
        )
        if path:
            if not path.lower().endswith(".mp4"):
                path += ".mp4"
            self._out_edit.setText(path)
            from PyQt6.QtCore import QSettings
            settings = QSettings("KathTTS", "KathSlideToVideoMaker")
            settings.setValue("last_export_dir", str(Path(path).parent))

    def _resolution(self) -> tuple[int, int]:
        idx = self._res_combo.currentIndex()
        return [(1920, 1080), (1280, 720), (854, 480)][idx]

    def _start_export(self):
        output = self._out_edit.text().strip()
        if not output:
            QMessageBox.warning(self, "Thiếu đường dẫn", "Vui lòng chọn nơi lưu file.")
            return

        # Nếu không có JSON → dùng fallback estimation
        json_path = self.json_path if (self.json_path and Path(self.json_path).exists()) else ""

        self._export_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._status_lbl.setVisible(True)
        self._status_lbl.setText("Đang chuẩn bị…")

        self._thread = ExportVideoThread(
            self.slides, self.script_text,
            self.mp3_path, json_path,
            output, self._resolution(),
            sub_settings=self.sub_settings,
            media_items=getattr(self, "media_items", None),
            parent=self,
        )
        self._thread.progress.connect(self._on_progress)
        self._thread.finished.connect(self._on_finished)
        self._thread.start()

    def _on_progress(self, pct: int, msg: str):
        self._progress.setValue(pct)
        self._status_lbl.setText(msg)

    def _on_finished(self, success: bool, result: str):
        self._progress.setVisible(False)
        self._export_btn.setEnabled(True)

        if success:
            QMessageBox.information(
                self, "✓ Xuất thành công!",
                f"Video đã lưu tại:\n{result}\n\n"
                "Bạn có thể mở file MP4 bằng bất kỳ trình phát video nào."
            )
            # Offer to open folder
            folder = str(Path(result).parent)
            reply = QMessageBox.question(
                self, "Mở thư mục?",
                "Mở thư mục chứa file video?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                os.startfile(folder)
            self.accept()
        else:
            self._status_lbl.setText("❌ Thất bại")
            QMessageBox.critical(self, "Lỗi xuất video", result)


# ═══════════════════════════════════════════════════════════════════════════
#  PREVIEW DIALOG (slide slideshow + timer)
# ═══════════════════════════════════════════════════════════════════════════

class PreviewVideoDialog(QDialog):
    """
    Xem trước: hiển thị từng slide theo timeline và phát âm thanh tương ứng,
    có lớp hiển thị phụ đề với khả năng cấu hình style.
    """

    def __init__(
        self,
        slides: List[SlideInfo],
        script_text: str,
        mp3_path: str,
        json_path: str,
        sub_settings: dict = None,
        media_items=None,    # List[MediaItem]
        parent=None,
    ):
        super().__init__(parent)
        self.slides      = slides
        self.script_text = script_text
        self.mp3_path    = mp3_path
        self.json_path   = json_path
        self.media_items = media_items
        self.sub_settings = sub_settings if sub_settings is not None else {
            "enabled": True, "font_size": 20, "color": "Trắng", "style": "Viền đen", "position": 3
        }
        # Đảm bảo luôn có key position
        if "position" not in self.sub_settings:
            self.sub_settings["position"] = 3
        self._timeline   = []
        self._sentences  = []
        self._cur_idx    = 0
        self._playing    = False

        self.setWindowTitle("Xem trước Video")
        self.setMinimumSize(820, 560)
        self.setStyleSheet("""
            QDialog { background:#0d1117; color:#e6edf3; }
            QLabel  { background:transparent; }
            QPushButton {
                background:#21262d; color:#c9d1d9;
                border:1px solid #30363d; border-radius:6px;
                padding:6px 14px; font-weight:600;
            }
            QPushButton:hover { background:#30363d; }
            QPushButton#primary { background:#6d28d9; color:#fff; border:none; }
            QPushButton#primary:hover { background:#7c3aed; }
        """)
        
        # Cấu hình âm thanh TTS chính
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        
        if self.mp3_path and os.path.exists(self.mp3_path):
            self._player.setSource(QUrl.fromLocalFile(self.mp3_path))
            
        self._player.positionChanged.connect(self._on_player_position_changed)
        self._player.playbackStateChanged.connect(self._on_player_state_changed)

        self._build_ui()
        self._load_timeline()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(10)

        # Hàng chứa ảnh preview bên trái và bảng cấu hình phụ đề bên phải
        main_row = QHBoxLayout()

        # Slide preview image — không dùng border-radius để tránh clip góc slide
        self._img_lbl = QLabel()
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setMinimumHeight(380)
        self._img_lbl.setStyleSheet("background:#161b22; border-radius:0px;")
        self._img_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Subtitle overlay label (nằm đè trên ảnh)
        self._sub_overlay = OutlinedLabel(self._img_lbl)
        self._sub_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sub_overlay.setWordWrap(True)
        self._sub_overlay.setVisible(False)
        
        # Bảng cấu hình phụ đề (Subtitle Panel)
        self._settings_panel = QFrame()
        self._settings_panel.setFixedWidth(200)
        self._settings_panel.setStyleSheet("""
            QFrame { background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; }
            QLabel { color: #8b949e; font-size: 11px; font-weight: 600; border: none; }
            QComboBox, QCheckBox { background-color: #0d1117; border: 1px solid #30363d; border-radius: 4px; padding: 4px; color: #e6edf3; }
        """)
        s_lay = QVBoxLayout(self._settings_panel)
        s_lay.setContentsMargins(10, 10, 10, 10)
        s_lay.setSpacing(8)

        title = QLabel("⚙️ PHỤ ĐỀ (SUBTITLE)")
        title.setStyleSheet("font-size: 11px; font-weight: 700; color: #c4b5fd;")
        s_lay.addWidget(title)

        self._sub_enable_cb = QCheckBox("Hiển thị phụ đề")
        self._sub_enable_cb.setChecked(self.sub_settings.get("enabled", True))
        self._sub_enable_cb.stateChanged.connect(self._on_sub_settings_changed)
        s_lay.addWidget(self._sub_enable_cb)

        s_lay.addWidget(QLabel("Cỡ chữ (px):"))
        self._sub_size_combo = QComboBox()
        self._sub_size_combo.addItems(["14", "16", "18", "20", "22", "24", "26", "28", "32"])
        self._sub_size_combo.setCurrentText(str(self.sub_settings.get("font_size", 20)))
        self._sub_size_combo.currentTextChanged.connect(self._on_sub_settings_changed)
        s_lay.addWidget(self._sub_size_combo)

        s_lay.addWidget(QLabel("Màu chữ:"))
        self._sub_color_combo = QComboBox()
        self._sub_color_combo.addItems(["Trắng", "Vàng", "Xanh lá", "Xanh lam"])
        self._sub_color_combo.setCurrentText(self.sub_settings.get("color", "Trắng"))
        self._sub_color_combo.currentTextChanged.connect(self._on_sub_settings_changed)
        s_lay.addWidget(self._sub_color_combo)

        s_lay.addWidget(QLabel("Kiểu hiển thị:"))
        self._sub_style_combo = QComboBox()
        self._sub_style_combo.addItems(["Viền đen", "Nền đen mờ", "Không viền"])
        self._sub_style_combo.setCurrentText(self.sub_settings.get("style", "Viền đen"))
        self._sub_style_combo.currentTextChanged.connect(self._on_sub_settings_changed)
        s_lay.addWidget(self._sub_style_combo)

        # Vị trí subtitle (% từ đáy slide)
        s_lay.addWidget(QLabel("Vị trí (% từ đáy):"))
        pos_row = QHBoxLayout()
        self._sub_pos_slider = QSlider(Qt.Orientation.Horizontal)
        self._sub_pos_slider.setMinimum(1)
        self._sub_pos_slider.setMaximum(60)
        self._sub_pos_slider.setValue(self.sub_settings.get("position", 1))
        self._sub_pos_slider.setStyleSheet(
            "QSlider::groove:horizontal { height:4px; background:#30363d; border-radius:2px; }"
            "QSlider::handle:horizontal { width:12px; height:12px; margin:-4px 0;"
            " background:#7c3aed; border-radius:6px; }"
            "QSlider::sub-page:horizontal { background:#6d28d9; border-radius:2px; }"
        )
        self._sub_pos_spin = QSpinBox()
        self._sub_pos_spin.setMinimum(1)
        self._sub_pos_spin.setMaximum(60)
        self._sub_pos_spin.setValue(self.sub_settings.get("position", 1))
        self._sub_pos_spin.setFixedWidth(44)
        self._sub_pos_spin.setStyleSheet(
            "QSpinBox { background:#0d1117; border:1px solid #30363d;"
            " border-radius:4px; color:#e6edf3; padding:2px; }"
        )
        self._sub_pos_slider.valueChanged.connect(self._sub_pos_spin.setValue)
        self._sub_pos_spin.valueChanged.connect(self._sub_pos_slider.setValue)
        self._sub_pos_slider.valueChanged.connect(self._on_sub_settings_changed)
        pos_row.addWidget(self._sub_pos_slider, 1)
        pos_row.addWidget(self._sub_pos_spin)
        s_lay.addLayout(pos_row)

        s_lay.addStretch()
        main_row.addWidget(self._img_lbl, 1)
        main_row.addWidget(self._settings_panel)
        lay.addLayout(main_row, 1)

        # Slide info
        info_row = QHBoxLayout()
        self._slide_info = QLabel("Slide 1")
        self._slide_info.setStyleSheet("font-size:13px; font-weight:700; color:#c9d1d9;")
        self._time_lbl = QLabel("⏱ 0.0s")
        self._time_lbl.setStyleSheet("color:#7d8590; font-size:12px;")
        self._counter_lbl = QLabel("")
        self._counter_lbl.setStyleSheet(
            "background:#21262d; border:1px solid #30363d; border-radius:10px; "
            "color:#8b949e; font-size:11px; padding:2px 10px;"
        )
        info_row.addWidget(self._slide_info)
        info_row.addSpacing(12)
        info_row.addWidget(self._time_lbl)
        info_row.addStretch()
        info_row.addWidget(self._counter_lbl)
        lay.addLayout(info_row)

        # Progress bar (slide timeline)
        self._timeline_bar = QProgressBar()
        self._timeline_bar.setFixedHeight(4)
        self._timeline_bar.setStyleSheet("""
            QProgressBar { background:#21262d; border:none; border-radius:2px; }
            QProgressBar::chunk { background:#6d28d9; border-radius:2px; }
        """)
        self._timeline_bar.setValue(0)
        lay.addWidget(self._timeline_bar)

        # Controls
        ctrl_row = QHBoxLayout()
        self._prev_btn = QPushButton("⏮  Trước")
        self._prev_btn.clicked.connect(self._go_prev)

        self._play_btn = QPushButton("▶  Phát")
        self._play_btn.setObjectName("primary")
        self._play_btn.clicked.connect(self._toggle_play)

        self._next_btn = QPushButton("Tiếp  ⏭")
        self._next_btn.clicked.connect(self._go_next)

        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(self.accept)

        self._export_from_preview_btn = QPushButton("🎬  Xuất Video")
        self._export_from_preview_btn.setObjectName("export_btn")
        self._export_from_preview_btn.setStyleSheet(
            "QPushButton#export_btn { background:#1a7f37; color:#fff; border:none;"
            " border-radius:6px; padding:7px 16px; font-weight:700; }"
            "QPushButton#export_btn:hover { background:#238636; }"
        )
        self._export_from_preview_btn.clicked.connect(self._open_export_dialog)

        ctrl_row.addWidget(self._prev_btn)
        ctrl_row.addWidget(self._play_btn)
        ctrl_row.addWidget(self._next_btn)
        ctrl_row.addStretch()
        ctrl_row.addWidget(close_btn)
        ctrl_row.addWidget(self._export_from_preview_btn)
        lay.addLayout(ctrl_row)

        note = QLabel(
            "💡 Xem trước phát âm thanh kịch bản và hiển thị slide tương ứng trong thời gian thực. Kiểu phụ đề sẽ được giữ nguyên khi xuất video."
        )
        note.setStyleSheet("color:#484f58; font-size:10px;")
        note.setWordWrap(True)
        lay.addWidget(note)

        self._apply_sub_style()

    def _on_sub_settings_changed(self):
        self.sub_settings["enabled"]   = self._sub_enable_cb.isChecked()
        self.sub_settings["font_size"] = int(self._sub_size_combo.currentText())
        self.sub_settings["color"]     = self._sub_color_combo.currentText()
        self.sub_settings["style"]     = self._sub_style_combo.currentText()
        self.sub_settings["position"]  = self._sub_pos_slider.value()
        self._apply_sub_style()

    def _apply_sub_style(self):
        if not self.sub_settings.get("enabled", True):
            self._sub_overlay.setVisible(False)
            return

        color_map = {
            "Trắng": "#ffffff",
            "Vàng": "#ffeb3b",
            "Xanh lá": "#4caf50",
            "Xanh lam": "#2196f3"
        }
        color = color_map.get(self.sub_settings.get("color", "Trắng"), "#ffffff")
        size  = self.sub_settings.get("font_size", 20)
        style = self.sub_settings.get("style", "Viền đen")

        # Set font
        font = self.font()
        font.setBold(True)
        font.setPointSize(size)
        self._sub_overlay.setFont(font)

        # Set OutlinedLabel values dynamically
        self._sub_overlay.text_color = QColor(color)
        
        if style == "Viền đen":
            self._sub_overlay.tight_bg = False
            self._sub_overlay.outline_enabled = True
            self._sub_overlay.setStyleSheet("background: transparent; border: none; padding: 0px;")
        elif style == "Nền đen mờ":
            # Tight-fit: chỉ vẽ nền sát chữ trong paintEvent
            self._sub_overlay.tight_bg = True
            self._sub_overlay.outline_enabled = False
            self._sub_overlay.setStyleSheet("background: transparent; border: none; padding: 0px;")
        elif style == "Không viền":
            self._sub_overlay.tight_bg = False
            self._sub_overlay.outline_enabled = False
            self._sub_overlay.setStyleSheet(
                f"background: transparent; border: none; padding: 0px; color: {color};"
            )

        self._reposition_sub_overlay()
        self._sub_overlay.setVisible(bool(self._sub_overlay.text()))
        self._sub_overlay.update()

    def _reposition_sub_overlay(self):
        w = self._img_lbl.width()
        h = self._img_lbl.height()
        if w <= 0 or h <= 0:
            return

        text = self._sub_overlay.text().strip()
        if not text or not self.sub_settings.get("enabled", True):
            self._sub_overlay.setVisible(False)
            return

        size    = self.sub_settings.get("font_size", 20)
        pos_pct = self.sub_settings.get("position", 2)  # % từ đáy slide

        font = self.font()
        font.setBold(True)
        font.setPointSize(size)

        metrics  = QFontMetrics(font)
        line_h   = metrics.lineSpacing()
        MAX_LINES = 1  # Chỉ hiển thị tối đa 1 dòng theo yêu cầu người dùng
        max_text_h = line_h * MAX_LINES + 10   # Giới hạn tối đa 1 dòng + padding của tight_bg (2 * 5px)

        max_w  = int(w * 0.90)
        flags  = Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap
        br     = metrics.boundingRect(0, 0, max_w, 9999, flags, text)
        text_w = min(max_w, br.width() + 20)
        text_h = min(br.height() + 10, max_text_h)   # clamp: không quá 1 dòng

        # Tính đáy thực của slide (letterbox)
        img_bottom = h
        img_top    = 0
        pix = self._img_lbl.pixmap()
        if pix and not pix.isNull():
            scale    = min(w / pix.width(), h / pix.height())
            disp_h   = int(pix.height() * scale)
            disp_w   = int(pix.width() * scale)
            img_top  = (h - disp_h) // 2
            img_bottom = img_top + disp_h

        slide_h = img_bottom - img_top
        # pos_pct=1 → margin=0 (sát đáy hoàn toàn)
        margin = int(slide_h * (pos_pct - 1) / 100)

        # Đáy subtitle neo cứng tại img_bottom - margin
        bottom_anchor = img_bottom - margin
        y = bottom_anchor - text_h
        y = max(img_top, y)

        x = (w - text_w) // 2
        self._sub_overlay.setGeometry(x, y, text_w, text_h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_sub_overlay()

    def _load_timeline(self):
        # Đọc dữ liệu câu thoại để làm phụ đề
        self._sentences = []
        try:
            import json as _json
            from app.core.video_exporter import build_slide_timeline, split_sentences_into_single_lines

            json_data = {}
            if self.json_path and Path(self.json_path).exists():
                with open(self.json_path, "r", encoding="utf-8") as f:
                    json_data = _json.load(f)
                    raw_sentences = json_data.get("sentences", [])
                    self._sentences = split_sentences_into_single_lines(raw_sentences, max_chars=45)

            # Ưu tiên sử dụng media_items có cấu trúc đầy đủ
            items_to_use = self.media_items if self.media_items else self.slides

            if json_data:
                assigned = [s for s in items_to_use if s.is_assigned]
                self._timeline = build_slide_timeline(
                    assigned, self.script_text, json_data
                )
            else:
                assigned = [s for s in items_to_use if s.is_assigned]
                if not assigned:
                    assigned = items_to_use
                dur = 5.0
                from app.core.video_exporter import SlideTimedEntry
                self._timeline = [
                    SlideTimedEntry(s, i * dur, (i + 1) * dur, dur)
                    for i, s in enumerate(assigned)
                ]
        except Exception as e:
            items_to_use = self.media_items if self.media_items else self.slides
            assigned = [s for s in items_to_use if s.is_assigned] or items_to_use
            from app.core.video_exporter import SlideTimedEntry
            dur = 5.0
            self._timeline = [
                SlideTimedEntry(s, i * dur, (i + 1) * dur, dur)
                for i, s in enumerate(assigned)
            ]

        self._cur_idx = 0
        self._show_current()

    def _show_current(self):
        if not self._timeline:
            self._img_lbl.setText("Chưa có slide nào được gán.")
            return
 
        entry = self._timeline[self._cur_idx]
        slide = entry.slide
 
        # Tìm đường dẫn ảnh thu nhỏ hoặc ảnh slide
        img_path = (
            getattr(slide, "thumbnail_path", "") or
            getattr(slide, "image_path", "") or
            getattr(slide, "path", "")
        )
        
        if img_path and os.path.exists(img_path) and not img_path.lower().endswith(('.mp4', '.avi', '.mov', '.mkv')):
            pix = QPixmap(img_path)
            self._img_lbl.setPixmap(
                pix.scaled(self._img_lbl.width() or 760,
                           self._img_lbl.height() or 380,
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
            )
            self._img_lbl.setText("")
        else:
            self._img_lbl.setPixmap(QPixmap())
            self._img_lbl.setText(f"🎥  {slide.display_name}")

        title = getattr(slide, "title", "") if hasattr(slide, "title") else ""
        title_str = f" — {title}" if title else ""
        self._slide_info.setText(f"{slide.display_name}{title_str}")
        self._counter_lbl.setText(f"{self._cur_idx + 1} / {len(self._timeline)}")

    def _show_current_time(self, sec):
        self._show_current()
        if self._timeline:
            entry = self._timeline[self._cur_idx]
            self._time_lbl.setText(
                f"⏱ {sec:.1f}s / {entry.end_sec:.1f}s  "
                f"(Slide {self._cur_idx + 1}/{len(self._timeline)})"
            )

    def _on_player_position_changed(self, pos_ms):
        sec = pos_ms / 1000.0
        
        total_ms = self._player.duration() or 1
        pct = int(pos_ms / total_ms * 100)
        self._timeline_bar.setValue(pct)
        
        found_idx = 0
        for i, entry in enumerate(self._timeline):
            if entry.start_sec <= sec <= entry.end_sec:
                found_idx = i
                break
            if sec >= entry.end_sec:
                found_idx = i
                
        if found_idx != self._cur_idx:
            self._cur_idx = found_idx
            self._show_current_time(sec)
        else:
            if self._timeline:
                entry = self._timeline[self._cur_idx]
                self._time_lbl.setText(
                    f"⏱ {sec:.1f}s / {entry.end_sec:.1f}s  "
                    f"(Slide {self._cur_idx + 1}/{len(self._timeline)})"
                )

        # Cập nhật phụ đề
        current_text = ""
        for sent in self._sentences:
            start_ms = sent.get("start_ms", 0)
            end_ms   = sent.get("end_ms", start_ms + 1000)
            if start_ms <= pos_ms <= end_ms:
                current_text = sent.get("text", "").strip()
                break

        if self.sub_settings.get("enabled", True):
            self._sub_overlay.setText(current_text)
            self._sub_overlay.setVisible(bool(current_text))
            self._reposition_sub_overlay()
        else:
            self._sub_overlay.setVisible(False)
 
    def _on_player_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._playing = True
            self._play_btn.setText("⏸  Tạm dừng")
        else:
            self._playing = False
            self._play_btn.setText("▶  Phát")
            
            if self._player.position() >= self._player.duration() - 100 and self._player.duration() > 0:
                self._player.setPosition(0)

    def _toggle_play(self):
        if self._playing:
            self._player.pause()
        else:
            self._player.play()

    def _go_prev(self):
        if self._cur_idx > 0:
            prev_entry = self._timeline[self._cur_idx - 1]
            ms = int(prev_entry.start_sec * 1000)
            self._player.setPosition(ms)
            self._cur_idx -= 1
            self._show_current_time(prev_entry.start_sec)

    def _go_next(self):
        if self._cur_idx < len(self._timeline) - 1:
            next_entry = self._timeline[self._cur_idx + 1]
            ms = int(next_entry.start_sec * 1000)
            self._player.setPosition(ms)
            self._cur_idx += 1
            self._show_current_time(next_entry.start_sec)

    def _open_export_dialog(self):
        """Mở dialog xuất video từ ngay trong cửa sổ xem trước."""
        self._player.pause()
        from app.ui.video_export_dialog import ExportVideoDialog
        dlg = ExportVideoDialog(
            slides=self.slides,
            script_text=self.script_text,
            mp3_path=self.mp3_path,
            json_path=self.json_path,
            sub_settings=self.sub_settings,
            parent=self,
        )
        dlg.exec()

    def closeEvent(self, event):
        try:
            self._player.stop()
            self._video_player.stop()
            # Ngắt các kết nối signal để tránh callback chạy khi các widget đang bị hủy
            try:
                self._player.positionChanged.disconnect()
            except Exception:
                pass
            try:
                self._player.playbackStateChanged.disconnect()
            except Exception:
                pass
            
            # Giải phóng source và audio output
            self._player.setAudioOutput(None)
            self._player.setSource(QUrl())
            
            self._video_player.setAudioOutput(None)
            self._video_player.setSource(QUrl())
            
            # Hủy đối tượng an toàn trong event loop của Qt
            self._player.deleteLater()
            self._audio_output.deleteLater()
            self._video_player.deleteLater()
            self._video_audio.deleteLater()
        except Exception:
            pass
        super().closeEvent(event)
