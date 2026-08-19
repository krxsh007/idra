from datetime import UTC, date, datetime, timedelta

from app.rag.retriever import compute_bm25_lexical_score, is_document_stale


def test_bm25_lexical_scoring() -> None:
    query = "potable water supply"
    matching_text = (
        "Minimum emergency water supply standard requires 15 liters of potable water per person."
    )
    unrelated_text = "Traffic signal timing on arterial highway."

    score_match = compute_bm25_lexical_score(query, matching_text)
    score_unrelated = compute_bm25_lexical_score(query, unrelated_text)

    assert score_match > 0.4
    assert score_unrelated == 0.0


def test_bm25_exact_phrase_bonus() -> None:
    query = "search and rescue"
    exact_text = "NDRF teams conduct search and rescue operations."
    partial_text = "Rescue operations in search zones."

    score_exact = compute_bm25_lexical_score(query, exact_text)
    score_partial = compute_bm25_lexical_score(query, partial_text)

    assert score_exact > score_partial


def test_document_staleness_filters() -> None:
    today = datetime.now(UTC).date()

    # 1. Non-stale document (published 1 year ago)
    recent_pub = today - timedelta(days=365)
    assert is_document_stale(published_at=recent_pub) is False

    # 2. None publication date is not considered stale
    assert is_document_stale(published_at=None) is False

    # 3. Old publication date > 10 years (settings.KB_STALE_YEARS = 10)
    old_pub = date(2010, 1, 1)
    assert is_document_stale(published_at=old_pub) is True
