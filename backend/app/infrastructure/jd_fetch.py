"""SSRF 安全的受控链接抓取 Adapter。

实现 `JdInputPort.fetch_url`：先解析主机并验证所有解析结果都是公网单播地址，
再把连接固定到已验证地址（防 DNS Rebinding）；每次重定向目标都重新解析与验证；
限制响应大小、超时与 Content-Type；网页正文视为不可信输入，不做脚本、Cookie 或登录。
"""

import socket
import ssl
from html.parser import HTMLParser
from typing import Any, Awaitable, Callable
from urllib.parse import urljoin

import anyio
import httpx
from httpcore import AsyncConnectionPool
from httpcore._backends.anyio import AnyIOBackend
from httpcore._backends.base import AsyncNetworkStream

from app.ports.jd_input import (
    JdImageInput,
    JdInputError,
    JdInputErrorCode,
    JdInputKind,
    JdInputPort,
    JdInputResult,
    JdUrlFetchPolicy,
    JdUrlInput,
)

MAX_PREVIEW_TEXT_LENGTH = 100_000
_ALLOWED_CONTENT_TYPE_PREFIXES = ("text/", "application/json", "application/xhtml+xml")
_SKIP_TAGS = frozenset({"script", "style", "noscript", "template", "svg", "head"})


async def _default_resolver(host: str, port: int) -> list[str]:
    """异步解析主机，返回全部地址字符串（含 IPv6）。"""

    infos = await anyio.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list({info[4][0] for info in infos})


Resolver = Callable[[str, int], Awaitable[list[str]]]


class _VerifiedBackend(AnyIOBackend):
    """把 DNS 解析与公网验证收敛到连接前，并把连接固定到已验证地址。"""

    def __init__(self, policy: JdUrlFetchPolicy, resolver: Resolver) -> None:
        super().__init__()
        self._policy = policy
        self._resolver = resolver

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> AsyncNetworkStream:
        target = await _resolve_and_verify(self._resolver, self._policy, host, port)
        return await super().connect_tcp(
            target,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


async def _resolve_and_verify(
    resolver: Resolver, policy: JdUrlFetchPolicy, host: str, port: int
) -> str:
    """解析主机并验证所有地址为公网单播，返回固定连接的地址。"""

    addresses = await resolver(host, port)
    policy.ensure_public_addresses(addresses)
    return addresses[0]


class _SafeTransport(httpx.AsyncHTTPTransport):
    """使用 `_VerifiedBackend` 的 httpx 传输，所有连接先验证再固定地址。"""

    def __init__(
        self,
        policy: JdUrlFetchPolicy,
        resolver: Resolver,
        verify: ssl.SSLContext | bool = True,
    ) -> None:
        ssl_context = (
            ssl.create_default_context()
            if verify is True
            else (None if verify is False else verify)
        )
        self._pool = AsyncConnectionPool(
            network_backend=_VerifiedBackend(policy, resolver),
            ssl_context=ssl_context,
            http1=True,
            http2=False,
            retries=0,
        )


class JdFetchAdapter(JdInputPort):
    """受控链接抓取 Adapter：`fetch_url` 返回网页提取文本与来源 URL。"""

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Resolver = _default_resolver,
    ) -> None:
        self._transport = transport
        self._resolver = resolver

    async def extract_image(self, request: JdImageInput) -> JdInputResult:
        raise JdInputError(
            "Image OCR is not implemented by this adapter",
            JdInputErrorCode.OCR_FAILED,
        )

    async def fetch_url(self, request: JdUrlInput) -> JdInputResult:
        policy = request.policy
        transport = self._transport or _SafeTransport(policy, self._resolver)
        timeout = httpx.Timeout(
            connect=policy.connect_timeout_seconds,
            read=policy.read_timeout_seconds,
            write=policy.connect_timeout_seconds,
            pool=policy.connect_timeout_seconds,
        )
        async with httpx.AsyncClient(
            transport=transport, timeout=timeout, follow_redirects=False, trust_env=False
        ) as client:
            final_url, response = await self._follow_redirects(client, request.url, policy)
        try:
            self._ensure_content_type(response.headers.get("content-type"))
            content = await self._read_capped(response, policy)
            text = _decode_content(content, response.encoding)
        finally:
            await response.aclose()
        return JdInputResult(jd_text=text, kind=JdInputKind.URL, source_url=final_url)

    async def _follow_redirects(
        self, client: httpx.AsyncClient, url: str, policy: JdUrlFetchPolicy
    ) -> tuple[str, httpx.Response]:
        redirect_count = 0
        while True:
            policy.ensure_redirect_count(redirect_count)
            request = client.build_request("GET", url)
            response = await client.send(request, stream=True)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                await response.aclose()
                if not location:
                    raise JdInputError(
                        "JD URL redirect is missing a location header",
                        JdInputErrorCode.FETCH_FAILED,
                    )
                url = urljoin(url, location)
                redirect_count += 1
                continue
            return url, response

    async def _read_capped(self, response: httpx.Response, policy: JdUrlFetchPolicy) -> bytes:
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            policy.ensure_response_size(total)
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _ensure_content_type(content_type: str | None) -> None:
        if not content_type:
            return
        lowered = content_type.lower().split(";", 1)[0].strip()
        if not lowered.startswith(_ALLOWED_CONTENT_TYPE_PREFIXES):
            raise JdInputError(
                "JD URL returned an unsupported content type",
                JdInputErrorCode.FETCH_FAILED,
            )


def _decode_content(content: bytes, encoding: str | None) -> str:
    if _is_html(content):
        return _extract_html_text(content)
    return content.decode(encoding or "utf-8", errors="replace").strip()


def _is_html(content: bytes) -> bool:
    head = content[:1024].lower()
    return b"<html" in head or b"<!doctype html" in head


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data.strip():
            self._parts.append(data.strip())

    def text(self) -> str:
        return "\n".join(self._parts)


def _extract_html_text(content: bytes) -> str:
    parser = _TextExtractor()
    parser.feed(content.decode("utf-8", errors="replace"))
    text = parser.text()
    if len(text) > MAX_PREVIEW_TEXT_LENGTH:
        raise JdInputError(
            "JD URL page text exceeds the content limit",
            JdInputErrorCode.CONTENT_TOO_LARGE,
        )
    return text
