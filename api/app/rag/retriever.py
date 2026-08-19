from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.enums import DisasterType
from app.db.models.knowledge import KBDocument, KBChunk
from app.rag.embeddings import embedding_service


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    doc_title: str
    doc_type: str
    disaster_type: DisasterType | None
    page_number: int
    heading_path: str | None
    text: str
    vector_score: float
    lexical_score: float
    hybrid_score: float
    publication_date: date | None
    valid_until: date | None


def compute_bm25_lexical_score(query: str, text: str) -> float:
    """Compute a lightweight term-frequency lexical overlap score normalized to [0, 1]."""
    q_terms = set(re_clean(query).split())
    if not q_terms:
        return 0.0

    doc_words = re_clean(text).split()
    if not doc_words:
        return 0.0

    matches = sum(1 for term in q_terms if term in doc_words)
    # Simple Jaccard/overlap heuristic normalized between 0 and 1
    overlap = matches / len(q_terms)
    # Bonus for exact query phrase match
    phrase_bonus = 0.3 if query.lower().strip() in text.lower() else 0.0
    return min(1.0, overlap * 0.7 + phrase_bonus)


def re_clean(text: str) -> str:
    import re
    return re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())


def is_document_stale(pub_date: date | None, valid_until: date | None) -> bool:
    """Check if document has expired or is older than configured KB_STALE_YEARS."""
    today = datetime.now(UTC).date()

    if valid_until is not None and valid_until < today:
        return True

    if pub_date is not None:
        years_old = (today - pub_date).days / 365.25
        if years_old > settings.KB_STALE_YEARS:
            return True

    return False


class HybridRetriever:
    def __init__(self) -> None:
        self.score_floor = settings.RAG_SCORE_FLOOR  # 0.35
        self.default_top_k = settings.RAG_TOP_K  # 8

    async def search(
        self,
        db: AsyncSession,
        query: str,
        top_k: int | None = None,
        disaster_type: DisasterType | None = None,
        doc_type: str | None = None,
        include_stale: bool = False,
        vector_weight: float = 0.7,
        lexical_weight: float = 0.3,
    ) -> list[RetrievedChunk]:
        """Perform hybrid vector + lexical search over pgvector chunks."""
        k = top_k or self.default_top_k
        query_vector = embedding_service.embed_text(query)

        # Base query joining chunks with documents
        stmt = (
            select(
                KBChunk,
                KBDocument,
                KBChunk.embedding.cosine_distance(query_vector).label("distance"),
            )
            .join(KBDocument, KBChunk.document_id == KBDocument.id)
            .where(KBDocument.is_active == True)  # noqa: E712
        )

        if disaster_type is not None:
            stmt = stmt.where(
                (KBDocument.disaster_type == disaster_type) | (KBDocument.disaster_type.is_(None))
            )

        if doc_type is not None:
            stmt = stmt.where(KBDocument.doc_type == doc_type)

        # Fetch candidate chunks ordered by vector proximity
        stmt = stmt.order_by("distance").limit(k * 3)
        res = await db.execute(stmt)
        candidates = res.all()

        scored_chunks: list[RetrievedChunk] = []

        for chunk_row, doc_row, dist in candidates:
            # Staleness filter
            if not include_stale and is_document_stale(doc_row.publication_date, doc_row.valid_until):
                continue

            # Cosine similarity in [0, 1]
            distance_val = float(dist) if dist is not None else 1.0
            vector_score = max(0.0, min(1.0, 1.0 - distance_val))

            # BM25 / Lexical score
            lexical_score = compute_bm25_lexical_score(query, chunk_row.text)

            # Combined hybrid score
            hybrid_score = (vector_weight * vector_score) + (lexical_weight * lexical_score)

            if hybrid_score >= self.score_floor:
                scored_chunks.append(
                    RetrievedChunk(
                        chunk_id=chunk_row.id,
                        document_id=doc_row.id,
                        doc_title=doc_row.title,
                        doc_type=doc_row.doc_type,
                        disaster_type=doc_row.disaster_type,
                        page_number=chunk_row.page_number,
                        heading_path=chunk_row.heading_path,
                        text=chunk_row.text,
                        vector_score=round(vector_score, 4),
                        lexical_score=round(lexical_score, 4),
                        hybrid_score=round(hybrid_score, 4),
                        publication_date=doc_row.publication_date,
                        valid_until=doc_row.valid_until,
                    )
                )

        # Sort by hybrid score descending
        scored_chunks.sort(key=lambda c: c.hybrid_score, reverse=True)
        return scored_chunks[:k]


retriever = HybridRetriever()
