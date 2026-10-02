"""
pptx_builder.py — Trình tạo Slide phong cách Gemini / NotebookLM Bento Box Đỉnh Cao
Hỗ trợ:
1. 9 Kiểu Slide Layout chuyên sâu chuẩn PPTX hoàn chỉnh:
   - hero_cover: Bìa mở đầu / Tiêu đề lớn & Tổng quan chiến lược.
   - stat_metric: Card số liệu to nổi bật ($67B, 85%, 1.541 km) + thẻ phân tích số liệu.
   - three_columns: 3 Cột trụ chiến lược song song với icons SVG và chi tiết.
   - bento_grid_2x2: Ma trận 4 ô phân tích đa chiều (SWOT / 4 Trụ cột / 4 Nhóm giải pháp).
   - comparison_vs: So sánh đối lập (Thực trạng vs Giải pháp / Truyền thống vs Số hóa).
   - timeline_process: Lộ trình 4 giai đoạn với trục nối phát sáng gradient và node mốc.
   - visual_split: Slide có hình minh họa sơ đồ kỹ thuật vector SVG công nghệ cao + Thẻ phân tích.
   - key_takeaway_quote: Đúc kết chiến lược / Thông điệp cốt lõi với trích dẫn nổi bật.
   - asymmetric_bento: Bento bất đối xứng hiện đại.
2. 5 Bảng màu (Theme Palettes) luân chuyển sống động: Sapphire Cyan, Emerald, Quantum Violet, Amber, Ruby.
3. Thư viện SVG Vector Icons & Diagrams sắc nét tích hợp trực tiếp (không phụ thuộc kết nối mạng).
4. Render ảnh Slide 1080p (1920x1080) siêu nét qua Playwright Chromium Engine.
5. Xuất file PowerPoint .pptx chuẩn tương ứng cho Microsoft Office / Google Slides.
"""

from __future__ import annotations

import os
import sys
import tempfile
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

from PIL import Image, ImageDraw, ImageFont


# ═══════════════════════════════════════════════════════════════════════════
#  THEME PALETTES (5 Bảng màu đa dạng cho từng Slide)
# ═══════════════════════════════════════════════════════════════════════════

THEME_PALETTES = {
    "sapphire": {
        "name": "Sapphire Cyber",
        "bg": "#08101e",
        "bg_grad": "radial-gradient(circle at 85% 15%, #162a45 0%, #08101e 70%)",
        "card_bg": "rgba(16, 28, 48, 0.88)",
        "card_bg_alt": "rgba(20, 36, 61, 0.95)",
        "card_border": "rgba(56, 189, 248, 0.25)",
        "accent": "#38bdf8",
        "accent_sub": "#60a5fa",
        "accent_grad": "linear-gradient(135deg, #38bdf8 0%, #2563eb 100%)",
        "glow": "rgba(56, 189, 248, 0.35)",
        "badge_bg": "rgba(56, 189, 248, 0.15)",
        "badge_text": "#38bdf8",
        "text_white": "#ffffff",
        "text_body": "#cbd5e1",
        "text_muted": "#94a3b8",
        "pptx_bg": RGBColor(8, 16, 30),
        "pptx_card": RGBColor(16, 28, 48),
        "pptx_card_alt": RGBColor(20, 36, 61),
        "pptx_accent": RGBColor(56, 189, 248),
        "pptx_accent_sub": RGBColor(96, 165, 250),
    },
    "emerald": {
        "name": "Emerald Growth",
        "bg": "#051814",
        "bg_grad": "radial-gradient(circle at 85% 15%, #0e3b2e 0%, #051814 70%)",
        "card_bg": "rgba(13, 40, 32, 0.88)",
        "card_bg_alt": "rgba(19, 56, 45, 0.95)",
        "card_border": "rgba(16, 185, 129, 0.28)",
        "accent": "#10b981",
        "accent_sub": "#34d399",
        "accent_grad": "linear-gradient(135deg, #34d399 0%, #059669 100%)",
        "glow": "rgba(16, 185, 129, 0.35)",
        "badge_bg": "rgba(16, 185, 129, 0.15)",
        "badge_text": "#34d399",
        "text_white": "#ffffff",
        "text_body": "#cbd5e1",
        "text_muted": "#94a3b8",
        "pptx_bg": RGBColor(5, 24, 20),
        "pptx_card": RGBColor(13, 40, 32),
        "pptx_card_alt": RGBColor(19, 56, 45),
        "pptx_accent": RGBColor(16, 185, 129),
        "pptx_accent_sub": RGBColor(52, 211, 153),
    },
    "violet": {
        "name": "Quantum Violet",
        "bg": "#0c0a1f",
        "bg_grad": "radial-gradient(circle at 85% 15%, #241d52 0%, #0c0a1f 70%)",
        "card_bg": "rgba(23, 20, 51, 0.88)",
        "card_bg_alt": "rgba(32, 27, 71, 0.95)",
        "card_border": "rgba(168, 85, 247, 0.28)",
        "accent": "#a855f7",
        "accent_sub": "#c084fc",
        "accent_grad": "linear-gradient(135deg, #c084fc 0%, #7c3aed 100%)",
        "glow": "rgba(168, 85, 247, 0.35)",
        "badge_bg": "rgba(168, 85, 247, 0.15)",
        "badge_text": "#c084fc",
        "text_white": "#ffffff",
        "text_body": "#cbd5e1",
        "text_muted": "#94a3b8",
        "pptx_bg": RGBColor(12, 10, 31),
        "pptx_card": RGBColor(23, 20, 51),
        "pptx_card_alt": RGBColor(32, 27, 71),
        "pptx_accent": RGBColor(168, 85, 247),
        "pptx_accent_sub": RGBColor(192, 132, 252),
    },
    "amber": {
        "name": "Amber Energy",
        "bg": "#140f07",
        "bg_grad": "radial-gradient(circle at 85% 15%, #3d2a10 0%, #140f07 70%)",
        "card_bg": "rgba(36, 27, 16, 0.88)",
        "card_bg_alt": "rgba(51, 38, 22, 0.95)",
        "card_border": "rgba(245, 158, 11, 0.28)",
        "accent": "#f59e0b",
        "accent_sub": "#fbbf24",
        "accent_grad": "linear-gradient(135deg, #fbbf24 0%, #d97706 100%)",
        "glow": "rgba(245, 158, 11, 0.35)",
        "badge_bg": "rgba(245, 158, 11, 0.15)",
        "badge_text": "#fbbf24",
        "text_white": "#ffffff",
        "text_body": "#cbd5e1",
        "text_muted": "#94a3b8",
        "pptx_bg": RGBColor(20, 15, 7),
        "pptx_card": RGBColor(36, 27, 16),
        "pptx_card_alt": RGBColor(51, 38, 22),
        "pptx_accent": RGBColor(245, 158, 11),
        "pptx_accent_sub": RGBColor(251, 191, 36),
    },
    "ruby": {
        "name": "Ruby Focus",
        "bg": "#17090e",
        "bg_grad": "radial-gradient(circle at 85% 15%, #421625 0%, #17090e 70%)",
        "card_bg": "rgba(41, 18, 26, 0.88)",
        "card_bg_alt": "rgba(56, 25, 36, 0.95)",
        "card_border": "rgba(244, 63, 94, 0.28)",
        "accent": "#f43f5e",
        "accent_sub": "#fb7185",
        "accent_grad": "linear-gradient(135deg, #fb7185 0%, #e11d48 100%)",
        "glow": "rgba(244, 63, 94, 0.35)",
        "badge_bg": "rgba(244, 63, 94, 0.15)",
        "badge_text": "#fb7185",
        "text_white": "#ffffff",
        "text_body": "#cbd5e1",
        "text_muted": "#94a3b8",
        "pptx_bg": RGBColor(23, 9, 14),
        "pptx_card": RGBColor(41, 18, 26),
        "pptx_card_alt": RGBColor(56, 25, 36),
        "pptx_accent": RGBColor(244, 63, 94),
        "pptx_accent_sub": RGBColor(251, 113, 133),
    },
    "cyan": {
        "name": "Cyber Aqua",
        "bg": "#06131a",
        "bg_grad": "radial-gradient(circle at 85% 15%, #0c2b3b 0%, #06131a 70%)",
        "card_bg": "rgba(10, 35, 48, 0.88)",
        "card_bg_alt": "rgba(15, 48, 66, 0.95)",
        "card_border": "rgba(34, 211, 238, 0.28)",
        "accent": "#22d3ee",
        "accent_sub": "#67e8f9",
        "accent_grad": "linear-gradient(135deg, #22d3ee 0%, #0891b2 100%)",
        "glow": "rgba(34, 211, 238, 0.35)",
        "badge_bg": "rgba(34, 211, 238, 0.15)",
        "badge_text": "#22d3ee",
        "text_white": "#ffffff",
        "text_body": "#cbd5e1",
        "text_muted": "#94a3b8",
        "pptx_bg": RGBColor(6, 19, 26),
        "pptx_card": RGBColor(10, 35, 48),
        "pptx_card_alt": RGBColor(15, 48, 66),
        "pptx_accent": RGBColor(34, 211, 238),
        "pptx_accent_sub": RGBColor(103, 232, 249),
    },
    "sunset": {
        "name": "Neon Sunset",
        "bg": "#180c07",
        "bg_grad": "radial-gradient(circle at 85% 15%, #421d0f 0%, #180c07 70%)",
        "card_bg": "rgba(43, 22, 14, 0.88)",
        "card_bg_alt": "rgba(61, 31, 20, 0.95)",
        "card_border": "rgba(251, 146, 60, 0.28)",
        "accent": "#fb923c",
        "accent_sub": "#fdba74",
        "accent_grad": "linear-gradient(135deg, #fb923c 0%, #ea580c 100%)",
        "glow": "rgba(251, 146, 60, 0.35)",
        "badge_bg": "rgba(251, 146, 60, 0.15)",
        "badge_text": "#fb923c",
        "text_white": "#ffffff",
        "text_body": "#cbd5e1",
        "text_muted": "#94a3b8",
        "pptx_bg": RGBColor(24, 12, 7),
        "pptx_card": RGBColor(43, 22, 14),
        "pptx_card_alt": RGBColor(61, 31, 20),
        "pptx_accent": RGBColor(251, 146, 60),
        "pptx_accent_sub": RGBColor(253, 186, 116),
    },
}

THEME_ORDER = ["sapphire", "emerald", "violet", "amber", "ruby", "cyan", "sunset"]


# ═══════════════════════════════════════════════════════════════════════════
#  SVG ICONS & TECH ILLUSTRATIONS LIBRARY
# ═══════════════════════════════════════════════════════════════════════════

def get_svg_icon(icon_name: str, color: str = "#38bdf8", size: int = 24) -> str:
    """Trả về SVG icon vector chuẩn nét 24x24."""
    icons = {
        "target": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>',
        "cpu": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/></svg>',
        "shield": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>',
        "chart": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>',
        "train": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="3" width="16" height="16" rx="2"/><path d="M4 11h16M12 3v8M8 19l-3 3M16 19l3 3M8 15h.01M16 15h.01"/></svg>',
        "cloud": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/></svg>',
        "layers": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 2 10 5-10 5L2 7l10-5Z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/></svg>',
        "rocket": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/></svg>',
        "compass": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/></svg>',
        "zap": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
        "warning": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
        "check": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
        "award": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="7"/><polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"/></svg>',
        "database": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>',
        "gear": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
        "thumbs_up": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>',
        "bell": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>',
        "message": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
        "sparkles": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/></svg>',
        "heart": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/></svg>',
        "help": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
        "share": f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>',
    }
    return icons.get(icon_name, icons["target"])
    return icons.get(icon_name, icons["target"])


