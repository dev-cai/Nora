import httpx
import pytest
from app.agent_runtime.profile_import import (
    PROFILE_IMPORT_MAX_INPUT_TOKENS,
    ProfileImportAgent,
    ProfileImportOutput,
)
from app.infrastructure.model import (
    DEEPSEEK_BASE_URL,
    DEEPSEEK_CHAT_MODEL,
    DeepSeekChatAdapter,
    FakeModelAdapter,
)
from app.infrastructure.pdf_text import extract_pdf_text

_API_KEY = "deepseek-test-secret"


def _pdf(text: str) -> bytes:
    encoded = f"({text}) Tj".encode()
    return b"%PDF-1.4\n1 0 obj\nstream\n" + encoded + b"\nendstream\n%%EOF"


def _success_response() -> httpx.Response:
    content = (
        '{"basic_information":{"display_name":{"value":"Bob"},'
        '"current_location":{"value":"上海"}},'
        '"preferences":{"target_locations":{"value":["上海"]},'
        '"accepts_remote":{"value":false},"target_roles":{"value":[]}},'
        '"education":[],"experiences":[],"skills":[]}'
    )
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}]},
    )


def test_pdf_text_extractor_keeps_ascii_text() -> None:
    assert extract_pdf_text(_pdf("Bob Resume")) == "Bob Resume"


@pytest.mark.asyncio
async def test_profile_import_returns_unconfirmed_editable_facts() -> None:
    model = FakeModelAdapter(
        [
            ProfileImportOutput(
                basic_information={
                    "display_name": {"value": "Bob"},
                    "current_location": {"value": "上海"},
                },
                education=[],
                experiences=[],
                skills=[],
            )
        ]
    )
    result = await ProfileImportAgent(model).run(_pdf("Bob Resume"))
    assert result["basic_information"] == {
        "display_name": {"value": "Bob", "confirmation_status": "unconfirmed"},
        "current_location": {"value": "上海", "confirmation_status": "unconfirmed"},
    }
    assert model.requests[0].max_input_tokens == PROFILE_IMPORT_MAX_INPUT_TOKENS


@pytest.mark.asyncio
async def test_profile_import_accepts_large_text_resume() -> None:
    """A large resume reaches the model instead of being blocked by the preflight."""

    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return _success_response()

    adapter = DeepSeekChatAdapter(
        api_key=_API_KEY,
        base_url=DEEPSEEK_BASE_URL,
        model=DEEPSEEK_CHAT_MODEL,
        timeout_seconds=10,
        transport=httpx.MockTransport(handler),
        retry_base_delay_seconds=0,
    )

    large_text = "负责高并发交易系统的架构设计与核心模块开发。" * 900  # ~20k chars
    result = await ProfileImportAgent(adapter).run(_pdf(large_text))

    assert called is True
    assert result["basic_information"]["display_name"]["value"] == "Bob"
