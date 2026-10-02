"""
file_reader.py — Đọc nội dung từ file .txt, .docx, .pdf, .md
"""

from pathlib import Path
import re


def read_file(file_path: str) -> str:
    """
    Đọc nội dung văn bản từ file .txt, .docx, .pdf hoặc .md.
    Trả về chuỗi văn bản đã được chuẩn hóa.
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext in (".txt", ".md", ".csv"):
        return _read_txt(path)
    elif ext == ".docx":
        return _read_docx(path)
    elif ext == ".pdf":
        return _read_pdf(path)
    else:
        raise ValueError(f"Định dạng file không được hỗ trợ: '{ext}'. Hỗ trợ .txt, .docx, .pdf, .md")


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
    """Đọc file .docx, lấy text từ từng paragraph và table."""
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

    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                lines.append(row_text)

    return _normalize("\n".join(lines))


def _read_pdf(path: Path) -> str:
    """Đọc file .pdf bằng PyMuPDF (fitz)."""
    try:
        import fitz
    except ImportError:
        raise ImportError("Thiếu thư viện PyMuPDF. Chạy: pip install PyMuPDF")

    doc = fitz.open(str(path))
    lines = []
    for page in doc:
        text = page.get_text().strip()
        if text:
            lines.append(text)
    doc.close()

    return _normalize("\n\n".join(lines))


def _normalize(text: str) -> str:
    """Chuẩn hóa văn bản: xóa khoảng trắng thừa, chuẩn hóa dòng."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