def resolve_illustration_type(scene_data: Dict[str, Any], slide_idx: int = 1) -> str:
    """Xác định loại hình minh họa/biểu đồ thông minh dựa vào từ khóa nội dung hoặc luân chuyển ngẫu nhiên chống trùng lặp."""
    req_ill = scene_data.get("illustration_type", "").strip()
    valid_ills = [
        "growth_chart", "donut_chart", "neural_ai", "cloud_architecture",
        "global_mesh", "strategy_target", "workflow_pipeline", "cyber_shield",
        "speed_gauge", "tech_matrix", "transit_network"
    ]
    if req_ill in valid_ills and req_ill != "transit_network":
        return req_ill
    
    # Phân tích nội dung văn bản để gán biểu đồ chính xác
    title = scene_data.get("slide_title", "")
    voiceover = scene_data.get("voiceover_text", "")
    bullets = " ".join(scene_data.get("bullet_points", []))
    all_text = f"{title} {voiceover} {bullets}".lower()

    if any(k in all_text for k in ["đường sắt", "tàu hỏa", "ga ", "tuyến đường sắt", "đoàn tàu", "cao tốc", "350 km/h"]):
        return "transit_network"
    elif any(k in all_text for k in ["tăng trưởng", "doanh thu", "doanh số", "lợi nhuận", "chi phí", "tỉ lệ", "tăng ", "%", "kpi", "thị phần", "quy mô", "tài chính"]):
        return "growth_chart"
    elif any(k in all_text for k in ["cơ cấu", "tỉ trọng", "phần trăm", "tỉ lệ %", "donut", "phân bổ", "chiếm", "cơ cấu"]):
        return "donut_chart"
    elif any(k in all_text for k in ["ai", "trí tuệ nhân tạo", "mô hình ngôn ngữ", "llm", "thuật toán", "machine learning", "tự động hóa", "robot", "thông minh"]):
        return "neural_ai"
    elif any(k in all_text for k in ["bảo mật", "an toàn", "rủi ro", "phòng chống", "shield", "chứng chỉ", "tiêu chuẩn", "sil 4", "bảo vệ"]):
        return "cyber_shield"
    elif any(k in all_text for k in ["cloud", "hạ tầng", "máy chủ", "kiến trúc", "hệ thống", "microservice", "database", "api", "mạng", "phần mềm", "nền tảng"]):
        return "cloud_architecture"
    elif any(k in all_text for k in ["chiến lược", "mục tiêu", "tầm nhìn", "định hướng", "radar", "trọng tâm", "kế hoạch", "bứt phá"]):
        return "strategy_target"
    elif any(k in all_text for k in ["toàn cầu", "thế giới", "quốc tế", "kết nối", "mạng lưới", "vệ tinh", "phủ sóng", "hệ sinh thái"]):
        return "global_mesh"
    elif any(k in all_text for k in ["lộ trình", "quy trình", "giai đoạn", "pipeline", "bước", "triển khai", "funnel", "các bước"]):
        return "workflow_pipeline"
    elif any(k in all_text for k in ["tốc độ", "hiệu năng", "hiệu suất", "tối ưu", "xử lý", "băng thông", "đo lường"]):
        return "speed_gauge"
    else:
        # Luân chuyển luân phiên đa dạng theo slide_idx để KHÔNG BAO GIỜ bị trùng lặp
        pool = ["growth_chart", "donut_chart", "neural_ai", "cloud_architecture", "global_mesh", "strategy_target", "tech_matrix", "speed_gauge", "cyber_shield", "workflow_pipeline"]
        return pool[(slide_idx - 1) % len(pool)]


