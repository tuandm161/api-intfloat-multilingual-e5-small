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
    section_path: str | None
    text: str
    text_hash: str
    token_count: int
    quality_flags: list[str]


@dataclass
class SectionDraft:
    section_index: int
    title: str
    level: int
    parent_index: int | None
    page_start: int | None
    page_end: int | None
    path: str
    confidence: float


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
    section_drafts = build_section_tree(pages)
    default_section = section_drafts[0] if len(section_drafts) == 1 else None
    section_title: str | None = default_section.title if default_section else None
    section_path: str | None = default_section.path if default_section else None
    title_to_path = _section_path_lookup(section_drafts)

    def flush() -> None:
        nonlocal current, current_len, section_title, section_path
        if not current:
            return
        text = "\n\n".join(segment for _, segment, _ in current).strip()
        if not text:
            current = []
            current_len = 0
            return
        page_numbers = [page for page, _, _ in current if page]
        titles = [title for _, _, title in current if title]
        effective_title = titles[-1] if titles else section_title
        effective_path = title_to_path.get(effective_title or "") or section_path
        chunks.append(
            ChunkDraft(
                chunk_index=len(chunks) + 1,
                page_start=min(page_numbers) if page_numbers else None,
                page_end=max(page_numbers) if page_numbers else None,
                section_title=effective_title,
                section_path=effective_path,
                text=text,
                text_hash=hash_normalized_text(text),
                token_count=_estimate_token_count(text),
                quality_flags=_chunk_quality_flags(text, effective_title),
            )
        )
        carry = _overlap_tail(text, overlap_chars) if overlap_chars > 0 else ""
        carry_page = page_numbers[-1] if page_numbers else 0
        current = [(carry_page, carry, section_title)] if carry else []
        current_len = len(carry)

    for page_number, segment, detected_title in segments:
        if detected_title:
            section_title = detected_title
            section_path = title_to_path.get(detected_title)
        if current_len and current_len + len(segment) > target_chars:
            flush()
        current.append((page_number, segment, section_title))
        current_len += len(segment)
        if current_len >= max_chars:
            flush()
    flush()
    return [chunk for chunk in chunks if len(chunk.text.strip()) >= 40]


def build_section_tree(pages: list[CleanPage]) -> list[SectionDraft]:
    sections: list[SectionDraft] = []
    stack: list[SectionDraft] = []
    for page in pages:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", page.text) if part.strip()]
        for paragraph in paragraphs:
            if not _looks_like_heading(paragraph):
                continue
            level = _heading_level(paragraph)
            while stack and stack[-1].level >= level:
                stack.pop()
            parent = stack[-1] if stack else None
            path_parts = [*(parent.path.split(" > ") if parent else []), paragraph]
            section = SectionDraft(
                section_index=len(sections) + 1,
                title=paragraph[:255],
                level=level,
                parent_index=parent.section_index if parent else None,
                page_start=page.page_number,
                page_end=page.page_number,
                path=" > ".join(path_parts)[:1000],
                confidence=0.85,
            )
            sections.append(section)
            stack.append(section)
        for section in stack:
            section.page_end = page.page_number
    if sections:
        return sections
    page_numbers = [page.page_number for page in pages if page.text.strip()]
    return [
        SectionDraft(
            section_index=1,
            title="Tài liệu",
            level=1,
            parent_index=None,
            page_start=min(page_numbers) if page_numbers else None,
            page_end=max(page_numbers) if page_numbers else None,
            path="Tài liệu",
            confidence=0.35,
        )
    ]


def _clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text, flags=re.UNICODE)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    compact: list[str] = []
    blank = False
    for line in lines:
        if _looks_like_noise_line(line):
            continue
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
    sentences = re.split(r"(?<=[.!?。！？])\s+", paragraph)
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
    if re.match(r"^(?:chương|bài|mục|phần)\s+\S+", text, flags=re.IGNORECASE):
        return True
    if re.match(r"^(?:[IVXLCDM]+|[A-Z]|\d+(?:\.\d+){0,3})[.)]?\s+\S+", text):
        return True
    return bool(re.search(r"[A-Za-zÀ-ỹ]", text))


def _heading_level(text: str) -> int:
    lowered = text.casefold()
    if lowered.startswith(("chương ", "phần ")):
        return 1
    if lowered.startswith(("bài ", "mục ")):
        return 2
    numbered = re.match(r"^(\d+(?:\.\d+){0,3})[.)]?\s+\S+", text)
    if numbered:
        return min(4, numbered.group(1).count(".") + 1)
    if re.match(r"^[IVXLCDM]+[.)]?\s+\S+", text):
        return 1
    if re.match(r"^[A-Z][.)]\s+\S+", text):
        return 2
    return 3


def _section_path_lookup(sections: list[SectionDraft]) -> dict[str, str]:
    return {section.title: section.path for section in sections}


def _estimate_token_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _chunk_quality_flags(text: str, section_title: str | None) -> list[str]:
    flags: list[str] = []
    token_count = _estimate_token_count(text)
    if token_count < 40:
        flags.append("LOW_INFORMATION_DENSITY")
    if token_count > 1200:
        flags.append("ABOVE_TARGET_TOKEN_RANGE")
    if not section_title:
        flags.append("LOW_SECTION_CONFIDENCE")
    if _looks_like_noise_line(text.strip()):
        flags.append("NOISE_LIKE_TEXT")
    return flags


def _looks_like_noise_line(line: str) -> bool:
    if not line:
        return False
    if re.fullmatch(r"[-–—_ .]*\d+[-–—_ .]*", line):
        return True
    if re.fullmatch(r"\d+\s*/\s*\d+", line):
        return True
    if re.search(r"\.{4,}\s*\d+\s*$", line):
        return True
    return False


def _overlap_tail(text: str, overlap_chars: int) -> str:
    if overlap_chars <= 0:
        return ""
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    selected: list[str] = []
    total = 0
    for paragraph in reversed(paragraphs):
        if selected and total + len(paragraph) > overlap_chars:
            break
        selected.append(paragraph)
        total += len(paragraph)
        if total >= overlap_chars * 0.7:
            break
    if selected:
        return "\n\n".join(reversed(selected)).strip()

    sentences = [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+", text) if part.strip()]
    selected_sentences: list[str] = []
    total = 0
    for sentence in reversed(sentences):
        if selected_sentences and total + len(sentence) > overlap_chars:
            break
        selected_sentences.append(sentence)
        total += len(sentence)
        if total >= overlap_chars * 0.7:
            break
    if selected_sentences:
        return " ".join(reversed(selected_sentences)).strip()
    return text[-overlap_chars:].strip()
