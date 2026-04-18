"""OIDC JWT validator.

Wraps PyJWT + a JWKS client. Verifies signature, expiry, audience, and
issuer. Raises `InvalidTokenError` on any failure; never returns
silently on an invalid token.

Kept tiny and protocol-friendly so unit tests can inject a fake JWKS
client (tests at `tests/test_jwt_validator.py`). The actual JWKS fetch
happens at app startup via `OidcValidator.from_uri` — same pattern as
the gateway's `backend/app/api/middleware.py`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class InvalidTokenError(Exception):
    """Raised for any JWT validation failure — expiry, bad sig, wrong aud."""


class SigningKeyLike(Protocol):
    key: Any


class JwksClientLike(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> SigningKeyLike: ...


@dataclass(frozen=True, slots=True)
class OidcValidator:
    jwks_client: JwksClientLike
    issuer: str
    audience: str
    algorithms: tuple[str, ...] = ("RS256",)

    @classmethod
    def from_uri(
        cls,
        *,
        jwks_uri: str,
        issuer: str,
        audience: str,
    ) -> OidcValidator:  # pragma: no cover - network
        """Construct a validator backed by PyJWT's PyJWKClient."""
        import jwt  # type: ignore[import-untyped]

        return cls(
            jwks_client=jwt.PyJWKClient(jwks_uri),
            issuer=issuer,
            audience=audience,
        )

    def validate(self, token: str) -> dict[str, object]:
        """Validate and decode. Raise InvalidTokenError on any failure."""
        if not token:
            raise InvalidTokenError("empty token")
        try:
            import jwt  # type: ignore[import-untyped]

            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(self.algorithms),
                audience=self.audience,
                issuer=self.issuer,
            )
        except Exception as exc:  # PyJWT raises many subclasses; unify.
            logger.info("jwt validation failed", extra={"error": str(exc)})
            raise InvalidTokenError(str(exc)) from exc
        if not isinstance(claims, dict):
            raise InvalidTokenError("decoded claims not a dict")
        return claims
