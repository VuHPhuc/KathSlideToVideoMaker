"""
file_reader.py — Đọc nội dung từ file .txt hoặc .docx
"""

from pathlib import Path


def read_file(file_path: str) -> str:
    """
    Đọc nội dung văn bản từ file .txt hoặc .docx.
    Trả về chuỗi văn bản đã được chuẩn hóa.
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".txt":
        return _read_txt(path)
    elif ext == ".docx":
        return _read_docx(path)
    else:
        raise ValueError(f"Định dạng file không được hỗ trợ: '{ext}'. Chỉ hỗ trợ .txt và .docx")


def _read_txt(path: Path) -> str:
    """Đọc file text, thử nhiều encoding phổ biến."""
    encodings = ["utf-8", "utf-8-sig", "cp1258", "latin-1"]
    for enc in encodings:
        try:
            text = path.read_text(encoding=enc)
            return _normalize(text)
        except (UnicodeDecodeError, LookupError):
            continue
    raise RuntimeError(f"Không thể đọc file '{path.name}': không xác định được mã hóa ký tự.")


def _read_docx(path: Path) -> str:
    """Đọc file .docx, lấy text từ từng paragraph."""
    try:
        import docx
    except ImportError:
        raise ImportError("Thiếu thư viện python-docx. Chạy: pip install python-docx")

    doc = docx.Document(str(path))
    lines = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            lines.append(text)

    return _normalize("\n".join(lines))


def _normalize(text: str) -> str:
    """Chuẩn hóa văn bản: xóa khoảng trắng thừa, chuẩn hóa dòng."""
    # Chuẩn hóa line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Xóa dòng trắng liên tiếp quá 2 dòng
    import re
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
