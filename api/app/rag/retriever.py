from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.enums import DisasterType
from app.db.models.knowledge import KBChunk, KBDocument
from app.rag.embeddings import embedding_service


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    doc_title: str
    source_type: str
    hazard_types: list[DisasterType]
    section_path: str | None
    content: str
    vector_score: float
    lexical_score: float
    hybrid_score: float
    published_at: date | None


def compute_bm25_lexical_score(query: str, text: str) -> float:
    """Compute a lightweight term-frequency lexical overlap score normalized to [0, 1]."""
    stopwords = {
        "what",
        "how",
        "when",
        "where",
        "who",
        "which",
        "why",
        "is",
        "are",
        "was",
        "were",
        "the",
        "for",
        "in",
        "on",
        "at",
        "to",
        "of",
        "by",
        "with",
        "from",
        "into",
        "under",
        "during",
        "near",
        "should",
        "must",
        "many",
        "much",
        "does",
        "do",
        "an",
        "a",
        "or",
    }
    raw_q_terms = set(re_clean(query).split())
    if not raw_q_terms:
        return 0.0
    q_terms = {t for t in raw_q_terms if t not in stopwords and len(t) >= 2} or raw_q_terms

    doc_words = set(re_clean(text).split())
    if not doc_words:
        return 0.0
    doc_stems = {w[:5] for w in doc_words if len(w) >= 5}

    matches = sum(
        1 for term in q_terms if term in doc_words or (len(term) >= 5 and term[:5] in doc_stems)
    )
    overlap = matches / len(q_terms)
    phrase_bonus = 0.3 if query.lower().strip() in text.lower() else (0.15 if matches >= 2 else 0.0)
    return min(1.0, overlap * 0.7 + phrase_bonus)


def re_clean(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())


def is_document_stale(published_at: date | None) -> bool:
    """Check if document is older than configured KB_STALE_YEARS."""
    if published_at is None:
        return False
    today = datetime.now(UTC).date()
    years_old = (today - published_at).days / 365.25
    return years_old > settings.KB_STALE_YEARS


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
        source_type: str | None = None,
        include_stale: bool = False,
        vector_weight: float = 0.7,
        lexical_weight: float = 0.3,
        score_floor: float | None = None,
    ) -> list[RetrievedChunk]:
        """Perform hybrid vector + lexical search over pgvector chunks."""
        k = top_k or self.default_top_k
        floor = self.score_floor if score_floor is None else score_floor
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
            stmt = stmt.where(KBDocument.hazard_types.contains([disaster_type]))

        if source_type is not None:
            stmt = stmt.where(KBDocument.source_type == source_type)

        # Fetch candidate chunks ordered by vector proximity
        stmt = stmt.order_by("distance").limit(k * 3)
        res = await db.execute(stmt)
        candidates = res.all()

        scored_chunks: list[RetrievedChunk] = []

        for chunk_row, doc_row, dist in candidates:
            # Staleness filter
            if not include_stale and is_document_stale(doc_row.published_at):
                continue

            # Cosine similarity in [0, 1]
            distance_val = float(dist) if dist is not None else 1.0
            vector_score = max(0.0, min(1.0, 1.0 - distance_val))

            # BM25 / Lexical score
            lexical_score = compute_bm25_lexical_score(query, chunk_row.content)

            # Combined hybrid score
            hybrid_score = (vector_weight * vector_score) + (lexical_weight * lexical_score)

            if hybrid_score >= floor:
                scored_chunks.append(
                    RetrievedChunk(
                        chunk_id=chunk_row.id,
                        document_id=doc_row.id,
                        doc_title=doc_row.title,
                        source_type=doc_row.source_type,
                        hazard_types=doc_row.hazard_types,
                        section_path=chunk_row.section_path,
                        content=chunk_row.content,
                        vector_score=round(vector_score, 4),
                        lexical_score=round(lexical_score, 4),
                        hybrid_score=round(hybrid_score, 4),
                        published_at=doc_row.published_at,
                    )
                )

        # Sort by hybrid score descending
        scored_chunks.sort(key=lambda c: c.hybrid_score, reverse=True)
        return scored_chunks[:k]


retriever = HybridRetriever()
