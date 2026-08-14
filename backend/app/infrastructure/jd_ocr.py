"""PIL + 百度智能云 OCR 的截图 OCR Adapter。

实现 `JdInputPort.extract_image`：对已验证的 PNG/JPEG 做受限解码（像素与解压膨胀防护），
再通过百度智能云通用/高精度 OCR 识别为 JD 文本；OCR 输出视为不可信输入，不自动抽取或猜测内容。
凭据通过 `BAIDU_OCR_API_KEY` / `BAIDU_OCR_SECRET_KEY` 环境变量配置。
"""

import asyncio
import base64
import io
import time
from typing import Protocol

import httpx
from PIL import Image

from app.domain.base.exceptions import ErrorCode
from app.ports.jd_input import (
    JdImageInput,
    JdInputError,
    JdInputKind,
    JdInputPort,
    JdInputResult,
    JdUrlInput,
)

MAX_IMAGE_PIXELS = 40_000_000
MAX_DIMENSION = 10_000
BAIDU_TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
BAIDU_OCR_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1"
_REQUEST_TIMEOUT = 10.0

_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


class OcrEngine(Protocol):
    """可替换的 OCR 引擎，便于测试注入。"""

    def extract_text(self, image: Image.Image) -> str: ...


class BaiduOcrEngine:
    """基于百度智能云 OCR 的真实引擎，凭据为空时抛出明确错误。"""

    def __init__(
        self,
        *,
        api_key: str = "",
        secret_key: str = "",
        endpoint: str = "accurate_basic",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._endpoint = endpoint
        self._transport = transport

    def extract_text(self, image: Image.Image) -> str:
        if not self._api_key or not self._secret_key:
            raise JdInputError(
                "Baidu OCR credentials are not configured",
                ErrorCode.OCR_FAILED,
            )
        access_token = _access_token(self._api_key, self._secret_key, self._transport)
        image_b64 = base64.b64encode(_image_to_bytes(image)).decode("ascii")
        with httpx.Client(transport=self._transport, timeout=_REQUEST_TIMEOUT) as client:
            response = client.post(
                f"{BAIDU_OCR_URL}/{self._endpoint}",
                params={"access_token": access_token},
                data={"image": image_b64},
            )
            payload = response.json()
        if "error_code" in payload:
            raise JdInputError(
                f"Baidu OCR failed: {payload.get('error_msg', 'unknown error')}",
                ErrorCode.OCR_FAILED,
            )
        words = [
            item["words"]
            for item in payload.get("words_result", [])
            if isinstance(item, dict) and "words" in item
        ]
        return "\n".join(words)


class JdOcrAdapter(JdInputPort):
    """截图 OCR Adapter：`extract_image` 返回识别的 JD 文本。"""

    def __init__(self, *, engine: OcrEngine | None = None) -> None:
        self._engine = engine or BaiduOcrEngine()

    async def fetch_url(self, request: JdUrlInput) -> JdInputResult:
        raise JdInputError(
            "URL fetch is not implemented by this adapter",
            ErrorCode.FETCH_FAILED,
        )

    async def extract_image(self, request: JdImageInput) -> JdInputResult:
        image = _decode_image(request)
        text = await asyncio.to_thread(self._engine.extract_text, image)
        return JdInputResult(jd_text=text, kind=JdInputKind.IMAGE)


def _decode_image(request: JdImageInput) -> Image.Image:
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        image = Image.open(io.BytesIO(request.content))
        image.load()
    except Exception as exc:
        raise JdInputError("JD image could not be decoded", ErrorCode.DECODE_FAILED) from exc
    width, height = image.size
    if width > MAX_DIMENSION or height > MAX_DIMENSION:
        raise JdInputError(
            "JD image dimensions exceed the decode limit",
            ErrorCode.UNSUPPORTED_IMAGE,
        )
    return image.convert("RGB")


def _image_to_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _access_token(api_key: str, secret_key: str, transport: httpx.BaseTransport | None) -> str:
    cache_key = f"{api_key}:{secret_key}"
    now = time.monotonic()
    cached = _TOKEN_CACHE.get(cache_key)
    if cached is not None and cached[1] > now:
        return cached[0]
    with httpx.Client(transport=transport, timeout=_REQUEST_TIMEOUT) as client:
        response = client.post(
            BAIDU_TOKEN_URL,
            params={
                "grant_type": "client_credentials",
                "client_id": api_key,
                "client_secret": secret_key,
            },
        )
        payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise JdInputError(
            "Baidu OCR token request failed",
            ErrorCode.OCR_FAILED,
        )
    expires_in = int(payload.get("expires_in", 2_592_000))
    _TOKEN_CACHE[cache_key] = (token, now + expires_in - 300)
    return token