def get_tech_illustration_svg(ill_type: str, accent: str = "#38bdf8", accent_sub: str = "#60a5fa") -> str:
    """Tạo sơ đồ kỹ thuật / biểu đồ SVG vector siêu nét 1080p đa dạng theo chủ đề."""
    # 1. Biểu đồ cột tăng trưởng (Growth Bar Chart)
    if ill_type == "growth_chart":
        return f"""
        <svg viewBox="0 0 520 340" width="100%" height="100%" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <linearGradient id="bar_grad_1" x1="0%" y1="100%" x2="0%" y2="0%">
                    <stop offset="0%" stop-color="{accent}" stop-opacity="0.2"/>
                    <stop offset="100%" stop-color="{accent}"/>
                </linearGradient>
                <linearGradient id="bar_grad_2" x1="0%" y1="100%" x2="0%" y2="0%">
                    <stop offset="0%" stop-color="{accent_sub}" stop-opacity="0.2"/>
                    <stop offset="100%" stop-color="{accent_sub}"/>
                </linearGradient>
                <filter id="glow_chart" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="5" result="blur"/>
                    <feComposite in="SourceGraphic" in2="blur" operator="over"/>
                </filter>
            </defs>
            <!-- Lưới nền -->
            <line x1="60" y1="260" x2="480" y2="260" stroke="#ffffff" stroke-opacity="0.1" stroke-width="1.5"/>
            <line x1="60" y1="200" x2="480" y2="200" stroke="#ffffff" stroke-opacity="0.08" stroke-dasharray="4 4"/>
            <line x1="60" y1="140" x2="480" y2="140" stroke="#ffffff" stroke-opacity="0.08" stroke-dasharray="4 4"/>
            <line x1="60" y1="80" x2="480" y2="80" stroke="#ffffff" stroke-opacity="0.08" stroke-dasharray="4 4"/>
            <!-- Các cột biểu đồ -->
            <rect x="90" y="190" width="48" height="70" rx="8" fill="url(#bar_grad_1)"/>
            <text x="114" y="175" fill="#94a3b8" font-size="12" font-weight="700" text-anchor="middle">2023</text>
            <rect x="170" y="150" width="48" height="110" rx="8" fill="url(#bar_grad_1)"/>
            <text x="194" y="135" fill="#94a3b8" font-size="12" font-weight="700" text-anchor="middle">2024</text>
            <rect x="250" y="110" width="48" height="150" rx="8" fill="url(#bar_grad_1)"/>
            <text x="274" y="95" fill="{accent}" font-size="12" font-weight="800" text-anchor="middle">+45%</text>
            <rect x="330" y="70" width="48" height="190" rx="8" fill="url(#bar_grad_2)" filter="url(#glow_chart)"/>
            <text x="354" y="55" fill="#ffffff" font-size="13" font-weight="900" text-anchor="middle">+88%</text>
            <rect x="410" y="40" width="48" height="220" rx="8" fill="{accent}" filter="url(#glow_chart)"/>
            <text x="434" y="25" fill="{accent}" font-size="14" font-weight="900" text-anchor="middle">+142%</text>
            <!-- Đường xu hướng Gradient Line -->
            <path d="M 114 185 Q 194 140, 274 105 T 434 35" stroke="#ffffff" stroke-width="3" stroke-linecap="round" fill="none" filter="url(#glow_chart)"/>
            <circle cx="434" cy="35" r="5" fill="#ffffff"/>
            <!-- Nhãn trục hoành -->
            <text x="270" y="300" fill="{accent}" font-size="13" font-weight="800" text-anchor="middle" letter-spacing="1">TĂNG TRƯỞNG QUY MÔ & HIỆU SUẤT ĐỘT PHÁ</text>
        </svg>
        """

    # 2. Biểu đồ tròn phân tích cơ cấu (Donut Analytics Chart)
    elif ill_type == "donut_chart":
        return f"""
        <svg viewBox="0 0 520 340" width="100%" height="100%" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <filter id="glow_donut" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="6" result="blur"/>
                    <feComposite in="SourceGraphic" in2="blur" operator="over"/>
                </filter>
            </defs>
            <circle cx="210" cy="170" r="100" stroke="rgba(255,255,255,0.06)" stroke-width="26"/>
            <!-- Segment 1 -->
            <circle cx="210" cy="170" r="100" stroke="{accent}" stroke-width="26" stroke-dasharray="314 314" stroke-dashoffset="60" stroke-linecap="round" filter="url(#glow_donut)"/>
            <!-- Segment 2 -->
            <circle cx="210" cy="170" r="100" stroke="{accent_sub}" stroke-width="26" stroke-dasharray="180 448" stroke-dashoffset="-260" stroke-linecap="round"/>
            <!-- Center Label -->
            <circle cx="210" cy="170" r="70" fill="rgba(15, 23, 42, 0.9)"/>
            <text x="210" y="165" fill="#ffffff" font-size="28" font-weight="900" text-anchor="middle">85.4%</text>
            <text x="210" y="188" fill="{accent}" font-size="11" font-weight="800" text-anchor="middle">TỐI ƯU CỐT LÕI</text>
            <!-- Legend Items bên phải -->
            <rect x="360" y="90" width="14" height="14" rx="4" fill="{accent}"/>
            <text x="385" y="102" fill="#ffffff" font-size="13" font-weight="700">Hạ tầng số: 55%</text>
            <rect x="360" y="135" width="14" height="14" rx="4" fill="{accent_sub}"/>
            <text x="385" y="147" fill="#cbd5e1" font-size="13" font-weight="600">Vận hành OCC: 30%</text>
            <rect x="360" y="180" width="14" height="14" rx="4" fill="#64748b"/>
            <text x="385" y="192" fill="#94a3b8" font-size="13" font-weight="600">Dự phòng: 15%</text>
            <rect x="350" y="225" width="150" height="34" rx="8" fill="rgba(56, 189, 248, 0.12)" stroke="{accent}" stroke-opacity="0.3"/>
            <text x="425" y="247" fill="{accent}" font-size="11" font-weight="800" text-anchor="middle">CHUẨN ĐỘT PHÁ</text>
        </svg>
        """

    # 3. Mạng lưới nơ-ron AI & Trí tuệ nhân tạo (Neural AI Lattice)
    elif ill_type == "neural_ai":
        return f"""
        <svg viewBox="0 0 520 340" width="100%" height="100%" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <filter id="glow_ai_net" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="6" result="blur"/>
                    <feComposite in="SourceGraphic" in2="blur" operator="over"/>
                </filter>
            </defs>
            <circle cx="260" cy="170" r="125" stroke="{accent}" stroke-opacity="0.12" stroke-width="1.5"/>
            <circle cx="260" cy="170" r="85" stroke="{accent_sub}" stroke-opacity="0.2" stroke-width="1.5" stroke-dasharray="4 4"/>
            <!-- Các đường liên kết synapse -->
            <line x1="260" y1="170" x2="130" y2="80" stroke="{accent}" stroke-width="2" stroke-opacity="0.6"/>
            <line x1="260" y1="170" x2="390" y2="80" stroke="{accent}" stroke-width="2" stroke-opacity="0.6"/>
            <line x1="260" y1="170" x2="110" y2="240" stroke="{accent}" stroke-width="2" stroke-opacity="0.6"/>
            <line x1="260" y1="170" x2="410" y2="240" stroke="{accent}" stroke-width="2" stroke-opacity="0.6"/>
            <line x1="260" y1="170" x2="260" y2="40" stroke="{accent_sub}" stroke-width="2" stroke-opacity="0.6"/>
            <line x1="130" y1="80" x2="260" y2="40" stroke="{accent_sub}" stroke-width="1.5" stroke-opacity="0.4"/>
            <line x1="390" y1="80" x2="260" y2="40" stroke="{accent_sub}" stroke-width="1.5" stroke-opacity="0.4"/>
            <line x1="110" y1="240" x2="260" y2="300" stroke="{accent_sub}" stroke-width="1.5" stroke-opacity="0.4"/>
            <line x1="410" y1="240" x2="260" y2="300" stroke="{accent_sub}" stroke-width="1.5" stroke-opacity="0.4"/>
            <!-- Trung tâm AI Core -->
            <circle cx="260" cy="170" r="28" fill="{accent}" filter="url(#glow_ai_net)"/>
            <circle cx="260" cy="170" r="12" fill="#ffffff"/>
            <!-- Các node ngoại vi -->
            <circle cx="130" cy="80" r="14" fill="{accent_sub}" filter="url(#glow_ai_net)"/>
            <text x="130" y="52" fill="#cbd5e1" font-size="12" font-weight="700" text-anchor="middle">Cảm Biến Realtime</text>
            <circle cx="390" cy="80" r="14" fill="{accent_sub}" filter="url(#glow_ai_net)"/>
            <text x="390" y="52" fill="#cbd5e1" font-size="12" font-weight="700" text-anchor="middle">Mô Hình Dự Báo</text>
            <circle cx="110" cy="240" r="14" fill="{accent_sub}" filter="url(#glow_ai_net)"/>
            <text x="110" y="272" fill="#cbd5e1" font-size="12" font-weight="700" text-anchor="middle">Tự Động Hóa Lõi</text>
            <circle cx="410" cy="240" r="14" fill="{accent_sub}" filter="url(#glow_ai_net)"/>
            <text x="410" y="272" fill="#cbd5e1" font-size="12" font-weight="700" text-anchor="middle">Học Sâu & Tối Ưu</text>
            <circle cx="260" cy="40" r="10" fill="{accent}"/>
            <circle cx="260" cy="300" r="12" fill="{accent}" filter="url(#glow_ai_net)"/>
            <text x="260" y="328" fill="{accent}" font-size="12" font-weight="800" text-anchor="middle">MẠNG TRÍ TUỆ NHÂN TẠO ĐA TẦNG</text>
        </svg>
        """

    # 4. Kiến trúc hạ tầng Cloud & Microservices (Cloud Architecture)
    elif ill_type == "cloud_architecture":
        return f"""
        <svg viewBox="0 0 520 340" width="100%" height="100%" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <filter id="glow_cloud_arch" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="5" result="blur"/>
                    <feComposite in="SourceGraphic" in2="blur" operator="over"/>
                </filter>
            </defs>
            <!-- Layer 1: API Gateway -->
            <rect x="60" y="45" width="400" height="60" rx="14" fill="rgba(30, 41, 59, 0.85)" stroke="{accent}" stroke-width="1.5" filter="url(#glow_cloud_arch)"/>
            <circle cx="95" cy="75" r="10" fill="{accent}"/>
            <text x="120" y="72" fill="#ffffff" font-size="14" font-weight="800">Tầng 1: API Gateway & Edge Ingress Routing</text>
            <text x="120" y="90" fill="{accent}" font-size="11" font-weight="700">ĐỘ TRỄ CỰC THẤP &lt; 5ms  •  BĂNG THÔNG CAO</text>
            <!-- Connecting Arrows -->
            <line x1="260" y1="105" x2="260" y2="135" stroke="{accent}" stroke-width="2" stroke-dasharray="4 4"/>
            <!-- Layer 2: Microservices Cluster -->
            <rect x="60" y="135" width="400" height="65" rx="14" fill="rgba(30, 41, 59, 0.85)" stroke="{accent_sub}" stroke-width="1.5"/>
            <circle cx="95" cy="167" r="10" fill="{accent_sub}"/>
            <text x="120" y="162" fill="#ffffff" font-size="14" font-weight="800">Tầng 2: Cụm Dịch Vụ Phân Tán (Microservices)</text>
            <text x="120" y="182" fill="#cbd5e1" font-size="11" font-weight="600">KUBERNETES AUTO-SCALE  •  EVENT STREAM KAFKA</text>
            <!-- Connecting Arrows -->
            <line x1="260" y1="200" x2="260" y2="230" stroke="{accent_sub}" stroke-width="2" stroke-dasharray="4 4"/>
            <!-- Layer 3: High-Availability Database -->
            <rect x="60" y="230" width="400" height="65" rx="14" fill="rgba(30, 41, 59, 0.85)" stroke="{accent}" stroke-width="1.5" filter="url(#glow_cloud_arch)"/>
            <circle cx="95" cy="262" r="10" fill="#10b981"/>
            <text x="120" y="257" fill="#ffffff" font-size="14" font-weight="800">Tầng 3: Cơ Sở Dữ Liệu & Data Lakehouse Đa Vùng</text>
            <text x="120" y="277" fill="#10b981" font-size="11" font-weight="700">SẴN SÀNG 99.999%  •  MÃ HÓA ĐẦU CUỐI ZERO TRUST</text>
        </svg>
        """

    # 5. Mạng lưới kết nối toàn cầu (Global Connectivity Mesh)
    elif ill_type == "global_mesh":
        return f"""
        <svg viewBox="0 0 520 340" width="100%" height="100%" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <filter id="glow_mesh" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="6" result="blur"/>
                    <feComposite in="SourceGraphic" in2="blur" operator="over"/>
                </filter>
            </defs>
            <ellipse cx="260" cy="170" rx="150" ry="95" stroke="{accent}" stroke-opacity="0.2" stroke-width="1.5"/>
            <ellipse cx="260" cy="170" rx="150" ry="40" stroke="{accent_sub}" stroke-opacity="0.3" stroke-width="1.5" stroke-dasharray="4 4"/>
            <line x1="260" y1="65" x2="260" y2="275" stroke="{accent}" stroke-opacity="0.2" stroke-width="1.5"/>
            <line x1="110" y1="170" x2="410" y2="170" stroke="{accent}" stroke-opacity="0.2" stroke-width="1.5"/>
            <!-- Nodes -->
            <circle cx="260" cy="170" r="22" fill="{accent}" filter="url(#glow_mesh)"/>
            <circle cx="260" cy="170" r="10" fill="#ffffff"/>
            <circle cx="160" cy="130" r="10" fill="{accent_sub}" filter="url(#glow_mesh)"/>
            <circle cx="360" cy="130" r="10" fill="{accent_sub}" filter="url(#glow_mesh)"/>
            <circle cx="180" cy="220" r="10" fill="{accent_sub}" filter="url(#glow_mesh)"/>
            <circle cx="340" cy="220" r="10" fill="{accent_sub}" filter="url(#glow_mesh)"/>
            <!-- Arcs -->
            <path d="M 160 130 Q 260 100, 360 130" stroke="{accent}" stroke-width="2.5" fill="none" filter="url(#glow_mesh)"/>
            <path d="M 180 220 Q 260 250, 340 220" stroke="{accent_sub}" stroke-width="2.5" fill="none"/>
            <text x="260" y="315" fill="{accent}" font-size="13" font-weight="800" text-anchor="middle">MẠNG LƯỚI KẾT NỐI TOÀN CẦU & VỆ TINH SỐ</text>
        </svg>
        """

    # 6. La bàn mục tiêu chiến lược & Radar (Strategy Target)
    elif ill_type == "strategy_target":
        return f"""
        <svg viewBox="0 0 520 340" width="100%" height="100%" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <filter id="glow_target" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="6" result="blur"/>
                    <feComposite in="SourceGraphic" in2="blur" operator="over"/>
                </filter>
            </defs>
            <circle cx="260" cy="165" r="120" stroke="{accent}" stroke-opacity="0.15" stroke-width="1.5"/>
            <circle cx="260" cy="165" r="85" stroke="{accent_sub}" stroke-opacity="0.25" stroke-width="1.5" stroke-dasharray="6 6"/>
            <circle cx="260" cy="165" r="50" stroke="{accent}" stroke-opacity="0.4" stroke-width="2"/>
            <circle cx="260" cy="165" r="18" fill="{accent}" filter="url(#glow_target)"/>
            <circle cx="260" cy="165" r="8" fill="#ffffff"/>
            <!-- Crosshairs -->
            <line x1="260" y1="30" x2="260" y2="300" stroke="{accent}" stroke-opacity="0.3" stroke-width="1.5"/>
            <line x1="125" y1="165" x2="395" y2="165" stroke="{accent}" stroke-opacity="0.3" stroke-width="1.5"/>
            <!-- Target Callouts -->
            <circle cx="320" cy="115" r="8" fill="{accent_sub}" filter="url(#glow_target)"/>
            <text x="335" y="112" fill="#ffffff" font-size="12" font-weight="700">Mục Tiêu Q4</text>
            <circle cx="200" cy="215" r="8" fill="{accent_sub}" filter="url(#glow_target)"/>
            <text x="185" y="235" fill="#cbd5e1" font-size="12" font-weight="700" text-anchor="end">Trọng Tâm 2026</text>
            <text x="260" y="325" fill="{accent}" font-size="13" font-weight="800" text-anchor="middle">ĐỊNH VỊ CHIẾN LƯỢC & TẦM NHÌN DẪN ĐẦU</text>
        </svg>
        """

    # 7. Sơ đồ quy trình 4 bước (Workflow Pipeline)
    elif ill_type == "workflow_pipeline":
        return f"""
        <svg viewBox="0 0 520 340" width="100%" height="100%" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <filter id="glow_pipe" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="5" result="blur"/>
                    <feComposite in="SourceGraphic" in2="blur" operator="over"/>
                </filter>
            </defs>
            <line x1="80" y1="150" x2="440" y2="150" stroke="{accent}" stroke-width="4" stroke-opacity="0.4"/>
            <!-- Stage 1 -->
            <circle cx="100" cy="150" r="24" fill="rgba(30,41,59,0.9)" stroke="{accent}" stroke-width="2.5" filter="url(#glow_pipe)"/>
            <text x="100" y="156" fill="#ffffff" font-size="14" font-weight="900" text-anchor="middle">01</text>
            <text x="100" y="200" fill="#cbd5e1" font-size="12" font-weight="700" text-anchor="middle">Khảo Sát</text>
            <!-- Stage 2 -->
            <circle cx="205" cy="150" r="24" fill="rgba(30,41,59,0.9)" stroke="{accent}" stroke-width="2.5" filter="url(#glow_pipe)"/>
            <text x="205" y="156" fill="#ffffff" font-size="14" font-weight="900" text-anchor="middle">02</text>
            <text x="205" y="200" fill="#cbd5e1" font-size="12" font-weight="700" text-anchor="middle">Thiết Kế</text>
            <!-- Stage 3 -->
            <circle cx="310" cy="150" r="24" fill="rgba(30,41,59,0.9)" stroke="{accent_sub}" stroke-width="2.5" filter="url(#glow_pipe)"/>
            <text x="310" y="156" fill="#ffffff" font-size="14" font-weight="900" text-anchor="middle">03</text>
            <text x="310" y="200" fill="{accent}" font-size="12" font-weight="800" text-anchor="middle">Triển Khai</text>
            <!-- Stage 4 -->
            <circle cx="415" cy="150" r="28" fill="{accent}" filter="url(#glow_pipe)"/>
            <text x="415" y="156" fill="#0f172a" font-size="15" font-weight="900" text-anchor="middle">04</text>
            <text x="415" y="205" fill="#ffffff" font-size="13" font-weight="800" text-anchor="middle">Bứt Phá</text>
            <text x="260" y="280" fill="{accent}" font-size="13" font-weight="800" text-anchor="middle">QUY TRÌNH THỰC THI CHUẨN HOÁ LIÊN TỤC</text>
        </svg>
        """

    # 8. Khiên bảo mật an toàn (Cyber Security Shield)
    elif ill_type == "cyber_shield":
        return f"""
        <svg viewBox="0 0 520 340" width="100%" height="100%" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <filter id="glow_shield_v2" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="6" result="blur"/>
                    <feComposite in="SourceGraphic" in2="blur" operator="over"/>
                </filter>
            </defs>
            <circle cx="260" cy="165" r="130" stroke="{accent}" stroke-opacity="0.12" stroke-width="2"/>
            <circle cx="260" cy="165" r="105" stroke="{accent}" stroke-opacity="0.2" stroke-width="1.5" stroke-dasharray="6 6"/>
            <path d="M260 50 L350 95 V180 C350 245 260 280 260 280 C260 280 170 245 170 180 V95 Z" fill="rgba(16, 28, 48, 0.9)" stroke="{accent}" stroke-width="3.5" filter="url(#glow_shield_v2)"/>
            <path d="M260 75 L330 110 V175 C330 225 260 255 260 255 C260 255 190 225 190 175 V110 Z" fill="{accent}" fill-opacity="0.18" stroke="{accent_sub}" stroke-width="1.5"/>
            <path d="M232 165 L255 188 L295 145" stroke="#ffffff" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round" filter="url(#glow_shield_v2)"/>
            <text x="260" y="315" fill="{accent}" font-size="13" font-weight="800" text-anchor="middle">TIÊU CHUẨN AN TOÀN TUYỆT ĐỐI (99.999%)</text>
        </svg>
        """

    # 9. Đồng hồ đo tốc độ & Hiệu năng cao (Speed & Performance Gauge)
    elif ill_type == "speed_gauge":
        return f"""
        <svg viewBox="0 0 520 340" width="100%" height="100%" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <filter id="glow_gauge" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="6" result="blur"/>
                    <feComposite in="SourceGraphic" in2="blur" operator="over"/>
                </filter>
            </defs>
            <path d="M 120 230 A 150 150 0 1 1 400 230" stroke="rgba(255,255,255,0.08)" stroke-width="26" stroke-linecap="round"/>
            <path d="M 120 230 A 150 150 0 1 1 350 110" stroke="{accent}" stroke-width="26" stroke-linecap="round" filter="url(#glow_gauge)"/>
            <line x1="260" y1="210" x2="330" y2="130" stroke="#ffffff" stroke-width="4" stroke-linecap="round" filter="url(#glow_gauge)"/>
            <circle cx="260" cy="210" r="16" fill="{accent}"/>
            <circle cx="260" cy="210" r="8" fill="#ffffff"/>
            <text x="260" y="160" fill="#ffffff" font-size="34" font-weight="900" text-anchor="middle">98.8%</text>
            <text x="260" y="185" fill="{accent}" font-size="12" font-weight="800" text-anchor="middle">HIỆU SUẤT XỬ LÝ</text>
            <text x="260" y="290" fill="#94a3b8" font-size="13" font-weight="700" text-anchor="middle">TỐC ĐỘ PHẢN HỒI THỜI GIAN THỰC ĐỈNH CAO</text>
        </svg>
        """

    # 10. Đường sắt cao tốc (Transit Network - Chỉ dùng khi chủ đề về đường sắt)
    elif ill_type == "transit_network":
        return f"""
        <svg viewBox="0 0 520 340" width="100%" height="100%" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <linearGradient id="grad_track_v2" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stop-color="{accent}" stop-opacity="0.15"/>
                    <stop offset="50%" stop-color="{accent}" stop-opacity="0.9"/>
                    <stop offset="100%" stop-color="{accent_sub}" stop-opacity="0.15"/>
                </linearGradient>
                <linearGradient id="grad_train_v2" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="{accent}"/>
                    <stop offset="100%" stop-color="{accent_sub}"/>
                </linearGradient>
                <filter id="glow_transit_v2" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="6" result="blur"/>
                    <feComposite in="SourceGraphic" in2="blur" operator="over"/>
                </filter>
            </defs>
            <path d="M30 240 C 160 210, 260 140, 490 80" stroke="url(#grad_track_v2)" stroke-width="6" filter="url(#glow_transit_v2)"/>
            <path d="M30 260 C 160 230, 260 160, 490 100" stroke="url(#grad_track_v2)" stroke-width="2" stroke-dasharray="6 6"/>
            <circle cx="100" cy="225" r="8" fill="{accent}" filter="url(#glow_transit_v2)"/>
            <text x="100" y="265" fill="#cbd5e1" font-size="12" font-weight="600" text-anchor="middle">Ga Khởi Hành</text>
            <circle cx="260" cy="155" r="10" fill="{accent_sub}" filter="url(#glow_transit_v2)"/>
            <text x="260" y="195" fill="#ffffff" font-size="13" font-weight="700" text-anchor="middle">Trung Tâm OCC</text>
            <circle cx="430" cy="95" r="8" fill="{accent}" filter="url(#glow_transit_v2)"/>
            <text x="430" y="135" fill="#cbd5e1" font-size="12" font-weight="600" text-anchor="middle">Ga Đến</text>
            <path d="M 290 135 L 390 105 C 405 100, 415 100, 405 112 L 325 145 Z" fill="url(#grad_train_v2)" filter="url(#glow_transit_v2)"/>
            <circle cx="395" cy="106" r="3" fill="#ffffff"/>
            <text x="350" y="90" fill="{accent}" font-size="12" font-weight="800">350 km/h</text>
            <text x="260" y="310" fill="{accent}" font-size="13" font-weight="800" text-anchor="middle">HỆ THỐNG ĐIỀU HÀNH & TÍN HIỆU ĐƯỜNG SẮT CAO TỐC</text>
        </svg>
        """

    # 11. Ma trận công nghệ số (Tech Matrix Hub)
    else:
        return f"""
        <svg viewBox="0 0 520 340" width="100%" height="100%" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <filter id="glow_matrix" x="-20%" y="-20%" width="140%" height="140%">
                    <feGaussianBlur stdDeviation="5" result="blur"/>
                    <feComposite in="SourceGraphic" in2="blur" operator="over"/>
                </filter>
            </defs>
            <rect x="50" y="40" width="420" height="250" rx="20" fill="rgba(15, 23, 42, 0.7)" stroke="{accent}" stroke-opacity="0.3" stroke-width="1.5"/>
            <!-- 4 Grid Cells -->
            <rect x="75" y="65" width="170" height="95" rx="12" fill="rgba(30, 41, 59, 0.7)" stroke="{accent}" stroke-opacity="0.4" stroke-width="1"/>
            <circle cx="100" cy="90" r="7" fill="{accent}" filter="url(#glow_matrix)"/>
            <text x="115" y="94" fill="#ffffff" font-size="13" font-weight="800">Khối Dữ Liệu</text>
            <text x="88" y="125" fill="#94a3b8" font-size="11" font-weight="600">Đồng bộ đa điểm</text>

            <rect x="275" y="65" width="170" height="95" rx="12" fill="rgba(30, 41, 59, 0.7)" stroke="{accent_sub}" stroke-opacity="0.4" stroke-width="1"/>
            <circle cx="300" cy="90" r="7" fill="{accent_sub}" filter="url(#glow_matrix)"/>
            <text x="315" y="94" fill="#ffffff" font-size="13" font-weight="800">Lõi Xử Lý</text>
            <text x="288" y="125" fill="#94a3b8" font-size="11" font-weight="600">Điện toán song song</text>

            <rect x="75" y="175" width="170" height="95" rx="12" fill="rgba(30, 41, 59, 0.7)" stroke="{accent_sub}" stroke-opacity="0.4" stroke-width="1"/>
            <circle cx="100" cy="200" r="7" fill="#10b981" filter="url(#glow_matrix)"/>
            <text x="115" y="204" fill="#ffffff" font-size="13" font-weight="800">Bảo Mật Kép</text>
            <text x="88" y="235" fill="#94a3b8" font-size="11" font-weight="600">Xác thực Zero Trust</text>

            <rect x="275" y="175" width="170" height="95" rx="12" fill="rgba(30, 41, 59, 0.7)" stroke="{accent}" stroke-opacity="0.4" stroke-width="1"/>
            <circle cx="300" cy="200" r="7" fill="{accent}" filter="url(#glow_matrix)"/>
            <text x="315" y="204" fill="#ffffff" font-size="13" font-weight="800">Tối Ưu Realtime</text>
            <text x="288" y="235" fill="#94a3b8" font-size="11" font-weight="600">Độ trễ mili-giây</text>
        </svg>
        """


