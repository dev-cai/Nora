"""Minimal, dependency-free extraction of text operators from a PDF.

This is intentionally a bounded ingestion helper for text-based resumes. It does
not attempt OCR and rejects documents that contain no extractable text.
"""

from __future__ import annotations

import re
import zlib

from app.domain.base.exceptions import ApplicationError, ErrorCode

_STREAM_RE = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
_TEXT_RE = re.compile(rb"(?:\((?:\\.|[^\\()])*\)|<[^>]*>)\s*(?:Tj|'|\")")
_ARRAY_RE = re.compile(rb"\[(.*?)\]\s*TJ", re.DOTALL)
_STRING_RE = re.compile(rb"\((?:\\.|[^\\()])*\)|<[^>]*>")


def extract_pdf_text(data: bytes, *, max_chars: int = 60_000) -> str:
    """Extract visible text operators from a text-based PDF within a hard bound."""

    if not data.startswith(b"%PDF-"):
        raise ApplicationError("Resume file is not a valid PDF", error_code=ErrorCode.DECODE_FAILED)

    chunks: list[str] = []
    for match in _STREAM_RE.finditer(data):
        stream = match.group(1)
        header = data[max(0, match.start() - 300) : match.start()]
        if b"/FlateDecode" in header:
            try:
                stream = zlib.decompress(stream)
            except zlib.error:
                continue
        for item in _TEXT_RE.finditer(stream):
            chunks.append(_decode_pdf_string(item.group(0).rsplit(None, 1)[0]))
        for item in _ARRAY_RE.finditer(stream):
            values = [_decode_pdf_string(value) for value in _STRING_RE.findall(item.group(1))]
            if values:
                chunks.append("".join(values))
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


def _decode_pdf_string(value: bytes) -> str:
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
    encodings = ("utf-16-be", "utf-8", "gb18030", "latin-1") if (
        value.startswith((b"\xfe\xff", b"\xff\xfe")) or b"\x00" in value
    ) else ("utf-8", "gb18030", "utf-16-be", "latin-1")
    for encoding in encodings:
        try:
            decoded = value.decode(encoding)
            if decoded.strip():
                return decoded
        except UnicodeDecodeError:
            continue
    return value.decode("utf-8", errors="ignore")


__all__ = ("extract_pdf_text",)
