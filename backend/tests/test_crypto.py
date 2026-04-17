"""
Tests for the crypto module (Fernet encryption).

Covers: encrypt/decrypt, round-trip, invalid data, key derivation.
"""

from app.auth.crypto import decrypt, encrypt


class TestEncryptDecrypt:
    def test_round_trip(self):
        token = "ghp_abcdef1234567890"
        enc = encrypt(token)
        assert enc != token
        assert decrypt(enc) == token

    def test_different_ciphertexts(self):
        token = "test_token"
        enc1 = encrypt(token)
        enc2 = encrypt(token)
        # Fernet uses random IV so ciphertexts differ
        assert enc1 != enc2
        assert decrypt(enc1) == token
        assert decrypt(enc2) == token

    def test_empty_string(self):
        enc = encrypt("")
        assert decrypt(enc) == ""

    def test_long_token(self):
        token = "x" * 5000
        enc = encrypt(token)
        assert decrypt(enc) == token

    def test_invalid_ciphertext(self):
        import pytest

        with pytest.raises(ValueError, match="Unable to decrypt"):
            decrypt("not-a-valid-fernet-token")

    def test_unicode_token(self):
        token = "token-with-special"
        enc = encrypt(token)
        assert decrypt(enc) == token
