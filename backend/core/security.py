"""Password hashing (hashlib.scrypt) and JWT HS256 (hmac) helpers. Stdlib only.

Passwords: `scrypt$n$r$p$salt_b64$hash_b64`, constant time comparison.
Tokens: compact JWT, HS256 only. Tokens with any other alg (including none) are rejected.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Callable, Optional

SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
KEY_LEN = 32
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 256


class TokenError(ValueError):
    pass


class PasswordPolicyError(ValueError):
    pass


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def check_password_policy(password: str) -> None:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"password must be at most {MAX_PASSWORD_LENGTH} characters")


def hash_password(password: str, salt: Optional[bytes] = None, n: int = SCRYPT_N, r: int = SCRYPT_R,
                  p: int = SCRYPT_P) -> str:
    check_password_policy(password)
    salt = salt if salt is not None else os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=KEY_LEN, maxmem=128 * n * r * 2 + 2 ** 20)
    return f"scrypt${n}${r}${p}${_b64e(salt)}${_b64e(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        n, r, p = int(n), int(r), int(p)
        expected = _b64d(digest)
        dk = hashlib.scrypt(password.encode("utf-8"), salt=_b64d(salt), n=n, r=r, p=p, dklen=len(expected),
                            maxmem=128 * n * r * 2 + 2 ** 20)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk, expected)


def create_token(subject: str, secret: str, ttl_seconds: int = 3600, claims: Optional[dict] = None,
                 now: Optional[float] = None) -> str:
    if not secret or len(secret) < 16:
        raise TokenError("secret too short")
    iat = int(time.time() if now is None else now)
    payload = dict(claims or {})
    payload.update({"sub": subject, "iat": iat, "exp": iat + int(ttl_seconds)})
    header = {"alg": "HS256", "typ": "JWT"}
    signing = _b64e(json.dumps(header, separators=(",", ":")).encode()) + "." + \
        _b64e(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    sig = hmac.new(secret.encode(), signing.encode("ascii"), hashlib.sha256).digest()
    return signing + "." + _b64e(sig)


def decode_token(token: str, secret: str, now: Optional[float] = None) -> dict:
    try:
        h, p, s = token.split(".")
        header = json.loads(_b64d(h))
        if header.get("alg") != "HS256":
            raise TokenError("unsupported algorithm")
        expected = hmac.new(secret.encode(), f"{h}.{p}".encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64d(s)):
            raise TokenError("bad signature")
        payload = json.loads(_b64d(p))
    except TokenError:
        raise
    except Exception as e:  # malformed input of any kind
        raise TokenError("malformed token") from e
    t = time.time() if now is None else now
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or t >= exp:
        raise TokenError("token expired")
    if not payload.get("sub"):
        raise TokenError("missing subject")
    return payload


# ---------------------------------------------------------------- RBAC
ROLE_ORDER = {"viewer": 1, "editor": 2, "owner": 3}


def role_allows(actual: Optional[str], minimum: str) -> bool:
    """True when `actual` project role is at least `minimum`. Unknown or missing roles never pass."""
    return ROLE_ORDER.get(actual or "", 0) >= ROLE_ORDER[minimum]
