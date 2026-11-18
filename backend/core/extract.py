"""Content extraction for uploads. Stdlib only.

Text, Markdown and CSV are decoded. PDFs go through a best-effort text extractor (Flate or uncompressed content streams,
Tj/TJ/'/" operators, simple fonts). It reports failure instead of guessing for encrypted PDFs, scanned PDFs (no text
operators), composite (Type0/CID) fonts, unreadable output and files with no content streams. Images are never read here:
they are interpreted only by a provider that supports vision, and the stdlib providers do not. Nothing is invented.
"""
from __future__ import annotations

import re
import zlib
from dataclasses import dataclass
from typing import List, Optional

MAX_TEXT_CHARS = 50000          # matches the discovery text limit
MAX_INFLATED_BYTES = 20 * 1024 * 1024
MIN_READABLE_RATIO = 0.85


@dataclass
class Extraction:
    kind: str
    interpreted: bool
    text: str = ""
    method: str = "none"
    reason: Optional[str] = None
    truncated: bool = False

    def to_dict(self, preview_chars: int = 500) -> dict:
        return {"interpreted": self.interpreted, "method": self.method, "reason": self.reason, "chars": len(self.text),
                "truncated": self.truncated, "preview": self.text[:preview_chars]}


def _fail(kind: str, reason: str, method: str = "pdf_text") -> Extraction:
    return Extraction(kind, False, "", method, reason)


def _finish(kind: str, text: str, method: str) -> Extraction:
    truncated = len(text) > MAX_TEXT_CHARS
    return Extraction(kind, True, text[:MAX_TEXT_CHARS], method, None, truncated)


def extract(kind: str, data: bytes, provider=None) -> Extraction:
    """Extract text from validated upload bytes. `provider` is only used for images."""
    if kind in ("text", "csv"):
        return _finish(kind, data.decode("utf-8"), "utf8")
    if kind == "pdf":
        return extract_pdf(data)
    if kind in ("png", "jpeg"):
        return extract_image(kind, data, provider)
    return Extraction(kind, False, "", "none", f"{kind.upper()} content is validated and stored but not read in this version")


def extract_image(kind: str, data: bytes, provider=None) -> Extraction:
    if provider is None:
        return Extraction(kind, False, "", "none", "images are not interpreted: no vision capable provider was requested "
                          "(there is no OCR in the stdlib runtime)")
    describe = getattr(provider, "describe_image", None)
    if describe is None:
        from ai_providers.base import ProviderUnsupported
        raise ProviderUnsupported(f"provider '{getattr(provider, 'name', '?')}' does not support image input")
    text = describe(data, "image/png" if kind == "png" else "image/jpeg")  # raises on any failure
    if not isinstance(text, str) or not text.strip():
        from ai_providers.base import ProviderError
        raise ProviderError("provider returned no description for the image")
    return _finish(kind, text, "provider_vision")


# ------------------------------------------------------------------ PDF
_OBJ = re.compile(rb"(\d+)\s+(\d+)\s+obj\b(.*?)endobj", re.S)
_STREAM = re.compile(rb"stream\r?\n(.*?)\r?\n?endstream", re.S)
_ESC = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12, ord("("): 40, ord(")"): 41, ord("\\"): 92}
_TOKEN = re.compile(rb"\[|\]|<[0-9A-Fa-f\s]*>|\((?:\\.|[^\\()])*\)|[-+]?\d*\.?\d+|[A-Za-z'\"*]+|/[^\s/\[\]()<>]*|<<|>>", re.S)


def _unescape(raw: bytes) -> bytes:
    out, i = bytearray(), 0
    while i < len(raw):
        c = raw[i]
        if c != 92:
            out.append(c)
            i += 1
            continue
        i += 1
        if i >= len(raw):
            break
        c = raw[i]
        if 48 <= c <= 55:  # octal, up to 3 digits
            j = i
            while j < len(raw) and j < i + 3 and 48 <= raw[j] <= 55:
                j += 1
            out.append(int(raw[i:j], 8) & 255)
            i = j
            continue
        if c in (10, 13):  # line continuation
            if c == 13 and raw[i + 1:i + 2] == b"\n":
                i += 1
            i += 1
            continue
        out.append(_ESC.get(c, c))
        i += 1
    return bytes(out)


def _decode(b: bytes) -> str:
    return b.decode("cp1252", errors="replace")