def _extract_metric(text: str) -> Optional[Tuple[str, str]]:
    """Trích xuất số liệu to (ví dụ: '$67B', '1.541 km', '85%', '10x', '350 km/h') và nhãn đi kèm."""
    patterns = [
        r'(\$[\d\.,]+[BMKbmk]?)',
        r'([\d\.,]+%)',
        r'([\d\.,]+\s*(?:km\/h|km|triệu|tỷ|nghìn|USD|VNĐ|GB|TB|x|X|giây|phút))',
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            val = m.group(1).strip()
            lbl = text.replace(val, "").strip(" -:–,")
            if not lbl:
                lbl = "Chỉ số trọng tâm"
            elif len(lbl) > 50:
                lbl = lbl[:47] + "..."
            return val, lbl
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  HTML BENTO SLIDE GENERATOR (Chuẩn Pixel-Perfect 1920x1080)
# ═══════════════════════════════════════════════════════════════════════════

def generate_slide_html(scene_data: Dict[str, Any], slide_idx: int = 1, total_slides: int = 10) -> str:
    """Tạo HTML5/CSS3 Bento Box Slide 1920x1080 đa phong cách chuẩn NotebookLM & Gemini Executive."""
    title = scene_data.get("slide_title", f"Phân Cảnh {slide_idx}")
    clean_title = title.replace("|", "").strip()
    voiceover = scene_data.get("voiceover_text", "")
    bullets = scene_data.get("bullet_points", [])
    if not bullets and voiceover:
        bullets = [voiceover]

    # Chọn Theme Palette đa dạng luân chuyển (7 Theme Palettes)
    theme_key = scene_data.get("theme_color", "")
    if not theme_key or theme_key not in THEME_PALETTES:
        theme_key = THEME_ORDER[(slide_idx - 1) % len(THEME_ORDER)]
    th = THEME_PALETTES[theme_key]

    valid_layouts = {
        "hero_cover", "three_columns", "visual_split", "stat_metric",
        "bento_grid_2x2", "comparison_vs", "timeline_process", "key_takeaway_quote", "ending_outro"
    }

    # Xác định Layout Archetype thông minh & chuẩn xác
    layout_type = scene_data.get("layout_type", "")
    if layout_type not in valid_layouts or layout_type in ["", "standard", "bento", "custom"]:
        clean_lower = clean_title.lower()
        all_text = (clean_title + " " + voiceover + " " + " ".join(bullets)).lower()

        # 1. Slide đầu tiên -> Hero Cover
        if slide_idx == 1:
            layout_type = "hero_cover"
        # 2. Slide cuối cùng -> Ending Outro
        elif slide_idx == total_slides and total_slides >= 2:
            layout_type = "ending_outro"
        # 3. Đúc kết / Kết luận -> Key Takeaway Quote
        elif any(k in clean_lower for k in ["đúc kết", "tầm nhìn", "kết luận", "tổng kết", "thông điệp"]):
            layout_type = "key_takeaway_quote"
        # 3. So sánh đối lập -> Comparison VS
        elif any(k in clean_lower for k in ["so sánh", " vs ", "thực trạng vs", "đối lập", "trước và sau"]):
            layout_type = "comparison_vs"
        # 4. Lộ trình thời gian -> Timeline Process
        elif any(re.search(p, all_text) for p in [r'\b20\d\d\b', r'giai đoạn', r'lộ trình', r'roadmap', r'tiến độ', r'bước \d']):
            layout_type = "timeline_process"
        # 5. Số liệu lớn -> Stat Metric
        elif _extract_metric(clean_title) or any(_extract_metric(b) for b in bullets):
            layout_type = "stat_metric"
        # 6. Kiến trúc / Sơ đồ / OCC -> Visual Split
        elif any(w in clean_lower for w in ["kiến trúc", "sơ đồ", "occ", "mô hình", "diagram", "onboard", "trackside", "điều hành"]):
            layout_type = "visual_split"
        # 7. Có 3 trụ cột / 3 điểm chính -> Three Columns
        elif any(w in clean_lower for w in ["3 trụ cột", "ba trụ cột", "3 cột trụ", "3 giải pháp", "3 nhóm", "3 định hướng"]) or len(bullets) == 3:
            layout_type = "three_columns"
        # 8. Có 4 điểm -> Bento Grid 2x2
        elif len(bullets) >= 4:
            layout_type = "bento_grid_2x2"
        # 9. Fallback luân chuyển đa dạng chống trùng lặp
        else:
            cycle = ["three_columns", "visual_split", "bento_grid_2x2", "stat_metric", "timeline_process", "comparison_vs"]
            layout_type = cycle[(slide_idx - 1) % len(cycle)]

    body_content = ""

    # 1. HERO COVER (Slide Bìa Mở Đầu Chuyên Nghiệp)
    if layout_type == "hero_cover":
        tag_badge = scene_data.get("category_tag", "🌟 BÁO CÁO PHÂN TÍCH CHUYÊN SÂU")
        if not tag_badge.startswith("🌟") and not tag_badge.startswith("✦") and not tag_badge.startswith("🎬"):
            tag_badge = f"🌟 {tag_badge}"

        # Lấy subtitle ngắn gọn từ bullets[0] hoặc summary (không lấy cả đoạn thuyết minh dài)
        short_sub = ""
        if bullets:
            first_b = bullets[0]
            if ":" in first_b:
                short_sub = first_b.split(":", 1)[-1].strip()
            else:
                short_sub = first_b.strip()
            if len(short_sub) > 140:
                short_sub = short_sub[:137] + "..."
        if not short_sub:
            short_sub = "Bản trình bày phân tích dữ liệu chuyên sâu & tổng hợp bức tranh chiến lược toàn cảnh."

        img_path = scene_data.get("image_path") or scene_data.get("media_path")
        has_real_img = img_path and os.path.exists(img_path) and img_path.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))

        if has_real_img:
            # Nếu đã có ảnh AI thật -> Nhúng ảnh AI thật vào bên phải
            import base64
            with open(img_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")
            ext = Path(img_path).suffix.lstrip(".").lower()
            mime = "image/png" if ext == "png" else "image/jpeg"
            img_src = f"data:{mime};base64,{img_b64}"

            body_content = f"""
            <div class="hero-cover-container">
                <div class="hero-left-pane">
                    <div class="hero-top-section">
                        <div class="hero-badge-tag">{tag_badge}</div>
                        <h1 class="hero-main-title">{clean_title}</h1>
                        <div class="hero-subtitle-bar"></div>
                        <p class="hero-subtitle-text">{short_sub}</p>
                    </div>
                </div>
                <div class="hero-right-pane">
                    <div class="hero-visual-card" style="padding: 0; overflow: hidden; border: 1.5px solid {th['card_border']};">
                        <img src="{img_src}" style="width: 100%; height: 100%; object-fit: cover; border-radius: 26px;" />
                    </div>
                </div>
            </div>
            """
        else:
            # Mặc định Slide Bìa là dạng Center Keynote Full-Width cực kỳ thoáng đãng & sang trọng
            body_content = f"""
            <div class="hero-center-container">
                <div class="hero-center-aura"></div>
                <div class="hero-center-card">
                    <div class="hero-center-badge">{tag_badge}</div>
                    <h1 class="hero-center-title">{clean_title}</h1>
                    <div class="hero-center-divider">
                        <span class="divider-line"></span>
                        <span class="divider-dot"></span>
                        <span class="divider-line"></span>
                    </div>
                    <p class="hero-center-sub">{short_sub}</p>
                    <div class="hero-center-footer">
                        <span>✦ BẢN TRÌNH BÀY CHIẾN LƯỢC TOÀN DIỆN  •  KATHFLOW AI STUDIO ✦</span>
                    </div>
                </div>
            </div>
            """

    # 2. THREE COLUMNS (3 Cột Trụ Cân Đối)
    elif layout_type == "three_columns":
        col_cards = []
        icons = ["cpu", "shield", "rocket"]
        tags = ["CÔNG NGHỆ LÕI", "AN TOÀN & VẬN HÀNH", "ĐỘT PHÁ TƯƠNG LAI"]
        
        for idx, b in enumerate(bullets[:3]):
            ic_svg = get_svg_icon(icons[idx % len(icons)], th["accent"], 30)
            title_p, desc_p = (b.split(":", 1)[0].strip(), b.split(":", 1)[1].strip()) if ":" in b else (f"Trụ Cột 0{idx+1}", b)
            tag_name = tags[idx % len(tags)]
            
            col_cards.append(f"""
            <div class="pillar-column-card {'pillar-featured' if idx == 1 else ''}">
                <div class="pillar-top-row">
                    <div class="pillar-icon-box">{ic_svg}</div>
                    <div class="pillar-num-badge">PILLAR 0{idx+1}</div>
                </div>
                <div class="pillar-tag">{tag_name}</div>
                <div class="pillar-title">{title_p}</div>
                <div class="pillar-body">{desc_p}</div>
                <div class="pillar-footer-indicator">
                    <span class="indicator-bar"></span> ƯU TIÊN CHIẾN LƯỢC
                </div>
            </div>
            """)

        body_content = f"""
        <div class="three-pillars-grid">
            {''.join(col_cards)}
        </div>
        """

    # 3. VISUAL SPLIT (Sơ Đồ Minh Họa + Spec Cards)
    elif layout_type == "visual_split":
        ill_type = resolve_illustration_type(scene_data, slide_idx)
        ill_svg = get_tech_illustration_svg(ill_type, th["accent"], th["accent_sub"])
        
        detail_items = []
        icons = ["cpu", "shield", "database", "target"]
        for idx, b in enumerate(bullets[:3]):
            title_p, desc_p = (b.split(":", 1)[0].strip(), b.split(":", 1)[1].strip()) if ":" in b else (f"Phân Hệ 0{idx+1}", b)
            ic_svg = get_svg_icon(icons[idx % len(icons)], th["accent"], 26)
            detail_items.append(f"""
            <div class="visual-insight-card">
                <div class="insight-ic">{ic_svg}</div>
                <div class="insight-body">
                    <div class="insight-title">{title_p}</div>
                    <div class="insight-desc">{desc_p}</div>
                </div>
            </div>
            """)

        body_content = f"""
        <div class="visual-split-layout">
            <div class="visual-diagram-pane">
                <div class="diagram-header-tag">
                    <span class="live-pulse"></span> SƠ ĐỒ HỆ THỐNG MÔ HÌNH HÓA THỜI GIAN THỰC
                </div>
                <div class="diagram-svg-wrap">
                    {ill_svg}
                </div>
                <div class="diagram-footer-metrics">
                    <span>TIÊU CHUẨN: SIL 4 (99.999%)</span>
                    <span>TRẠNG THÁI: ACTIVE</span>
                </div>
            </div>
            
            <div class="visual-insights-pane">
                {''.join(detail_items)}
            </div>
        </div>
        """

    # 4. STAT METRIC (Số Liệu Lớn KPI)
    elif layout_type == "stat_metric":
        metric_info = _extract_metric(clean_title)
        if not metric_info:
            for b in bullets + [voiceover]:
                metric_info = _extract_metric(b)
                if metric_info:
                    break
        val_str, lbl_str = metric_info if metric_info else ("$67B", "Quy mô Dự án Toàn diện")

        bullet_cards = []
        icons = ["cpu", "shield", "target", "chart"]
        for idx, b in enumerate(bullets[:3]):
            tag, desc = (b.split(":", 1)[0].strip(), b.split(":", 1)[1].strip()) if ":" in b else (f"Chỉ số 0{idx+1}", b)
            ic_svg = get_svg_icon(icons[idx % len(icons)], th["accent"], 28)
            bullet_cards.append(f"""
            <div class="stat-detail-card">
                <div class="stat-card-icon">{ic_svg}</div>
                <div class="stat-card-body">
                    <div class="stat-card-tag">{tag}</div>
                    <div class="stat-card-text">{desc}</div>
                </div>
            </div>
            """)

        body_content = f"""
        <div class="stat-metric-layout">
            <div class="stat-giant-card">
                <div class="stat-trend-tag">{get_svg_icon("chart", th["accent"], 18)} CHỈ SỐ ĐỘT PHÁ CỐT LÕI</div>
                <div class="stat-big-number">{val_str}</div>
                <div class="stat-big-label">{lbl_str}</div>
                <div class="stat-mini-desc">Được xác định là đòn bẩy trọng tâm tạo bước chuyển dịch chiến lược toàn diện.</div>
            </div>
            <div class="stat-details-col">
                {''.join(bullet_cards)}
            </div>
        </div>
        """

    # 5. 2x2 BENTO MATRIX (Ma Trận 4 Ô)
    elif layout_type == "bento_grid_2x2":
        q_cards = []
        icons = ["cpu", "cloud", "shield", "compass"]
        default_tags = ["HẠ TẦNG & SỐ HÓA", "VẬN HÀNH CABIN", "CHUẨN AN TOÀN", "NGUỒN LỰC CHIẾN LƯỢC"]

        for idx, b in enumerate(bullets[:4]):
            ic_svg = get_svg_icon(icons[idx % len(icons)], th["accent"], 26)
            title_p, desc_p = (b.split(":", 1)[0].strip(), b.split(":", 1)[1].strip()) if ":" in b else (f"Mục 0{idx+1}", b)
            tag_name = default_tags[idx % len(default_tags)]

            q_cards.append(f"""
            <div class="matrix-card">
                <div class="matrix-card-header">
                    <div class="matrix-badge">0{idx+1} • {tag_name}</div>
                    <div class="matrix-icon">{ic_svg}</div>
                </div>
                <div class="matrix-title">{title_p}</div>
                <div class="matrix-desc">{desc_p}</div>
            </div>
            """)

        body_content = f"""
        <div class="matrix-bento-grid">
            {''.join(q_cards)}
        </div>
        """

    # 6. COMPARISON VS (Đối Lập Thực Trạng vs Giải Pháp)
    elif layout_type == "comparison_vs":
        left_bullets = []
        right_bullets = []

        for b in bullets:
            b_lower = b.lower()
            if any(k in b_lower for k in ["thực trạng", "thách thức", "hạn chế", "truyền thống", "lệch", "rủi ro", "vấn đề"]):
                left_bullets.append(b)
            else:
                right_bullets.append(b)

        if not left_bullets and bullets:
            left_bullets = bullets[:len(bullets)//2 or 1]
            right_bullets = bullets[len(bullets)//2 or 1:]

        left_items = "".join([f'<div class="comp-item comp-item-problem">{get_svg_icon("warning", "#f43f5e", 22)} <span>{b}</span></div>' for b in left_bullets[:3]])
        right_items = "".join([f'<div class="comp-item comp-item-solution">{get_svg_icon("check", "#10b981", 22)} <span>{b}</span></div>' for b in right_bullets[:3]])

        body_content = f"""
        <div class="comparison-layout">
            <div class="comp-card comp-problem-card">
                <div class="comp-header comp-header-problem">
                    {get_svg_icon("warning", "#f43f5e", 26)}
                    <span>THỰC TRẠNG & THÁCH THỨC</span>
                </div>
                <div class="comp-body">
                    {left_items}
                </div>
                <div class="comp-footer-tag tag-problem">CẦN THAY ĐỔI CẤP THIẾT</div>
            </div>
            
            <div class="comp-vs-badge">VS</div>

            <div class="comp-card comp-solution-card">
                <div class="comp-header comp-header-solution">
                    {get_svg_icon("rocket", "#10b981", 26)}
                    <span>GIẢI PHÁP ĐỘT PHÁ SỐ HÓA</span>
                </div>
                <div class="comp-body">
                    {right_items}
                </div>
                <div class="comp-footer-tag tag-solution">MỤC TIÊU CHIẾN LƯỢC ĐẠT ĐƯỢC</div>
            </div>
        </div>
        """

    # 7. TIMELINE ROADMAP (Lộ Trình Từng Bước)
    elif layout_type == "timeline_process":
        phases = bullets[:4] if bullets else ["2026 - 2027: Khởi động", "2027 - 2028: Xây dựng", "2028 - 2029: Vận hành"]
        step_cards = []
        action_tags = ["🎯 Mục tiêu trọng tâm giai đoạn", "⚡ Nghiệm thu & Lắp đặt hạ tầng", "🚀 Khai thác vận hành thương mại", "💎 Tối ưu hóa & Chuyển giao 100%"]

        for idx, p_text in enumerate(phases):
            parts = p_text.split(":", 1) if ":" in p_text else p_text.split(" - ", 1)
            p_year = parts[0].strip()
            p_desc = parts[1].strip() if len(parts) > 1 else p_year

            if " - " in p_desc:
                p_sub, p_body = p_desc.split(" - ", 1)
            elif ":" in p_desc:
                p_sub, p_body = p_desc.split(":", 1)
            else:
                p_sub, p_body = "", p_desc

            sub_html = f'<div class="roadmap-sub-title">{p_sub}</div>' if p_sub else ''
            act_tag = action_tags[idx % len(action_tags)]

            step_cards.append(f"""
            <div class="roadmap-step-card {'roadmap-step-featured' if idx == 0 else ''}">
                <div class="roadmap-step-top">
                    <div class="roadmap-badge">GIAI ĐOẠN 0{idx+1}</div>
                    <div class="roadmap-step-num">PHASE 0{idx+1}</div>
                </div>
                <div class="roadmap-phase-year">{p_year}</div>
                {sub_html}
                <div class="roadmap-step-desc">{p_body}</div>
                <div class="roadmap-action-pill">{act_tag}</div>
                <div class="roadmap-step-indicator">
                    <span class="indicator-dot"></span> TIẾN ĐỘ CHUẨN
                </div>
            </div>
            """)

        body_content = f"""
        <div class="roadmap-container">
            <div class="roadmap-axis-track"></div>
            <div class="roadmap-grid">
                {''.join(step_cards)}
            </div>
        </div>
        """

    # 8. ENDING OUTRO (Slide Kết Thúc & Cảm Ơn Khán Giả)
    elif layout_type == "ending_outro":
        tag_badge = scene_data.get("category_tag", "🎬 LỜI CẢM ƠN")
        if not tag_badge.startswith("🎬") and not tag_badge.startswith("✦"):
            tag_badge = f"🎬 {tag_badge}"

        # Subtitle cảm ơn & chúc kết thúc ngắn gọn
        outro_sub = "Hy vọng bài thuyết trình đã mang lại những thông tin hữu ích và góc nhìn giá trị cho bạn."
        if bullets and len(bullets[0]) > 10:
            first_b = bullets[0]
            if ":" in first_b:
                first_b = first_b.split(":", 1)[-1].strip()
            if any(k in first_b.lower() for k in ["hy vọng", "cảm ơn", "chúc", "giá trị", "đúc kết", "lắng nghe", "theo dõi"]):
                outro_sub = first_b[:140]

        body_content = f"""
        <div class="outro-container">
            <div class="outro-hero-card">
                <div class="outro-badge-tag">{tag_badge}</div>
                <h1 class="outro-main-title">CẢM ƠN CÁC BẠN ĐÃ THEO DÕI & LẮNG NGHE!</h1>
                <div class="outro-subtitle-bar"></div>
                <p class="outro-subtitle">{outro_sub}</p>
                <div class="outro-footer-banner">
                    <span>✦ HẸN GẶP LẠI TRONG CÁC CHUYÊN ĐỀ TIẾP THEO ✦</span>
                </div>
            </div>
        </div>
        """

    # 9. KEY TAKEAWAY QUOTE (Đúc Kết Chiến Lược)
    else:
        pills = []
        for b in bullets[:3]:
            txt = b.split(":", 1)[-1].strip() if ":" in b else b
            tag = b.split(":", 1)[0].strip() if ":" in b else "Điểm Nhấn"
            pills.append(f'<div class="takeaway-pill"><span class="takeaway-pill-tag">{tag}:</span> <span>{txt}</span></div>')

        body_content = f"""
        <div class="takeaway-layout">
            <div class="takeaway-main-card">
                <div class="takeaway-header-badge">🎯  ĐÚC KẾT CHIẾN LƯỢC & TẦM NHÌN LÕI</div>
                <div class="takeaway-big-quote">
                    <span class="quote-sym">❝</span>
                    <span class="quote-body">{voiceover if voiceover else clean_title}</span>
                    <span class="quote-sym">❞</span>
                </div>
                <div class="takeaway-pills-row">
                    {''.join(pills)}
                </div>
            </div>
        </div>
        """

    # Ghép toàn bộ vào Template HTML5 / CSS3 siêu nét 1920x1080
    full_html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<style>
    * {{
        box-sizing: border-box;
        margin: 0;
        padding: 0;
    }}
    body {{
        width: 1920px;
        height: 1080px;
        background: {th['bg']};
        background-image: {th['bg_grad']};
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        color: {th['text_body']};
        overflow: hidden;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        padding: 55px 80px;
        position: relative;
    }}

    /* Top Title Header */
    .header-row {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 24px;
    }}
    .header-title-left {{
        display: flex;
        align-items: center;
        gap: 16px;
    }}
    .title-bar {{
        width: 6px;
        height: 40px;
        background: {th['accent']};
        border-radius: 3px;
        box-shadow: 0 0 16px {th['glow']};
    }}
    .slide-title {{
        font-size: 38px;
        font-weight: 800;
        color: #ffffff;
        letter-spacing: -0.5px;
    }}
    .header-theme-badge {{
        background: {th['badge_bg']};
        color: {th['badge_text']};
        font-size: 13px;
        font-weight: 800;
        padding: 8px 18px;
        border-radius: 20px;
        border: 1px solid {th['card_border']};
        letter-spacing: 1px;
    }}

    /* 1. HERO COVER STYLES (Slide Bìa Mở Đầu Chuyên Nghiệp - Center Keynote & Split) */
    .hero-center-container {{
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        flex: 1;
        margin: 20px 0 10px 0;
        position: relative;
    }}
    .hero-center-aura {{
        position: absolute;
        width: 800px;
        height: 500px;
        background: {th['accent']};
        opacity: 0.15;
        border-radius: 50%;
        filter: blur(140px);
        pointer-events: none;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
    }}
    .hero-center-card {{
        background: {th['card_bg']};
        border: 2px solid {th['card_border']};
        border-radius: 36px;
        padding: 80px 100px;
        width: 100%;
        max-width: 1600px;
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        box-shadow: 0 35px 80px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.15);
        position: relative;
        z-index: 2;
    }}
    .hero-center-badge {{
        display: inline-block;
        background: {th['badge_bg']};
        color: {th['accent']};
        font-size: 16px;
        font-weight: 800;
        letter-spacing: 2.5px;
        padding: 10px 28px;
        border-radius: 24px;
        margin-bottom: 28px;
        border: 1px solid {th['card_border']};
        box-shadow: 0 4px 18px {th['glow']};
    }}
    .hero-center-title {{
        font-size: 62px;
        font-weight: 900;
        color: #ffffff;
        line-height: 1.22;
        margin-bottom: 24px;
        letter-spacing: -1px;
        max-width: 1400px;
        text-shadow: 0 4px 30px rgba(0,0,0,0.7);
    }}
    .hero-center-divider {{
        display: flex;
        align-items: center;
        gap: 14px;
        margin-bottom: 28px;
        width: 320px;
        justify-content: center;
    }}
    .divider-line {{
        flex: 1;
        height: 4px;
        background: {th['accent_grad']};
        border-radius: 2px;
    }}
    .divider-dot {{
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: {th['accent']};
        box-shadow: 0 0 12px {th['accent']};
    }}
    .hero-center-sub {{
        font-size: 26px;
        line-height: 1.6;
        color: {th['text_body']};
        font-weight: 500;
        max-width: 1150px;
        margin-bottom: 35px;
    }}
    .hero-center-footer {{
        font-size: 15px;
        font-weight: 800;
        color: {th['accent']};
        letter-spacing: 2px;
        padding-top: 24px;
        border-top: 1px solid rgba(255,255,255,0.08);
        width: 100%;
    }}

    .hero-cover-container {{
        display: grid;
        grid-template-columns: 1.15fr 0.85fr;
        gap: 50px;
        align-items: stretch;
        flex: 1;
        margin: 25px 0 15px 0;
    }}
    .hero-left-pane {{
        display: flex;
        flex-direction: column;
        justify-content: center;
        padding-right: 20px;
    }}
    .hero-top-section {{
        display: flex;
        flex-direction: column;
        justify-content: center;
    }}
    .hero-badge-tag {{
        display: inline-block;
        background: {th['badge_bg']};
        color: {th['accent']};
        font-size: 15px;
        font-weight: 800;
        letter-spacing: 2px;
        padding: 9px 24px;
        border-radius: 10px;
        margin-bottom: 28px;
        border: 1px solid {th['card_border']};
        align-self: flex-start;
        box-shadow: 0 4px 16px {th['glow']};
    }}
    .hero-main-title {{
        font-size: 58px;
        font-weight: 900;
        color: #ffffff;
        line-height: 1.22;
        margin-bottom: 24px;
        letter-spacing: -1px;
        text-shadow: 0 4px 24px rgba(0,0,0,0.6);
    }}
    .hero-subtitle-bar {{
        width: 90px;
        height: 6px;
        background: {th['accent_grad']};
        border-radius: 3px;
        margin-bottom: 24px;
        box-shadow: 0 0 14px {th['glow']};
    }}
    .hero-subtitle-text {{
        font-size: 24px;
        line-height: 1.65;
        color: {th['text_body']};
        font-weight: 500;
        max-width: 920px;
    }}
    .hero-right-pane {{
        display: flex;
        flex-direction: column;
    }}
    .hero-visual-card {{
        background: {th['card_bg']};
        border: 1.5px solid {th['card_border']};
        border-radius: 28px;
        padding: 32px;
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-shadow: 0 25px 60px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.1);
        position: relative;
        overflow: hidden;
    }}
    .hero-visual-card::before {{
        content: "";
        position: absolute;
        top: -30%;
        right: -30%;
        width: 350px;
        height: 350px;
        background: {th['accent']};
        opacity: 0.15;
        border-radius: 50%;
        filter: blur(80px);
        pointer-events: none;
    }}
    .hero-visual-header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
    }}
    .visual-header-badge {{
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 13px;
        font-weight: 800;
        color: {th['accent']};
        letter-spacing: 1px;
    }}
    .visual-header-id {{
        font-size: 12px;
        font-weight: 800;
        color: {th['text_muted']};
        letter-spacing: 1.5px;
    }}
    .hero-visual-art {{
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 20px 0;
    }}
    .hero-visual-footer {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-top: 1px solid rgba(255,255,255,0.08);
        padding-top: 16px;
    }}
    .visual-pill {{
        font-size: 12px;
        font-weight: 800;
        color: {th['accent']};
        letter-spacing: 1.5px;
    }}
    .visual-pill-sub {{
        font-size: 12px;
        font-weight: 700;
        color: {th['text_muted']};
        letter-spacing: 1px;
    }}

    /* 2. THREE PILLARS STYLES */
    .three-pillars-grid {{
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 36px;
        flex: 1;
        align-items: center;
    }}
    .pillar-column-card {{
        background: {th['card_bg']};
        border: 1px solid {th['card_border']};
        border-radius: 24px;
        padding: 44px 36px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-shadow: 0 18px 40px rgba(0,0,0,0.35);
        position: relative;
        min-height: 560px;
        max-height: 640px;
    }}
    .pillar-featured {{
        border-color: {th['accent']};
        background: {th['card_bg_alt']};
        box-shadow: 0 22px 50px rgba(0,0,0,0.55), 0 0 24px {th['glow']};
    }}
    .pillar-top-row {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 18px;
    }}
    .pillar-icon-box {{
        width: 64px;
        height: 64px;
        border-radius: 18px;
        background: {th['badge_bg']};
        display: flex;
        align-items: center;
        justify-content: center;
    }}
    .pillar-num-badge {{
        font-size: 13px;
        font-weight: 800;
        color: {th['accent']};
        letter-spacing: 1px;
    }}
    .pillar-tag {{
        font-size: 13px;
        font-weight: 800;
        color: {th['accent_sub']};
        letter-spacing: 1px;
        margin-bottom: 10px;
    }}
    .pillar-title {{
        font-size: 26px;
        font-weight: 800;
        color: #ffffff;
        line-height: 1.35;
        margin-bottom: 16px;
    }}
    .pillar-body {{
        font-size: 19px;
        line-height: 1.65;
        color: {th['text_body']};
        flex: 1;
    }}
    .pillar-footer-indicator {{
        display: flex;
        align-items: center;
        gap: 8px;
        margin-top: 25px;
        padding-top: 18px;
        border-top: 1px solid rgba(255,255,255,0.08);
        font-size: 12px;
        font-weight: 700;
        color: {th['text_muted']};
        letter-spacing: 1px;
    }}
    .indicator-bar {{
        width: 14px;
        height: 4px;
        background: {th['accent']};
        border-radius: 2px;
    }}

    /* 3. VISUAL SPLIT STYLES */
    .visual-split-layout {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 45px;
        flex: 1;
        align-items: center;
    }}
    .visual-diagram-pane {{
        background: {th['card_bg']};
        border: 1px solid {th['card_border']};
        border-radius: 24px;
        padding: 32px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-shadow: 0 18px 45px rgba(0,0,0,0.4);
        min-height: 580px;
        max-height: 660px;
    }}
    .diagram-header-tag {{
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 13px;
        font-weight: 800;
        color: {th['accent']};
        letter-spacing: 1px;
    }}
    .live-pulse {{
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #10b981;
        box-shadow: 0 0 8px #10b981;
    }}
    .diagram-svg-wrap {{
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 15px 0;
    }}
    .diagram-footer-metrics {{
        display: flex;
        justify-content: space-between;
        font-size: 12px;
        font-weight: 700;
        color: {th['text_muted']};
        border-top: 1px solid rgba(255,255,255,0.08);
        padding-top: 12px;
    }}
    .visual-insights-pane {{
        display: flex;
        flex-direction: column;
        justify-content: center;
        gap: 20px;
        min-height: 580px;
        max-height: 660px;
    }}
    .visual-insight-card {{
        background: {th['card_bg_alt']};
        border: 1px solid {th['card_border']};
        border-left: 4px solid {th['accent']};
        border-radius: 20px;
        padding: 30px 36px;
        display: flex;
        align-items: flex-start;
        gap: 24px;
        box-shadow: 0 12px 28px rgba(0,0,0,0.3);
        flex: 1;
    }}
    .insight-ic {{
        width: 58px;
        height: 58px;
        border-radius: 16px;
        background: {th['badge_bg']};
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
    }}
    .insight-body {{
        flex: 1;
    }}
    .insight-title {{
        font-size: 25px;
        font-weight: 800;
        color: #ffffff;
        margin-bottom: 8px;
    }}
    .insight-desc {{
        font-size: 20px;
        line-height: 1.6;
        color: {th['text_body']};
    }}

    /* 4. STAT METRIC STYLES */
    .stat-metric-layout {{
        display: grid;
        grid-template-columns: 540px 1fr;
        gap: 40px;
        align-items: center;
        flex: 1;
    }}
    .stat-giant-card {{
        background: {th['card_bg']};
        border: 2px solid {th['card_border']};
        border-radius: 24px;
        padding: 48px 36px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        text-align: center;
        box-shadow: 0 25px 50px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.08);
        min-height: 580px;
    }}
    .stat-trend-tag {{
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 15px;
        font-weight: 800;
        color: {th['accent']};
        background: {th['badge_bg']};
        padding: 8px 20px;
        border-radius: 20px;
        margin-bottom: 25px;
        letter-spacing: 1px;
    }}
    .stat-big-number {{
        font-size: 108px;
        font-weight: 900;
        line-height: 1;
        letter-spacing: -3px;
        background: {th['accent_grad']};
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 20px;
        filter: drop-shadow(0 6px 16px {th['glow']});
    }}
    .stat-big-label {{
        font-size: 26px;
        font-weight: 800;
        color: #ffffff;
        margin-bottom: 14px;
        line-height: 1.35;
    }}
    .stat-mini-desc {{
        font-size: 17px;
        color: {th['text_muted']};
        line-height: 1.6;
    }}
    .stat-details-col {{
        display: flex;
        flex-direction: column;
        justify-content: center;
        gap: 22px;
        min-height: 580px;
    }}
    .stat-detail-card {{
        background: {th['card_bg_alt']};
        border: 1px solid {th['card_border']};
        border-left: 5px solid {th['accent']};
        border-radius: 20px;
        padding: 30px 36px;
        display: flex;
        align-items: flex-start;
        gap: 24px;
        box-shadow: 0 12px 30px rgba(0,0,0,0.3);
        flex: 1;
    }}
    .stat-card-icon {{
        width: 58px;
        height: 58px;
        border-radius: 16px;
        background: {th['badge_bg']};
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
    }}
    .stat-card-body {{
        flex: 1;
    }}
    .stat-card-tag {{
        font-size: 24px;
        font-weight: 800;
        color: {th['accent']};
        margin-bottom: 8px;
        letter-spacing: 0.5px;
    }}
    .stat-card-text {{
        font-size: 21px;
        line-height: 1.6;
        color: #f8fafc;
        font-weight: 500;
    }}

    /* 5. 2x2 BENTO MATRIX STYLES */
    .matrix-bento-grid {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        grid-template-rows: 1fr 1fr;
        gap: 26px;
        flex: 1;
        align-items: center;
    }}
    .matrix-card {{
        background: {th['card_bg']};
        border: 1px solid {th['card_border']};
        border-radius: 22px;
        padding: 36px 40px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        box-shadow: 0 12px 28px rgba(0,0,0,0.3);
        min-height: 270px;
    }}
    .matrix-card-header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 14px;
    }}
    .matrix-badge {{
        font-size: 14px;
        font-weight: 800;
        color: {th['accent']};
        letter-spacing: 1px;
    }}
    .matrix-title {{
        font-size: 26px;
        font-weight: 800;
        color: #ffffff;
        margin-bottom: 10px;
    }}
    .matrix-desc {{
        font-size: 20px;
        line-height: 1.6;
        color: {th['text_body']};
    }}

    /* 6. COMPARISON VS STYLES */
    .comparison-layout {{
        display: grid;
        grid-template-columns: 1fr 60px 1fr;
        gap: 32px;
        align-items: center;
        flex: 1;
    }}
    .comp-card {{
        background: {th['card_bg']};
        border-radius: 24px;
        padding: 44px 38px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-shadow: 0 18px 45px rgba(0,0,0,0.4);
        min-height: 560px;
        max-height: 640px;
    }}
    .comp-problem-card {{
        border: 1.5px solid rgba(244, 63, 94, 0.4);
    }}
    .comp-solution-card {{
        border: 1.5px solid rgba(16, 185, 129, 0.4);
    }}
    .comp-header {{
        display: flex;
        align-items: center;
        gap: 12px;
        font-size: 22px;
        font-weight: 800;
        letter-spacing: 0.5px;
        margin-bottom: 24px;
    }}
    .comp-header-problem {{
        color: #f43f5e;
    }}
    .comp-header-solution {{
        color: #10b981;
    }}
    .comp-body {{
        display: flex;
        flex-direction: column;
        justify-content: center;
        gap: 18px;
        flex: 1;
    }}
    .comp-item {{
        display: flex;
        align-items: flex-start;
        gap: 16px;
        font-size: 20px;
        line-height: 1.6;
        color: #f8fafc;
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.06);
        border-radius: 14px;
        padding: 18px 22px;
    }}
    .comp-vs-badge {{
        width: 60px;
        height: 60px;
        border-radius: 50%;
        background: #1e293b;
        border: 2px solid #334155;
        color: #ffffff;
        font-size: 18px;
        font-weight: 900;
        display: flex;
        align-items: center;
        justify-content: center;
        align-self: center;
        box-shadow: 0 0 18px rgba(0,0,0,0.6);
    }}
    .comp-footer-tag {{
        font-size: 13px;
        font-weight: 800;
        letter-spacing: 1px;
        padding: 10px 16px;
        border-radius: 10px;
        text-align: center;
        margin-top: 20px;
    }}
    .tag-problem {{
        background: rgba(244, 63, 94, 0.15);
        color: #fb7185;
    }}
    .tag-solution {{
        background: rgba(16, 185, 129, 0.15);
        color: #34d399;
    }}

    /* 7. TIMELINE ROADMAP STYLES */
    .roadmap-container {{
        flex: 1;
        display: flex;
        flex-direction: column;
        justify-content: center;
        position: relative;
    }}
    .roadmap-axis-track {{
        position: absolute;
        left: 60px;
        right: 60px;
        top: 50%;
        height: 6px;
        background: {th['accent_grad']};
        border-radius: 3px;
        box-shadow: 0 0 16px {th['glow']};
        z-index: 1;
    }}
    .roadmap-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
        gap: 36px;
        align-items: stretch;
        position: relative;
        z-index: 2;
    }}
    .roadmap-step-card {{
        background: {th['card_bg']};
        border: 1.5px solid {th['card_border']};
        border-radius: 24px;
        padding: 44px 36px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-shadow: 0 18px 40px rgba(0,0,0,0.4);
        min-height: 520px;
    }}
    .roadmap-step-featured {{
        border-color: {th['accent']};
        background: {th['card_bg_alt']};
        box-shadow: 0 22px 50px rgba(0,0,0,0.55), 0 0 20px {th['glow']};
    }}
    .roadmap-step-top {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 20px;
    }}
    .roadmap-badge {{
        font-size: 14px;
        font-weight: 800;
        color: {th['accent']};
        background: {th['badge_bg']};
        padding: 8px 16px;
        border-radius: 12px;
        letter-spacing: 1px;
    }}
    .roadmap-step-num {{
        font-size: 15px;
        font-weight: 900;
        color: {th['text_muted']};
        letter-spacing: 1px;
    }}
    .roadmap-phase-year {{
        font-size: 34px;
        font-weight: 900;
        color: #ffffff;
        margin-bottom: 14px;
        line-height: 1.25;
        letter-spacing: -0.5px;
    }}
    .roadmap-sub-title {{
        font-size: 22px;
        font-weight: 800;
        color: {th['accent']};
        margin-bottom: 12px;
        line-height: 1.4;
    }}
    .roadmap-step-desc {{
        font-size: 20px;
        color: {th['text_body']};
        line-height: 1.65;
        font-weight: 500;
        flex: 1;
    }}
    .roadmap-action-pill {{
        background: {th['badge_bg']};
        border: 1px solid {th['card_border']};
        border-radius: 12px;
        padding: 12px 18px;
        font-size: 16px;
        font-weight: 700;
        color: {th['accent']};
        margin: 16px 0;
        display: inline-flex;
        align-items: center;
        gap: 8px;
    }}
    .roadmap-step-indicator {{
        display: flex;
        align-items: center;
        gap: 10px;
        margin-top: 20px;
        padding-top: 18px;
        border-top: 1px solid rgba(255,255,255,0.08);
        font-size: 13px;
        font-weight: 800;
        color: {th['text_muted']};
        letter-spacing: 1px;
    }}
    .indicator-dot {{
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: {th['accent']};
        box-shadow: 0 0 8px {th['accent']};
    }}

    /* 8. KEY TAKEAWAY STYLES */
    .takeaway-layout {{
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: center;
    }}
    .takeaway-main-card {{
        background: {th['card_bg']};
        border: 2px solid {th['card_border']};
        border-radius: 28px;
        padding: 55px 75px;
        width: 100%;
        max-width: 1550px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: space-between;
        min-height: 520px;
        text-align: center;
        box-shadow: 0 25px 60px rgba(0,0,0,0.5);
    }}
    .takeaway-header-badge {{
        font-size: 16px;
        font-weight: 800;
        color: {th['accent']};
        background: {th['badge_bg']};
        padding: 10px 26px;
        border-radius: 20px;
        letter-spacing: 1.5px;
        margin-bottom: 20px;
    }}
    .takeaway-big-quote {{
        font-size: 38px;
        line-height: 1.6;
        color: #ffffff;
        font-weight: 700;
        margin: 20px 0 35px 0;
        max-width: 1400px;
        text-wrap: balance;
        word-break: keep-all;
        overflow-wrap: break-word;
    }}
    .quote-sym {{
        color: {th['accent']};
        font-size: 48px;
        margin: 0 8px;
        vertical-align: -6px;
    }}
    .takeaway-pills-row {{
        display: flex;
        gap: 24px;
        justify-content: center;
        flex-wrap: wrap;
        width: 100%;
    }}
    .takeaway-pill {{
        display: flex;
        align-items: center;
        gap: 12px;
        background: {th['card_bg_alt']};
        border: 1.5px solid {th['card_border']};
        border-radius: 16px;
        padding: 18px 30px;
        font-size: 20px;
        font-weight: 600;
        color: #f1f5f9;
        flex: 1;
        min-width: 320px;
        max-width: 460px;
        justify-content: center;
    }}
    .takeaway-pill-tag {{
        color: {th['accent']};
        font-weight: 800;
    }}

    /* 8. ENDING OUTRO STYLES (Slide Bìa Kết Thúc & Lời Cảm Ơn) */
    .outro-container {{
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        flex: 1;
        margin: 20px 0 10px 0;
    }}
    .outro-hero-card {{
        background: {th['card_bg']};
        border: 2px solid {th['card_border']};
        border-radius: 36px;
        padding: 80px 90px;
        width: 100%;
        max-width: 1550px;
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        box-shadow: 0 35px 80px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.15);
        position: relative;
        overflow: hidden;
    }}
    .outro-hero-card::before {{
        content: "";
        position: absolute;
        top: -50%;
        left: 50%;
        transform: translateX(-50%);
        width: 700px;
        height: 450px;
        background: {th['accent']};
        opacity: 0.2;
        border-radius: 50%;
        filter: blur(120px);
        pointer-events: none;
    }}
    .outro-badge-tag {{
        display: inline-block;
        background: {th['badge_bg']};
        color: {th['accent']};
        font-size: 16px;
        font-weight: 800;
        letter-spacing: 2.5px;
        padding: 10px 28px;
        border-radius: 24px;
        margin-bottom: 30px;
        border: 1px solid {th['card_border']};
        box-shadow: 0 4px 18px {th['glow']};
    }}
    .outro-main-title {{
        font-size: 58px;
        font-weight: 900;
        color: #ffffff;
        line-height: 1.25;
        margin-bottom: 20px;
        letter-spacing: -0.5px;
        text-shadow: 0 4px 25px rgba(0,0,0,0.7);
    }}
    .outro-subtitle-bar {{
        width: 100px;
        height: 6px;
        background: {th['accent_grad']};
        border-radius: 3px;
        margin-bottom: 28px;
        box-shadow: 0 0 16px {th['glow']};
    }}
    .outro-subtitle {{
        font-size: 26px;
        color: {th['text_body']};
        font-weight: 500;
        margin-bottom: 45px;
        max-width: 1150px;
        line-height: 1.6;
    }}
    .outro-footer-banner {{
        font-size: 16px;
        font-weight: 800;
        color: {th['accent']};
        letter-spacing: 2px;
        padding-top: 28px;
        border-top: 1px solid rgba(255,255,255,0.1);
        width: 100%;
    }}

    /* Footer Meta */
    .footer-row {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding-top: 18px;
        border-top: 1px solid rgba(255, 255, 255, 0.08);
        font-size: 14px;
        color: #64748b;
    }}
