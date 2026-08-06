"""受控链接抓取 Adapter 的 SSRF、重定向、大小与内容类型测试。"""

import httpx
import pytest
from app.infrastructure.jd_fetch import JdFetchAdapter, _resolve_and_verify
from app.ports.jd_input import (
    JdInputError,
    JdInputErrorCode,
    JdInputKind,
    JdUrlFetchPolicy,
    JdUrlInput,
)


def _resolver(*addresses: str):
    async def resolver(host: str, port: int) -> list[str]:
        return list(addresses)

    return resolver


def _adapter(handler) -> JdFetchAdapter:
    return JdFetchAdapter(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_resolve_and_verify_rejects_private_address() -> None:
    policy = JdUrlFetchPolicy()
    with pytest.raises(JdInputError) as error:
        await _resolve_and_verify(_resolver("127.0.0.1"), policy, "jobs.example.com", 443)
    assert error.value.error_code == JdInputErrorCode.UNSAFE_URL


@pytest.mark.asyncio
async def test_resolve_and_verify_rejects_if_any_private_address() -> None:
    policy = JdUrlFetchPolicy()
    with pytest.raises(JdInputError) as error:
        await _resolve_and_verify(
            _resolver("93.184.216.34", "10.0.0.1"), policy, "jobs.example.com", 443
        )
    assert error.value.error_code == JdInputErrorCode.UNSAFE_URL


@pytest.mark.asyncio
async def test_resolve_and_verify_returns_public_address() -> None:
    policy = JdUrlFetchPolicy()
    target = await _resolve_and_verify(_resolver("93.184.216.34"), policy, "jobs.example.com", 443)
    assert target == "93.184.216.34"


@pytest.mark.asyncio
async def test_resolve_and_verify_empty_resolution_fails() -> None:
    policy = JdUrlFetchPolicy()
    with pytest.raises(JdInputError) as error:
        await _resolve_and_verify(_resolver(), policy, "jobs.example.com", 443)
    assert error.value.error_code == JdInputErrorCode.FETCH_FAILED


@pytest.mark.asyncio
async def test_fetch_extracts_html_text_and_source_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=(
                "<html><head><title>Hidden</title></head>"
                "<body><h1>Backend Engineer</h1>"
                "<script>var x = 1;</script>"
                "<p>Python and FastAPI required.</p></body></html>"
            ),
            headers={"content-type": "text/html; charset=utf-8"},
        )

    result = await _adapter(handler).fetch_url(JdUrlInput("https://jobs.example.com/role"))

    assert result.kind is JdInputKind.URL
    assert result.source_url == "https://jobs.example.com/role"
    assert "Backend Engineer" in result.jd_text
    assert "Python and FastAPI required." in result.jd_text
    assert "Hidden" not in result.jd_text
    assert "var x = 1" not in result.jd_text


@pytest.mark.asyncio
async def test_fetch_returns_plain_text_as_is() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text="Senior backend engineer", headers={"content-type": "text/plain"}
        )

    result = await _adapter(handler).fetch_url(JdUrlInput("https://jobs.example.com/x"))

    assert result.jd_text == "Senior backend engineer"


@pytest.mark.asyncio
async def test_fetch_follows_redirect_and_revalidates_target() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(
                302, headers={"location": "https://jobs.example.com/final"}, text=""
            )
        return httpx.Response(
            200,
            text="<html><body>Final JD text</body></html>",
            headers={"content-type": "text/html"},
        )

    result = await _adapter(handler).fetch_url(JdUrlInput("https://jobs.example.com/start"))

    assert result.source_url == "https://jobs.example.com/final"
    assert "Final JD text" in result.jd_text


@pytest.mark.asyncio
async def test_fetch_rejects_too_many_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": request.url.path}, text="")

    with pytest.raises(JdInputError) as error:
        await _adapter(handler).fetch_url(JdUrlInput("https://jobs.example.com/a"))
    assert error.value.error_code == JdInputErrorCode.TOO_MANY_REDIRECTS


@pytest.mark.asyncio
async def test_fetch_rejects_redirect_to_fragment() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(
                302,
                headers={"location": "https://jobs.example.com/final#section"},
                text="",
            )
        return httpx.Response(200, text="ok", headers={"content-type": "text/plain"})

    with pytest.raises(JdInputError) as error:
        await _adapter(handler).fetch_url(JdUrlInput("https://jobs.example.com/start"))
    assert error.value.error_code == JdInputErrorCode.INVALID_URL


@pytest.mark.asyncio
async def test_fetch_rejects_redirect_to_private_host() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "http://192.168.1.1/x"}, text="")
        return httpx.Response(200, text="ok", headers={"content-type": "text/plain"})

    with pytest.raises(JdInputError) as error:
        await _adapter(handler).fetch_url(JdUrlInput("https://jobs.example.com/start"))
    assert error.value.error_code == JdInputErrorCode.UNSAFE_URL


@pytest.mark.asyncio
async def test_fetch_rejects_oversized_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"a" * 1_000, headers={"content-type": "text/plain"})

    policy = JdUrlFetchPolicy(max_response_bytes=100)
    adapter = JdFetchAdapter(transport=httpx.MockTransport(handler))
    with pytest.raises(JdInputError) as error:
        await adapter.fetch_url(JdUrlInput("https://jobs.example.com/x", policy=policy))
    assert error.value.error_code == JdInputErrorCode.RESPONSE_TOO_LARGE


@pytest.mark.asyncio
async def test_fetch_rejects_unsupported_content_type() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"%PDF-1.4 fake", headers={"content-type": "application/pdf"}
        )

    with pytest.raises(JdInputError) as error:
        await _adapter(handler).fetch_url(JdUrlInput("https://jobs.example.com/resume.pdf"))
    assert error.value.error_code == JdInputErrorCode.FETCH_FAILED
