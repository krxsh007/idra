# IDRA Hybrid RAG & Knowledge Base Pipeline

## 1. Corpus & Document Provenance (`data/kb/raw/`)
The IDRA Knowledge Base contains curated, real-world disaster management SOPs and humanitarian standards:
1. **`ndma_flood_guidelines.md`**: National Disaster Management Authority (NDMA) Urban Flood Management Guidelines — early warning thresholds (`State Green/Yellow/Orange/Red`), SAR boat team composition, electrical hazard de-energization, and shelter siting.
2. **`sphere_handbook_standards.md`**: Sphere Handbook Minimum Standards — survival water (`15 L/person/day`), water point distance (`<= 500 m`), Free Residual Chlorine (`0.2–0.5 mg/L`), shelter covered area (`3.5 m²/person`), latrine ratio (`1 per 20 persons`), and nutritional rations (`2,100 kcal/person/day`).
3. **`tnsdma_chennai_Flood_sop.md`**: Tamil Nadu State Disaster Management Authority (TNSDMA) & Greater Chennai Corporation SOP — Chembarambakkam/Poondi/Puzhal reservoir release protocols, Adyar/Cooum floodways, 18 low-lying subway closures, Emergency Helpline `1913` / `1070`, and coastal cyclone evacuation within `5 km`.

---

## 2. Parsing, Cleaning & Section-Aware Chunking
- **Markdown Parser (`api/app/rag/parser.py`):** Extracts document title, YAML/metadata headers, and hierarchical Markdown headings (`#`, `##`, `###`) so every paragraph retains its full `section_path` breadcrumb.
- **Chunking (`api/app/rag/chunking.py`):** Splits documents into overlapping chunks (`max_tokens = 400`, `overlap_tokens = 80`) while respecting section boundaries and discarding separator-only noise.
- **Staleness Filter (`is_document_stale`):** Automatically excludes documents older than `settings.KB_STALE_YEARS` (`10` years) unless `include_stale=True` is explicitly requested.

---

## 3. Embeddings & Hybrid Retrieval (`api/app/rag/retriever.py`)
- **384-Dimensional Embeddings (`EmbeddingService`):**
  - Uses `sentence-transformers/all-MiniLM-L6-v2` (`384` dimensions, unit-normalized) in online mode.
  - Provides a deterministic feature-hashed 384-d unit vector fallback (`_generate_deterministic_mock_vector`) when `LLM_BACKEND=fake`, hashing lowercase content tokens and 4–5 character stems into signed buckets for zero-network reproducibility.
- **Hybrid Scoring Formula:**
  $$\text{score}_{\text{hybrid}}(q, c) = 0.70 \cdot \text{sim}_{\cos}(\mathbf{e}_q, \mathbf{e}_c) + 0.30 \cdot \text{score}_{\text{BM25}}(q, c)$$
- **Strict Score Floor (`RAG_SCORE_FLOOR = 0.35`):**
  - Chunks with $\text{score}_{\text{hybrid}} < 0.35$ are discarded before returning results.
  - When a query yields zero chunks above the `0.35` floor, `CitizenAssistantAgent` immediately returns a safe out-of-domain refusal with emergency helpline numbers (`1070`, `1913`, `108`, `112`) and makes **zero LLM calls** (`zero_llm_call_on_floor_miss_rate = 1.0`).
