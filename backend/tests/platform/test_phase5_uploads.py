"""Upload endpoint and content extraction: real PDFs built with the stdlib, live server, end to end."""
import hashlib
import json
import urllib.error
import urllib.request
import zlib

import pytest

from ai_providers.base import ProviderUnsupported
from ai_providers.local import LocalProvider
from core.extract import extract, extract_image, extract_pdf
from core.uploads import interpretation
from tests.platform.test_server import srv, start, stop  # noqa: F401

PROBLEM = ["A pump moves fluid through the pipe.", "The pipe constrains the fluid flow.",
           "Friction dissipates energy at the wall.", "The goal is to minimise energy loss."]


def make_pdf(lines, compress=False, extra_objects=b"", trailer=b"", font=b"/Type /Font /Subtype /Type1 /BaseFont /Helvetica"):
    ops = b"BT /F1 12 Tf 72 720 Td 14 TL\n"
    for i, ln in enumerate(lines):
        esc = ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("cp1252")
        ops += b"(" + esc + b") Tj T*\n" if i % 2 == 0 else b"[(" + esc[:5] + b") -300 (" + esc[5:] + b")] TJ T*\n"
    ops += b"ET"
    body, filt = (zlib.compress(ops), b"/Filter /FlateDecode ") if compress else (ops, b"")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< " + filt + b"/Length " + str(len(body)).encode() + b" >>\nstream\n" + body + b"\nendstream",
            b"<< " + font + b" >>"]
    out = b"%PDF-1.4\n"
    for i, o in enumerate(objs, 1):
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    return out + extra_objects + b"trailer\n<< /Root 1 0 R " + trailer + b">>\n%%EOF\n"


def post(client, path, raw, headers=None):
    return client.call("POST", path, raw=raw, headers=headers or {"Content-Type": "application/octet-stream"})


@pytest.mark.parametrize("compress", [False, True])
def test_pdf_text_extraction(compress):
    r = extract_pdf(make_pdf(PROBLEM, compress))
    assert r.interpreted and r.reason is None
    for ln in PROBLEM:
        assert ln.replace(" ", "") in r.text.replace(" ", "").replace("\n", "")
    assert "pump moves fluid" in r.text


def test_pdf_escapes_and_hex():
    r = extract_pdf(make_pdf(["Cost (net) is 5\\3 units, flow rate holds"]))
    assert "Cost (net) is 5\\3 units" in r.text


@pytest.mark.parametrize("data,word", [
    (make_pdf([], False), "scanned"),
    (make_pdf(PROBLEM, trailer=b"/Encrypt 9 0 R "), "encrypted"),
    (make_pdf(PROBLEM, font=b"/Type /Font /Subtype /Type0 /BaseFont /X /Encoding /Identity-H"), "composite"),
    (b"%PDF-1.4\ngarbage", "no PDF objects"),
])
def test_unreadable_pdf_reports_failure(data, word):
    r = extract_pdf(data)
    assert not r.interpreted and r.text == "" and word in r.reason
    assert interpretation("pdf", r)["interpreted"] is False and "NOT read" in interpretation("pdf", r)["note"]


def test_unreadable_garbage_text_is_rejected():
    r = extract_pdf(make_pdf(["\x01\x02\x03\x04\x05\x06\x07\x08"]))
    assert not r.interpreted


def test_images_are_not_interpreted_without_vision():
    r = extract("png", b"\x89PNG\r\n\x1a\nxx")
    assert not r.interpreted and r.text == "" and "not interpreted" in r.reason
    assert interpretation("png", r)["interpreted"] is False
    with pytest.raises(ProviderUnsupported):
        extract_image("jpeg", b"\xff\xd8\xff", LocalProvider())


def test_interpretation_pdf_with_text():
    assert interpretation("pdf", extract_pdf(make_pdf(PROBLEM))) == {"interpreted": True, "note": None}


