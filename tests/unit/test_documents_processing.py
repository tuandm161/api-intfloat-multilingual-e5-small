from app.modules.documents.extractors import ExtractedPage
from app.modules.documents.processing import clean_pages, split_into_chunks
from app.modules.paraphrase.providers.api import ApiParaphraseGenerator


def test_clean_pages_and_split_chunks_preserve_metadata_and_overlap() -> None:
    pages = clean_pages(
        [
            ExtractedPage(
                1,
                "Giáo trình ABC\n\nAirway - Breathing - Circulation giúp ưu tiên cấp cứu. " * 20,
            ),
            ExtractedPage(
                2,
                "Breathing cần được đánh giá để phát hiện suy hô hấp. " * 20,
            ),
        ]
    )

    chunks = split_into_chunks(pages, target_chars=450, max_chars=650, overlap_chars=80)

    assert len(chunks) >= 2
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 2
    assert chunks[0].text[-40:] in chunks[1].text


def test_api_paraphrase_response_parser_accepts_json_candidates() -> None:
    stems = ApiParaphraseGenerator._parse_stems(
        {"candidates": [{"stem": "Câu hỏi đã được viết lại là gì?"}]},
        3,
    )

    assert stems == ["Câu hỏi đã được viết lại là gì?"]
