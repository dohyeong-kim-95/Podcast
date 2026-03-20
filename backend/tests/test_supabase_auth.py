from unittest.mock import MagicMock, patch

import jwt
import pytest

from app.services.supabase_auth import (
    AuthVerificationServiceError,
    InvalidAccessTokenError,
    verify_access_token,
)


@pytest.mark.anyio
async def test_verify_access_token_decodes_valid_jwt():
    signing_key = MagicMock()
    signing_key.key = object()

    with patch.dict("os.environ", {"SUPABASE_URL": "https://example.supabase.co"}), \
         patch("app.services.supabase_auth.jwt.get_unverified_header", return_value={"alg": "RS256", "kid": "kid-1"}), \
         patch("app.services.supabase_auth._jwks_client") as mock_jwks_client, \
         patch("app.services.supabase_auth.jwt.decode", return_value={
             "sub": "user-1",
             "email": "user@example.com",
             "user_metadata": {"full_name": "User One"},
         }):
        mock_jwks_client.return_value.get_signing_key_from_jwt.return_value = signing_key
        result = await verify_access_token("valid-token")

    assert result["uid"] == "user-1"
    assert result["email"] == "user@example.com"
    assert result["name"] == "User One"


@pytest.mark.anyio
async def test_verify_access_token_rejects_invalid_header():
    with patch(
        "app.services.supabase_auth.jwt.get_unverified_header",
        side_effect=jwt.InvalidTokenError("bad header"),
    ):
        with pytest.raises(InvalidAccessTokenError):
            await verify_access_token("bad-token")


@pytest.mark.anyio
async def test_verify_access_token_requires_asymmetric_signing_keys():
    with patch("app.services.supabase_auth.jwt.get_unverified_header", return_value={"alg": "HS256"}):
        with pytest.raises(AuthVerificationServiceError):
            await verify_access_token("hs256-token")
