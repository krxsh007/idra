import pytest
from app.llm.client import get_llm_client
from app.llm.fake import FakeLLMClient
from pydantic import BaseModel, Field


class SampleSchema(BaseModel):
    summary: str
    count: int = Field(default=0)


@pytest.mark.asyncio
async def test_fake_client_structured_dict_fixture():
    client = FakeLLMClient(
        fixture_responses=[{"summary": "Flooding reported in Velachery", "count": 42}]
    )
    result = await client.structured("Analyze situation", SampleSchema)
    assert isinstance(result, SampleSchema)
    assert result.summary == "Flooding reported in Velachery"
    assert result.count == 42
    assert client.call_count == 1
    assert "Analyze situation" in client.recorded_prompts


@pytest.mark.asyncio
async def test_fake_client_structured_json_string_fixture():
    client = FakeLLMClient(
        fixture_responses=['{"summary": "Water rising near Adyar", "count": 15}']
    )
    result = await client.structured("Check water levels", SampleSchema)
    assert result.summary == "Water rising near Adyar"
    assert result.count == 15
    assert client.call_count == 1


@pytest.mark.asyncio
async def test_fake_client_structured_instance_fixture():
    fixture = SampleSchema(summary="Cyclone warning", count=100)
    client = FakeLLMClient(fixture_responses=[fixture])
    result = await client.structured("Check cyclone", SampleSchema)
    assert result == fixture
    assert client.call_count == 1


@pytest.mark.asyncio
async def test_fake_client_error_raising():
    client = FakeLLMClient(error_to_raise=RuntimeError("Provider connection error"))
    with pytest.raises(RuntimeError, match="Provider connection error"):
        await client.structured("test", SampleSchema)


@pytest.mark.asyncio
async def test_fake_client_short_text():
    client = FakeLLMClient(default_short_text="Quick summary text")
    text = await client.short_text("Provide a summary")
    assert text == "Quick summary text"
    assert client.call_count == 1


def test_get_llm_client_factory():
    client = get_llm_client("fake")
    assert isinstance(client, FakeLLMClient)

    with pytest.raises(ValueError, match="Unsupported LLM backend"):
        get_llm_client("unsupported_backend_xyz")


class _StubResponse:
    def __init__(self, text: str) -> None:
        self.text = text


def _gemini_with_stub(outcomes, fallback_model_name="fallback-model", max_retries=2):
    """Build a GeminiLLMClient whose generate_content replays `outcomes` and records models."""
    from app.llm.gemini import GeminiLLMClient

    client = GeminiLLMClient(
        api_key="test-key",
        model_name="primary-model",
        fallback_model_name=fallback_model_name,
        max_retries=max_retries,
        retry_backoff_s=0,
    )
    calls: list[str] = []

    def fake_generate_content(*, model, contents, config):
        calls.append(model)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return _StubResponse(outcome)

    client._client.models.generate_content = fake_generate_content
    return client, calls


def _api_error(code: int):
    from google.genai import errors

    return errors.APIError(code, {"error": {"code": code, "message": "x", "status": "X"}})


@pytest.mark.asyncio
async def test_gemini_retries_transient_error_on_fallback_model():
    client, calls = _gemini_with_stub([_api_error(503), '{"summary": "ok", "count": 1}'])
    result = await client.structured("p", SampleSchema)
    assert result.summary == "ok"
    assert calls == ["primary-model", "fallback-model"]


@pytest.mark.asyncio
async def test_gemini_retries_on_primary_when_no_fallback_configured():
    client, calls = _gemini_with_stub([_api_error(429), "done"], fallback_model_name="")
    assert await client.short_text("p") == "done"
    assert calls == ["primary-model", "primary-model"]


@pytest.mark.asyncio
async def test_gemini_does_not_retry_non_transient_error():
    from google.genai import errors

    client, calls = _gemini_with_stub([_api_error(400)])
    with pytest.raises(errors.APIError):
        await client.structured("p", SampleSchema)
    assert calls == ["primary-model"]


@pytest.mark.asyncio
async def test_gemini_gives_up_after_max_retries():
    from google.genai import errors

    client, calls = _gemini_with_stub([_api_error(503)] * 3, max_retries=2)
    with pytest.raises(errors.APIError):
        await client.structured("p", SampleSchema)
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_gemini_walks_the_fallback_chain_until_a_model_answers():
    client, calls = _gemini_with_stub(
        [_api_error(503), _api_error(429), '{"summary": "ok", "count": 1}'],
        fallback_model_name="fallback-a, fallback-b, fallback-c",
        max_retries=1,
    )
    result = await client.structured("p", SampleSchema)
    assert result.summary == "ok"
    assert calls == ["primary-model", "fallback-a", "fallback-b"]


@pytest.mark.asyncio
async def test_gemini_moves_on_when_an_attempt_hangs():
    import time

    from app.llm.gemini import GeminiLLMClient

    client = GeminiLLMClient(
        api_key="test-key",
        model_name="primary-model",
        fallback_model_name="fallback-a",
        max_retries=1,
        retry_backoff_s=0,
        attempt_timeout_s=0.2,
    )
    calls: list[str] = []

    def fake_generate_content(*, model, contents, config):
        calls.append(model)
        if model == "primary-model":
            time.sleep(1)  # hung request
        return _StubResponse('{"summary": "ok", "count": 1}')

    client._client.models.generate_content = fake_generate_content
    result = await client.structured("p", SampleSchema)
    assert result.summary == "ok"
    assert calls == ["primary-model", "fallback-a"]
