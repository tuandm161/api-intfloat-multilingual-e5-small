"""Document cleaning and chunking utilities."""

from collections import Counter
from dataclasses import dataclass
import re
import unicodedata

from app.modules.documents.extractors import ExtractedPage
from app.modules.normalization.text_normalizer import hash_normalized_text


@dataclass
class CleanPage:
    page_number: int
    text: str


@dataclass
class ChunkDraft:
    chunk_index: int
    page_start: int | None
    page_end: int | None
    section_title: str | None
    text: str
    text_hash: str


def clean_pages(pages: list[ExtractedPage]) -> list[CleanPage]:
    cleaned = [CleanPage(page.page_number, _clean_text(page.text)) for page in pages]
    repeated = _repeated_short_lines(cleaned)
    if repeated:
        cleaned = [
            CleanPage(
                page.page_number,
                "\n".join(
                    line for line in page.text.splitlines() if line.strip() not in repeated
                ).strip(),
            )
            for page in cleaned
        ]
    return cleaned


def split_into_chunks(
    pages: list[CleanPage],
    *,
    target_chars: int,
    max_chars: int,
    overlap_chars: int,
) -> list[ChunkDraft]:
    segments = _segments_from_pages(pages, max_chars)
    chunks: list[ChunkDraft] = []
    current: list[tuple[int, str, str | None]] = []
    current_len = 0
    section_title: str | None = None

    def flush() -> None:
        nonlocal current, current_len, section_title
        if not current:
            return
        text = "\n\n".join(segment for _, segment, _ in current).strip()
        if not text:
            current = []
            current_len = 0
            return
        page_numbers = [page for page, _, _ in current if page]
        titles = [title for _, _, title in current if title]
        chunks.append(
            ChunkDraft(
                chunk_index=len(chunks) + 1,
                page_start=min(page_numbers) if page_numbers else None,
                page_end=max(page_numbers) if page_numbers else None,
                section_title=titles[-1] if titles else section_title,
                text=text,
                text_hash=hash_normalized_text(text),
            )
        )
        carry = text[-overlap_chars:].strip() if overlap_chars > 0 else ""
        carry_page = page_numbers[-1] if page_numbers else 0
        current = [(carry_page, carry, section_title)] if carry else []
        current_len = len(carry)

    for page_number, segment, detected_title in segments:
        if detected_title:
            section_title = detected_title
        if current_len and current_len + len(segment) > target_chars:
            flush()
        current.append((page_number, segment, section_title))
        current_len += len(segment)
        if current_len >= max_chars:
            flush()
    flush()
    return [chunk for chunk in chunks if len(chunk.text.strip()) >= 40]


def _clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text, flags=re.UNICODE)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    compact: list[str] = []
    blank = False
    for line in lines:
        if not line:
            if not blank:
                compact.append("")
            blank = True
            continue
        compact.append(line)
        blank = False
    return "\n".join(compact).strip()


def _repeated_short_lines(pages: list[CleanPage]) -> set[str]:
    if len(pages) < 3:
        return set()
    counts: Counter[str] = Counter()
    for page in pages:
        seen = {line.strip() for line in page.text.splitlines() if 0 < len(line.strip()) <= 80}
        counts.update(seen)
    minimum = min(3, len(pages)) if pages else 0
    return {line for line, count in counts.items() if minimum and count >= minimum}


def _segments_from_pages(
    pages: list[CleanPage],
    max_chars: int,
) -> list[tuple[int, str, str | None]]:
    segments: list[tuple[int, str, str | None]] = []
    for page in pages:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", page.text) if part.strip()]
        for paragraph in paragraphs:
            title = paragraph if _looks_like_heading(paragraph) else None
            for piece in _split_long_paragraph(paragraph, max_chars):
                segments.append((page.page_number, piece, title))
    return segments


def _split_long_paragraph(paragraph: str, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]
    sentences = re.split(r"(?<=[.!?。])\s+", paragraph)
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > max_chars:
            pieces.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current.strip())
    return pieces


def _looks_like_heading(text: str) -> bool:
    if len(text) > 90 or len(text.split()) > 12:
        return False
    if text.endswith((".", "?", "!", ":", ";")):
        return False
    return bool(re.search(r"[A-Za-zÀ-ỹ]", text))
