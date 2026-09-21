import pytest
from pydantic import BaseModel, Field

from app.llm.client import get_llm_client
from app.llm.fake import FakeLLMClient


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