def _inflate(data: bytes) -> Optional[bytes]:
    d = zlib.decompressobj()
    try:
        out = d.decompress(data, MAX_INFLATED_BYTES)
    except zlib.error:
        return None
    return out


def _content_text(content: bytes) -> str:
    """Text shown by one content stream, with a newline per line move or text object."""
    parts: List[str] = []
    stack: list = []
    for m in _TOKEN.finditer(content):
        t = m.group(0)
        if t.startswith(b"("):
            stack.append(_decode(_unescape(t[1:-1])))
        elif t.startswith(b"<") and t not in (b"<<",):
            hx = re.sub(rb"\s", b"", t[1:-1])
            if len(hx) % 2:
                hx += b"0"
            stack.append(_decode(bytes.fromhex(hx.decode())))
        elif t in (b"[", b"]"):
            stack.append(t)
        elif t in (b"Tj", b"'", b'"'):
            if t != b"Tj":
                parts.append("\n")
            parts.append(stack[-1] if stack and isinstance(stack[-1], str) else "")
            stack.clear()
        elif t == b"TJ":
            for s in stack:
                if isinstance(s, str):
                    parts.append(s)
                elif isinstance(s, float) and s < -200:
                    parts.append(" ")  # a large negative kern is a word gap
            stack.clear()
        elif t in (b"Td", b"TD", b"T*", b"ET", b"Tm"):
            parts.append("\n")
            stack.clear()
        elif t[:1].isalpha() or t[:1] in (b"'", b'"'):
            stack.clear()
        else:
            stack.append(float(t) if re.fullmatch(rb"[-+]?\d*\.?\d+", t) else t)
    text = "".join(parts)
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+\n", "\n", text))


def extract_pdf(data: bytes) -> Extraction:
    if not data.startswith(b"%PDF-"):
        return _fail("pdf", "content does not look like a PDF")
    if re.search(rb"/Encrypt\b", data):
        return _fail("pdf", "PDF is encrypted; text was not extracted")
    objs = _OBJ.findall(data)
    if not objs:
        return _fail("pdf", "no PDF objects could be parsed (damaged or unsupported file structure)")
    chunks: List[str] = []
    unsupported_filter = False
    has_stream = False
    composite = False
    for _num, _gen, body in objs:
        if re.search(rb"/Subtype\s*/Type0\b|/Encoding\s*/Identity-H\b", body):
            composite = True
        sm = _STREAM.search(body)
        if not sm:
            continue
        has_stream = True
        head, raw = body[:sm.start()], sm.group(1)
        if re.search(rb"/Subtype\s*/Image\b|/Type\s*/XRef\b", head):
            continue
        filt = re.findall(rb"/(FlateDecode|Fl|LZWDecode|ASCII85Decode|ASCIIHexDecode|RunLengthDecode|DCTDecode|CCITTFaxDecode"
                          rb"|JBIG2Decode|JPXDecode|Crypt)\b", head)
        if filt in ([b"FlateDecode"], [b"Fl"]):
            raw = _inflate(raw)
            if raw is None:
                continue
        elif filt:
            unsupported_filter = True
            continue
        if re.search(rb"/Type\s*/ObjStm\b", head):
            if re.search(rb"/Type0\b|/Identity-H\b", raw):
                composite = True
            continue
        if re.search(rb"\bBT\b", raw) and re.search(rb"\bET\b", raw):
            t = _content_text(raw).strip()
            if t:
                chunks.append(t)
    if composite:
        return _fail("pdf", "PDF uses composite (CID or Type0) fonts, whose text needs font maps this reader does not "
                     "implement; nothing was extracted")
    text = "\n\n".join(chunks).strip()
    if not text:
        if unsupported_filter:
            return _fail("pdf", "PDF content uses a compression filter that is not supported; nothing was extracted")
        why = ("no text operators were found; this looks like a scanned or image only PDF, which needs OCR that is not "
               "available" if has_stream else "no content streams were found")
        return _fail("pdf", why)
    printable = sum(1 for c in text if c.isprintable() or c in "\n\t")
    letters = sum(1 for c in text if c.isalpha())
    if printable / len(text) < MIN_READABLE_RATIO or letters < 3:
        return _fail("pdf", "extracted bytes are not readable text (custom font encoding); nothing was used")
    return _finish("pdf", text, "pdf_text")
