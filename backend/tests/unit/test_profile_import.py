import pytest
from app.agent_runtime.profile_import import ProfileImportAgent, ProfileImportOutput
from app.infrastructure.model import FakeModelAdapter
from app.infrastructure.pdf_text import extract_pdf_text


def _pdf(text: str) -> bytes:
    encoded = f"({text}) Tj".encode()
    return b"%PDF-1.4\n1 0 obj\nstream\n" + encoded + b"\nendstream\n%%EOF"


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
