"""Password and opaque session helpers. Never persist a raw session cookie."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets


SESSION_TTL = timedelta(days=7)
_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != "scrypt" or (int(n), int(r), int(p)) != (
            _SCRYPT_N, _SCRYPT_R, _SCRYPT_P
        ):
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt),
            n=_SCRYPT_N,
            r=_SCRYPT_R,
            p=_SCRYPT_P,
        )
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def new_session() -> tuple[str, str, datetime]:
    token = secrets.token_urlsafe(32)
    return token, session_hash(token), datetime.now(timezone.utc).replace(
        tzinfo=None
    ) + SESSION_TTL


def session_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
