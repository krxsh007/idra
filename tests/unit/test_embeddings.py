import math

from app.rag.embeddings import embedding_service


def test_embedding_dimensions() -> None:
    text = "Emergency response protocol for urban flooding in Chennai"
    emb = embedding_service.embed_text(text)
    assert isinstance(emb, list)
    assert len(emb) == 384
    assert all(isinstance(x, float) for x in emb)


def test_embedding_normalization() -> None:
    text = "Minimum potable water requirement per person in relief camp"
    emb = embedding_service.embed_text(text)
    # L2 norm must equal 1.0 within floating tolerance
    norm = math.sqrt(sum(x * x for x in emb))
    assert abs(norm - 1.0) < 1e-4


def test_embedding_batch_generation() -> None:
    texts = [
        "NDRF search and rescue inflatable boat deployment",
        "Hospital power generator fuel supply line",
        "Sphere standard minimum living space per person",
    ]
    embeddings = embedding_service.embed_batch(texts)
    assert len(embeddings) == 3
    for emb in embeddings:
        assert len(emb) == 384
        norm = math.sqrt(sum(x * x for x in emb))
        assert abs(norm - 1.0) < 1e-4


def test_empty_string_embedding() -> None:
    emb = embedding_service.embed_text("   ")
    assert len(emb) == 384
    assert all(x == 0.0 for x in emb)
