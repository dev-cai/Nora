"""JD 输入 Port、资源限制与 SSRF 契约测试。"""

from dataclasses import replace

import pytest
from app.ports.jd_input import (
    MAX_JD_IMAGE_BYTES,
    JdImageInput,
    JdInputError,
    JdInputErrorCode,
    JdInputKind,
    JdInputPort,
    JdInputResult,
    JdUrlFetchPolicy,
    JdUrlInput,
)


class FakeJdInputAdapter:
    async def extract_image(self, request: JdImageInput) -> JdInputResult:
        return JdInputResult(jd_text="Extracted role", kind=JdInputKind.IMAGE)

    async def fetch_url(self, request: JdUrlInput) -> JdInputResult:
        return JdInputResult(
            jd_text="Fetched role",
            kind=JdInputKind.URL,
            source_url=request.url,
        )


def assert_error_code(error: pytest.ExceptionInfo[JdInputError], code: JdInputErrorCode) -> None:
    assert error.value.error_code == code


async def test_port_is_runtime_checkable_and_results_feed_text_path() -> None:
    adapter = FakeJdInputAdapter()
    assert isinstance(adapter, JdInputPort)

    image_result = await adapter.extract_image(
        JdImageInput(content=b"\x89PNG\r\n\x1a\ncontent", media_type="image/png")
    )
    url_result = await adapter.fetch_url(JdUrlInput("https://jobs.example.com/role"))

    assert image_result.jd_text == "Extracted role"
    assert url_result.source_url == "https://jobs.example.com/role"


def test_result_normalizes_text_for_existing_job_posting_path() -> None:
    result = JdInputResult(jd_text="  Line one  \r\nLine two  ", kind=JdInputKind.IMAGE)
    assert result.jd_text == "Line one\nLine two"


@pytest.mark.parametrize(
    ("media_type", "content"),
    [
        ("image/png", b"\x89PNG\r\n\x1a\ncontent"),
        ("IMAGE/JPEG", b"\xff\xd8\xffcontent"),
    ],
)
def test_image_contract_accepts_matching_png_and_jpeg(media_type: str, content: bytes) -> None:
    request = JdImageInput(content=content, media_type=media_type)
    assert request.media_type in {"image/png", "image/jpeg"}


@pytest.mark.parametrize(
    ("media_type", "content"),
    [
        ("image/gif", b"GIF89a"),
        ("image/png", b"\xff\xd8\xffcontent"),
        ("image/jpeg", b""),
    ],
)
def test_image_contract_rejects_unsupported_or_mismatched_content(
    media_type: str, content: bytes
) -> None:
    with pytest.raises(JdInputError) as error:
        JdImageInput(content=content, media_type=media_type)
    assert_error_code(error, JdInputErrorCode.UNSUPPORTED_IMAGE)


def test_image_contract_rejects_payload_above_ten_mib() -> None:
    with pytest.raises(JdInputError) as error:
        JdImageInput(
            content=b"\x89PNG\r\n\x1a\n" + b"x" * MAX_JD_IMAGE_BYTES,
            media_type="image/png",
        )
    assert_error_code(error, JdInputErrorCode.IMAGE_TOO_LARGE)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://jobs.example.com/role",
        "https://user:secret@jobs.example.com/role",
        "https://jobs.example.com/role#fragment",
        "https://bad_host.example/role",
        "https://jobs.example.com:invalid/role",
    ],
)
def test_url_contract_rejects_invalid_urls(url: str) -> None:
    with pytest.raises(JdInputError) as error:
        JdUrlInput(url)
    assert_error_code(error, JdInputErrorCode.INVALID_URL)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/admin",
        "https://service.internal/role",
        "http://127.0.0.1/role",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/role",
    ],
)
def test_url_contract_rejects_local_and_private_targets(url: str) -> None:
    with pytest.raises(JdInputError) as error:
        JdUrlInput(url)
    assert_error_code(error, JdInputErrorCode.UNSAFE_URL)


@pytest.mark.parametrize(
    "url",
    [
        "http://ｌｏｃａｌｈｏｓｔ/admin",
        "http://１２７。０。０。１/admin",
    ],
)
def test_url_contract_rechecks_hosts_after_idna_normalization(url: str) -> None:
    with pytest.raises(JdInputError) as error:
        JdUrlInput(url)
    assert_error_code(error, JdInputErrorCode.UNSAFE_URL)