def test_upload_endpoint_end_to_end(srv):
    app, server, c, tmp = srv
    for compress in (False, True):
        pdf = make_pdf(PROBLEM, compress)
        st, rec = post(c, "/api/v1/uploads?filename=paper.pdf", pdf)
        assert st == 201 and rec["interpreted"] is True and rec["kind"] == "pdf"
        assert rec["sha256"] == hashlib.sha256(pdf).hexdigest() and rec["stored"]
        assert "pump moves fluid" in rec["extraction"]["preview"]
    st, d = c.call("POST", "/api/v1/discoveries", {"upload_id": rec["sha256"], "title": "from pdf"})
    assert st == 202
    run = c.wait_done(d["id"])
    assert run["status"] == "done"
    assert "pump" in run["input"]["text"] and run["input"]["source_upload"]["sha256"] == rec["sha256"]
    assert run["input"]["source_upload"]["kind"] == "pdf"


def test_csv_upload_feeds_discovery(srv):
    app, server, c, tmp = srv
    csv = b"time,temp,pressure\n1,20,1.0\n2,25,1.2\n3,30,1.5\n4,35,1.9\n"
    st, rec = post(c, "/api/v1/uploads?filename=data.csv", csv)
    assert st == 201 and rec["interpreted"] is True
    st, d = c.call("POST", "/api/v1/discoveries", {"upload_id": rec["sha256"]})
    assert st == 202 and c.wait_done(d["id"])["input"]["problem"]


def test_multipart_upload(srv):
    app, server, c, tmp = srv
    b = "XBOUNDARYX"
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"n.txt\"\r\nContent-Type: text/plain\r\n\r\n"
            "A pump moves fluid. Friction dissipates energy.\r\n" f"--{b}--\r\n").encode()
    st, rec = post(c, "/api/v1/uploads", body, {"Content-Type": f"multipart/form-data; boundary={b}"})
    assert st == 201 and rec["original_filename"] == "n.txt" and rec["interpreted"]


def test_scanned_pdf_and_image_not_interpreted_over_http(srv):
    app, server, c, tmp = srv
    st, rec = post(c, "/api/v1/uploads?filename=scan.pdf", make_pdf([]))
    assert st == 201 and rec["interpreted"] is False and "scanned" in rec["note"] and rec["extraction"]["preview"] == ""
    st, d = c.call("POST", "/api/v1/discoveries", {"upload_id": rec["sha256"]})
    assert st == 422
    st, img = post(c, "/api/v1/uploads?filename=a.png", b"\x89PNG\r\n\x1a\n" + b"0" * 20)
    assert st == 201 and img["interpreted"] is False and "not interpreted" in img["note"]
    st, d = c.call("POST", "/api/v1/discoveries", {"upload_id": img["sha256"]})
    assert st == 422


def test_image_with_unsupported_provider_raises(srv):
    app, server, c, tmp = srv
    st, e = post(c, "/api/v1/uploads?filename=a.png&interpret=local", b"\x89PNG\r\n\x1a\n" + b"0" * 20)
    assert st == 502 and e["error"]["code"] == "provider_error"


def test_rejections(srv):
    app, server, c, tmp = srv
    assert post(c, "/api/v1/uploads?filename=x.pdf", b"not a pdf")[0] == 422
    assert post(c, "/api/v1/uploads?filename=x.exe", b"MZ")[0] == 422
    assert post(c, "/api/v1/uploads", b"hello")[0] == 422  # no filename
    assert c.call("POST", "/api/v1/discoveries", {"upload_id": "zz"})[0] == 422
    assert c.call("POST", "/api/v1/discoveries", {"upload_id": "a" * 64})[0] == 404
    assert c.call("POST", "/api/v1/discoveries", {"upload_id": "a" * 64, "text": "x y z"})[0] == 422


def test_oversize_rejected(tmp_path):
    app, server, c = start(tmp_path, max_body_bytes=1000)
    try:
        st, e = post(c, "/api/v1/uploads?filename=big.txt", b"a" * 2000)
        assert st == 413
    finally:
        stop(app, server)


def test_upload_requires_token(tmp_path):
    app, server, c = start(tmp_path, token="s3cret")
    try:
        st, _ = c.call("POST", "/api/v1/uploads?filename=a.txt", raw=b"hello", token=None,
                       headers={"Content-Type": "text/plain"})
        assert st == 401
        st, _ = c.call("POST", "/api/v1/uploads?filename=a.txt", raw=b"hello there", headers={"Content-Type": "text/plain"})
        assert st == 201
    finally:
        stop(app, server)


