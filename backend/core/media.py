"""Content sniffing for uploaded media.

The client-declared ``Content-Type`` / ``mime_type`` is a hint, never proof.
Before anything is stored or handed to OpenCV we look at the magic bytes, so a
renamed PDF or an arbitrary blob cannot enter the image pipeline and blow up
later with an unreadable-image error.
"""

from __future__ import annotations

_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
    (b"\x00\x00\x00\x0cjP  ", "image/jp2"),
    (b"\x00\x00\x00\x14ftypavif", "image/avif"),
)

_AUDIO_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"ID3", "audio/mpeg"),
    (b"OggS", "audio/ogg"),
    (b"fLaC", "audio/flac"),
    (b"RIFF", "audio/wav"),
    (b"\x1a\x45\xdf\xa3", "audio/webm"),
)


def sniff_image_content_type(data: bytes) -> str | None:
    """Return the real image type, or ``None`` when the bytes are not an image."""
    if not data:
        return None
    for signature, content_type in _IMAGE_SIGNATURES:
        if data.startswith(signature):
            return content_type
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    # ISO base media (HEIC/HEIF/AVIF/DNG): 'ftyp' at offset 4.
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in {b"heic", b"heix", b"hevc", b"mif1", b"msf1"}:
            return "image/heic"
        if brand == b"avif":
            return "image/avif"
        if brand == b"dng ":
            return "image/x-dng"
    return None


def sniff_audio_content_type(data: bytes) -> str | None:
    """Return the real audio type, or ``None`` when the bytes are not audio."""
    if not data:
        return None
    for signature, content_type in _AUDIO_SIGNATURES:
        if data.startswith(signature):
            return content_type
    if data.startswith(b"RIFF") and data[8:12] in {b"WAVE", b"AVI "}:
        return "audio/wav"
    if data[4:8] == b"ftyp":
        return "audio/mp4"
    return None


def looks_like_base64_text(data: bytes) -> bool:
    """True when the payload is printable ASCII that decodes as base64.

    Phone recordings are often sent as a data URL or a raw base64 string, so the
    audio path accepts those and this is the only way to tell real audio apart
    from a text file.
    """
    if not data or len(data) > 4096:
        return False
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        return False
    stripped = text.strip()
    if not stripped or len(stripped) < 16:
        return False
    if stripped.startswith("data:"):
        stripped = stripped.split(",", 1)[-1]
    return bool(stripped) and all(char.isalnum() or char in "+/=\r\n" for char in stripped)


__all__ = [
    "looks_like_base64_text",
    "sniff_audio_content_type",
    "sniff_image_content_type",
]
