"""Tests for the OIDC JWT validator.

We craft a real RSA-signed JWT with PyJWT (dev dep via labeling[ui])
and feed it through the validator. When PyJWT is not installed we skip
(tests still cover the error branch via a fake jwks client).
"""

from __future__ import annotations

from typing import Any

import pytest

from labeling.jwt_validator import InvalidTokenError, OidcValidator

jwt = pytest.importorskip("jwt")


def _gen_keypair() -> tuple[Any, Any]:
    from cryptography.hazmat.primitives.asymmetric import rsa

    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


class FakeJwksClient:
    def __init__(self, key: Any) -> None:
        self._key = key

    def get_signing_key_from_jwt(self, token: str) -> Any:
        class _K:
            pass

        k = _K()
        k.key = self._key
        return k


def test_validate_accepts_correctly_signed_token() -> None:
    priv, pub = _gen_keypair()
    token = jwt.encode(
        {
            "sub": "u-1",
            "aud": "afya-sahihi",
            "iss": "https://idp.aku.edu",
            "role": "clinical_reviewer",
        },
        priv,
        algorithm="RS256",
    )
    validator = OidcValidator(
        jwks_client=FakeJwksClient(pub),
        issuer="https://idp.aku.edu",
        audience="afya-sahihi",
    )
    claims = validator.validate(token)
    assert claims["sub"] == "u-1"
    assert claims["role"] == "clinical_reviewer"


def test_validate_rejects_empty_token() -> None:
    validator = OidcValidator(
        jwks_client=FakeJwksClient(None),
        issuer="https://idp.aku.edu",
        audience="afya-sahihi",
    )
    with pytest.raises(InvalidTokenError, match="empty"):
        validator.validate("")


def test_validate_rejects_wrong_audience() -> None:
    priv, pub = _gen_keypair()
    token = jwt.encode(
        {
            "sub": "u-1",
            "aud": "wrong-audience",
            "iss": "https://idp.aku.edu",
        },
        priv,
        algorithm="RS256",
    )
    validator = OidcValidator(
        jwks_client=FakeJwksClient(pub),
        issuer="https://idp.aku.edu",
        audience="afya-sahihi",
    )
    with pytest.raises(InvalidTokenError):
        validator.validate(token)


def test_validate_rejects_wrong_issuer() -> None:
    priv, pub = _gen_keypair()
    token = jwt.encode(
        {
            "sub": "u-1",
            "aud": "afya-sahihi",
            "iss": "https://attacker.example.com",
        },
        priv,
        algorithm="RS256",
    )
    validator = OidcValidator(
        jwks_client=FakeJwksClient(pub),
        issuer="https://idp.aku.edu",
        audience="afya-sahihi",
    )
    with pytest.raises(InvalidTokenError):
        validator.validate(token)


def test_validate_rejects_wrong_signing_key() -> None:
    priv, _ = _gen_keypair()
    _, wrong_pub = _gen_keypair()
    token = jwt.encode(
        {
            "sub": "u-1",
            "aud": "afya-sahihi",
            "iss": "https://idp.aku.edu",
        },
        priv,
        algorithm="RS256",
    )
    validator = OidcValidator(
        jwks_client=FakeJwksClient(wrong_pub),
        issuer="https://idp.aku.edu",
        audience="afya-sahihi",
    )
    with pytest.raises(InvalidTokenError):
        validator.validate(token)
