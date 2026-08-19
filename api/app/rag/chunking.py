from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from app.rag.parser import ParsedDocument


@dataclass
class DocumentChunk:
    chunk_index: int
    text: str
    page_number: int
    token_count: int
    heading_path: str
    metadata: dict[str, Any]


def estimate_token_count(text: str) -> int:
    """Approximate token count using word/whitespace and character heuristics (4 chars/token)."""
    return max(1, len(text) // 4)


def split_text_recursively(
    text: str,
    max_chars: int = 1600,  # ~400 tokens
    overlap_chars: int = 320,  # ~80 tokens
) -> list[str]:
    """Recursively splits text on double-newlines, single-newlines, sentences, then spaces."""
    if len(text) <= max_chars:
        clean = text.strip()
        return [clean] if clean else []

    separators = ["\n\n", "\n", ". ", " ", ""]
    chunks: list[str] = []

    def _split(subtext: str, sep_idx: int) -> None:
        if not subtext.strip():
            return
        if len(subtext) <= max_chars or sep_idx >= len(separators):
            clean = subtext.strip()
            if clean:
                chunks.append(clean)
            return

        sep = separators[sep_idx]
        if sep == "":
            # Hard split
            start = 0
            while start < len(subtext):
                end = start + max_chars
                chunks.append(subtext[start:end].strip())
                start = end - overlap_chars
            return

        splits = subtext.split(sep)
        current_chunk: list[str] = []
        current_len = 0

        for part in splits:
            part_len = len(part) + len(sep)
            if current_len + part_len > max_chars and current_chunk:
                merged = sep.join(current_chunk).strip()
                if merged:
                    chunks.append(merged)
                # Keep overlap if possible
                overlap_text = sep.join(current_chunk[-2:]) if len(current_chunk) > 1 else ""
                current_chunk = [overlap_text, part] if overlap_text else [part]
                current_len = sum(len(p) + len(sep) for p in current_chunk)
            else:
                current_chunk.append(part)
                current_len += part_len

        if current_chunk:
            merged = sep.join(current_chunk).strip()
            if merged:
                chunks.append(merged)

    _split(text, 0)
    return chunks


def chunk_parsed_document(
    doc: ParsedDocument,
    doc_id: str,
    doc_type: str = "SOP",
    disaster_type: str | None = None,
    max_tokens: int = 400,
    overlap_tokens: int = 80,
) -> list[DocumentChunk]:
    """Break a parsed document into indexed chunks with heading tracking and metadata."""
    max_chars = max_tokens * 4
    overlap_chars = overlap_tokens * 4

    result: list[DocumentChunk] = []
    chunk_idx = 0
    current_heading = doc.title

    for page in doc.pages:
        # Check for markdown headings in this page
        text_blocks = page.text.split("\n\n")

        for block in text_blocks:
            lines = block.strip().split("\n")
            for line in lines:
                if line.startswith("#"):
                    current_heading = line.lstrip("#").strip()

            split_blocks = split_text_recursively(block, max_chars=max_chars, overlap_chars=overlap_chars)
            for split_txt in split_blocks:
                tokens = estimate_token_count(split_txt)
                chunk = DocumentChunk(
                    chunk_index=chunk_idx,
                    text=split_txt,
                    page_number=page.page_number,
                    token_count=tokens,
                    heading_path=current_heading,
                    metadata={
                        "doc_id": doc_id,
                        "doc_title": doc.title,
                        "doc_type": doc_type,
                        "disaster_type": disaster_type,
                        "page_number": page.page_number,
                    },
                )
                result.append(chunk)
                chunk_idx += 1

    return result
