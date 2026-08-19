import asyncio
import os
from datetime import UTC, datetime
from typing import Any
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.logging import logger, setup_logging
from app.db.models.enums import DisasterType
from app.db.models.knowledge import KBChunk, KBDocument
from app.rag.chunking import chunk_parsed_document
from app.rag.embeddings import embedding_service
from app.rag.parser import parse_markdown_file, parse_pdf_file


async def ingest_file(
    db: AsyncSession,
    file_path: str,
    doc_type: str = "SOP",
    disaster_type: DisasterType | None = DisasterType.FLOOD,
    author: str = "NDMA / TNSDMA / Sphere",
) -> int:
    """Parse, chunk, embed, and store a single document file into the database."""
    filename = os.path.basename(file_path)
    logger.info("ingesting_document", filename=filename)

    if filename.endswith(".pdf"):
        parsed = parse_pdf_file(file_path, filename=filename)
    elif filename.endswith(".md") or filename.endswith(".txt"):
        parsed = parse_markdown_file(file_path)
    else:
        logger.warning("unsupported_file_format", filename=filename)
        return 0

    # 1. Check if document already exists
    stmt = select(KBDocument).where(KBDocument.title == parsed.title)
    res = await db.execute(stmt)
    existing_doc = res.scalar_one_or_none()

    if existing_doc:
        doc = existing_doc
        # Delete existing chunks for re-ingestion
        await db.execute(delete(KBChunk).where(KBChunk.document_id == doc.id))
        doc.doc_type = doc_type
        doc.disaster_type = disaster_type
        doc.author = author
        doc.is_active = True
    else:
        doc = KBDocument(
            title=parsed.title,
            doc_type=doc_type,
            disaster_type=disaster_type,
            source_url=None,
            author=author,
            publication_date=datetime.now(UTC).date(),
            valid_until=None,
            is_active=True,
        )
        db.add(doc)
        await db.flush()

    # 2. Chunk document
    chunks = chunk_parsed_document(
        doc=parsed,
        doc_id=str(doc.id),
        doc_type=doc_type,
        disaster_type=disaster_type.value if disaster_type else None,
        max_tokens=400,
        overlap_tokens=80,
    )

    if not chunks:
        logger.warning("no_chunks_generated", title=parsed.title)
        return 0

    # 3. Batch Embeddings
    texts = [c.text for c in chunks]
    embeddings = embedding_service.embed_batch(texts)

    # 4. Insert Chunks
    for chunk, emb in zip(chunks, embeddings, strict=False):
        kb_chunk = KBChunk(
            document_id=doc.id,
            chunk_index=chunk.chunk_index,
            text=chunk.text,
            token_count=chunk.token_count,
            page_number=chunk.page_number,
            heading_path=chunk.heading_path,
            embedding=emb,
        )
        db.add(kb_chunk)

    await db.commit()
    logger.info("document_ingested_successfully", title=parsed.title, chunks_count=len(chunks))
    return len(chunks)


async def main() -> None:
    setup_logging("INFO")
    logger.info("starting_knowledge_base_ingestion")

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    data_dir = os.path.join(os.path.dirname(__file__), "../data/kb/raw")
    if not os.path.exists(data_dir):
        logger.error("data_directory_missing", path=data_dir)
        return

    files = [f for f in os.listdir(data_dir) if f.endswith((".md", ".pdf", ".txt"))]
    logger.info("found_knowledge_files", count=len(files), files=files)

    total_chunks = 0
    async with session_maker() as session:
        for fname in sorted(files):
            fpath = os.path.join(data_dir, fname)
            disaster_type = DisasterType.FLOOD
            if "cyclone" in fname.lower():
                disaster_type = DisasterType.CYCLONE
            elif "sphere" in fname.lower():
                disaster_type = None

            try:
                chunks_count = await ingest_file(
                    db=session,
                    file_path=fpath,
                    doc_type="SOP" if not "sphere" in fname.lower() else "STANDARD",
                    disaster_type=disaster_type,
                )
                total_chunks += chunks_count
            except Exception as e:
                logger.error("ingestion_failed_for_file", filename=fname, error=str(e))
                await session.rollback()

    await engine.dispose()
    logger.info("knowledge_base_ingestion_complete", total_chunks=total_chunks)


if __name__ == "__main__":
    asyncio.run(main())
