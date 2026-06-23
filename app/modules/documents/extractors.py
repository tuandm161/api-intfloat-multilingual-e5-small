"""Text extraction for supported document formats."""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from app.core.enums import ErrorCode
from app.core.errors import AppError


@dataclass
class ExtractedPage:
    page_number: int
    text: str


def extract_pages(filename: str, content: bytes) -> list[ExtractedPage]:
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md"}:
        return [ExtractedPage(page_number=1, text=_decode_text(content))]
    if suffix == ".pdf":
        return _extract_pdf(content)
    if suffix == ".docx":
        return _extract_docx(content)
    raise AppError(
        ErrorCode.VALIDATION_ERROR,
        "Chỉ hỗ trợ tài liệu PDF, DOCX, TXT hoặc MD",
        details={"filename": filename},
    )


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1258"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


def _extract_pdf(content: bytes) -> list[ExtractedPage]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            "Thiếu thư viện pypdf để đọc PDF",
            status_code=500,
        ) from exc

    reader = PdfReader(BytesIO(content))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        pages.append(ExtractedPage(page_number=index, text=page.extract_text() or ""))
    return pages


def _extract_docx(content: bytes) -> list[ExtractedPage]:
    try:
        from docx import Document as DocxDocument
    except ImportError as exc:
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            "Thiếu thư viện python-docx để đọc DOCX",
            status_code=500,
        ) from exc

    document = DocxDocument(BytesIO(content))
    parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    return [ExtractedPage(page_number=1, text="\n\n".join(parts))]
