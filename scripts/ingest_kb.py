import asyncio
import hashlib
import os
from datetime import UTC, datetime

from app.core.config import settings
from app.core.logging import logger, setup_logging
from app.db.models.enums import DisasterType
from app.db.models.knowledge import KBChunk, KBDocument
from app.rag.chunking import chunk_parsed_document
from app.rag.embeddings import embedding_service
from app.rag.parser import parse_markdown_file, parse_pdf_file
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


async def ingest_file(
    db: AsyncSession,
    file_path: str,
    source_type: str = "SOP",
    hazard_types: list[DisasterType] | None = None,
    publisher: str = "NDMA / TNSDMA / Sphere",
    jurisdiction: str = "National / Tamil Nadu",
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

    with open(file_path, "rb") as f:
        file_bytes = f.read()
    content_sha256 = hashlib.sha256(file_bytes).hexdigest()

    h_types = hazard_types or []

    # 1. Check if document already exists by content hash or title
    stmt = select(KBDocument).where(
        (KBDocument.content_sha256 == content_sha256) | (KBDocument.title == parsed.title)
    )
    res = await db.execute(stmt)
    existing_doc = res.scalar_one_or_none()

    if existing_doc:
        doc = existing_doc
        # Delete existing chunks for re-ingestion
        await db.execute(delete(KBChunk).where(KBChunk.document_id == doc.id))
        doc.source_type = source_type
        doc.publisher = publisher
        doc.hazard_types = h_types
        doc.jurisdiction = jurisdiction
        doc.content_sha256 = content_sha256
        doc.is_active = True
    else:
        doc = KBDocument(
            title=parsed.title,
            source_type=source_type,
            source_url=None,
            publisher=publisher,
            hazard_types=h_types,
            jurisdiction=jurisdiction,
            published_at=datetime.now(UTC).date(),
            content_sha256=content_sha256,
            is_active=True,
        )
        db.add(doc)
        await db.flush()

    # 2. Chunk document
    chunks = chunk_parsed_document(
        doc=parsed,
        doc_id=str(doc.id),
        doc_type=source_type,
        disaster_type=h_types[0].value if h_types else None,
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
            section_path=chunk.heading_path,
            content=chunk.text,
            token_count=chunk.token_count,
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
            hazard_types: list[DisasterType] = [DisasterType.FLOOD]
            if "cyclone" in fname.lower():
                hazard_types = [DisasterType.CYCLONE, DisasterType.FLOOD]
            elif "sphere" in fname.lower():
                hazard_types = [
                    DisasterType.FLOOD,
                    DisasterType.CYCLONE,
                    DisasterType.EARTHQUAKE,
                ]

            try:
                chunks_count = await ingest_file(
                    db=session,
                    file_path=fpath,
                    source_type="SOP" if "sphere" not in fname.lower() else "STANDARD",
                    hazard_types=hazard_types,
                )
                total_chunks += chunks_count
            except Exception as e:
                logger.error("ingestion_failed_for_file", filename=fname, error=str(e))
                await session.rollback()

    await engine.dispose()
    logger.info("knowledge_base_ingestion_complete", total_chunks=total_chunks)


if __name__ == "__main__":
    asyncio.run(main())
