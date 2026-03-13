from __future__ import annotations

from io import BytesIO
import logging
from pathlib import Path

from fastapi import UploadFile
from pypdf import PdfReader

logger = logging.getLogger("uvicorn.error")


async def extract_text_from_upload(
    file: UploadFile,
    max_file_bytes: int,
    allowed_extensions: set[str],
    debug_logging: bool = False,
) -> str:
    """
    Purpose: Extract text from one upload after validating extension and file-size limits.
    Args/Params:
    - `file` (UploadFile): Input parameter used by this function.
    - `max_file_bytes` (int): Input parameter used by this function.
    - `allowed_extensions` (set[str]): Input parameter used by this function.
    - `debug_logging` (bool): Input parameter used by this function.
    Returns:
    - `str`: Function output value.
    Raises/Exceptions:
    - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
    Examples:
    - `extract_text_from_upload(file=..., max_file_bytes=..., allowed_extensions=..., debug_logging=...)`
    """
    content = await _read_upload_with_limit(file, max_file_bytes)
    filename = (file.filename or "uploaded_file").lower()
    extension = _get_extension(filename)
    if debug_logging:
        logger.info(
            "Attachment received filename=%s extension=%s size_bytes=%d",
            file.filename or "uploaded_file",
            extension or "unknown",
            len(content),
        )

    if extension not in allowed_extensions:
        raise ValueError(f"Unsupported file type: {extension or 'unknown'}")
    if len(content) > max_file_bytes:
        raise ValueError(
            f"File is too large ({len(content)} bytes). Max allowed is {max_file_bytes} bytes."
        )

    if extension == ".pdf":
        extracted = _extract_pdf_text(content)
        if debug_logging:
            logger.info(
                "Attachment PDF extracted filename=%s extracted_chars=%d",
                file.filename or "uploaded_file",
                len(extracted),
            )
        return extracted

    extracted = _extract_text_bytes(content)
    if debug_logging:
        logger.info(
            "Attachment text extracted filename=%s extracted_chars=%d",
            file.filename or "uploaded_file",
            len(extracted),
        )
    return extracted


def _extract_pdf_text(content: bytes) -> str:
    """
    Purpose: Extract text from all readable PDF pages and return trimmed result.
    Args/Params:
    - `content` (bytes): Input parameter used by this function.
    Returns:
    - `str`: Function output value.
    Raises/Exceptions:
    - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
    Examples:
    - `_extract_pdf_text(content=...)`
    """
    if not content:
        return ""

    reader = PdfReader(BytesIO(content))
    pages: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(page_text.strip())
    return "\n\n".join(pages).strip()


def _extract_text_bytes(content: bytes) -> str:
    """
    Purpose: Decode text-based files with UTF-8 fallback strategy.
    Args/Params:
    - `content` (bytes): Input parameter used by this function.
    Returns:
    - `str`: Function output value.
    Raises/Exceptions:
    - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
    Examples:
    - `_extract_text_bytes(content=...)`
    """
    if not content:
        return ""

    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return content.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return ""


def _get_extension(filename: str) -> str:
    """
    Purpose: Return normalized lowercase file extension including leading dot.
    Args/Params:
    - `filename` (str): Input parameter used by this function.
    Returns:
    - `str`: Function output value.
    Raises/Exceptions:
    - May propagate runtime exceptions from downstream operations (I/O, network, validation, or parsing).
    Examples:
    - `_get_extension(filename=...)`
    """
    return Path(filename).suffix.lower()


async def _read_upload_with_limit(file: UploadFile, max_file_bytes: int) -> bytes:
    """
    Purpose: Read upload in chunks while enforcing a hard size limit.
    Args/Params:
    - `file` (UploadFile): Input parameter used by this function.
    - `max_file_bytes` (int): Input parameter used by this function.
    Returns:
    - `bytes`: Function output value.
    Raises/Exceptions:
    - `ValueError` if file exceeds size limit.
    Examples:
    - `_read_upload_with_limit(file=..., max_file_bytes=...)`
    """
    if max_file_bytes <= 0:
        return await file.read()

    chunks: list[bytes] = []
    total = 0
    chunk_size = min(1024 * 1024, max_file_bytes)
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_file_bytes:
            raise ValueError(
                f"File is too large ({total} bytes). Max allowed is {max_file_bytes} bytes."
            )
    return b"".join(chunks)
