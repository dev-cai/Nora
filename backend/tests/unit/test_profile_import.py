import zlib

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


def _cid_pdf() -> bytes:
    cmap = b"""/CIDInit /ProcSet findresource begin
12 dict begin
begincmap
1 begincodespacerange
<0000> <FFFF>
endcodespacerange
2 beginbfchar
<0001> <4F60>
<0002> <597D>
endbfchar
endcmap
CMapName currentdict /CMap defineresource pop
end
end
"""
    compressed_cmap = zlib.compress(cmap)
    content = b"BT\n/F1 12 Tf\n<0001>Tj<0002>Tj\nET\n"
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<</Resources <</Font <</F1 2 0 R>>>>>>\nendobj\n"
        b"2 0 obj\n<</Subtype /Type0 /ToUnicode 4 0 R>>\nendobj\n"
        b"3 0 obj\n<</Length "
        + str(len(content)).encode()
        + b">>\nstream\n"
        + content
        + b"endstream\nendobj\n"
        b"4 0 obj\n<</Filter /FlateDecode /Length "
        + str(len(compressed_cmap)).encode()
        + b">>\nstream\n"
        + compressed_cmap
        + b"\nendstream\nendobj\n"
        b"5 0 obj\n<</Subtype /Image /Length 30>>\nstream\n"
        b"BT /F1 12 Tf <0001>Tj ET\n"
        b"endstream\nendobj\n%%EOF"
    )


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


def test_pdf_text_extractor_decodes_cid_font_using_tounicode() -> None:
    extracted = extract_pdf_text(_cid_pdf())

    assert extracted == "你好"
    assert "Tj" not in extracted


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
