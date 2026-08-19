import os

from app.rag.chunking import chunk_parsed_document, split_text_recursively
from app.rag.parser import ParsedDocument, ParsedPage, parse_markdown_file


def test_split_text_recursively_short() -> None:
    text = "Short guideline sentence."
    chunks = split_text_recursively(text, max_chars=1600, overlap_chars=320)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_split_text_recursively_long() -> None:
    paragraphs = [
        f"Paragraph {i}: " + ("This is standard operating procedure text. " * 15) for i in range(10)
    ]
    long_text = "\n\n".join(paragraphs)
    chunks = split_text_recursively(long_text, max_chars=800, overlap_chars=160)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 1000  # Within bounds with separator tolerance


def test_parse_markdown_file() -> None:
    sample_file = os.path.join(
        os.path.dirname(__file__), "../../data/kb/raw/sphere_handbook_standards.md"
    )
    if os.path.exists(sample_file):
        parsed = parse_markdown_file(sample_file)
        assert parsed.title != ""
        assert len(parsed.pages) == 1
        assert "Water Supply" in parsed.pages[0].text


def test_chunk_parsed_document_metadata() -> None:
    doc = ParsedDocument(
        filename="test_doc.md",
        title="Test Flood Guidelines",
        pages=[
            ParsedPage(
                page_number=1,
                text=(
                    "# Heading 1\n\nContent for section 1.\n\n"
                    "# Heading 2\n\nContent for section 2."
                ),
            )
        ],
    )
    chunks = chunk_parsed_document(doc, doc_id="doc-123", doc_type="SOP", disaster_type="FLOOD")
    assert len(chunks) >= 2
    assert chunks[0].metadata["doc_id"] == "doc-123"
    assert chunks[0].metadata["doc_type"] == "SOP"
    assert chunks[0].metadata["disaster_type"] == "FLOOD"
    assert chunks[0].page_number == 1