</style>
</head>
<body>
    {'<div class="header-row"><div class="header-title-left"><div class="title-bar"></div><div class="slide-title">' + clean_title + '</div></div><div class="header-theme-badge">✦ NOTEBOOKLM EXECUTIVE DECK ✦</div></div>' if layout_type not in ["hero_cover", "ending_outro"] else ''}

    {body_content}

    <div class="footer-row">
        <span>KathFlow AI Studio  •  NotebookLM Executive Presentation</span>
        <span>Phân cảnh {slide_idx:02d} / {total_slides:02d}</span>
    </div>
</body>
</html>"""
    return full_html


# ═══════════════════════════════════════════════════════════════════════════
#  HIGH-RES SLIDE IMAGE RENDERER (Playwright Chromium Engine)
# ═══════════════════════════════════════════════════════════════════════════

def render_slide_to_image(
    pptx_path: str,
    slide_index: int,
    output_image_path: str,
    scene_data: Optional[Dict[str, Any]] = None,
    total_slides: int = 10,
    width: int = 1920,
    height: int = 1080,
) -> bool:
    """
    Render 1 slide cụ thể ra file ảnh PNG 1920x1080 siêu nét chuẩn phong cách Gemini / NotebookLM Bento
    thông qua Playwright Chromium Engine (Pixel-Perfect).
    """
    out_p = Path(output_image_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    # 1. Ưu tiên render bằng Playwright Chromium (Pixel-Perfect HTML/CSS)
    if scene_data:
        try:
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

            from playwright.sync_api import sync_playwright

            html_content = generate_slide_html(scene_data, slide_idx=slide_index + 1, total_slides=total_slides)
            
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": width, "height": height})
                page.set_content(html_content, wait_until="domcontentloaded", timeout=15000)
                page.screenshot(path=str(out_p), type="png")
                browser.close()

            if out_p.exists() and out_p.stat().st_size > 10000:
                return True
        except Exception as exc:
            print(f"[render_slide_to_image] Playwright render error: {exc}")

    # 2. Fallback: COM PowerPoint
    if pptx_path and os.path.exists(pptx_path) and sys.platform == "win32":
        try:
            import comtypes.client
            ppt_app = comtypes.client.CreateObject("PowerPoint.Application")
            ppt_app.Visible = 1
            presentation = ppt_app.Presentations.Open(os.path.abspath(pptx_path), WithWindow=False)
            target_idx = max(1, min(slide_index + 1, presentation.Slides.Count))
            target_slide = presentation.Slides(target_idx)
            target_slide.Export(os.path.abspath(output_image_path), "PNG", width, height)
            presentation.Close()
            if out_p.exists() and out_p.stat().st_size > 1000:
                return True
        except Exception:
            pass


    # 3. Fallback: Pillow High-Res Bento Renderer
    try:
        th_key = scene_data.get("theme_color", "sapphire") if scene_data else "sapphire"
        th = THEME_PALETTES.get(th_key, THEME_PALETTES["sapphire"])
        
        bg_rgb = (8, 16, 30)
        card_rgb = (16, 28, 48)
        accent_rgb = (56, 189, 248)

        img = Image.new("RGB", (width, height), color=bg_rgb)
        draw = ImageDraw.Draw(img)

        # Title bar & Title
        draw.rectangle([85, 60, 91, 110], fill=accent_rgb)
        
        font_hero = None
        for font_name in ["segoeuib.ttf", "arialbd.ttf", "calibrib.ttf", "segoeui.ttf"]:
            try:
                font_hero = ImageFont.truetype(font_name, 44)
                font_title = ImageFont.truetype(font_name, 32)
                font_body = ImageFont.truetype(font_name, 24)
                break
            except Exception:
                continue

        if not font_hero:
            font_hero = ImageFont.load_default()
            font_title = font_hero
            font_body = font_hero

        title = scene_data.get("slide_title", f"Phân cảnh {slide_index + 1}") if scene_data else f"Phân cảnh {slide_index + 1}"
        clean_title = title.replace("|", "").strip()
        layout_type = scene_data.get("layout_type", "") if scene_data else ""
        bullets = scene_data.get("bullet_points", []) if scene_data else []

        if layout_type == "hero_cover" or slide_index == 0:
            # Hero Cover Slide
            draw.text((120, 280), clean_title, fill=(255, 255, 255), font=font_hero)
            sub_t = bullets[0] if bullets else "Bản trình bày phân tích dữ liệu chuyên sâu & tổng hợp bức tranh chiến lược."
            draw.text((120, 390), sub_t[:90], fill=(203, 213, 225), font=font_title)
            draw.rounded_rectangle([1100, 160, 1800, 920], radius=24, fill=card_rgb, outline=accent_rgb, width=3)
            draw.text((1200, 500), "✦ EXECUTIVE KEYNOTE ✦", fill=accent_rgb, font=font_title)
        elif layout_type == "ending_outro" or slide_index == total_slides - 1:
            # Ending Outro Slide
            draw.text((360, 320), "CẢM ƠN CÁC BẠN ĐÃ THEO DÕI & LẮNG NGHE!", fill=(255, 255, 255), font=font_hero)
            draw.text((450, 420), "Hy vọng bài thuyết trình đã mang lại nhiều góc nhìn giá trị.", fill=(203, 213, 225), font=font_title)
            draw.rounded_rectangle([320, 240, 1600, 780], radius=32, fill=card_rgb, outline=accent_rgb, width=2)
        else:
            # Content Bento Slide
            draw.text((110, 60), clean_title, fill=(255, 255, 255), font=font_hero)
            # Left Bento Card
            draw.rounded_rectangle([85, 160, 650, 960], radius=20, fill=card_rgb, outline=accent_rgb, width=2)
            voiceover = scene_data.get("voiceover_text", "") if scene_data else ""
            
            import textwrap
            v_lines = textwrap.wrap(voiceover, width=28)
            cur_y = 260
            for vl in v_lines[:8]:
                draw.text((125, cur_y), vl, fill=(203, 213, 225), font=font_title)
                cur_y += 50

            # Right Bento Cards
            for i, bp in enumerate(bullets[:3]):
                y_pos = 160 + i * 270
                draw.rounded_rectangle([690, y_pos, 1835, y_pos + 240], radius=16, fill=card_rgb, outline=(32, 51, 84), width=2)
                draw.ellipse([720, y_pos + 30, 780, y_pos + 90], fill=(2, 132, 199))
                draw.text((742, y_pos + 42), f"{i+1}", fill=(255, 255, 255), font=font_title)
                
                b_lines = textwrap.wrap(bp, width=45)
                cur_by = y_pos + 35
                for bl in b_lines[:3]:
                    draw.text((810, cur_by), bl, fill=(255, 255, 255) if i == 0 else (203, 213, 225), font=font_title if i == 0 else font_body)
                    cur_by += 46

        img.save(str(out_p), "PNG")
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════
#  PPTX BUILDER (PowerPoint Export)
# ═══════════════════════════════════════════════════════════════════════════

class PPTXBuilder:
    """Xây dựng Presentation chuẩn 16:9 với đa dạng thiết kế phong cách NotebookLM & Gemini."""

    def __init__(self):
        self.palettes = THEME_PALETTES

    def create_presentation(
        self,
        storyboard_data: Dict[str, Any],
        output_pptx_path: str,
    ) -> str:
        """Tạo file presentation .pptx hoàn chỉnh từ Storyboard."""
        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)
        blank_layout = prs.slide_layouts[6]

        scenes = storyboard_data.get("scenes", [])
        project_title = storyboard_data.get("project_title", "NotebookLM Executive Presentation")
        project_summary = storyboard_data.get("summary", "Tổng hợp nội dung chiến lược và phân tích chi tiết.")

        # 1. Slide Bìa
        self._build_hero_cover(prs, blank_layout, project_title, project_summary, len(scenes))

        # 2. Slides Nội Dung
        for idx, scene in enumerate(scenes, 1):
            self._build_bento_scene(prs, blank_layout, idx, scene, len(scenes), project_title)

        out_path = Path(output_pptx_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        prs.save(str(out_path))
        return str(out_path)

    def _build_hero_cover(self, prs, layout, title: str, summary: str, total_scenes: int):
        slide = prs.slides.add_slide(layout)
        th = self.palettes["sapphire"]

        # Nền
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5))
        bg.fill.solid()
        bg.fill.fore_color.rgb = th["pptx_bg"]
        bg.line.fill.background()

        # Thanh Accent
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.2), Inches(1.8), Inches(0.1), Inches(3.0))
        bar.fill.solid()
        bar.fill.fore_color.rgb = th["pptx_accent"]
        bar.line.fill.background()

        # Tiêu đề Hero chính
        title_box = slide.shapes.add_textbox(Inches(1.5), Inches(1.8), Inches(10.5), Inches(2.2))
        tf = title_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(38)
        p.font.bold = True
        p.font.color.rgb = RGBColor(255, 255, 255)

        # Callout summary
        if summary:
            card_s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.5), Inches(4.5), Inches(10.5), Inches(1.5))
            card_s.fill.solid()
            card_s.fill.fore_color.rgb = th["pptx_card"]
            card_s.line.color.rgb = th["pptx_accent"]
            card_s.line.width = Pt(1)

            tb_s = slide.shapes.add_textbox(Inches(1.8), Inches(4.65), Inches(9.9), Inches(1.2))
            tf_s = tb_s.text_frame
            tf_s.word_wrap = True
            p_s = tf_s.paragraphs[0]
            p_s.text = f"❝ {summary} ❞"
            p_s.font.size = Pt(16)
            p_s.font.italic = True
            p_s.font.color.rgb = RGBColor(203, 213, 225)

    def _build_bento_scene(self, prs, layout, scene_num: int, scene_data: Dict[str, Any], total_scenes: int, proj_title: str):
        slide = prs.slides.add_slide(layout)
        th_key = scene_data.get("theme_color", THEME_ORDER[(scene_num - 1) % len(THEME_ORDER)])
        th = self.palettes.get(th_key, self.palettes["sapphire"])

        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5))
        bg.fill.solid()
        bg.fill.fore_color.rgb = th["pptx_bg"]
        bg.line.fill.background()

        # Accent Bar
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.9), Inches(0.8), Inches(0.08), Inches(0.6))
        bar.fill.solid()
        bar.fill.fore_color.rgb = th["pptx_accent"]
        bar.line.fill.background()

        # Tiêu đề
        t_box = slide.shapes.add_textbox(Inches(1.1), Inches(0.7), Inches(11.3), Inches(0.8))
        tf_t = t_box.text_frame
        tf_t.word_wrap = True
        p_t = tf_t.paragraphs[0]
        p_t.text = scene_data.get("slide_title", f"Phân cảnh {scene_num}").replace("|", "").strip()
        p_t.font.size = Pt(26)
        p_t.font.bold = True
        p_t.font.color.rgb = RGBColor(255, 255, 255)

        layout_type = scene_data.get("layout_type", "standard")
        bullets = scene_data.get("bullet_points", [])

        # 1. 3 Columns
        if layout_type == "three_columns" and len(bullets) >= 3:
            card_w = Inches(3.6)
            for idx, b in enumerate(bullets[:3]):
                x_pos = Inches(0.9 + idx * 4.0)
                card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x_pos, Inches(1.8), card_w, Inches(4.8))
                card.fill.solid()
                card.fill.fore_color.rgb = th["pptx_card_alt"] if idx == 1 else th["pptx_card"]
                card.line.color.rgb = th["pptx_accent"] if idx == 1 else RGBColor(40, 60, 90)
                card.line.width = Pt(1.5)

                tb = slide.shapes.add_textbox(x_pos + Inches(0.2), Inches(2.0), card_w - Inches(0.4), Inches(4.4))
                tf = tb.text_frame
                tf.word_wrap = True
                p_hd = tf.paragraphs[0]
                p_hd.text = f"PILLAR 0{idx+1}"
                p_hd.font.size = Pt(12)
                p_hd.font.bold = True
                p_hd.font.color.rgb = th["pptx_accent"]

                p_b = tf.add_paragraph()
                p_b.space_before = Pt(12)
                p_b.text = b
                p_b.font.size = Pt(14)
                p_b.font.color.rgb = RGBColor(203, 213, 225)

        # 2. Comparison VS
        elif layout_type == "comparison_vs":
            card_w = Inches(5.5)
            # Left Problem Card
            card_l = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.9), Inches(1.8), card_w, Inches(4.8))
            card_l.fill.solid()
            card_l.fill.fore_color.rgb = th["pptx_card"]
            card_l.line.color.rgb = RGBColor(244, 63, 94)
            card_l.line.width = Pt(1.5)

            tb_l = slide.shapes.add_textbox(Inches(1.1), Inches(2.0), card_w - Inches(0.4), Inches(4.4))
            tf_l = tb_l.text_frame
            tf_l.word_wrap = True
            p_lh = tf_l.paragraphs[0]
            p_lh.text = "⚠️  THỰC TRẠNG & THÁCH THỨC"
            p_lh.font.size = Pt(14)
            p_lh.font.bold = True
            p_lh.font.color.rgb = RGBColor(244, 63, 94)

            for b in bullets[:2]:
                p_item = tf_l.add_paragraph()
                p_item.space_before = Pt(10)
                p_item.text = f"• {b}"
                p_item.font.size = Pt(13)
                p_item.font.color.rgb = RGBColor(203, 213, 225)

            # Right Solution Card
            card_r = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.9), Inches(1.8), card_w, Inches(4.8))
            card_r.fill.solid()
            card_r.fill.fore_color.rgb = th["pptx_card_alt"]
            card_r.line.color.rgb = RGBColor(16, 185, 129)
            card_r.line.width = Pt(1.5)

            tb_r = slide.shapes.add_textbox(Inches(7.1), Inches(2.0), card_w - Inches(0.4), Inches(4.4))
            tf_r = tb_r.text_frame
            tf_r.word_wrap = True
            p_rh = tf_r.paragraphs[0]
            p_rh.text = "🚀  GIẢI PHÁP ĐỘT PHÁ"
            p_rh.font.size = Pt(14)
            p_rh.font.bold = True
            p_rh.font.color.rgb = RGBColor(16, 185, 129)

            for b in bullets[2:4] if len(bullets) > 2 else bullets:
                p_item = tf_r.add_paragraph()
                p_item.space_before = Pt(10)
                p_item.text = f"• {b}"
                p_item.font.size = Pt(13)
                p_item.font.color.rgb = RGBColor(255, 255, 255)

        # 3. Ending Outro
        elif layout_type == "ending_outro":
            card_main = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.5), Inches(1.8), Inches(10.3), Inches(4.8))
            card_main.fill.solid()
            card_main.fill.fore_color.rgb = th["pptx_card"]
            card_main.line.color.rgb = th["pptx_accent"]
            card_main.line.width = Pt(2)

            tb_m = slide.shapes.add_textbox(Inches(1.8), Inches(2.8), Inches(9.7), Inches(2.8))
            tf_m = tb_m.text_frame
            tf_m.word_wrap = True
            p_m = tf_m.paragraphs[0]
            p_m.text = "CẢM ƠN CÁC BẠN ĐÃ THEO DÕI & LẮNG NGHE!"
            p_m.font.size = Pt(32)
            p_m.font.bold = True
            p_m.font.color.rgb = RGBColor(255, 255, 255)
            p_m.alignment = PP_ALIGN.CENTER

            p_sub = tf_m.add_paragraph()
            p_sub.space_before = Pt(16)
            p_sub.text = "Hy vọng bài thuyết trình đã mang lại những thông tin hữu ích và góc nhìn giá trị cho bạn."
            p_sub.font.size = Pt(16)
            p_sub.font.color.rgb = RGBColor(203, 213, 225)
            p_sub.alignment = PP_ALIGN.CENTER

            p_tag = tf_m.add_paragraph()
            p_tag.space_before = Pt(24)
            p_tag.text = "✦ HẸN GẶP LẠI TRONG CÁC CHUYÊN ĐỀ TIẾP THEO ✦"
            p_tag.font.size = Pt(13)
            p_tag.font.bold = True
            p_tag.font.color.rgb = th["pptx_accent"]
            p_tag.alignment = PP_ALIGN.CENTER

        # 4. Standard / Default 2-Column Bento
        else:
            card_l = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.9), Inches(1.8), Inches(4.5), Inches(4.8))
            card_l.fill.solid()
            card_l.fill.fore_color.rgb = th["pptx_card_alt"]
            card_l.line.color.rgb = th["pptx_accent"]
            card_l.line.width = Pt(1.5)

            t_l = slide.shapes.add_textbox(Inches(1.2), Inches(2.1), Inches(3.9), Inches(4.2))
            tf_l = t_l.text_frame
            tf_l.word_wrap = True
            p_lh = tf_l.paragraphs[0]
            p_lh.text = "🎯  TRỌNG TÂM CỐT LÕI"
            p_lh.font.size = Pt(13)
            p_lh.font.bold = True
            p_lh.font.color.rgb = th["pptx_accent"]

            p_lb = tf_l.add_paragraph()
            p_lb.space_before = Pt(14)
            p_lb.text = scene_data.get("voiceover_text", "")[:130]
            p_lb.font.size = Pt(15)
            p_lb.font.color.rgb = RGBColor(203, 213, 225)

            start_y = 1.8
            card_h = 1.45
            for i, bp in enumerate(bullets[:3]):
                y_pos = start_y + i * (card_h + 0.2)
                card_r = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(5.7), Inches(y_pos), Inches(6.7), Inches(card_h))
                card_r.fill.solid()
                card_r.fill.fore_color.rgb = th["pptx_card"]
                card_r.line.color.rgb = RGBColor(40, 60, 90)
                card_r.line.width = Pt(1)

                num_box = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(5.9), Inches(y_pos + 0.2), Inches(0.45), Inches(0.45))
                num_box.fill.solid()
                num_box.fill.fore_color.rgb = th["pptx_accent"]
                num_box.line.fill.background()
                tf_num = num_box.text_frame
                tf_num.vertical_anchor = MSO_ANCHOR.MIDDLE
                p_n = tf_num.paragraphs[0]
                p_n.text = f"{i+1}"
                p_n.font.size = Pt(11)
                p_n.font.bold = True
                p_n.font.color.rgb = RGBColor(255, 255, 255)
                p_n.alignment = PP_ALIGN.CENTER

                tb_r = slide.shapes.add_textbox(Inches(6.5), Inches(y_pos + 0.1), Inches(5.7), Inches(card_h - 0.2))
                tf_r = tb_r.text_frame
                tf_r.word_wrap = True
                p_rb = tf_r.paragraphs[0]
                p_rb.text = bp
                p_rb.font.size = Pt(13)
                p_rb.font.color.rgb = RGBColor(255, 255, 255) if i == 0 else RGBColor(203, 213, 225)
