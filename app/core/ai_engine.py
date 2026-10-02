"""
ai_engine.py — Não bộ AI tích hợp Google Gemini & Google Veo Video API
Xử lý:
1. Phân tích tài liệu -> Tạo kịch bản phân cảnh phong cách Gemini Bento & NotebookLM.
2. Tự động trích xuất Big Metrics ($67B, 85%), Timeline Roadmaps, Bento Points.
3. Sinh Video 10s AI qua Google Veo API chính thức (veo-3.1 / veo-2.0) và Google Flow.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from app.core.google_flow_engine import GoogleFlowEngine


GEMINI_API_HOST = "https://generativelanguage.googleapis.com"
API_VERSIONS = ["v1beta", "v1"]

DEFAULT_MODEL = "gemini-flash-latest"

VEO_CANDIDATE_MODELS = [
    "veo-3.1-generate-preview",
    "veo-2.0-generate-001",
    "veo-3.1-fast-generate-preview",
]

FALLBACK_CANDIDATE_MODELS = [
    "gemini-flash-latest",
    "gemini-3.7-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-pro-latest",
    "gemini-3.1-pro-preview",
    "gemini-2.5-pro",
    "gemini-3.1-flash-lite",
]

AVAILABLE_MODELS = [
    ("⚡ Gemini Flash Latest (Gemini 3.7 Flash - Khuyên dùng)", "gemini-flash-latest"),
    ("⚡ Gemini 3.7 Flash", "gemini-3.7-flash"),
    ("🚀 Gemini 3.5 Flash Lite (Siêu tốc & Tiết kiệm)", "gemini-3.5-flash-lite"),
    ("⚡ Gemini 3.6 Flash", "gemini-3.6-flash"),
    ("⚡ Gemini 2.5 Flash", "gemini-2.5-flash"),
    ("🧠 Gemini 3.1 Pro (Phân tích chuyên sâu)", "gemini-3.1-pro-preview"),
    ("🧠 Gemini Pro Latest", "gemini-pro-latest"),
]

IMAGE_CANDIDATE_MODELS = [
    "gemini-3.1-flash-image",
    "gemini-2.5-flash-image",
    "gemini-3-pro-image",
    "gemini-3.1-flash-lite-image",
    "imagen-3.0-generate-002",
]

NON_TEXT_KEYWORDS = ["tts", "audio", "image", "robotics", "embed", "aqa", "realtime", "live"]


def _is_valid_text_model(model_name: str) -> bool:
    m_lower = model_name.lower()
    return not any(kw in m_lower for kw in NON_TEXT_KEYWORDS)


def _parse_json_robust(raw_text: str) -> Dict[str, Any]:
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.MULTILINE).strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict) and "scenes" in data:
            return data
    except Exception:
        pass

    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate_json = cleaned[first_brace:last_brace + 1]
        try:
            data = json.loads(candidate_json)
            if isinstance(data, dict) and "scenes" in data:
                return data
        except Exception:
            pass

    scenes = []
    scene_matches = re.finditer(r'\{[^{}]*"scene_id"[^{}]*\}', cleaned)
    for m in scene_matches:
        try:
            s_obj = json.loads(m.group(0))
            if "voiceover_text" in s_obj or "slide_title" in s_obj:
                scenes.append(s_obj)
        except Exception:
            continue

    if scenes:
        return {
            "project_title": "Báo Cáo Phân Tích Chiến Lược",
            "summary": "Tổng hợp nội dung từ tài liệu",
            "scenes": scenes
        }

    raise ValueError(f"Không thể parse cấu trúc Storyboard từ phản hồi AI: {cleaned[:300]}")


class GeminiAIEngine:
    """Class điều phối toàn bộ các tác vụ AI qua Google Gemini & Google Veo."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key.strip()
        self.discovered_models: List[str] = []
        self.flow_engine = GoogleFlowEngine()

    def set_api_key(self, api_key: str):
        self.api_key = api_key.strip()

    def list_available_models(self) -> List[Tuple[str, str]]:
        if not self.api_key:
            return AVAILABLE_MODELS

        found_models = []
        for ver in API_VERSIONS:
            url = f"{GEMINI_API_HOST}/{ver}/models?key={self.api_key}"
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("models", [])
                    for m in models:
                        name = m.get("name", "").replace("models/", "")
                        methods = m.get("supportedGenerationMethods", [])
                        if "generateContent" in methods and _is_valid_text_model(name):
                            found_models.append(name)
                    if found_models:
                        break
            except Exception:
                continue

        if found_models:
            self.discovered_models = found_models
            res = []
            for m in found_models:
                if m == "gemini-flash-latest" or "3.7-flash" in m:
                    res.append((f"⚡ Gemini 3.7 Flash ({m})", m))
                elif "3.5-flash-lite" in m or m == "gemini-flash-lite-latest":
                    res.append((f"🚀 Gemini 3.5 Flash Lite ({m})", m))
                elif "3.6-flash" in m:
                    res.append((f"⚡ Gemini 3.6 Flash ({m})", m))
                elif "3.5-flash" in m:
                    res.append((f"⚡ Gemini 3.5 Flash ({m})", m))
                elif "2.5-flash" in m:
                    res.append((f"⚡ Gemini 2.5 Flash ({m})", m))
                elif "3.1-pro" in m or m == "gemini-pro-latest":
                    res.append((f"🧠 Gemini 3.1 Pro ({m})", m))
                elif "2.5-pro" in m:
                    res.append((f"🧠 Gemini 2.5 Pro ({m})", m))
                else:
                    res.append((f"✨ Gemini ({m})", m))
            if res:
                return res

        return AVAILABLE_MODELS

    def validate_api_key(self) -> Tuple[bool, str]:
        if not self.api_key:
            return False, "Chưa nhập API Key"

        last_error = ""
        model_list = []
        for ver in API_VERSIONS:
            url = f"{GEMINI_API_HOST}/{ver}/models?key={self.api_key}"
            try:
                resp = requests.get(url, timeout=12)
                if resp.status_code == 200:
                    data = resp.json()
                    for m in data.get("models", []):
                        name = m.get("name", "").replace("models/", "")
                        methods = m.get("supportedGenerationMethods", [])
                        if "generateContent" in methods and _is_valid_text_model(name):
                            model_list.append((ver, name))
                    if model_list:
                        break
                elif resp.status_code == 400:
                    return False, "API Key không hợp lệ (Lỗi 400: Invalid API Key)."
                elif resp.status_code == 403:
                    return False, "API Key bị từ chối quyền truy cập (Lỗi 403: Permission Denied)."
                else:
                    last_error = f"Lỗi {resp.status_code}: {resp.text[:200]}"
            except Exception as exc:
                last_error = str(exc)

        if not model_list:
            for cand in FALLBACK_CANDIDATE_MODELS:
                for ver in API_VERSIONS:
                    model_list.append((ver, cand))

        for ver, model_name in model_list:
            url = f"{GEMINI_API_HOST}/{ver}/models/{model_name}:generateContent?key={self.api_key}"
            payload = {
                "contents": [{"parts": [{"text": "Hello, respond with 1 word: OK"}]}]
            }
            try:
                resp = requests.post(url, json=payload, timeout=10)
                if resp.status_code == 200:
                    return True, f"API Key hợp lệ! Đã kết nối thành công với model '{model_name}'."
            except Exception:
                continue

        return False, f"Không thể kết nối với Gemini API:\n{last_error or 'Không tìm thấy model phù hợp.'}"

    def _call_gemini_generate(
        self,
        prompt: str,
        preferred_model: str = DEFAULT_MODEL,
        json_mode: bool = True,
        temperature: float = 0.3,
        timeout: int = 90,
    ) -> Dict[str, Any]:
        candidate_queue = []
        if _is_valid_text_model(preferred_model):
            candidate_queue.append(preferred_model)
        for m in self.discovered_models:
            if m not in candidate_queue and _is_valid_text_model(m):
                candidate_queue.append(m)
        for m in FALLBACK_CANDIDATE_MODELS:
            if m not in candidate_queue and _is_valid_text_model(m):
                candidate_queue.append(m)

        generation_config = {
            "temperature": temperature,
            "maxOutputTokens": 8192,
        }
        if json_mode:
            generation_config["response_mime_type"] = "application/json"

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": generation_config,
        }

        last_err = ""
        for model_name in candidate_queue:
            for ver in API_VERSIONS:
                url = f"{GEMINI_API_HOST}/{ver}/models/{model_name}:generateContent?key={self.api_key}"
                try:
                    resp = requests.post(url, json=payload, timeout=timeout)
                    if resp.status_code == 200:
                        data = resp.json()
                        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                        if json_mode:
                            return _parse_json_robust(raw_text)
                        else:
                            return {"text": raw_text}
                    elif resp.status_code in (400, 404):
                        last_err = f"Model '{model_name}' ({resp.status_code}): {resp.text[:150]}"
                        continue
                    elif resp.status_code == 403:
                        raise RuntimeError(f"Lỗi quyền/API Key (403): {resp.text}")
                    else:
                        last_err = f"HTTP {resp.status_code}: {resp.text[:150]}"
                except requests.exceptions.RequestException as e:
                    last_err = str(e)
                    continue

        raise RuntimeError(f"Không thể tạo phản hồi từ các model Gemini khả dụng:\n{last_err}")

    def analyze_document_to_storyboard(
        self,
        document_text: str,
        model_name: str = DEFAULT_MODEL,
        style: str = "review",
        target_scene_duration_sec: int = 10,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("Vui lòng cung cấp Gemini API Key hợp lệ.")

        if progress_callback:
            progress_callback(10, "Đang gửi tài liệu sang Gemini AI phân tích...")

        doc_len = len(document_text)
        est_scenes = "10 đến 16" if doc_len > 10000 else "6 đến 12"

        system_instruction = (
            "Bạn là Giám đốc Sáng tạo, Chuyên gia Thiết kế Presentation Bento chuẩn NotebookLM & Gemini Executive, kiêm Đạo diễn Kịch bản Video AI hàng đầu.\n"
            f"Nhiệm vụ của bạn là phân tích sâu sắc toàn bộ tài liệu đầu vào và chuyển thể thành một kịch bản Presentation hoàn chỉnh gồm {est_scenes} phân cảnh (Scenes).\n\n"
            "QUY TẮC BẮT BUỘC VỀ CẤU TRÚC KỊCH BẢN 3 PHẦN CHUYÊN NGHIỆP (MỞ ĐẦU - THÂN BÀI - KẾT THÚC):\n\n"
            "1. PHẦN 1: MỞ ĐẦU (Scene 1 - BẮT BUỘC LÀ SLIDE BÌA MỞ ĐẦU / TITLE & COVER):\n"
            "   - 'layout_type': 'hero_cover'\n"
            "   - 'category_tag': '🌟 BÁO CÁO PHÂN TÍCH CHUYÊN SÂU'\n"
            "   - 'slide_title': Tiêu đề chính của toàn bộ bài thuyết trình / video (Ngắn gọn, cuốn hút, ví dụ: '| Đại Dự Án Đường Sắt Tốc Độ Cao & Kỷ Nguyên Số').\n"
            "   - 'voiceover_text': Lời dẫn mở đầu thuyết minh (Hook/Intro chào mừng khán giả, đặt vấn đề hấp dẫn và mở ra bức tranh toàn cảnh) từ 50 đến 85 từ tiếng Việt.\n"
            "   - 'bullet_points': 1 dòng tóm tắt phụ đề / chủ đề ngắn gọn (ví dụ: ['Tổng quan chiến lược, kiến trúc công nghệ và lộ trình chuyển đổi số']). TUYỆT ĐỐI KHÔNG viết các gạch đầu dòng phân tích dài trên slide bìa.\n\n"
            "2. PHẦN 2: THÂN BÀI (Scenes 2 đến N-1 - CÁC PHÂN CẢNH NỘI DUNG CHUYÊN SÂU):\n"
            "   - Phân tích chi tiết từng khía cạnh, dữ liệu, số liệu, bài toán và giải pháp từ tài liệu.\n"
            "   - 'voiceover_text': Đoạn thuyết minh sâu sắc, liên kết từ 50 đến 85 từ tiếng Việt.\n"
            "   - 'bullet_points': MỖI BULLET TỪ 25 ĐẾN 50 TỪ với cấu trúc: [Tiêu đề / Trọng tâm]: [Phân tích chi tiết kèm số liệu và giải pháp].\n"
            "   - Đa dạng hóa 'layout_type' cho từng cảnh:\n"
            "     * 'stat_metric': Cảnh có số liệu to ($67B, 85%, 1.541 km, 10x, 99.9%).\n"
            "     * 'three_columns': 3 trụ cột cốt lõi / 3 giải pháp trọng tâm / 3 nhóm yếu tố.\n"
            "     * 'bento_grid_2x2': Ma trận 4 ô phân tích đa chiều (SWOT / 4 góc nhìn / 4 hợp phần).\n"
            "     * 'comparison_vs': So sánh đối lập (Thực trạng vs Giải pháp / Truyền thống vs Số hóa).\n"
            "     * 'timeline_process': Lộ trình triển khai theo mốc thời gian (2026-2027, 2027-2028,...).\n"
            "     * 'visual_split': Giải thích kiến trúc kỹ thuật / mô hình hệ thống có sơ đồ minh họa.\n\n"
            "3. PHẦN 3: KẾT THÚC (Scene N - BẮT BUỘC LÀ SLIDE BÌA KẾT THÚC / THANK YOU & OUTRO):\n"
            "   - 'layout_type': 'ending_outro'\n"
            "   - 'category_tag': '🎬 LỜI CẢM ƠN'\n"
            "   - 'slide_title': '| Cảm Ơn Các Bạn Đã Theo Dõi & Lắng Nghe'\n"
            "   - 'voiceover_text': Lời kết thuyết minh hoàn chỉnh từ 45 đến 75 từ tiếng Việt, đúc kết ngắn gọn giá trị cốt lõi, gửi lời cảm ơn khán giả đã dành thời gian theo dõi và gửi lời chúc tốt đẹp.\n"
            "   - 'bullet_points': ['Hy vọng bài thuyết trình đã mang lại những thông tin hữu ích và góc nhìn chiến lược toàn diện cho bạn.'].\n\n"
            "4. CÁC THÔNG SỐ KHÁC:\n"
            "   - 'theme_color': Chọn bảng màu chủ đạo cho từng slide ('sapphire', 'emerald', 'violet', 'amber', 'ruby', 'cyan', 'sunset').\n"
            "   - 'illustration_type': Chọn 1 trong các kiểu minh họa/biểu đồ tương thích nhất với nội dung cảnh ('growth_chart', 'donut_chart', 'neural_ai', 'cloud_architecture', 'global_mesh', 'strategy_target', 'workflow_pipeline', 'cyber_shield', 'speed_gauge', 'tech_matrix'). Chỉ chọn 'transit_network' khi tài liệu nói về đường sắt/tàu hỏa.\n"
            "   - 'visual_type': MẶC ĐỊNH LÀ 'pptx' cho tất cả các phân cảnh.\n"
            "   - 'image_prompt' & 'video_prompt': Prompt tiếng Anh mô tả chi tiết hình ảnh/video 4K điện ảnh.\n\n"
            "ĐỊNH DẠNG ĐẦU RA BẮT BUỘC LÀ JSON CHUẨN:\n"
            "{\n"
            '  "project_title": "Tiêu đề tài liệu tổng quan",\n'
            '  "summary": "Tóm tắt ngắn gọn 1-2 câu",\n'
            '  "scenes": [\n'
            "    {\n"
            '      "scene_id": 1,\n'
            '      "slide_title": "| Đại Dự Án Đường Sắt Tốc Độ Cao & Kỷ Nguyên Số",\n'
            '      "layout_type": "hero_cover",\n'
            '      "theme_color": "sapphire",\n'
            '      "illustration_type": "tech_matrix",\n'
            '      "category_tag": "🌟 BÁO CÁO PHÂN TÍCH CHUYÊN SÂU",\n'
            '      "bullet_points": [\n'
            '        "Tổng quan chiến lược, kiến trúc công nghệ và lộ trình chuyển đổi số toàn diện."\n'
            '      ],\n'
            '      "voiceover_text": "Chào mừng các bạn đến với bản phân tích chuyên sâu hôm nay. Việt Nam đang chính thức bước vào kỷ nguyên mới với đại dự án đường sắt tốc độ cao quy mô 67 tỷ USD. Đây không chỉ đơn thuần là công trình hạ tầng giao thông khổng lồ, mà là cuộc cách mạng công nghệ đòi hỏi sự đột phá toàn diện về hệ thống viễn thông, tín hiệu số và trung tâm điều hành thông minh.",\n'
            '      "visual_type": "pptx",\n'
            '      "image_prompt": "Cinematic modern high speed bullet train on futuristic track across Vietnam landscape, 8k resolution, photorealistic",\n'
            '      "video_prompt": "Cinematic forward drone tracking shot of high-speed train speeding through scenic landscape 10s"\n'
            "    }\n"
            "  ]\n"
            "}"
        )

        user_prompt = f"{system_instruction}\n\nDƯỚI ĐÂY LÀ TOÀN BỘ NỘI DUNG TÀI LIỆU CẦN CHUYỂN THỂ:\n\n{document_text}"

        if progress_callback:
            progress_callback(30, "Gemini đang phân tích chi tiết & tạo bộ Slide đa phong cách...")

        storyboard = self._call_gemini_generate(
            prompt=user_prompt,
            preferred_model=model_name,
            json_mode=True,
            temperature=0.3,
            timeout=90,
        )

        VALID_LAYOUTS = [
            "hero_cover", "three_columns", "visual_split", "stat_metric",
            "bento_grid_2x2", "comparison_vs", "timeline_process", "key_takeaway_quote", "ending_outro"
        ]
        THEMES = ["sapphire", "emerald", "violet", "amber", "ruby", "cyan", "sunset"]

        from app.core.pptx_builder import resolve_illustration_type

        scenes = storyboard.get("scenes", [])
        total_sc = len(scenes)

        for idx, scene in enumerate(scenes, 1):
            scene["scene_id"] = idx
            # Mặc định tất cả là pptx (Slide)
            scene["visual_type"] = "pptx"

            clean_title = scene.get("slide_title", "").replace("|", "").strip()
            voiceover = scene.get("voiceover_text", "")
            bullets = scene.get("bullet_points", [])
            all_text = (clean_title + " " + voiceover + " " + " ".join(bullets)).lower()

            l_type = scene.get("layout_type", "")
            if l_type not in VALID_LAYOUTS or l_type in ["", "standard", "bento", "custom"]:
                if idx == 1:
                    l_type = "hero_cover"
                elif idx == total_sc and total_sc >= 2:
                    l_type = "ending_outro"
                elif any(re.search(p, all_text) for p in [r'\b20\d\d\b', r'giai đoạn', r'lộ trình', r'roadmap', r'triển khai', r'bước \d', r'kế hoạch']):
                    l_type = "timeline_process"
                elif any(w in all_text for w in ["kiến trúc", "hệ thống", "occ", "sơ đồ", "mô hình", "onboard", "trackside", "điều hành", "tín hiệu", "hạ tầng số", "diagram", "cabin"]):
                    l_type = "visual_split"
                elif any(_extract_metric(b) for b in bullets + [clean_title]):
                    l_type = "stat_metric"
                elif any(w in all_text for w in ["so sánh", "thực trạng", "nghịch lý", "thách thức", "đối lập", "trước vs sau", "vấn đề", "hạn chế"]):
                    l_type = "comparison_vs"
                elif len(bullets) == 3:
                    l_type = "three_columns"
                elif len(bullets) >= 4:
                    l_type = "bento_grid_2x2"
                else:
                    cycle = ["three_columns", "visual_split", "bento_grid_2x2", "stat_metric", "timeline_process", "comparison_vs"]
                    l_type = cycle[(idx - 1) % len(cycle)]

            # Đảm bảo cảnh 1 luôn là hero_cover và cảnh cuối luôn là ending_outro
            if idx == 1:
                l_type = "hero_cover"
            elif idx == total_sc and total_sc >= 2:
                l_type = "ending_outro"
            elif idx > 1 and scenes[idx - 2].get("layout_type") == l_type and l_type not in ["hero_cover", "ending_outro", "key_takeaway_quote"]:
                avail = [lt for lt in VALID_LAYOUTS if lt != l_type and lt not in ["hero_cover", "ending_outro", "key_takeaway_quote"]]
                l_type = avail[(idx - 1) % len(avail)]

            scene["layout_type"] = l_type
            scene["theme_color"] = THEMES[(idx - 1) % len(THEMES)]
            scene["illustration_type"] = resolve_illustration_type(scene, slide_idx=idx)

        if progress_callback:
            progress_callback(100, f"Hoàn tất phân tích {len(scenes)} phân cảnh Slide chuyên nghiệp!")

        return storyboard

        if progress_callback:
            progress_callback(100, f"Hoàn tất phân tích {len(scenes)} phân cảnh Slide chuyên nghiệp!")

        return storyboard

    def generate_ai_video_10s(
        self,
        prompt: str,
        output_path: str,
        image_path: Optional[str] = None,
        progress_callback: Optional[callable] = None,
    ) -> Tuple[bool, str]:
        """
        Sinh Video AI 10s bằng Google Veo API chính thức (veo-3.1 / veo-2.0)
        hoặc Google Flow / AI Video Engine.
        """
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        def report(pct: int, msg: str):
            if progress_callback:
                progress_callback(pct, msg)

        # ── 1. Thử gọi Google Veo API trực tiếp qua Google GenAI SDK ──
        if self.api_key:
            report(15, "Đang kết nối Google Veo API chính thức (Google GenAI)...")
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=self.api_key)
                for veo_model in VEO_CANDIDATE_MODELS:
                    try:
                        report(25, f"Đang gửi yêu cầu sinh Video tới {veo_model}...")
                        operation = client.models.generate_videos(
                            model=veo_model,
                            prompt=f"{prompt}, cinematic 4k, 10s video, photorealistic, 60fps",
                            config=types.GenerateVideosConfig(
                                aspect_ratio="16:9",
                            ),
                        )

                        # Polling operation
                        poll_count = 0
                        while not operation.done and poll_count < 30:
                            time.sleep(8)
                            poll_count += 1
                            report(30 + min(poll_count * 2, 55), f"Google Veo đang render Video AI ({poll_count * 8}s)...")
                            operation = client.operations.get(operation)

                        if operation.done and operation.response:
                            gen_vids = operation.response.generated_videos
                            if gen_vids and len(gen_vids) > 0:
                                v_obj = gen_vids[0].video
                                report(90, "Đang lưu file Video Google Veo...")
                                if hasattr(v_obj, "save"):
                                    v_obj.save(str(out_p))
                                elif hasattr(v_obj, "video_bytes") and v_obj.video_bytes:
                                    with open(str(out_p), "wb") as f:
                                        f.write(v_obj.video_bytes)
                                elif hasattr(v_obj, "uri") and v_obj.uri:
                                    v_resp = requests.get(v_obj.uri, timeout=60)
                                    if v_resp.status_code == 200:
                                        with open(str(out_p), "wb") as f:
                                            f.write(v_resp.content)

                                if out_p.exists() and out_p.stat().st_size > 10000:
                                    report(100, f"Đã sinh Video AI bằng {veo_model} thành công!")
                                    return True, str(out_p)
                    except Exception:
                        continue
            except Exception:
                pass

        # ── 2. Thử Google Flow / Downloads Pull / AI Video Engine ──
        return self.flow_engine.generate_video_flow(
            prompt=prompt,
            output_path=output_path,
            image_path=image_path,
            duration_sec=10.0,
            progress_callback=progress_callback,
        )

    def generate_image_imagen(
        self,
        prompt: str,
        output_path: str,
        aspect_ratio: str = "16:9",
        progress_callback: Optional[callable] = None,
    ) -> Tuple[bool, str]:
        if progress_callback:
            progress_callback(20, "Đang gửi prompt tạo ảnh 4K...")

        if self.api_key:
            for img_model in IMAGE_CANDIDATE_MODELS:
                for ver in ["v1beta", "v1"]:
                    url = f"{GEMINI_API_HOST}/{ver}/models/{img_model}:predict?key={self.api_key}"
                    payload = {
                        "instances": [
                            {
                                "prompt": f"{prompt}, high quality 4k resolution, 16:9 widescreen, photorealistic masterpiece, no text, sharp focus"
                            }
                        ],
                        "parameters": {
                            "sampleCount": 1,
                            "aspectRatio": aspect_ratio,
                            "outputMimeType": "image/jpeg",
                        }
                    }

                    try:
                        resp = requests.post(url, json=payload, timeout=35)
                        if resp.status_code == 200:
                            res_json = resp.json()
                            predictions = res_json.get("predictions", [])
                            if predictions and "bytesBase64Encoded" in predictions[0]:
                                b64_data = predictions[0]["bytesBase64Encoded"]
                                img_bytes = base64.b64decode(b64_data)
                                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                                with open(output_path, "wb") as f:
                                    f.write(img_bytes)
                                if progress_callback:
                                    progress_callback(100, f"Tạo ảnh bằng {img_model} thành công!")
                                return True, output_path
                    except Exception:
                        pass

        if progress_callback:
            progress_callback(50, "Đang kết nối AI Image Engine...")

        try:
            encoded_prompt = urllib.parse.quote(f"{prompt} 16:9 cinematic photography 4k photorealistic sharp")
            fallback_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1920&height=1080&nologo=true&enhance=true&seed={os.urandom(2).hex()}"
            
            f_resp = requests.get(fallback_url, timeout=35)
            if f_resp.status_code == 200 and len(f_resp.content) > 5000:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(f_resp.content)
                if progress_callback:
                    progress_callback(100, "Đã tạo ảnh minh họa 16:9 thành công!")
                return True, output_path
        except Exception as fb_err:
            return False, f"Không thể sinh ảnh: {fb_err}"

        return False, "Không thể tạo ảnh từ các dịch vụ AI."
