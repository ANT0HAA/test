"""
Хеширование паролей и токены сессий на стандартной библиотеке (без внешних
зависимостей). PBKDF2-HMAC-SHA256 с солью; формат строки —
`pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>`.
"""
import hashlib
import hmac
import secrets

_ITERATIONS = 200_000
_ALGO = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGO}${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != _ALGO:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def new_token() -> str:
    """Случайный непредсказуемый токен сессии."""
    return secrets.token_urlsafe(32)
