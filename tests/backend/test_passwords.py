# Offline tests for password hashing. Each test is a few hundred ms (scrypt is slow on purpose)
import pytest
import unicodedata

from backend.services import passwords
from backend.services.passwords import (
    MAX_PASSWORD_LENGTH,
    hash_password,
    needs_rehash,
    verify_password,
)


def test_hash_is_not_plaintext_and_is_salted():
    first, second = hash_password("correct horse"), hash_password("correct horse")
    assert "correct horse" not in first
    assert first != second  # random salt


def test_verify_accepts_right_and_rejects_wrong():
    stored = hash_password("correct horse")
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong horse", stored)


@pytest.mark.parametrize("stored", ["", "garbage", "bcrypt$1$2$3$aa$bb", "scrypt$x$8$3$zz$zz"])
def test_malformed_hash_is_a_mismatch_not_a_crash(stored):
    assert verify_password("anything", stored) is False


def test_unicode_forms_are_equivalent():
    composed = "m\u1eadt kh\u1ea9u"  # "mật khẩu" as precomposed characters
    decomposed = unicodedata.normalize("NFD", composed)  # same text, base letters + marks
    assert composed != decomposed  # different bytes, same visible text
    assert verify_password(decomposed, hash_password(composed))


def test_overlong_password_is_rejected_without_hashing():
    stored = hash_password("short enough")
    assert verify_password("x" * (MAX_PASSWORD_LENGTH + 1), stored) is False


def test_needs_rehash_when_cost_changes(monkeypatch):
    stored = hash_password("correct horse")
    assert not needs_rehash(stored)
    monkeypatch.setattr(passwords, "_N", 2**16)  # pretend we raised the cost later
    assert needs_rehash(stored)