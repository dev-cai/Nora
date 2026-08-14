"""截图 OCR Adapter 与百度 OCR 引擎的解码、资源限制与错误码测试。"""

import io

import app.infrastructure.jd_ocr as jd_ocr_module
import httpx
import pytest
from app.domain.base.exceptions import ErrorCode
from app.infrastructure.jd_ocr import BaiduOcrEngine, JdOcrAdapter
from app.ports.jd_input import (
    JdImageInput,
    JdInputError,
    JdInputKind,
)
from PIL import Image


class FakeEngine:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self, image: Image.Image) -> str:
        return self._text


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 20), "white").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_extract_image_returns_engine_text() -> None:
    adapter = JdOcrAdapter(engine=FakeEngine("Python 后端工程师\n要求 FastAPI"))
    result = await adapter.extract_image(JdImageInput(content=_png_bytes(), media_type="image/png"))
    assert result.kind is JdInputKind.IMAGE
    assert result.source_url is None
    assert result.jd_text == "Python 后端工程师\n要求 FastAPI"


@pytest.mark.asyncio
async def test_extract_image_rejects_undecodable_content() -> None:
    content = b"\x89PNG\r\n\x1a\n" + b"not a real png"
    adapter = JdOcrAdapter(engine=FakeEngine("ignored"))
    with pytest.raises(JdInputError) as error:
        await adapter.extract_image(JdImageInput(content=content, media_type="image/png"))
    assert error.value.error_code == ErrorCode.DECODE_FAILED


@pytest.mark.asyncio
async def test_extract_image_rejects_oversized_dimensions(monkeypatch) -> None:
    monkeypatch.setattr(jd_ocr_module, "MAX_DIMENSION", 10)
    adapter = JdOcrAdapter(engine=FakeEngine("ignored"))
    with pytest.raises(JdInputError) as error:
        await adapter.extract_image(JdImageInput(content=_png_bytes(), media_type="image/png"))
    assert error.value.error_code == ErrorCode.UNSUPPORTED_IMAGE


@pytest.mark.asyncio
async def test_extract_image_empty_text_raises_empty_content() -> None:
    adapter = JdOcrAdapter(engine=FakeEngine("   \n  "))
    with pytest.raises(JdInputError) as error:
        await adapter.extract_image(JdImageInput(content=_png_bytes(), media_type="image/png"))
    assert error.value.error_code == ErrorCode.EMPTY_CONTENT


def _baidu_transport(words_result: list[dict[str, object]] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/2.0/token":
            return httpx.Response(200, json={"access_token": "token-1", "expires_in": 2_592_000})
        if "ocr" in request.url.path:
            return httpx.Response(
                200,
                json={"words_result": words_result or [{"words": "Python"}]},
            )
        return httpx.Response(404, json={"error_code": 404})

    return httpx.MockTransport(handler)


def test_baidu_engine_requests_token_and_ocr() -> None:
    engine = BaiduOcrEngine(
        api_key="api-key",
        secret_key="secret-key",
        transport=_baidu_transport([{"words": "Python 后端"}, {"words": "要求 FastAPI"}]),
    )
    text = engine.extract_text(Image.new("RGB", (10, 10), "white"))
    assert text == "Python 后端\n要求 FastAPI"


def test_baidu_engine_missing_credentials() -> None:
    engine = BaiduOcrEngine(transport=_baidu_transport())
    with pytest.raises(JdInputError) as error:
        engine.extract_text(Image.new("RGB", (10, 10), "white"))
    assert error.value.error_code == ErrorCode.OCR_FAILED


def test_baidu_engine_maps_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/2.0/token":
            return httpx.Response(200, json={"access_token": "token-1", "expires_in": 2_592_000})
        return httpx.Response(200, json={"error_code": 17, "error_msg": "limit reached"})

    engine = BaiduOcrEngine(api_key="a", secret_key="b", transport=httpx.MockTransport(handler))
    with pytest.raises(JdInputError) as error:
        engine.extract_text(Image.new("RGB", (10, 10), "white"))
    assert error.value.error_code == ErrorCode.OCR_FAILED
