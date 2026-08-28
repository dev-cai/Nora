"""Minimal, dependency-free extraction of text operators from a PDF.

This is intentionally a bounded ingestion helper for text-based resumes. It does
not attempt OCR and rejects documents that contain no extractable text.
"""

from __future__ import annotations

import re
import zlib
from collections.abc import Iterator

from app.domain.base.exceptions import ApplicationError, ErrorCode

_STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
_OBJECT_RE = re.compile(rb"(?:^|[\r\n])(\d+)\s+\d+\s+obj\b(.*?)endobj", re.DOTALL)
_TEXT_BLOCK_RE = re.compile(rb"BT(.*?)ET", re.DOTALL)
_TEXT_TOKEN_RE = re.compile(
    rb"(?P<array>\[(?P<array_body>.*?)\]\s*TJ)"
    rb"|(?P<string>\((?:\\.|[^\\()])*\)|<[^>]*>)\s*(?P<operator>Tj|'|\")",
    re.DOTALL,
)
_FONT_RE = re.compile(rb"/([A-Za-z][A-Za-z0-9_.-]*)\s+[-+0-9.]+\s+Tf")
_STRING_RE = re.compile(rb"\((?:\\.|[^\\()])*\)|<[^>]*>")
_FONT_RESOURCE_RE = re.compile(rb"/([A-Za-z][A-Za-z0-9_.-]*)\s+(\d+)\s+\d+\s+R")
_TYPE0_FONT_RE = re.compile(rb"/Subtype\s*/Type0.*?/ToUnicode\s+(\d+)\s+\d+\s+R", re.DOTALL)
_BFCHAR_RE = re.compile(rb"<([0-9A-Fa-f]+)>\s+<([0-9A-Fa-f]+)>")
_BFRANGE_RE = re.compile(
    rb"<([0-9A-Fa-f]+)>\s+<([0-9A-Fa-f]+)>\s+(?:<([0-9A-Fa-f]+)>|\[((?:[^\]])*)\])",
    re.DOTALL,
)


def extract_pdf_text(data: bytes, *, max_chars: int = 60_000) -> str:
    """Extract visible text operators from a text-based PDF within a hard bound."""

    if not data.startswith(b"%PDF-"):
        raise ApplicationError("Resume file is not a valid PDF", error_code=ErrorCode.DECODE_FAILED)

    font_maps = _font_maps(data)
    chunks: list[str] = []
    for match in _STREAM_RE.finditer(data):
        stream = match.group(1)
        header = data[max(0, match.start() - 300) : match.start()]
        if _is_non_text_stream(header):
            continue
        if b"/FlateDecode" in header:
            try:
                stream = zlib.decompress(stream)
            except zlib.error:
                continue
        blocks = list(_TEXT_BLOCK_RE.finditer(stream))
        if blocks:
            chunks.extend(
                value
                for block in blocks
                if (value := _extract_text_block(block.group(1), font_maps))
            )
        else:
            value = _extract_text_block(stream, {})
            if value:
                chunks.append(value)
        if sum(len(value) for value in chunks) >= max_chars:
            break

    text = "\n".join(value.strip() for value in chunks if value.strip())
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise ApplicationError(
            "未能从 PDF 中提取文字；扫描件请先转换为可搜索 PDF",
            error_code=ErrorCode.EMPTY_CONTENT,
        )
    return text[:max_chars]


def _is_non_text_stream(header: bytes) -> bool:
    return any(
        marker in header
        for marker in (
            b"/Subtype /Image",
            b"/FontFile",
            b"/FontFile2",
            b"/FontFile3",
        )
    )


def _font_maps(data: bytes) -> dict[bytes, dict[bytes, str]]:
    """Resolve page font resource names to their embedded ToUnicode maps."""

    objects = {match.group(1): match.group(2) for match in _OBJECT_RE.finditer(data)}
    cmap_by_object: dict[bytes, dict[bytes, str]] = {}
    for object_id, body in objects.items():
        font_match = _TYPE0_FONT_RE.search(body)
        if font_match:
            cmap_body = objects.get(font_match.group(1))
            if cmap_body is not None:
                cmap_stream = _decode_object_stream(cmap_body)
                cmap_by_object[font_match.group(1)] = _parse_cmap(cmap_stream)

    resource_maps: dict[bytes, dict[bytes, str]] = {}
    for body in objects.values():
        for font_dictionary in re.findall(rb"/Font\s*<<(.*?)>>", body, re.DOTALL):
            for resource_name, object_id in _FONT_RESOURCE_RE.findall(font_dictionary):
                cmap = _cmap_for_font_object(objects.get(object_id), cmap_by_object)
                if cmap:
                    resource_maps[resource_name] = cmap
    return resource_maps


def _cmap_for_font_object(
    body: bytes | None,
    cmap_by_object: dict[bytes, dict[bytes, str]],
) -> dict[bytes, str] | None:
    if body is None:
        return None
    font_match = _TYPE0_FONT_RE.search(body)
    if font_match:
        return cmap_by_object.get(font_match.group(1))
    return None


