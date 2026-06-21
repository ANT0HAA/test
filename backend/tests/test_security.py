"""Тесты хеширования паролей и токенов (без внешних сервисов)."""
import security


def test_hash_and_verify():
    h = security.hash_password("Тайный-Пароль-123")
    assert h.startswith("pbkdf2_sha256$")
    assert security.verify_password("Тайный-Пароль-123", h)
    assert not security.verify_password("неправильный", h)


def test_hash_is_salted():
    # Один и тот же пароль → разные хеши (случайная соль)
    assert security.hash_password("x") != security.hash_password("x")


def test_verify_rejects_garbage():
    assert not security.verify_password("x", "не-формат")
    assert not security.verify_password("x", "")


def test_new_token_unique():
    assert security.new_token() != security.new_token()
    assert len(security.new_token()) >= 32