def test_url_contract_normalizes_public_url_without_losing_query() -> None:
    request = JdUrlInput(" HTTPS://Jobs.Example.COM:443/roles/1?from=nora ")
    assert request.url == "https://jobs.example.com/roles/1?from=nora"


def test_fetch_policy_rejects_any_non_public_dns_answer() -> None:
    policy = JdUrlFetchPolicy()
    policy.ensure_public_addresses(["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"])

    with pytest.raises(JdInputError) as error:
        policy.ensure_public_addresses(["93.184.216.34", "10.0.0.7"])
    assert_error_code(error, JdInputErrorCode.UNSAFE_URL)


def test_fetch_policy_enforces_redirect_and_response_limits() -> None:
    policy = JdUrlFetchPolicy()
    policy.ensure_redirect_count(3)
    policy.ensure_response_size(policy.max_response_bytes)

    with pytest.raises(JdInputError) as redirects:
        policy.ensure_redirect_count(4)
    assert_error_code(redirects, JdInputErrorCode.TOO_MANY_REDIRECTS)

    with pytest.raises(JdInputError) as response:
        policy.ensure_response_size(policy.max_response_bytes + 1)
    assert_error_code(response, JdInputErrorCode.RESPONSE_TOO_LARGE)


@pytest.mark.parametrize(
    "policy",
    [
        {"allowed_schemes": frozenset({"http", "file"})},
        {"max_redirects": 4},
        {"max_response_bytes": 2 * 1024 * 1024 + 1},
        {"connect_timeout_seconds": 5.1},
        {"read_timeout_seconds": 10.1},
    ],
)
def test_fetch_policy_can_be_tightened_but_not_weakened(policy: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        JdUrlFetchPolicy(**policy)  # type: ignore[arg-type]

    tightened = JdUrlFetchPolicy(max_redirects=1, max_response_bytes=1024)
    assert tightened.max_redirects == 1
    assert tightened.max_response_bytes == 1024


def test_fetch_policy_copies_a_mutable_scheme_collection() -> None:
    schemes = {"https"}
    policy = JdUrlFetchPolicy(allowed_schemes=schemes)  # type: ignore[arg-type]

    schemes.add("file")

    assert policy.allowed_schemes == frozenset({"https"})
    with pytest.raises(JdInputError) as error:
        JdUrlInput("file://public.example/path", policy=policy)
    assert_error_code(error, JdInputErrorCode.INVALID_URL)


def test_result_requires_text_and_url_provenance() -> None:
    with pytest.raises(JdInputError) as empty:
        JdInputResult(jd_text="  ", kind=JdInputKind.IMAGE)
    assert_error_code(empty, JdInputErrorCode.EMPTY_CONTENT)

    with pytest.raises(JdInputError) as source:
        JdInputResult(jd_text="Role", kind=JdInputKind.URL)
    assert_error_code(source, JdInputErrorCode.INVALID_URL)

    with pytest.raises(JdInputError) as string_url:
        JdInputResult(jd_text="Role", kind="url")  # type: ignore[arg-type]
    assert_error_code(string_url, JdInputErrorCode.INVALID_URL)

    with pytest.raises(JdInputError) as string_image:
        JdInputResult(
            jd_text="Role",
            kind="image",  # type: ignore[arg-type]
            source_url="https://jobs.example.com/role",
        )
    assert_error_code(string_image, JdInputErrorCode.INVALID_URL)

    with pytest.raises(JdInputError) as invalid_kind:
        JdInputResult(jd_text="Role", kind="document")  # type: ignore[arg-type]
    assert_error_code(invalid_kind, JdInputErrorCode.INVALID_INPUT_KIND)

    url_result = JdInputResult(
        jd_text="Role",
        kind=JdInputKind.URL,
        source_url="HTTPS://Jobs.Example.COM:443/role",
    )
    assert url_result.source_url == "https://jobs.example.com/role"

    with pytest.raises(JdInputError) as too_large:
        replace(
            JdInputResult(jd_text="Role", kind=JdInputKind.IMAGE),
            jd_text="x" * 100_001,
        )
    assert_error_code(too_large, JdInputErrorCode.CONTENT_TOO_LARGE)
