from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.events import DisasterEvent, HazardZone, IncidentReport
from app.db.models.knowledge import KBChunk, KBDocument
from app.rag.chunking import chunk_parsed_document
from app.rag.embeddings import embedding_service
from app.rag.parser import ParsedDocument, ParsedPage


def generate_sitrep_text(
    event: DisasterEvent,
    hazard_zones: Sequence[HazardZone],
    reports: Sequence[IncidentReport],
) -> str:
    """Synthesize a structured situational report (SITREP) markdown document."""
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    declared_str = (
        event.declared_at.strftime("%Y-%m-%d %H:%M:%S UTC") if event.declared_at else "Unknown"
    )

    total_casualties_reported = sum(1 for r in reports if r.casualties_reported)
    total_people_affected = sum(r.people_affected or 0 for r in reports)
    impassable_zones = [z for z in hazard_zones if z.is_impassable]

    lines = [
        f"# SITREP: {event.name}",
        f"**Generated At:** {now_str}",
        f"**Disaster Type:** {event.disaster_type.value}",
        f"**Status:** {event.status.value}",
        f"**Declared Time:** {declared_str}",
        f"**Impact Radius:** {event.radius_m} meters",
        "",
        "## 1. Executive Summary",
        event.description or "No initial description provided.",
        "",
        "## 2. Hazard Zones & Infrastructure Blockages",
        f"- Total active hazard zones: {len(hazard_zones)}",
        f"- Impassable road zones: {len(impassable_zones)}",
    ]

    for z in hazard_zones:
        imp_tag = " [IMPASSABLE ROAD]" if z.is_impassable else ""
        note = z.source_note or "No notes"
        lines.append(
            f"  - **{z.label}** ({z.severity.value} {z.hazard_type.value}){imp_tag}: {note}"
        )

    lines.extend(
        [
            "",
            "## 3. Incident Reports & Casualties",
            f"- Total reports received: {len(reports)}",
            f"- Reports with casualties: {total_casualties_reported}",
            f"- Estimated people affected: {total_people_affected}",
            "",
            "### Recent Observations:",
        ]
    )

    for r in reports[:10]:
        cas_tag = " [CASUALTY REPORTED]" if r.casualties_reported else ""
        aff_tag = f" ({r.people_affected} affected)" if r.people_affected else ""
        time_str = r.reported_at.strftime("%H:%M")
        lines.append(f"- **{r.source.value}** ({time_str}): {r.body}{cas_tag}{aff_tag}")

    return "\n".join(lines)


async def ingest_event_sitrep(
    db: AsyncSession,
    event: DisasterEvent,
    hazard_zones: Sequence[HazardZone],
    reports: Sequence[IncidentReport],
) -> KBDocument:
    """Generate and ingest a SITREP document with embeddings and 24h TTL."""
    sitrep_text = generate_sitrep_text(event, hazard_zones, reports)
    today = datetime.now(UTC).date()
    content_hash = hashlib.sha256(sitrep_text.encode("utf-8")).hexdigest()

    # 1. Deactivate old SITREPs for this title prefix
    title_prefix = f"SITREP - {event.name}"
    deact_stmt = (
        update(KBDocument)
        .where(
            KBDocument.title.like(f"{title_prefix}%"),
            KBDocument.source_type == "SITREP",
        )
        .values(is_active=False)
    )
    await db.execute(deact_stmt)

    # 2. Insert new KBDocument
    doc_title = f"{title_prefix} - {datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    doc = KBDocument(
        title=doc_title,
        source_type="SITREP",
        source_url=None,
        publisher="IDRA Automated Synthesizer",
        hazard_types=[event.disaster_type],
        jurisdiction="Chennai",
        published_at=today,
        content_sha256=content_hash,
        is_active=True,
    )
    db.add(doc)
    await db.flush()

    # 3. Chunk and Embed
    parsed_doc = ParsedDocument(
        filename=f"sitrep_{event.id}.md",
        title=doc_title,
        pages=[ParsedPage(page_number=1, text=sitrep_text)],
    )
    chunks = chunk_parsed_document(
        doc=parsed_doc,
        doc_id=str(doc.id),
        doc_type="SITREP",
        disaster_type=event.disaster_type.value,
        max_tokens=400,
        overlap_tokens=80,
    )

    texts = [c.text for c in chunks]
    embeddings = embedding_service.embed_batch(texts)

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

    await db.flush()
    return doc
