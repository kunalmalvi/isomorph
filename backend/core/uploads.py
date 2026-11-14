"""Upload validation: size cap, extension allowlist, content sniffing, filename sanitisation. Stdlib only.

Validation never trusts the client content type. Content must match the extension.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from dataclasses import dataclass
from typing import Dict, Optional

from .errors import PayloadTooLarge, ValidationFailed

ALLOWED_EXTENSIONS: Dict[str, str] = {
    ".txt": "text", ".md": "text", ".csv": "csv", ".json": "json", ".pdf": "pdf", ".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg",
}
MAGIC = {"pdf": b"%PDF-", "png": b"\x89PNG\r\n\x1a\n", "jpeg": b"\xff\xd8\xff"}
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_SAFE_SCOPE = re.compile(r"[^A-Za-z0-9_-]")


@dataclass
class ValidatedUpload:
    filename: str
    extension: str
    kind: str
    size: int
    data: bytes


def sanitize_filename(name: str) -> str:
    base = (name or "").replace("\\", "/").split("/")[-1]
    base = _SAFE.sub("_", base).lstrip(".")
    return base[:100]


def validate_upload(filename: str, data: bytes, max_bytes: int, content_type: Optional[str] = None) -> ValidatedUpload:
    if len(data) > max_bytes:
        raise PayloadTooLarge(f"file exceeds {max_bytes} bytes")
    if not data:
        raise ValidationFailed("file is empty")
    safe = sanitize_filename(filename)
    if not safe:
        raise ValidationFailed("invalid filename")
    ext = os.path.splitext(safe)[1].lower()
    kind = ALLOWED_EXTENSIONS.get(ext)
    if kind is None:
        raise ValidationFailed(f"extension {ext or '(none)'} is not allowed", [sorted(ALLOWED_EXTENSIONS)])
    if kind in MAGIC:
        if not data.startswith(MAGIC[kind]):
            raise ValidationFailed(f"content does not look like a {kind} file")
    else:
        if b"\x00" in data:
            raise ValidationFailed("binary content in a text file")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise ValidationFailed("text files must be UTF-8")
        if kind == "json":
            try:
                json.loads(text)
            except ValueError:
                raise ValidationFailed("invalid JSON")
        elif kind == "csv":
            try:
                rows = list(csv.reader(io.StringIO(text), strict=True))
            except csv.Error:
                raise ValidationFailed("invalid CSV")
            if not rows or not any(any(c.strip() for c in r) for r in rows):
                raise ValidationFailed("CSV has no data")
    return ValidatedUpload(safe, ext, kind, len(data), data)


INTERPRETED_KINDS = ("text", "csv")  # json is validated only; nothing reads it into a model either
NOT_INTERPRETED_NOTE = ("{kind} content is validated and stored but NOT read or interpreted in this version. "
                        "No text, figures or structure were extracted from it, so nothing in the model is derived from this file.")


def interpretation(kind: str) -> dict:
    """Whether the server reads this kind of upload. Binary kinds (pdf, png, jpeg) and json are never interpreted."""
    ok = kind in INTERPRETED_KINDS
    return {"interpreted": ok, "note": None if ok else NOT_INTERPRETED_NOTE.format(kind=kind.upper())}


def store_upload(directory: str, scope: str, up: ValidatedUpload) -> dict:
    """Write the bytes under `directory/scope/<sha256><ext>` (content addressed, so a repeat upload is a no-op).

    `scope` must be a plain id (letters, digits, '-' and '_'). Returns the provenance record for the response.
    """
    if not scope or _SAFE_SCOPE.search(scope):
        raise ValidationFailed("invalid upload scope")
    digest = hashlib.sha256(up.data).hexdigest()
    folder = os.path.join(directory, scope)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, digest + up.extension)
    if not os.path.exists(path):
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(up.data)
        os.replace(tmp, path)
    return {"sha256": digest, "stored": True, "original_filename": up.filename, "size": up.size, **interpretation(up.kind)}
