"""
video_export_dialog.py — Dialog xuất video MP4 và xem trước slide timeline.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
    QComboBox,
)

from app.core.slide_processor import SlideInfo


# ═══════════════════════════════════════════════════════════════════════════
#  EXPORT WORKER THREAD
# ═══════════════════════════════════════════════════════════════════════════

class ExportVideoThread(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)   # success, error/path

    def __init__(self, slides, script_text, mp3_path, json_path,
                 output_path, resolution, parent=None):
        super().__init__(parent)
        self.slides      = slides
        self.script_text = script_text
        self.mp3_path    = mp3_path
        self.json_path   = json_path
        self.output_path = output_path
        self.resolution  = resolution

    def run(self):
        try:
            from app.core.video_exporter import export_video
            out = export_video(
                self.slides,
                self.script_text,
                self.mp3_path,
                self.json_path,
                self.output_path,
                resolution=self.resolution,
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
        parent=None,
    ):
        super().__init__(parent)
        self.slides      = slides
        self.script_text = script_text
        self.mp3_path    = mp3_path
        self.json_path   = json_path
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
        for label in ["1280 × 720  (HD)", "1920 × 1080  (Full HD)", "854 × 480  (SD)"]:
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

    def _resolution(self) -> tuple[int, int]:
        idx = self._res_combo.currentIndex()
        return [(1280, 720), (1920, 1080), (854, 480)][idx]

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
    Xem trước: hiển thị từng slide theo timeline ước tính.
    Không phát audio (chỉ visual slideshow).
    """

    def __init__(
        self,
        slides: List[SlideInfo],
        script_text: str,
        mp3_path: str,
        json_path: str,
        parent=None,
    ):
        super().__init__(parent)
        self.slides      = slides
        self.script_text = script_text
        self.mp3_path    = mp3_path
        self.json_path   = json_path
        self._timeline   = []
        self._cur_idx    = 0
        self._timer      = QTimer(self)
        self._timer.timeout.connect(self._advance)
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
        self._build_ui()
        self._load_timeline()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(10)

        # Slide preview image
        self._img_lbl = QLabel()
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setMinimumHeight(380)
        self._img_lbl.setStyleSheet("background:#161b22; border-radius:8px;")
        self._img_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay.addWidget(self._img_lbl, 1)

        # Slide info
        info_row = QHBoxLayout()
        self._slide_info = QLabel("Slide 1")
        self._slide_info.setStyleSheet("font-size:13px; font-weight:700; color:#c9d1d9;")
        self._time_lbl = QLabel("0.0s")
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

        ctrl_row.addWidget(self._prev_btn)
        ctrl_row.addWidget(self._play_btn)
        ctrl_row.addWidget(self._next_btn)
        ctrl_row.addStretch()
        ctrl_row.addWidget(close_btn)
        lay.addLayout(ctrl_row)

        note = QLabel(
            "💡 Xem trước chỉ hiển thị slide theo thứ tự. "
            "Thời điểm chuyển slide sẽ chính xác hơn trong file video xuất ra."
        )
        note.setStyleSheet("color:#484f58; font-size:10px;")
        note.setWordWrap(True)
        lay.addWidget(note)

    def _load_timeline(self):
        try:
            import json as _json
            from app.core.video_exporter import build_slide_timeline

            json_data = {}
            if self.json_path and Path(self.json_path).exists():
                with open(self.json_path, "r", encoding="utf-8") as f:
                    json_data = _json.load(f)

            if json_data:
                self._timeline = build_slide_timeline(
                    self.slides, self.script_text, json_data
                )
            else:
                # Fallback: chia đều theo số slide
                assigned = [s for s in self.slides if s.is_assigned]
                if not assigned:
                    assigned = self.slides
                dur = 5.0  # mặc định 5 giây/slide
                from app.core.video_exporter import SlideTimedEntry
                self._timeline = [
                    SlideTimedEntry(s, i * dur, (i + 1) * dur, dur)
                    for i, s in enumerate(assigned)
                ]
        except Exception as e:
            # Fallback nếu lỗi
            assigned = [s for s in self.slides if s.is_assigned] or self.slides
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

        # Load image
        if slide.image_path and os.path.exists(slide.image_path):
            pix = QPixmap(slide.image_path)
            self._img_lbl.setPixmap(
                pix.scaled(self._img_lbl.width() or 760,
                           self._img_lbl.height() or 380,
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
            )
            self._img_lbl.setText("")
        else:
            self._img_lbl.setText(f"📊  Slide {slide.display_number}")

        title = slide.title or f"Slide {slide.display_number}"
        self._slide_info.setText(f"Slide {slide.display_number}  —  {title}")
        self._time_lbl.setText(
            f"⏱ {entry.start_sec:.1f}s → {entry.end_sec:.1f}s  "
            f"(kéo dài {entry.duration_sec:.1f}s)"
        )
        self._counter_lbl.setText(f"{self._cur_idx + 1} / {len(self._timeline)}")

        total = max(1, self._timeline[-1].end_sec)
        pct   = int(entry.start_sec / total * 100)
        self._timeline_bar.setValue(pct)

    def _advance(self):
        if self._cur_idx < len(self._timeline) - 1:
            self._cur_idx += 1
            self._show_current()
            # Set timer for next slide
            entry = self._timeline[self._cur_idx]
            ms    = max(500, int(entry.duration_sec * 1000))
            self._timer.start(ms)
        else:
            self._timer.stop()
            self._playing = False
            self._play_btn.setText("▶  Phát lại")

    def _toggle_play(self):
        if self._playing:
            self._timer.stop()
            self._playing = False
            self._play_btn.setText("▶  Tiếp tục")
        else:
            if self._cur_idx >= len(self._timeline) - 1:
                self._cur_idx = 0
            self._playing = True
            self._play_btn.setText("⏸  Tạm dừng")
            entry = self._timeline[self._cur_idx]
            ms    = max(500, int(entry.duration_sec * 1000))
            self._timer.start(ms)

    def _go_prev(self):
        self._timer.stop()
        self._playing = False
        self._play_btn.setText("▶  Phát")
        if self._cur_idx > 0:
            self._cur_idx -= 1
            self._show_current()

    def _go_next(self):
        self._timer.stop()
        self._playing = False
        self._play_btn.setText("▶  Phát")
        if self._cur_idx < len(self._timeline) - 1:
            self._cur_idx += 1
            self._show_current()

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
