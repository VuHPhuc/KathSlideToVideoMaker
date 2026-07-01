"""
slide_sync_tab.py — Tab "Đồng bộ Slide"
Cho phép người dùng import PPTX/PDF, gán slide vào vị trí văn bản.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import (
    Qt, QThread, QSize, pyqtSignal, QPropertyAnimation, QEasingCurve,
)
from PyQt6.QtGui import (
    QColor, QFont, QPixmap, QTextCharFormat, QTextCursor, QPainter,
    QTextDocument,
)
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSizePolicy, QSplitter, QVBoxLayout, QWidget, QProgressBar,
    QToolButton, QGridLayout, QTextEdit,
)

from app.core.slide_processor import (
    SlideInfo, load_pptx, load_pdf, mapping_to_dict, apply_mapping_from_dict,
    SlideProcessorError,
)


# ═══════════════════════════════════════════════════════════════════════════
#  WORKER THREAD
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


# ═══════════════════════════════════════════════════════════════════════════
#  SLIDE THUMBNAIL CARD
# ═══════════════════════════════════════════════════════════════════════════

THUMB_W = 160
THUMB_H = 90

class SlideThumbnailCard(QFrame):
    """Card nhỏ đại diện cho một slide trong danh sách."""
    clicked = pyqtSignal(int)   # slide index
    removed = pyqtSignal(int)

    _STYLE_NORMAL = """
        QFrame#slideCard {
            background-color: #161b22;
            border: 2px solid #30363d;
            border-radius: 8px;
        }
    """
    _STYLE_SELECTED = """
        QFrame#slideCard {
            background-color: #1a0e36;
            border: 2px solid #7c3aed;
            border-radius: 8px;
        }
    """
    _STYLE_ASSIGNED = """
        QFrame#slideCard {
            background-color: #0f2d0f;
            border: 2px solid #238636;
            border-radius: 8px;
        }
    """

    def __init__(self, slide: SlideInfo, parent=None):
        super().__init__(parent)
        self.setObjectName("slideCard")
        self.slide = slide
        self._selected = False
        self._build()

    def _build(self):
        self.setFixedWidth(THUMB_W + 16)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        # Top row: remove button
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        num_lbl = QLabel(f"#{self.slide.display_number}")
        num_lbl.setStyleSheet(
            "color: #8b949e; font-size: 10px; font-weight: 700; background:transparent;"
        )
        self._remove_btn = QToolButton()
        self._remove_btn.setText("×")
        self._remove_btn.setFixedSize(18, 18)
        self._remove_btn.setStyleSheet(
            "QToolButton { color:#7d8590; background:transparent; border:none; "
            "font-size:14px; font-weight:700; }"
            "QToolButton:hover { color:#f85149; }"
        )
        self._remove_btn.clicked.connect(lambda: self.removed.emit(self.slide.index))
        top.addWidget(num_lbl)
        top.addStretch()
        top.addWidget(self._remove_btn)
        lay.addLayout(top)

        # Thumbnail image
        self._thumb_lbl = QLabel()
        self._thumb_lbl.setFixedSize(THUMB_W, THUMB_H)
        self._thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_lbl.setStyleSheet(
            "background-color: #21262d; border-radius: 4px;"
        )
        self._load_thumbnail()
        lay.addWidget(self._thumb_lbl)

        # Badge gán
        self._badge = QLabel("Chưa gán")
        self._badge.setObjectName("badge")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setFixedHeight(18)
        lay.addWidget(self._badge)

        # Title (clipped)
        if self.slide.title:
            title_lbl = QLabel(self.slide.title[:28] + ("…" if len(self.slide.title) > 28 else ""))
            title_lbl.setStyleSheet(
                "color: #8b949e; font-size: 10px; background:transparent;"
            )
            title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(title_lbl)

        self.setStyleSheet(self._STYLE_NORMAL)
        self.refresh_state()

    def _load_thumbnail(self):
        if self.slide.image_path and os.path.exists(self.slide.image_path):
            pix = QPixmap(self.slide.image_path)
            self._thumb_lbl.setPixmap(
                pix.scaled(THUMB_W, THUMB_H,
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
            )
        else:
            self._thumb_lbl.setText("📊")
            self._thumb_lbl.setStyleSheet(
                "background-color: #21262d; border-radius: 4px; "
                "font-size: 28px; color: #484f58;"
            )

    def refresh_state(self):
        if self.slide.is_assigned:
            snip = self.slide.assigned_text[:22] + "…" if len(self.slide.assigned_text) > 22 else self.slide.assigned_text
            self._badge.setText(f"✓ {snip}")
            self._badge.setObjectName("badge-green")
        else:
            self._badge.setText("Chưa gán")
            self._badge.setObjectName("badge")

        self._badge.style().unpolish(self._badge)
        self._badge.style().polish(self._badge)

        if self._selected:
            self.setStyleSheet(self._STYLE_SELECTED)
        elif self.slide.is_assigned:
            self.setStyleSheet(self._STYLE_ASSIGNED)
        else:
            self.setStyleSheet(self._STYLE_NORMAL)

    def set_selected(self, sel: bool):
        self._selected = sel
        self.refresh_state()

    def mousePressEvent(self, event):
        self.clicked.emit(self.slide.index)
        super().mousePressEvent(event)


# ═══════════════════════════════════════════════════════════════════════════
#  DROP ZONE (PPTX / PDF)
# ═══════════════════════════════════════════════════════════════════════════

class SlideDropZone(QFrame):
    file_dropped = pyqtSignal(str)

    _IDLE = """QFrame#slideDropZone {
        background-color: #161b22; border: 2px dashed #30363d; border-radius: 10px;
    }"""
    _HOVER = """QFrame#slideDropZone {
        background-color: #1a0e36; border: 2px dashed #7c3aed; border-radius: 10px;
    }"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("slideDropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(80)
        self.setMaximumHeight(110)
        self.setStyleSheet(self._IDLE)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)

        icon = QLabel("📊")
        icon.setStyleSheet("font-size:28px; background:transparent;")

        info_col = QVBoxLayout()
        self._lbl = QLabel("Kéo & thả file  .pptx  hoặc  .pdf  vào đây")
        self._lbl.setStyleSheet("color:#7d8590; font-size:12px; background:transparent;")
        info_col.addWidget(self._lbl)
        info_col.addSpacing(2)

        btn_row = QHBoxLayout()
        for label, filt in [("PPTX", "*.pptx"), ("PDF", "*.pdf")]:
            btn = QPushButton(f"Import {label}")
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda _, f=filt, l=label: self._open_dialog(f, l))
            btn_row.addWidget(btn)
        btn_row.addStretch()
        info_col.addLayout(btn_row)

        lay.addWidget(icon)
        lay.addSpacing(8)
        lay.addLayout(info_col)

    def _open_dialog(self, filt: str, label: str):
        ext_map = {"*.pptx": "PowerPoint (*.pptx)", "*.pdf": "PDF (*.pdf)"}
        path, _ = QFileDialog.getOpenFileName(
            self, f"Mở file {label}", "", f"{ext_map[filt]};;Tất cả (*.*)"
        )
        if path:
            self.file_dropped.emit(path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            url = event.mimeData().urls()[0].toLocalFile().lower()
            if url.endswith((".pptx", ".pdf")):
                event.acceptProposedAction()
                self.setStyleSheet(self._HOVER)
                self._lbl.setText("Thả file vào đây ✓")
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self._IDLE)
        self._lbl.setText("Kéo & thả file  .pptx  hoặc  .pdf  vào đây")

    def dropEvent(self, event):
        self.setStyleSheet(self._IDLE)
        self._lbl.setText("Kéo & thả file  .pptx  hoặc  .pdf  vào đây")
        url = event.mimeData().urls()[0].toLocalFile()
        self.file_dropped.emit(url)


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN SLIDE SYNC TAB
# ═══════════════════════════════════════════════════════════════════════════

