"""
timeline_widget.py — Widget Timeline ngang kiểu Clipchamp.
Hiển thị danh sách MediaItem theo chiều ngang với transition giữa mỗi clip.
"""
from __future__ import annotations

import os
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer, QMimeData
from PyQt6.QtGui import QColor, QPixmap, QPainter, QFont, QCursor, QDrag
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QScrollArea,
    QFrame, QToolButton, QDialog, QDialogButtonBox, QComboBox,
    QDoubleSpinBox, QSizePolicy, QApplication,
)

from app.models.media_item import MediaItem, TRANSITION_TYPES

# ─── Constants ──────────────────────────────────────────────────────────────
CLIP_W    = 162
CLIP_H    = 112
TRANS_W   = 38


# ═══════════════════════════════════════════════════════════════════════════
#  TRANSITION PICKER DIALOG
# ═══════════════════════════════════════════════════════════════════════════

class TransitionPickerDialog(QDialog):
    """Dialog chọn loại transition và thời lượng."""

    def __init__(self, current_type: str = "none",
                 current_dur: float = 0.5, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⬡  Chọn Transition")
        self.setMinimumWidth(330)
        self.setStyleSheet("""
            QDialog   { background:#161b22; color:#e6edf3; }
            QLabel    { background:transparent; color:#c9d1d9; font-size:12px; }
            QComboBox, QDoubleSpinBox {
                background:#0d1117; border:1px solid #30363d;
                border-radius:5px; color:#e6edf3; padding:5px 8px;
                min-height:28px;
            }
            QComboBox:hover, QDoubleSpinBox:hover { border-color:#6d28d9; }
            QComboBox QAbstractItemView {
                background:#161b22; border:1px solid #30363d;
                color:#e6edf3; selection-background-color:#6d28d9;
            }
            QPushButton {
                background:#21262d; color:#c9d1d9; border:1px solid #30363d;
                border-radius:5px; padding:6px 20px; font-weight:600;
            }
            QPushButton:hover { background:#30363d; }
            QPushButton:default {
                background:#6d28d9; color:#fff; border:none;
            }
            QPushButton:default:hover { background:#7c3aed; }
        """)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(16, 16, 16, 16)

        lay.addWidget(QLabel("Loại chuyển cảnh:"))
        self._type_combo = QComboBox()
        for display, key in TRANSITION_TYPES:
            icon = "✦ " if key != "none" else "╌ "
            self._type_combo.addItem(icon + display, key)
        for i, (_, key) in enumerate(TRANSITION_TYPES):
            if key == current_type:
                self._type_combo.setCurrentIndex(i)
                break
        lay.addWidget(self._type_combo)

        lay.addWidget(QLabel("Thời lượng (giây):"))
        self._dur_spin = QDoubleSpinBox()
        self._dur_spin.setMinimum(0.2)
        self._dur_spin.setMaximum(2.5)
        self._dur_spin.setSingleStep(0.1)
        self._dur_spin.setValue(current_dur)
        self._dur_spin.setSuffix(" s")
        lay.addWidget(self._dur_spin)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setDefault(True)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

    def get_result(self) -> tuple[str, float]:
        return self._type_combo.currentData(), self._dur_spin.value()


# ═══════════════════════════════════════════════════════════════════════════
#  CLIP BLOCK
# ═══════════════════════════════════════════════════════════════════════════

class ClipBlock(QFrame):
    """Một clip trong timeline."""
    clicked = pyqtSignal(str)  # item.id
    removed = pyqtSignal(str)  # item.id

    _TYPE_COLOR = {
        "slide": ("#7c3aed", "#2e1065", "#c4b5fd"),
        "video": ("#0891b2", "#0c4a6e", "#67e8f9"),
        "image": ("#059669", "#064e3b", "#6ee7b7"),
    }

    def __init__(self, item: MediaItem, parent=None):
        super().__init__(parent)
        self.item = item
        self._selected = False
        self._build()

    # ── Build ─────────────────────────────────────────────────────────────

    def _build(self):
        self.setFixedSize(CLIP_W, CLIP_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(5, 5, 5, 5)
        lay.setSpacing(3)

        # ── Top row: type icon + duration + remove ──────────────────────
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(3)

        _, _, accent = self._TYPE_COLOR.get(self.item.media_type,
                                             ("#7c3aed", "#2e1065", "#c4b5fd"))
        icon = {"slide": "📊", "video": "🎬", "image": "🖼️"}.get(
            self.item.media_type, "?")
        self._type_lbl = QLabel(icon)
        self._type_lbl.setStyleSheet("background:transparent; font-size:12px;")

        dur_text = f"{self.item.duration_sec:.1f}s"
        self._dur_lbl = QLabel(dur_text)
        self._dur_lbl.setStyleSheet(
            f"background:{accent}22; color:{accent}; font-size:9px; "
            f"font-weight:700; border-radius:3px; padding:1px 5px; "
            f"border:1px solid {accent}55;"
        )

        self._remove_btn = QToolButton()
        self._remove_btn.setText("×")
        self._remove_btn.setFixedSize(16, 16)
        self._remove_btn.setCursor(Qt.CursorShape.ArrowCursor)
        self._remove_btn.setStyleSheet(
            "QToolButton{color:#7d8590;background:transparent;border:none;"
            "font-size:14px;font-weight:700;}"
            "QToolButton:hover{color:#f85149;}"
        )
        self._remove_btn.clicked.connect(lambda: self.removed.emit(self.item.id))

        top.addWidget(self._type_lbl)
        top.addWidget(self._dur_lbl)
        top.addStretch()
        top.addWidget(self._remove_btn)
        lay.addLayout(top)

        # ── Thumbnail ───────────────────────────────────────────────────
        self._thumb = QLabel()
        self._thumb.setFixedSize(CLIP_W - 10, 64)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setStyleSheet("background:#0d1117; border-radius:4px;")
        self._load_thumbnail()
        lay.addWidget(self._thumb)

        # ── Name ────────────────────────────────────────────────────────
        self._name_lbl = QLabel(self.item.display_name)
        self._name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_lbl.setStyleSheet(
            "color:#c9d1d9; font-size:9px; background:transparent;"
        )
        self._name_lbl.setFixedWidth(CLIP_W - 10)
        lay.addWidget(self._name_lbl)

    def _load_thumbnail(self):
        img_path = self.item.image_path
        if img_path and os.path.exists(img_path):
            pix = QPixmap(img_path)
            self._thumb.setPixmap(
                pix.scaled(CLIP_W - 10, 64,
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
            )
        else:
            icons = {"slide": "📊", "video": "🎬", "image": "🖼️"}
            self._thumb.setText(icons.get(self.item.media_type, "?"))
            self._thumb.setStyleSheet(
                "background:#21262d; border-radius:4px; font-size:26px;"
            )

    def refresh_thumbnail(self):
        self._load_thumbnail()

    def refresh_duration(self):
        self._dur_lbl.setText(f"{self.item.duration_sec:.1f}s")

    def _apply_style(self):
        border, bg, _ = self._TYPE_COLOR.get(
            self.item.media_type, ("#7c3aed", "#2e1065", "#c4b5fd"))
        if self._selected:
            self.setStyleSheet(f"""
                QFrame {{
                    background:{bg};
                    border:2px solid {border};
                    border-radius:8px;
                }}
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    background:#161b22;
                    border:1.5px solid #30363d;
                    border-radius:8px;
                }
                QFrame:hover {
                    border:1.5px solid #484f58;
                    background:#1c2130;
                }
            """)

    def set_selected(self, val: bool):
        self._selected = val
        self._apply_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
        self.clicked.emit(self.item.id)
        super().mousePressEvent(event)
 
    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not hasattr(self, "_drag_start_pos"):
            return
        if (event.position().toPoint() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return
 
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-kath-media-id", self.item.id.encode("utf-8"))
        drag.setMimeData(mime)
 
        pixmap = self.grab()
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.position().toPoint())
        drag.exec(Qt.DropAction.MoveAction)


# ═══════════════════════════════════════════════════════════════════════════
#  TRANSITION NODE
# ═══════════════════════════════════════════════════════════════════════════

class TransitionNode(QFrame):
    """Nút transition nhỏ giữa 2 clip."""
    clicked = pyqtSignal(int)  # index (giữa items[i] và items[i+1])

    def __init__(self, index: int, trans_type: str = "none", parent=None):
        super().__init__(parent)
        self.index = index
        self._type = trans_type
        self._build()

    def _build(self):
        self.setFixedSize(TRANS_W, CLIP_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click để chọn transition")
        self._apply_style()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(2)

        self._icon = QLabel("✦" if self._type != "none" else "╌")
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon.setStyleSheet("background:transparent; font-size:13px;")
        lay.addWidget(self._icon)

        self._lbl = QLabel(self._short_name())
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl.setStyleSheet(
            "background:transparent; font-size:7px; color:#8b949e;"
        )
        lay.addWidget(self._lbl)

    def _short_name(self) -> str:
        for display, key in TRANSITION_TYPES:
            if key == self._type:
                return display[:5]
        return "Không"

    def _apply_style(self):
        if self._type != "none":
            self.setStyleSheet("""
                QFrame {
                    background:#1e0f4a;
                    border:1.5px dashed #7c3aed;
                    border-radius:6px;
                }
                QFrame:hover {
                    background:#2e1065;
                    border-color:#a78bfa;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    background:transparent;
                    border:1.5px dashed #30363d;
                    border-radius:6px;
                }
                QFrame:hover {
                    background:#161b22;
                    border-color:#484f58;
                }
            """)

    def update_type(self, trans_type: str):
        self._type = trans_type
        self._icon.setText("✦" if self._type != "none" else "╌")
        self._lbl.setText(self._short_name())
        self._apply_style()

    def mousePressEvent(self, event):
        self.clicked.emit(self.index)
        super().mousePressEvent(event)


# ═══════════════════════════════════════════════════════════════════════════
#  TIMELINE WIDGET  (main)
# ═══════════════════════════════════════════════════════════════════════════

class TimelineWidget(QWidget):
    """
    Timeline ngang kiểu Clipchamp.
    Hiển thị MediaItem theo hàng ngang, giữa mỗi clip có TransitionNode.
    """
    clip_selected      = pyqtSignal(str)        # item.id
    clip_removed       = pyqtSignal(str)        # item.id
    transition_changed = pyqtSignal(int, str, float)  # index, type, dur
    reordered          = pyqtSignal()
 
    def __init__(self, parent=None):
        super().__init__(parent)
        self._items:       List[MediaItem]        = []
        self._selected_id: Optional[str]          = None
        self._clip_widgets: dict[str, ClipBlock]  = {}
        self._trans_nodes:  list[TransitionNode]  = []
        self.setAcceptDrops(True)
        self._build()

    # ── Build UI ──────────────────────────────────────────────────────────

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Đảm bảo TimelineWidget luôn đủ chiều cao để hiển thị
        self.setMinimumHeight(CLIP_H + 22 + 24)   # header + scroll + scrollbar

        # Track header
        hdr = QLabel("  🎬  VIDEO TRACK")
        hdr.setFixedHeight(22)
        hdr.setStyleSheet(
            "background:#12161c; color:#484f58; font-size:10px; "
            "font-weight:700; letter-spacing:0.06em; "
            "border-top:1px solid #21262d; "
            "border-bottom:1px solid #21262d; padding:0 8px;"
        )
        outer.addWidget(hdr)

        # Scroll area — dùng min height thay vì fixed để không bị cắt
        self._scroll = QScrollArea()
        self._scroll.setMinimumHeight(CLIP_H + 24)
        self._scroll.setMaximumHeight(CLIP_H + 32)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("""
            QScrollArea { border:none; background:#0d1117; }
            QScrollBar:horizontal {
                height:8px; background:#0d1117; margin:0;
                border-radius:4px;
            }
            QScrollBar::handle:horizontal {
                background:#30363d; border-radius:4px; min-width:24px;
            }
            QScrollBar::handle:horizontal:hover { background:#484f58; }
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal { width:0; }
        """)


        self._inner = QWidget()
        self._inner.setStyleSheet("background:#0d1117;")
        self._inner_lay = QHBoxLayout(self._inner)
        self._inner_lay.setContentsMargins(10, 6, 10, 6)
        self._inner_lay.setSpacing(0)
        self._inner_lay.setAlignment(Qt.AlignmentFlag.AlignLeft |
                                     Qt.AlignmentFlag.AlignVCenter)

        self._scroll.setWidget(self._inner)
        outer.addWidget(self._scroll)

        self._show_empty()

    def _show_empty(self):
        self._empty_lbl = QLabel(
            "  Kéo & thả  hoặc  import  PPTX · PDF · Video · Ảnh  vào đây  ↑"
        )
        self._empty_lbl.setStyleSheet(
            "color:#3d444d; font-size:12px; background:transparent;"
        )
        self._inner_lay.addWidget(self._empty_lbl)
        self._inner_lay.addStretch()
        self._inner.setMinimumWidth(420)

    # ── Public API ────────────────────────────────────────────────────────

    def set_items(self, items: List[MediaItem]):
        self._items = items
        self._rebuild()

    def select_item(self, item_id: Optional[str]):
        if self._selected_id and self._selected_id in self._clip_widgets:
            self._clip_widgets[self._selected_id].set_selected(False)
        self._selected_id = item_id
        if item_id and item_id in self._clip_widgets:
            self._clip_widgets[item_id].set_selected(True)

    def get_selected_id(self) -> Optional[str]:
        return self._selected_id

    def refresh_clip(self, item_id: str):
        """Làm mới thumbnail và duration của một clip."""
        if item_id in self._clip_widgets:
            block = self._clip_widgets[item_id]
            block.refresh_thumbnail()
            block.refresh_duration()

    # ── Internal ─────────────────────────────────────────────────────────

    def _rebuild(self):
        # Xóa hết widget cũ
        while self._inner_lay.count():
            it = self._inner_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._clip_widgets.clear()
        self._trans_nodes.clear()

        if not self._items:
            self._show_empty()
            return
 
        # Đánh lại display_number của các item theo thứ tự thực tế trong timeline trước khi tạo block!
        for n, item in enumerate(self._items, start=1):
            item._display_number = n
 
        total_w = 20  # margins
        for i, item in enumerate(self._items):
            # TransitionNode trước mỗi clip (trừ clip đầu)
            if i > 0:
                node = TransitionNode(i - 1, item.transition_in)
                node.clicked.connect(self._on_transition_clicked)
                self._trans_nodes.append(node)
                self._inner_lay.addWidget(node)
                total_w += TRANS_W

            block = ClipBlock(item)
            block.clicked.connect(self._on_clip_clicked)
            block.removed.connect(self._on_clip_removed)
            self._clip_widgets[item.id] = block

            if item.id == self._selected_id:
                block.set_selected(True)

            self._inner_lay.addWidget(block)
            total_w += CLIP_W

        self._inner_lay.addStretch()
        self._inner.setMinimumWidth(max(420, total_w))

    def _on_clip_clicked(self, item_id: str):
        if self._selected_id and self._selected_id in self._clip_widgets:
            self._clip_widgets[self._selected_id].set_selected(False)
        self._selected_id = item_id
        if item_id in self._clip_widgets:
            self._clip_widgets[item_id].set_selected(True)
        self.clip_selected.emit(item_id)

    def _on_clip_removed(self, item_id: str):
        self.clip_removed.emit(item_id)

    def _on_transition_clicked(self, index: int):
        """Mở dialog chọn transition cho vị trí index (giữa items[index] và items[index+1])."""
        # Transition được lưu trong items[index+1].transition_in
        real_idx = index + 1
        if real_idx >= len(self._items):
            return
        item = self._items[real_idx]

        dlg = TransitionPickerDialog(item.transition_in, item.transition_dur, self)
        if dlg.exec():
            new_type, new_dur = dlg.get_result()
            item.transition_in  = new_type
            item.transition_dur = new_dur
            if index < len(self._trans_nodes):
                self._trans_nodes[index].update_type(new_type)
            self.transition_changed.emit(index, new_type, new_dur)
 
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-kath-media-id"):
            event.acceptProposedAction()
 
    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-kath-media-id"):
            event.acceptProposedAction()
 
    def dropEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat("application/x-kath-media-id"):
            item_id = mime.data("application/x-kath-media-id").data().decode("utf-8")
            
            src_idx = -1
            for idx, item in enumerate(self._items):
                if item.id == item_id:
                    src_idx = idx
                    break
            
            if src_idx != -1:
                # Tính target_idx dựa trên toạ độ X tại inner widget
                local_pos = self._inner.mapFromGlobal(QCursor.pos())
                drop_x = local_pos.x()
                
                target_idx = 0
                found = False
                for idx, item in enumerate(self._items):
                    block = self._clip_widgets.get(item.id)
                    if block:
                        center_x = block.x() + block.width() / 2
                        if drop_x < center_x:
                            target_idx = idx
                            found = True
                            break
                if not found:
                    target_idx = len(self._items)
                    
                if src_idx != target_idx:
                    item = self._items.pop(src_idx)
                    if target_idx > src_idx:
                        self._items.insert(target_idx - 1, item)
                    else:
                        self._items.insert(target_idx, item)
                    self._rebuild()
                    self.reordered.emit()
            event.acceptProposedAction()
