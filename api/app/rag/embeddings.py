from __future__ import annotations

import hashlib
import math
from typing import Any
from app.core.config import settings
from app.core.logging import logger


class EmbeddingService:
    _instance: EmbeddingService | null = None
    _model: Any = None

    def __init__(self) -> None:
        self._dim = settings.EMBEDDING_DIM  # 384
        self._model_name = settings.EMBEDDING_MODEL

    @classmethod
    def get_instance(cls) -> EmbeddingService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_model(self) -> Any:
        if self._model is None and settings.LLM_BACKEND != "fake":
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]

                logger.info("loading_embedding_model", model=self._model_name)
                self._model = SentenceTransformer(self._model_name)
            except Exception as e:
                logger.warning("sentence_transformers_load_failed", error=str(e))
                self._model = None
        return self._model

    def _generate_deterministic_mock_vector(self, text: str) -> list[float]:
        """Generate a reproducible, unit-normalized 384-dimensional vector from text hash."""
        vec: list[float] = []
        for i in range(self._dim):
            seed_str = f"{text}_{i}"
            val = int(hashlib.md5(seed_str.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
            # Shift to [-1.0, 1.0]
            vec.append((val * 2.0) - 1.0)

        # L2 Normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    def embed_text(self, text: str) -> list[float]:
        """Generate a normalized 384-dimensional embedding for a single text string."""
        clean_text = text.strip()
        if not clean_text:
            return [0.0] * self._dim

        model = self._load_model()
        if model is not None:
            emb = model.encode(clean_text, normalize_embeddings=True)
            return [float(x) for x in emb.tolist()]

        return self._generate_deterministic_mock_vector(clean_text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate normalized embeddings for a batch of text strings."""
        if not texts:
            return []

        clean_texts = [t.strip() for t in texts]
        model = self._load_model()

        if model is not None:
            embeddings = model.encode(clean_texts, normalize_embeddings=True, show_progress_bar=False)
            return [[float(x) for x in emb.tolist()] for emb in embeddings]

        return [self._generate_deterministic_mock_vector(t) for t in clean_texts]


embedding_service = EmbeddingService.get_instance()