class SlideSyncTab(QWidget):
    """
    Tab đồng bộ slide: trái = kịch bản văn bản, phải = danh sách slide + preview.
    """
    request_back    = pyqtSignal()          # quay lại MP3 tab
    request_export  = pyqtSignal(list)      # tiếp tục xuất video → pass slides

    def __init__(self, parent=None):
        super().__init__(parent)
        self._slides: List[SlideInfo] = []
        self._selected_index: Optional[int] = None
        self._script_text: str = ""
        self._mp3_path: str = ""
        self._json_path: str = ""
        self._card_map: dict[int, SlideThumbnailCard] = {}
        self._idx_to_pos: dict[int, int] = {}   # slide.index → list position
        self._load_thread: Optional[SlideLoadThread] = None
        self._build_ui()


    # ─────────────────────────────────────────────────────────────────────
    #  PUBLIC API
    # ─────────────────────────────────────────────────────────────────────

    def load_context(self, script_text: str, mp3_path: str, has_json: bool = True):
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
                "⚠️ Thiếu .json timestamps — Đồng bộ Slide OK, nhưng Xuất Video sẽ không chính xác theo giây"
            )

        self._update_stats()


    # ─────────────────────────────────────────────────────────────────────
    #  UI BUILD
    # ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Info bar ────────────────────────────────────────────────────
        info_bar = self._build_info_bar()
        root.addWidget(info_bar)

        # ── Main splitter ───────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([480, 560])
        root.addWidget(splitter, 1)

        # ── Action bar ──────────────────────────────────────────────────
        root.addWidget(self._build_action_bar())

    # ── Info bar ─────────────────────────────────────────────────────────

    def _build_info_bar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(38)
        bar.setStyleSheet(
            "QFrame { background-color:#12161c; border-bottom:1px solid #21262d; }"
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

        self._stats_lbl = QLabel("0 slide · 0 đã gán")
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

    # ── Left panel: kịch bản văn bản ─────────────────────────────────────

    def _build_left_panel(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background-color: #0d1117;")
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

        # Text editor
        self._editor = QPlainTextEdit()
        self._editor.setReadOnly(False)
        self._editor.setPlaceholderText(
            "Kịch bản sẽ được tải tự động từ bước tạo MP3.\n\n"
            "Bạn có thể chọn vị trí bất kỳ rồi nhấn 'Gán Slide' ở bên phải."
        )
        self._editor.setStyleSheet(
            "QPlainTextEdit { font-size:13px; line-height:1.7; "
            "selection-background-color:#4c1d95; }"
        )
        self._editor.cursorPositionChanged.connect(self._on_cursor_changed)
        lay.addWidget(self._editor, 1)

        # Assign button (prominent)
        assign_row = QHBoxLayout()
        self._assign_btn = QPushButton("⬅  Gán Slide đang chọn vào vị trí này")
        self._assign_btn.setObjectName("primary")
        self._assign_btn.setMinimumHeight(38)
        self._assign_btn.setEnabled(False)
        self._assign_btn.clicked.connect(self._assign_slide)
        self._assign_hint = QLabel("← Chọn 1 slide bên phải trước")
        self._assign_hint.setStyleSheet(
            "color:#484f58; font-size:11px; background:transparent;"
        )
        assign_row.addWidget(self._assign_btn, 1)
        lay.addLayout(assign_row)
        lay.addWidget(self._assign_hint)

        return w

    # ── Right panel: danh sách slide + preview ────────────────────────────

    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background-color: #0d1117;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 14, 16, 14)
        lay.setSpacing(8)

        # Header
        hdr = QHBoxLayout()
        lbl = QLabel("🖼  SLIDES")
        lbl.setObjectName("heading")
        self._slide_count_lbl = QLabel("0 slide")
        self._slide_count_lbl.setObjectName("badge")
        hdr.addWidget(lbl)
        hdr.addStretch()
        hdr.addWidget(self._slide_count_lbl)
        lay.addLayout(hdr)

        # Drop zone import
        self._drop_zone = SlideDropZone()
        self._drop_zone.file_dropped.connect(self._on_file_dropped)
        lay.addWidget(self._drop_zone)

        # Progress bar (import)
        self._import_progress = QProgressBar()
        self._import_progress.setFixedHeight(5)
        self._import_progress.setVisible(False)
        self._import_status = QLabel("")
        self._import_status.setStyleSheet(
            "color:#8b949e; font-size:11px; background:transparent;"
        )
        self._import_status.setVisible(False)
        lay.addWidget(self._import_progress)
        lay.addWidget(self._import_status)

        # Preview lớn của slide đang chọn
        preview_frame = QFrame()
        preview_frame.setObjectName("card")
        preview_frame.setFixedHeight(180)
        p_lay = QVBoxLayout(preview_frame)
        p_lay.setContentsMargins(6, 6, 6, 6)
        self._preview_lbl = QLabel("Chọn một slide để xem trước")
        self._preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_lbl.setStyleSheet(
            "color:#484f58; font-size:12px; background:transparent;"
        )
        self._preview_lbl.setScaledContents(False)
        p_lay.addWidget(self._preview_lbl)

        self._preview_title = QLabel("")
        self._preview_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_title.setStyleSheet(
            "color:#c9d1d9; font-size:12px; font-weight:600; background:transparent;"
        )
        p_lay.addWidget(self._preview_title)
        lay.addWidget(preview_frame)

        # Scroll area — danh sách thumbnail
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        scroll.setStyleSheet("QScrollArea { border: none; background:#0d1117; }")

        self._list_container = QWidget()
        self._list_container.setStyleSheet("background:#0d1117;")
        self._list_layout = QGridLayout(self._list_container)
        self._list_layout.setContentsMargins(4, 4, 4, 4)
        self._list_layout.setSpacing(8)
        scroll.setWidget(self._list_container)
        lay.addWidget(scroll, 1)

        # Remove all button
        clear_btn = QPushButton("🗑  Xóa tất cả slide")
        clear_btn.setObjectName("danger")
        clear_btn.clicked.connect(self._clear_slides)
        lay.addWidget(clear_btn)

        return w

    # ── Action bar ────────────────────────────────────────────────────────

    def _build_action_bar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(56)
        bar.setStyleSheet(
            "QFrame { background-color:#161b22; border-top:1px solid #21262d; }"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(10)

        back_btn = QPushButton("← Quay lại tạo MP3")
        back_btn.clicked.connect(self.request_back.emit)

        save_btn = QPushButton("💾  Lưu dự án")
        save_btn.clicked.connect(self._save_project)

        # Stats center
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

    # ─────────────────────────────────────────────────────────────────────
    #  SLIDE LOADING
    # ─────────────────────────────────────────────────────────────────────

    def _on_file_dropped(self, path: str):
        if self._load_thread and self._load_thread.isRunning():
            QMessageBox.warning(self, "Đang xử lý", "Vui lòng chờ lần import trước xong.")
            return

        self._import_progress.setVisible(True)
        self._import_progress.setValue(0)
        self._import_status.setVisible(True)
        self._import_status.setText(f"Đang tải: {Path(path).name}…")

        self._load_thread = SlideLoadThread(path, parent=self)
        self._load_thread.progress.connect(self._on_import_progress)
        self._load_thread.finished.connect(self._on_import_finished)
        self._load_thread.start()

    def _on_import_progress(self, pct: int, msg: str):
        self._import_progress.setValue(pct)
        self._import_status.setText(msg)

    def _on_import_finished(self, success: bool, slides: list, error: str):
        self._import_progress.setVisible(False)
        self._import_status.setVisible(False)

        if not success:
            QMessageBox.critical(self, "Lỗi import", error)
            return

        self._slides = slides
        self._rebuild_slide_list()
        self._update_stats()

    # ─────────────────────────────────────────────────────────────────────
    #  SLIDE LIST
    # ─────────────────────────────────────────────────────────────────────

    def _rebuild_slide_list(self):
        """Xây lại grid thumbnail từ self._slides."""
        # Clear layout
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._card_map.clear()
        self._selected_index = None

        COLS = 2
        for idx, slide in enumerate(self._slides):
            card = SlideThumbnailCard(slide)
            card.clicked.connect(self._on_slide_selected)
            card.removed.connect(self._remove_slide)
            self._card_map[slide.index] = card
            row, col = divmod(idx, COLS)
            self._list_layout.addWidget(card, row, col)

        self._slide_count_lbl.setText(f"{len(self._slides)} slide")
        # Build a fast lookup: slide.index -> list position
        self._idx_to_pos: dict[int, int] = {s.index: i for i, s in enumerate(self._slides)}
        self._select_slide(self._slides[0].index if self._slides else None)

    def _on_slide_selected(self, idx: int):
        self._select_slide(idx)

    def _select_slide(self, idx: Optional[int]):
        # Deselect previous
        if self._selected_index is not None and self._selected_index in self._card_map:
            self._card_map[self._selected_index].set_selected(False)

        self._selected_index = idx

        if idx is None or idx not in self._card_map:
            self._preview_lbl.setPixmap(QPixmap())
            self._preview_lbl.setText("Chọn một slide để xem trước")
            self._preview_title.setText("")
            self._assign_btn.setEnabled(False)
            self._assign_hint.setText("← Chọn 1 slide bên phải trước")
            return

        self._card_map[idx].set_selected(True)

        # Get slide by index using the lookup table
        pos = self._idx_to_pos.get(idx)
        if pos is None:
            return
        slide = self._slides[pos]

        # Update large preview
        if slide.image_path and os.path.exists(slide.image_path):
            pix = QPixmap(slide.image_path)
            self._preview_lbl.setPixmap(
                pix.scaled(self._preview_lbl.width() - 4, 150,
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
            )
            self._preview_lbl.setText("")
        else:
            self._preview_lbl.setText(f"📊  Slide {slide.display_number}")

        title = slide.title or f"Slide {slide.display_number}"
        self._preview_title.setText(title)
        self._assign_btn.setEnabled(True)
        self._assign_hint.setText(
            f"Slide #{slide.display_number} đã chọn  •  Nhấp vào văn bản bên trái rồi nhấn Gán"
        )

    def _remove_slide(self, idx: int):
        self._slides = [s for s in self._slides if s.index != idx]
        # Re-index
        for i, s in enumerate(self._slides):
            s.index = i
        self._rebuild_slide_list()
        self._update_stats()

    def _clear_slides(self):
        if not self._slides:
            return
        if QMessageBox.question(
            self, "Xác nhận", "Xóa toàn bộ slide đã import?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self._slides.clear()
            self._rebuild_slide_list()
            self._update_stats()

    # ─────────────────────────────────────────────────────────────────────
    #  ASSIGN LOGIC
    # ─────────────────────────────────────────────────────────────────────

    def _on_cursor_changed(self):
        cursor = self._editor.textCursor()
        pos    = cursor.position()
        block  = cursor.blockNumber() + 1
        col    = cursor.columnNumber() + 1
        self._cursor_lbl.setText(f"Dòng {block}, Cột {col}  (vị trí {pos})")

    def _assign_slide(self):
        if self._selected_index is None:
            return

        # Get slide via card_map — guaranteed same object the card holds
        card = self._card_map.get(self._selected_index)
        if card is None:
            return
        slide = card.slide

        cursor = self._editor.textCursor()
        pos    = cursor.position()

        # Get snippet (surrounding text ~50 chars)
        text = self._editor.toPlainText()
        snip_start = max(0, pos - 5)
        snip_end   = min(len(text), pos + 45)
        snippet    = text[snip_start:snip_end].replace("\n", " ").strip()

        slide.assigned_pos  = pos
        slide.assigned_text = snippet

        # Also ensure the object in self._slides is updated
        # (guard against any reference divergence)
        list_pos = self._idx_to_pos.get(slide.index)
        if list_pos is not None:
            self._slides[list_pos].assigned_pos  = pos
            self._slides[list_pos].assigned_text = snippet

        # Visual marker in text
        self._draw_markers()

        # Refresh card + force immediate repaint
        card.refresh_state()
        card.repaint()

        # Update stats
        self._update_stats()

        # Flash feedback on button
        orig = self._assign_btn.text()
        self._assign_btn.setText("✓  Đã gán!")
        self._assign_btn.setEnabled(False)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(800, lambda: (
            self._assign_btn.setText(orig),
            self._assign_btn.setEnabled(True),
        ))

    def _draw_markers(self):
        """Tô màu các vị trí gán slide trong editor."""
        extra_selections = []
        text = self._editor.toPlainText()

        for slide in self._slides:
            if not slide.is_assigned:
                continue
            pos = slide.assigned_pos
            if pos < 0 or pos > len(text):
                continue

            fmt = QTextCharFormat()
            fmt.setBackground(QColor("#2d1b69"))
            fmt.setForeground(QColor("#c4b5fd"))
            fmt.setToolTip(f"[Slide {slide.display_number}] {slide.title}")

            # Mark 1 character at position (or a small range)
            sel = QTextEdit.ExtraSelection()
            sel.format = fmt
            cursor = self._editor.textCursor()
            cursor.setPosition(max(0, pos - 1))
            cursor.setPosition(min(len(text), pos + 60), QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = cursor
            extra_selections.append(sel)

        self._editor.setExtraSelections(extra_selections)

    def _unassign_slide(self, idx: int):
        if idx < len(self._slides):
            self._slides[idx].assigned_pos  = -1
            self._slides[idx].assigned_text = ""
            self._draw_markers()
            if idx in self._card_map:
                self._card_map[idx].refresh_state()
            self._update_stats()

    # ─────────────────────────────────────────────────────────────────────
    #  STATS
    # ─────────────────────────────────────────────────────────────────────

    def _update_stats(self):
        total    = len(self._slides)
        assigned = sum(1 for s in self._slides if s.is_assigned)
        unassigned = total - assigned

        self._stats_lbl.setText(f"{total} slide  ·  {assigned} đã gán")
        self._slide_count_lbl.setText(f"{total} slide")
        self._action_stats.setText(
            f"✅ {assigned} đã gán  •  ⚠️ {unassigned} chưa gán"
            if unassigned > 0 else
            f"✅ Tất cả {total} slide đã được gán"
        )

        if total > 0 and unassigned > 0:
            self._warn_lbl.setText(f"⚠  Còn {unassigned} slide chưa gán vị trí")
        else:
            self._warn_lbl.setText("")

    # ─────────────────────────────────────────────────────────────────────
    #  SAVE / EXPORT
    # ─────────────────────────────────────────────────────────────────────

    def _save_project(self):
        if not self._mp3_path:
            QMessageBox.warning(self, "Chưa có MP3", "Cần xuất MP3 trước khi lưu dự án.")
            return
        data = mapping_to_dict(self._slides)
        data["script_text"] = self._script_text
        data["mp3_path"]    = self._mp3_path

        # Lưu cùng thư mục với MP3, đặt tên theo MP3
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
        if not self._slides:
            QMessageBox.warning(self, "Chưa có slide", "Vui lòng import slide trước.")
            return
        if not self._mp3_path:
            QMessageBox.warning(self, "Chưa có MP3", "Chưa có file audio.")
            return
        from app.ui.video_export_dialog import PreviewVideoDialog
        dlg = PreviewVideoDialog(
            slides=self._slides,
            script_text=self._script_text,
            mp3_path=self._mp3_path,
            json_path=self._json_path,
            parent=self,
        )
        dlg.exec()

    def _go_export(self):
        if not self._slides:
            QMessageBox.warning(self, "Chưa có slide", "Vui lòng import slide trước.")
            return
        if not self._mp3_path:
            QMessageBox.warning(self, "Chưa có MP3", "Chưa có file audio.")
            return

        unassigned = [s for s in self._slides if not s.is_assigned]
        if unassigned:
            reply = QMessageBox.question(
                self, "Còn slide chưa gán",
                f"Có {len(unassigned)} slide chưa được gán vị trí trong kịch bản.\n"
                "Những slide này sẽ được bỏ qua khi xuất video.\n\n"
                "Tiếp tục xuất không?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return

        from app.ui.video_export_dialog import ExportVideoDialog
        dlg = ExportVideoDialog(
            slides=self._slides,
            script_text=self._script_text,
            mp3_path=self._mp3_path,
            json_path=self._json_path,
            parent=self,
        )
        dlg.exec()

