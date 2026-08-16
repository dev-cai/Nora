"""Verify the real HTTPS Host Proxy -> Web -> API production path."""

from __future__ import annotations

import argparse
import json
import re
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

MAX_RESPONSE_BYTES = 64 * 1024
SECURITY_HEADERS = {
    "content-security-policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; "
        "frame-src blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    ),
    "referrer-policy": "no-referrer",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
}


class PublicSmokeError(RuntimeError):
    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


@dataclass(frozen=True)
class SmokeResponse:
    content_type: str
    headers: dict[str, str]
    body: bytes


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        return None


def _build_opener() -> Any:
    context = ssl.create_default_context()
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context),
        _RejectRedirects(),
    )


def validate_origin(origin: str) -> str:
    if origin != origin.strip():
        raise PublicSmokeError("invalid_origin")
    try:
        parsed = urlsplit(origin)
        parsed.port
    except ValueError as exc:
        raise PublicSmokeError("invalid_origin") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise PublicSmokeError("invalid_origin")
    return origin[:-1] if origin.endswith("/") else origin


def _request(
    url: str,
    *,
    timeout: float,
    opener: Any,
) -> SmokeResponse:
    try:
        with opener.open(urllib.request.Request(url, method="GET"), timeout=timeout) as response:
            if response.status != 200:
                raise PublicSmokeError("unexpected_status")
            if response.geturl() != url:
                raise PublicSmokeError("unexpected_redirect")
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise PublicSmokeError("response_too_large")
            headers = {name.lower(): value for name, value in response.headers.items()}
            return SmokeResponse(
                content_type=headers.get("content-type", "").split(";", 1)[0].strip().lower(),
                headers=headers,
                body=body,
            )
    except PublicSmokeError:
        raise
    except urllib.error.HTTPError as exc:
        raise PublicSmokeError("unexpected_status") from exc
    except (TimeoutError, ssl.SSLError, urllib.error.URLError, OSError) as exc:
        raise PublicSmokeError("tls_or_network_failure") from exc


def _verify_security_headers(response: SmokeResponse) -> None:
    for name, expected in SECURITY_HEADERS.items():
        if response.headers.get(name) != expected:
            raise PublicSmokeError("web_security_headers")
    hsts = response.headers.get("strict-transport-security", "")
    match = re.search(r"(?:^|;)\s*max-age=([0-9]+)(?:;|$)", hsts, re.IGNORECASE)
    if match is None or int(match.group(1)) < 1:
        raise PublicSmokeError("host_hsts")


def _verify_api(response: SmokeResponse, expected_status: str) -> None:
    if response.content_type != "application/json":
        raise PublicSmokeError("api_content_type")
    try:
        payload = json.loads(response.body)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PublicSmokeError("api_json") from exc
    if payload != {"status": expected_status}:
        raise PublicSmokeError("api_payload")
    if response.headers.get("x-nora-web-proxy") != "true":
        raise PublicSmokeError("web_proxy_path")
    _verify_security_headers(response)


def run_public_smoke(
    origin: str,
    *,
    timeout: float = 10.0,
    opener_factory: Callable[[], Any] = _build_opener,
) -> None:
    normalized = validate_origin(origin)
    if timeout <= 0 or timeout > 60:
        raise PublicSmokeError("invalid_timeout")
    opener = opener_factory()
    root = _request(f"{normalized}/", timeout=timeout, opener=opener)
    if root.content_type != "text/html":
        raise PublicSmokeError("web_content_type")
    _verify_security_headers(root)
    _verify_api(
        _request(f"{normalized}/api/live", timeout=timeout, opener=opener),
        "live",
    )
    _verify_api(
        _request(f"{normalized}/api/ready", timeout=timeout, opener=opener),
        "ready",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    arguments = parser.parse_args()
    try:
        run_public_smoke(arguments.origin, timeout=arguments.timeout)
    except PublicSmokeError as exc:
        raise SystemExit(f"public_smoke_error={exc.category}") from exc
    print("public_smoke=passed")


if __name__ == "__main__":
    main()
