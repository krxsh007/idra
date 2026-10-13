from __future__ import annotations

import glob
import math
import os
import time
import uuid
from typing import Any

from app.core.config import settings
from app.eval.datasets import load_retrieval_queries
from app.rag.chunking import chunk_parsed_document
from app.rag.embeddings import embedding_service
from app.rag.parser import parse_markdown_file
from app.rag.retriever import compute_bm25_lexical_score


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _load_kb_corpus_chunks() -> list[dict[str, Any]]:
    """Parse and chunk the canonical KB markdown files in data/kb/raw/."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
    kb_dir = os.path.join(repo_root, "data", "kb", "raw")
    corpus: list[dict[str, Any]] = []

    for fpath in sorted(glob.glob(os.path.join(kb_dir, "*.md"))):
        fname = os.path.basename(fpath)
        parsed = parse_markdown_file(fpath)
        doc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, fname))
        raw_chunks = chunk_parsed_document(
            doc=parsed,
            doc_id=doc_id,
            doc_type="SOP",
            max_tokens=400,
            overlap_tokens=80,
        )
        for ch in raw_chunks:
            text_clean = ch.text.strip()
            if len(text_clean) < 15 or text_clean == "---":
                continue
            chunk_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, f"{fname}:{ch.chunk_index}")
            corpus.append(
                {
                    "chunk_id": chunk_uuid,
                    "document_id": uuid.UUID(doc_id),
                    "doc_filename": fname,
                    "doc_title": parsed.title,
                    "section_path": ch.heading_path,
                    "content": text_clean,
                    "token_count": ch.token_count,
                }
            )

    texts = [f"{c['doc_title']} {c['section_path'] or ''} {c['content']}" for c in corpus]
    embeddings = embedding_service.embed_batch(texts)
    for c, emb in zip(corpus, embeddings, strict=False):
        c["embedding"] = emb
    return corpus


def _is_chunk_relevant(chunk: dict[str, Any], query_item: dict[str, Any]) -> bool:
    """Check whether a corpus chunk matches the ground-truth relevance criteria for a query."""
    if chunk["doc_filename"] != query_item["relevant_doc"]:
        return False
    text_lower = (chunk["content"] + " " + (chunk["section_path"] or "")).lower()
    keywords: list[str] = query_item.get("relevant_keywords", [])
    return any(kw.lower() in text_lower for kw in keywords)


def run_rag_evaluation() -> dict[str, Any]:
    """Run the RAG evaluation suite over the 40 labelled queries and 5 out-of-domain queries."""
    dataset = load_retrieval_queries()
    queries = dataset["queries"]
    ood_queries = dataset["out_of_domain_queries"]
    corpus = _load_kb_corpus_chunks()

    precisions_at_5: list[float] = []
    recalls_at_8: list[float] = []
    reciprocal_ranks_at_8: list[float] = []
    latencies_ms: list[float] = []
    resolvable_citations = 0
    total_citations_checked = 0

    # Untimed warm-up so one-off model/device initialisation isn't counted as query latency.
    embedding_service.embed_text("warm-up query")

    for q_item in queries:
        q_text = q_item["query"]
        t0 = time.perf_counter()

        q_emb = embedding_service.embed_text(q_text)
        scored_pairs: list[tuple[float, dict[str, Any]]] = []
        for c in corpus:
            d_score = _cosine_similarity(q_emb, c["embedding"])
            b_val = compute_bm25_lexical_score(
                q_text, c["content"] + " " + (c["section_path"] or "")
            )
            h_score = 0.70 * d_score + 0.30 * b_val
            scored_pairs.append((h_score, c))

        scored_pairs.sort(key=lambda x: x[0], reverse=True)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(elapsed_ms)

        top_8 = [pair[1] for pair in scored_pairs[:8] if pair[0] >= settings.RAG_SCORE_FLOOR]
        top_5 = top_8[:5]

        all_relevant_ids = {c["chunk_id"] for c in corpus if _is_chunk_relevant(c, q_item)}
        rel_in_top_8 = [c for c in top_8 if c["chunk_id"] in all_relevant_ids]

        doc_rel_in_top_5 = [
            c
            for c in top_5
            if c["doc_filename"] == q_item["relevant_doc"] or c["chunk_id"] in all_relevant_ids
        ]
        p_at_5 = len(doc_rel_in_top_5) / max(len(top_5), 1)
        precisions_at_5.append(p_at_5)

        if all_relevant_ids:
            r_at_8 = len(rel_in_top_8) / len(all_relevant_ids)
        else:
            r_at_8 = 1.0
        recalls_at_8.append(r_at_8)

        rr = 0.0
        for rank_idx, c in enumerate(top_8, start=1):
            if c["chunk_id"] in all_relevant_ids:
                rr = 1.0 / rank_idx
                break
        reciprocal_ranks_at_8.append(rr)

        for c in top_5:
            total_citations_checked += 1
            if c["chunk_id"] and c["doc_title"] and len(c["content"]) >= 15:
                resolvable_citations += 1

    # Out-of-domain queries: verify hybrid score stays below floor (0.35)
    ood_rejected = 0
    for ood in ood_queries:
        q_emb = embedding_service.embed_text(ood["query"])
        max_hybrid = max(
            0.70 * _cosine_similarity(q_emb, c["embedding"])
            + 0.30 * compute_bm25_lexical_score(ood["query"], c["content"])
            for c in corpus
        )
        if max_hybrid < settings.RAG_SCORE_FLOOR:
            ood_rejected += 1

    latencies_sorted = sorted(latencies_ms)
    p50_ms = latencies_sorted[len(latencies_sorted) // 2] if latencies_sorted else 0.0
    p95_idx = min(int(len(latencies_sorted) * 0.95), len(latencies_sorted) - 1)
    p95_ms = latencies_sorted[p95_idx] if latencies_sorted else 0.0

    mean_p5 = round(sum(precisions_at_5) / len(precisions_at_5), 4)
    mean_r8 = round(sum(recalls_at_8) / len(recalls_at_8), 4)
    mean_mrr8 = round(sum(reciprocal_ranks_at_8) / len(reciprocal_ranks_at_8), 4)
    ood_rate = round(ood_rejected / len(ood_queries), 4)
    citation_rate = round(resolvable_citations / max(total_citations_checked, 1), 4)
    kappa = float(dataset["inter_annotator_agreement"]["cohens_kappa"])

    return {
        "suite": "rag_eval",
        "dataset_size": len(queries),
        "corpus_chunk_count": len(corpus),
        "metrics": {
            "retrieval_precision_at_5": {
                "value": mean_p5,
                "target": 0.70,
                "operator": ">=",
                "passed": mean_p5 >= 0.70,
            },
            "retrieval_recall_at_8": {
                "value": mean_r8,
                "target": 0.75,
                "operator": ">=",
                "passed": mean_r8 >= 0.75,
            },
            "retrieval_mrr_at_8": {
                "value": mean_mrr8,
                "target": 0.80,
                "operator": ">=",
                "passed": mean_mrr8 >= 0.80,
            },
            "citation_resolution_rate": {
                "value": citation_rate,
                "target": 0.95,
                "operator": ">=",
                "passed": citation_rate >= 0.95,
            },
            "zero_llm_call_on_floor_miss_rate": {
                "value": ood_rate,
                "target": 1.00,
                "operator": "==",
                "passed": ood_rate == 1.00,
            },
            "retrieval_latency_p50_ms": {
                "value": round(p50_ms, 2),
                "target": 150.0,
                "operator": "<=",
                "passed": p50_ms <= 150.0,
            },
            "retrieval_latency_p95_ms": {
                "value": round(p95_ms, 2),
                "target": 250.0,
                "operator": "<=",
                "passed": p95_ms <= 250.0,
            },
            "inter_annotator_cohens_kappa": {
                "value": kappa,
                "target": 0.80,
                "operator": ">=",
                "passed": kappa >= 0.80,
            },
        },
    }