def test_cli_upload(tmp_path, capsys):
    from isomorph_app.cli import main
    f = tmp_path / "p.pdf"
    f.write_bytes(make_pdf(PROBLEM, True))
    assert main(["upload", str(f), "--home", str(tmp_path / "h")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["interpreted"] is True
    s = tmp_path / "scan.pdf"
    s.write_bytes(make_pdf([]))
    assert main(["upload", str(s), "--analyze", "--home", str(tmp_path / "h")]) == 1


# ---- adversarial PDFs: bounded time, honest failure
import time  # noqa: E402

ADVERSARIAL_LIMIT = 6.0  # seconds; the extractor budget is 4 s


def _bounded(data):
    t0 = time.monotonic()
    ex = extract_pdf(data)
    assert time.monotonic() - t0 < ADVERSARIAL_LIMIT
    return ex


def test_pdf_many_obj_markers_without_endobj_is_bounded():
    ex = _bounded(b"%PDF-1.4\n" + b"1 0 obj " * 250000)
    assert not ex.interpreted and ex.text == ""


def test_pdf_many_stream_markers_without_endstream_is_bounded():
    ex = _bounded(b"%PDF-1.4\n1 0 obj\n<< >>\n" + b"stream\n" * 250000)
    assert not ex.interpreted


def test_pdf_unterminated_strings_in_content_is_bounded():
    body = b"BT\n" + b"(" * 1500000 + b"\nET"
    pdf = b"%PDF-1.4\n1 0 obj\n<< >>\nstream\n" + body + b"\nendstream\nendobj\n"
    assert not _bounded(pdf).interpreted


def test_pdf_many_objects_over_cap_fails():
    pdf = b"%PDF-1.4\n" + b"".join(b"%d 0 obj\n<< >>\nendobj\n" % i for i in range(1, 6500))
    ex = _bounded(pdf)
    assert not ex.interpreted and "too large or complex" in ex.reason


def test_pdf_many_streams_over_cap_fails():
    one = zlib.compress(b"BT (a) Tj ET")
    pdf = b"%PDF-1.4\n" + b"".join(
        b"%d 0 obj\n<< /Filter /FlateDecode >>\nstream\n" % i + one + b"\nendstream\nendobj\n" for i in range(1, 400))
    ex = _bounded(pdf)
    assert not ex.interpreted and "too large or complex" in ex.reason


def test_pdf_inflate_cap_is_a_failure_not_truncation():
    big = zlib.compress(b"BT (hello world text) Tj ET\n" * 120000)  # about 3.4 MB inflated
    pdf = b"%PDF-1.4\n1 0 obj\n<< /Filter /FlateDecode >>\nstream\n" + big + b"\nendstream\nendobj\n"
    ex = _bounded(pdf)
    assert not ex.interpreted and ex.text == "" and "too large or complex" in ex.reason


def test_pdf_flate_bomb_streams_are_bounded():
    one = zlib.compress(b"BT (a) Tj ET\n" * 150000)  # about 2 MB inflated, small compressed
    pdf = b"%PDF-1.4\n" + b"".join(
        b"%d 0 obj\n<< /Filter /FlateDecode >>\nstream\n" % i + one + b"\nendstream\nendobj\n" for i in range(1, 40))
    assert not _bounded(pdf).interpreted


def test_json_upload_id_rejected_and_extraction_cached(srv):
    app, server, c, tmp = srv
    st, r = post(c, "/api/v1/uploads?filename=a.json", b'{"a": 1}')
    assert st == 201 and r["interpreted"] is False
    st, _ = c.call("POST", "/api/v1/discoveries", {"upload_id": r["sha256"]})
    assert st == 422
    st, r = post(c, "/api/v1/uploads?filename=p.pdf", make_pdf(PROBLEM))
    first = app._load_upload(r["sha256"])[1]
    assert app._load_upload(r["sha256"])[1] is first  # second start reuses the cached extraction
