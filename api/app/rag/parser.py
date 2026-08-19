from __future__ import annotations

import os
from dataclasses import dataclass
from typing import BinaryIO
from app.core.logging import logger


@dataclass
class ParsedPage:
    page_number: int
    text: str


@dataclass
class ParsedDocument:
    filename: str
    title: str
    pages: list[ParsedPage]


def parse_markdown_file(file_path: str) -> ParsedDocument:
    """Parse a Markdown text file into a ParsedDocument."""
    filename = os.path.basename(file_path)
    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    # Extract title from first H1 if present
    title = filename
    for line in content.splitlines():
        if line.strip().startswith("# "):
            title = line.strip("# ").strip()
            break

    return ParsedDocument(
        filename=filename,
        title=title,
        pages=[ParsedPage(page_number=1, text=content)],
    )


def parse_pdf_file(file_path_or_stream: str | BinaryIO, filename: str = "document.pdf") -> ParsedDocument:
    """Parse a PDF file into pages using pypdf."""
    try:
        from pypdf import PdfReader  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("pypdf_not_installed")
        return ParsedDocument(
            filename=filename,
            title=filename,
            pages=[ParsedPage(page_number=1, text="")],
        )

    reader = PdfReader(file_path_or_stream)
    pages: list[ParsedPage] = []

    for i, page in enumerate(reader.pages, start=1):
        extracted = page.extract_text() or ""
        pages.append(ParsedPage(page_number=i, text=extracted))

    # Read title from metadata or fallback
    title = filename
    if reader.metadata and reader.metadata.title:
        title = reader.metadata.title

    return ParsedDocument(
        filename=filename,
        title=title,
        pages=pages,
    )
