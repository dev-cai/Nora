"""Public HTTPS smoke contracts."""

import importlib.util
import json
import sys
from email.message import Message
from pathlib import Path

import pytest

SMOKE_PATH = Path(__file__).parents[3] / "deploy" / "public_smoke.py"
SPEC = importlib.util.spec_from_file_location("nora_public_smoke", SMOKE_PATH)
assert SPEC is not None and SPEC.loader is not None
SMOKE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SMOKE
SPEC.loader.exec_module(SMOKE)


class _Response:
    def __init__(self, url: str, content_type: str, body: bytes, *, proxied: bool) -> None:
        self.status = 200
        self._url = url
        self._body = body
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        for name, value in SMOKE.SECURITY_HEADERS.items():
            self.headers[name] = value
        if proxied:
            self.headers["X-Nora-Web-Proxy"] = "true"

    def __enter__(self):  # type: ignore[no-untyped-def]
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def geturl(self) -> str:
        return self._url

    def read(self, _limit: int) -> bytes:
        return self._body


class _Opener:
    def __init__(self, responses: dict[str, _Response]) -> None:
        self.responses = responses
        self.requests: list[str] = []

    def open(self, request, *, timeout: float):  # type: ignore[no-untyped-def]
        assert timeout == 5
        self.requests.append(request.full_url)
        return self.responses[request.full_url]


def _opener(origin: str = "https://nora.test") -> _Opener:
    return _Opener(
        {
            f"{origin}/": _Response(
                f"{origin}/", "text/html; charset=utf-8", b"<html>Nora</html>", proxied=False
            ),
            f"{origin}/api/live": _Response(
                f"{origin}/api/live",
                "application/json",
                json.dumps({"status": "live"}).encode(),
                proxied=True,
            ),
            f"{origin}/api/ready": _Response(
                f"{origin}/api/ready",
                "application/json",
                json.dumps({"status": "ready"}).encode(),
                proxied=True,
            ),
        }
    )


def test_public_smoke_verifies_https_web_and_proxied_api_chain() -> None:
    opener = _opener()

    SMOKE.run_public_smoke("https://nora.test/", timeout=5, opener_factory=lambda: opener)

    assert opener.requests == [
        "https://nora.test/",
        "https://nora.test/api/live",
        "https://nora.test/api/ready",
    ]


@pytest.mark.parametrize(
    "origin",
    [
        "http://nora.test",
        "https://user:pass@nora.test",
        "https://nora.test/path",
        "https://nora.test?query=1",
        "https://nora.test#fragment",
    ],
)
def test_public_smoke_rejects_non_origin_inputs(origin: str) -> None:
    with pytest.raises(SMOKE.PublicSmokeError, match="invalid_origin"):
        SMOKE.run_public_smoke(origin, opener_factory=lambda: _opener())


def test_public_smoke_requires_host_hsts_and_web_proxy_marker() -> None:
    opener = _opener()
    del opener.responses["https://nora.test/"].headers["Strict-Transport-Security"]
    with pytest.raises(SMOKE.PublicSmokeError, match="host_hsts"):
        SMOKE.run_public_smoke("https://nora.test", timeout=5, opener_factory=lambda: opener)

    opener = _opener()
    del opener.responses["https://nora.test/api/live"].headers["X-Nora-Web-Proxy"]
    with pytest.raises(SMOKE.PublicSmokeError, match="web_proxy_path"):
        SMOKE.run_public_smoke("https://nora.test", timeout=5, opener_factory=lambda: opener)
