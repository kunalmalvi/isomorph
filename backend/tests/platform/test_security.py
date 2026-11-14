import pytest

from core.security import (PasswordPolicyError, TokenError, create_token, decode_token, hash_password, role_allows,
                           verify_password)

SECRET = "x" * 40


def test_password_roundtrip_and_salt_uniqueness():
    h1, h2 = hash_password("correct horse battery"), hash_password("correct horse battery")
    assert h1 != h2 and h1.startswith("scrypt$")
    assert verify_password("correct horse battery", h1)
    assert not verify_password("wrong password!!", h1)
    assert "correct horse" not in h1


def test_password_policy_and_malformed_hash():
    with pytest.raises(PasswordPolicyError):
        hash_password("short")
    assert not verify_password("whatever12345", "not-a-hash")
    assert not verify_password("whatever12345", "bcrypt$1$2$3$a$b")


def test_token_roundtrip_expiry_and_tamper():
    t = create_token("user-1", SECRET, 60, {"role": "x"}, now=1000)
    assert decode_token(t, SECRET, now=1010)["sub"] == "user-1"
    with pytest.raises(TokenError):
        decode_token(t, SECRET, now=1061)
    with pytest.raises(TokenError):
        decode_token(t, "y" * 40, now=1010)
    h, p, s = t.split(".")
    with pytest.raises(TokenError):
        decode_token(f"{h}.{p[:-2]}ab.{s}", SECRET, now=1010)


def test_alg_none_and_garbage_rejected():
    import base64, json
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    forged = b({"alg": "none"}) + "." + b({"sub": "u", "exp": 9999999999}) + "."
    with pytest.raises(TokenError):
        decode_token(forged, SECRET)
    for bad in ("", "a.b", "a.b.c", "....."):
        with pytest.raises(TokenError):
            decode_token(bad, SECRET)


def test_role_ordering():
    assert role_allows("owner", "editor") and role_allows("editor", "editor")
    assert not role_allows("viewer", "editor")
    assert not role_allows(None, "viewer") and not role_allows("admin", "viewer")
