from __future__ import annotations

import os
from typing import Any

import jwt


class InvalidAccessTokenError(Exception):
    pass


class AuthVerificationServiceError(Exception):
    pass


def _normalize_env_value(value: str) -> str:
    return value.strip().replace("\r", "").replace("\n", "").strip("'\"")


def _supabase_url() -> str:
    value = _normalize_env_value(os.getenv("SUPABASE_URL", ""))
    if not value:
        raise RuntimeError("SUPABASE_URL not configured")
    return value.rstrip("/")


def _supabase_auth_issuer() -> str:
    return f"{_supabase_url()}/auth/v1"


def _jwks_url() -> str:
    return f"{_supabase_auth_issuer()}/.well-known/jwks.json"


def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(_jwks_url(), cache_jwk_set=True, lifespan=300, timeout=10)


def _decode_claims(token: str) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise InvalidAccessTokenError("Invalid or expired token") from exc

    algorithm = header.get("alg")
    key_id = header.get("kid")
    if not algorithm or not key_id or algorithm.upper() == "HS256":
        raise AuthVerificationServiceError(
            "Supabase project must use asymmetric JWT signing keys (RS256/ES256)"
        )

    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=[algorithm],
            audience="authenticated",
            issuer=_supabase_auth_issuer(),
        )
    except jwt.ExpiredSignatureError as exc:
        raise InvalidAccessTokenError("Invalid or expired token") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidAccessTokenError("Invalid or expired token") from exc
    except Exception as exc:
        raise AuthVerificationServiceError("Supabase JWKS verification failed") from exc


async def verify_access_token(token: str) -> dict[str, Any]:
    claims = _decode_claims(token)
    metadata = claims.get("user_metadata") or {}
    return {
        "uid": claims.get("sub"),
        "email": claims.get("email"),
        "name": metadata.get("full_name") or metadata.get("name"),
        "raw": claims,
    }
