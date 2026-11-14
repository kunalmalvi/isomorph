import json

import pytest

from core.config import ConfigError, load_settings
from core.errors import PayloadTooLarge, ValidationFailed, error_envelope
from core.rate_limit import RateLimiter
from core.sse import format_sse, progress_stream
from core.uploads import sanitize_filename, validate_upload


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def test_rate_limiter_window_and_keys():
    c = Clock()
    rl = RateLimiter(2, 10, c)
    assert rl.check("a") == (True, 0.0) and rl.check("a")[0]
    ok, retry = rl.check("a")
    assert not ok and retry == 10
    assert rl.check("b")[0]
    c.t = 10.0
    assert rl.check("a")[0]
    assert rl.remaining("a") == 1


def test_upload_accepts_valid_and_sanitizes():
    u = validate_upload("../../etc/pass wd.txt", b"hello", 100)
    assert u.filename == "pass_wd.txt" and u.kind == "text"
    assert validate_upload("d.csv", b"a,b\n1,2\n", 100).kind == "csv"
    assert validate_upload("d.json", b'{"a":1}', 100).kind == "json"
    assert validate_upload("p.pdf", b"%PDF-1.4 x", 100).kind == "pdf"
    assert sanitize_filename(".hidden") == "hidden"


@pytest.mark.parametrize("name,data", [
    ("a.exe", b"MZ"), ("a.txt", b"bin\x00ary"), ("a.json", b"{bad"), ("a.pdf", b"not pdf"), ("a.png", b"%PDF-"),
    ("a.csv", b"  \n"), ("noext", b"x"), ("a.txt", b""), ("a.txt", b"\xff\xfe\xfa"),
])
def test_upload_rejects(name, data):
    with pytest.raises(ValidationFailed):
        validate_upload(name, data, 100)


def test_upload_too_large():
    with pytest.raises(PayloadTooLarge):
        validate_upload("a.txt", b"x" * 101, 100)


def test_error_envelope_shape():
    assert error_envelope("c", "m") == {"error": {"code": "c", "message": "m", "details": []}}


def test_settings_defaults_and_validation():
    s = load_settings({})
    assert s.ai_provider == "local" and s.openai_api_key is None
    with pytest.raises(ConfigError):
        load_settings({"AI_PROVIDER": "nope"})
    with pytest.raises(ConfigError):
        load_settings({"ISOMORPH_ENV": "production"})
    with pytest.raises(ConfigError):
        load_settings({"ISOMORPH_SECRET_KEY": "short"})


def test_sse_format_and_stream():
    assert format_sse("progress", {"a": 1}, 3) == 'id: 3\nevent: progress\ndata: {"a":1}\n\n'
    snaps = iter([{"status": "running", "n": 1}, {"status": "running", "n": 1}, {"status": "done", "n": 2}])
    out = list(progress_stream(lambda: next(snaps), sleep=lambda s: None))
    assert [o.split("\n")[1] for o in out[1:]] == ["event: progress", "event: progress", "event: end"]
    assert list(progress_stream(lambda: None))[1].split("\n")[1] == "event: error"
    t = iter(range(0, 1000, 100))
    out = list(progress_stream(lambda: {"status": "running"}, sleep=lambda s: None, max_seconds=250, clock=lambda: next(t)))
    assert "event: timeout" in out[-1]
