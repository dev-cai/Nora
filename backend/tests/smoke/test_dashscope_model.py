"""Opt-in dynamic smoke for the approved DashScope model and application path."""

import os

import pytest
from app.application.model import VerifyStructuredModelUseCase
from app.infrastructure.config import Settings
from app.infrastructure.model import create_dashscope_chat_adapter


@pytest.mark.dynamic_provider
@pytest.mark.asyncio
async def test_dashscope_structured_output_dynamic_smoke() -> None:
    if os.environ.get("NORA_RUN_DASHSCOPE_SMOKE") != "1":
        pytest.skip("set NORA_RUN_DASHSCOPE_SMOKE=1 for the real provider smoke")
    settings = Settings(_env_file=None)
    if not settings.dashscope_api_key or not settings.dashscope_workspace_id:
        pytest.fail("DASHSCOPE_API_KEY and DASHSCOPE_WORKSPACE_ID are required")

    result = await VerifyStructuredModelUseCase(create_dashscope_chat_adapter(settings)).execute()

    assert result.status == "ready"
