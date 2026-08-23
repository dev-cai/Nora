"""Opt-in dynamic smoke for the approved DeepSeek model and application path."""

import os

import pytest
from app.application.model import VerifyStructuredModelUseCase
from app.infrastructure.config import Settings
from app.infrastructure.model import create_deepseek_chat_adapter


@pytest.mark.dynamic_provider
@pytest.mark.asyncio
async def test_deepseek_structured_output_dynamic_smoke() -> None:
    if os.environ.get("NORA_RUN_DEEPSEEK_SMOKE") != "1":
        pytest.skip("set NORA_RUN_DEEPSEEK_SMOKE=1 for the real provider smoke")
    settings = Settings(_env_file=None)
    if not settings.deepseek_api_key:
        pytest.fail("DEEPSEEK_API_KEY or DEEPSEEK_API_KEY_FILE is required")

    result = await VerifyStructuredModelUseCase(create_deepseek_chat_adapter(settings)).execute()

    assert result.status == "ready"