def _decode_object_stream(body: bytes) -> bytes:
    match = _STREAM_RE.search(body)
    if match is None:
        return b""
    stream = match.group(1)
    if b"/FlateDecode" in body[: match.start()]:
        try:
            return zlib.decompress(stream)
        except zlib.error:
            return b""
    return stream


def _parse_cmap(data: bytes) -> dict[bytes, str]:
    """Parse the bfchar/bfrange subset emitted by common PDF generators."""

    mappings: dict[bytes, str] = {}
    for section in _sections(data, b"beginbfchar", b"endbfchar"):
        for match in _BFCHAR_RE.finditer(section):
            mappings[bytes.fromhex(match.group(1).decode())] = _decode_unicode_hex(match.group(2))
    for section in _sections(data, b"beginbfrange", b"endbfrange"):
        for match in _BFRANGE_RE.finditer(section):
            start = int(match.group(1), 16)
            end = int(match.group(2), 16)
            destination = match.group(3)
            if destination is not None:
                first = int(destination, 16)
                width = len(match.group(1)) // 2
                for offset, source in enumerate(range(start, end + 1)):
                    mappings[source.to_bytes(width, "big")] = chr(first + offset)
                continue
            values = re.findall(rb"<([0-9A-Fa-f]+)>", match.group(4) or b"")
            width = len(match.group(1)) // 2
            for source, value in zip(range(start, end + 1), values):
                mappings[source.to_bytes(width, "big")] = _decode_unicode_hex(value)
    return mappings


def _sections(data: bytes, start_marker: bytes, end_marker: bytes) -> Iterator[bytes]:
    pattern = re.compile(start_marker + rb"(.*?)" + end_marker, re.DOTALL)
    for match in pattern.finditer(data):
        yield match.group(1)


def _extract_text_block(
    block: bytes,
    font_maps: dict[bytes, dict[bytes, str]],
) -> str:
    font_events = list(_FONT_RE.finditer(block))
    font_index = 0
    current_map: dict[bytes, str] | None = None
    values: list[str] = []
    for token in _TEXT_TOKEN_RE.finditer(block):
        while font_index < len(font_events) and font_events[font_index].start() < token.start():
            current_map = font_maps.get(font_events[font_index].group(1))
            font_index += 1
        if token.group("array") is not None:
            decoded = "".join(
                _decode_pdf_string(value, current_map)
                for value in _STRING_RE.findall(token.group("array_body"))
            )
        else:
            decoded = _decode_pdf_string(token.group("string"), current_map)
        if token.group("operator") in {b"'", b'"'}:
            values.append("\n")
        values.append(decoded)
    return "".join(values).strip()


def _decode_pdf_string(value: bytes, cmap: dict[bytes, str] | None = None) -> str:
    if value.startswith(b"(") and value.endswith(b")"):
        value = value[1:-1]
        value = re.sub(rb"\\([\\()\\\\])", rb"\1", value)
        value = re.sub(rb"\\([0-7]{1,3})", lambda m: bytes([int(m.group(1), 8)]), value)
        value = value.replace(rb"\\n", b"\n").replace(rb"\\r", b"\r").replace(rb"\\t", b"\t")
    elif value.startswith(b"<") and value.endswith(b">"):
        try:
            value = bytes.fromhex(value[1:-1].decode("ascii"))
        except (ValueError, UnicodeDecodeError):
            return ""
        if cmap:
            return _decode_cid_bytes(value, cmap)
    encodings = (
        ("utf-16-be", "utf-8", "gb18030", "latin-1")
        if (value.startswith((b"\xfe\xff", b"\xff\xfe")) or b"\x00" in value)
        else ("utf-8", "gb18030", "utf-16-be", "latin-1")
    )
    for encoding in encodings:
        try:
            decoded = value.decode(encoding)
            if decoded.strip():
                return decoded
        except UnicodeDecodeError:
            continue
    return value.decode("utf-8", errors="ignore")


def _decode_cid_bytes(value: bytes, cmap: dict[bytes, str]) -> str:
    widths = sorted({len(key) for key in cmap if key})
    width = widths[0] if widths else 2
    decoded: list[str] = []
    for offset in range(0, len(value), width):
        chunk = value[offset : offset + width]
        mapped = cmap.get(chunk)
        if mapped is not None:
            decoded.append(mapped)
        # A CID is a font-local glyph identifier, not a Unicode code point.
        # Do not turn an unmapped glyph into control characters or unrelated
        # text; ToUnicode is the only trustworthy mapping for this font.
    return "".join(decoded)


def _decode_unicode_hex(value: bytes) -> str:
    try:
        return bytes.fromhex(value.decode("ascii")).decode("utf-16-be")
    except (UnicodeDecodeError, ValueError):
        return _decode_raw_bytes(bytes.fromhex(value.decode("ascii")))


def _decode_raw_bytes(value: bytes) -> str:
    encodings = (
        ("utf-16-be", "utf-8", "gb18030", "latin-1")
        if b"\x00" in value
        else ("utf-8", "gb18030", "utf-16-be", "latin-1")
    )
    for encoding in encodings:
        try:
            decoded = value.decode(encoding)
            if decoded.strip():
                return decoded
        except UnicodeDecodeError:
            continue
    return value.decode("utf-8", errors="ignore")


__all__ = ("extract_pdf_text",)
