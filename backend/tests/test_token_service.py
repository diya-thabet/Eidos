"""
Tests for the JWT token service.

Covers: create, decode, expiry, invalid tokens, extra claims.
"""

import time

import jwt as pyjwt
import pytest

from app.auth.token_service import create_access_token, decode_access_token


class TestCreateAccessToken:
    def test_creates_string(self):
        token = create_access_token("user-1")
        assert isinstance(token, str)
        assert len(token) > 20

    def test_contains_subject(self):
        token = create_access_token("user-42")
        payload = decode_access_token(token)
        assert payload["sub"] == "user-42"

    def test_contains_expiry(self):
        token = create_access_token("u1")
        payload = decode_access_token(token)
        assert "exp" in payload
        assert payload["exp"] > time.time()

    def test_custom_expiry(self):
        token = create_access_token("u1", expires_in=10)
        payload = decode_access_token(token)
        assert payload["exp"] - payload["iat"] == 10

    def test_extra_claims(self):
        token = create_access_token("u1", extra={"role": "admin"})
        payload = decode_access_token(token)
        assert payload["role"] == "admin"


class TestDecodeAccessToken:
    def test_valid_token(self):
        token = create_access_token("u1")
        payload = decode_access_token(token)
        assert payload["sub"] == "u1"

    def test_expired_token(self):
        token = create_access_token("u1", expires_in=-1)
        with pytest.raises(pyjwt.ExpiredSignatureError):
            decode_access_token(token)

    def test_invalid_signature(self):
        token = create_access_token("u1")
        # Tamper with the token
        parts = token.split(".")
        parts[2] = parts[2][::-1]
        tampered = ".".join(parts)
        with pytest.raises(pyjwt.InvalidTokenError):
            decode_access_token(tampered)

    def test_garbage_token(self):
        with pytest.raises(pyjwt.InvalidTokenError):
            decode_access_token("not.a.jwt")

    def test_empty_token(self):
        with pytest.raises(pyjwt.InvalidTokenError):
            decode_access_token("")
