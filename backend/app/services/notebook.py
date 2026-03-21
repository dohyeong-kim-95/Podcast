"""T-030: notebooklm-py integration service.

Wraps the notebooklm-py library for notebook CRUD and audio generation.
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.services.db import get_db, utc_now

logger = logging.getLogger(__name__)


def _required_cookie_names() -> set[str]:
    raw = os.getenv("NB_REQUIRED_COOKIE_NAMES", "SID")
    return {part.strip() for part in raw.split(",") if part.strip()}


def missing_required_cookie_names(storage_state: dict[str, Any]) -> list[str]:
    cookies = storage_state.get("cookies")
    if not isinstance(cookies, list):
        return sorted(_required_cookie_names())

    present = {
        str(cookie.get("name"))
        for cookie in cookies
        if isinstance(cookie, dict) and cookie.get("name")
    }
    return sorted(_required_cookie_names() - present)


def validate_storage_state(storage_state: dict[str, Any]) -> None:
    if not isinstance(storage_state, dict):
        raise ValueError("NB session storage state must be a JSON object")

    missing = missing_required_cookie_names(storage_state)
    if missing:
        raise ValueError(f"NB session storage state missing required cookies: {', '.join(missing)}")


async def verify_storage_state_auth(storage_state: dict[str, Any]) -> None:
    """Verify that the saved Playwright state can actually authenticate NotebookLM."""
    from notebooklm import AuthTokens

    state_file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    try:
        json.dump(storage_state, state_file)
        state_file.close()
        await AuthTokens.from_storage(Path(state_file.name))
    finally:
        try:
            os.unlink(state_file.name)
        except OSError:
            pass


def _load_audio_timeout_seconds() -> int:
    raw = os.getenv("AUDIO_TIMEOUT_SECONDS", str(20 * 60))
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning("Invalid AUDIO_TIMEOUT_SECONDS=%r, falling back to 1200", raw)
        return 20 * 60


AUDIO_TIMEOUT_SECONDS = _load_audio_timeout_seconds()


def _get_fernet() -> Fernet:
    key = os.getenv("NB_COOKIE_ENCRYPTION_KEY", "")
    if not key:
        raise RuntimeError("NB_COOKIE_ENCRYPTION_KEY not configured")
    return Fernet(key.encode() if isinstance(key, str) else key)


def decrypt_storage_state(encrypted: str) -> dict:
    """Decrypt Fernet-encrypted NotebookLM storage state.

    Raises:
        ValueError: If decryption fails (key mismatch, corrupted data, invalid JSON).
    """
    try:
        f = _get_fernet()
        decrypted = f.decrypt(encrypted.encode())
        return json.loads(decrypted)
    except InvalidToken as e:
        raise ValueError(f"NB session decryption failed (invalid key or corrupted data): {e}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"NB session storage state is not valid JSON: {e}") from e


def encrypt_storage_state(storage_state: dict[str, Any]) -> str:
    """Encrypt NotebookLM storage state for Postgres persistence."""
    f = _get_fernet()
    payload = json.dumps(storage_state).encode()
    return f.encrypt(payload).decode()


def _normalize_expires_at(expires_at: Any) -> datetime | None:
    if expires_at is None or not hasattr(expires_at, "timestamp"):
        return None
    return expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)


def derive_nb_session_status(expires_at: Any, status: str = "") -> str:
    """Derive a stable status for current NB session metadata."""
    if status == "expired":
        return "expired"

    normalized = _normalize_expires_at(expires_at)
    if normalized is None:
        return status or "unknown"

    now = datetime.now(timezone.utc)
    if normalized <= now:
        return "expired"

    expiring_soon_days = int(os.getenv("NB_SESSION_EXPIRING_SOON_DAYS", "7"))
    if normalized <= now + timedelta(days=expiring_soon_days):
        return "expiring_soon"

    return "valid"


async def save_nb_session(
    uid: str,
    storage_state: dict[str, Any],
    *,
    auth_flow: str = "new_tab",
    expires_in_days: int = 30,
) -> dict[str, Any]:
    """Persist the current NB session for a user."""
    validate_storage_state(storage_state)
    await verify_storage_state_auth(storage_state)
    now = utc_now()
    expires_at = now + timedelta(days=expires_in_days)
    encrypted = encrypt_storage_state(storage_state)
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            insert into profiles (id)
            values (%s)
            on conflict (id) do nothing
            """,
            (uid,),
        )
        cur.execute(
            """
            insert into nb_sessions (
                user_id,
                storage_state,
                auth_flow,
                status,
                expires_at,
                last_updated
            )
            values (%s, %s, %s, %s, %s, %s)
            on conflict (user_id) do update
            set storage_state = excluded.storage_state,
                auth_flow = excluded.auth_flow,
                status = excluded.status,
                expires_at = excluded.expires_at,
                last_updated = excluded.last_updated
            """,
            (uid, encrypted, auth_flow, "valid", expires_at, now),
        )
    return {
        "status": "valid",
        "expiresAt": expires_at,
        "authFlow": auth_flow,
    }


async def load_nb_session(uid: str) -> dict[str, Any]:
    """Load and validate NB session from Postgres.

    Returns:
        Dict with 'storageState' (decrypted) and session metadata.

    Raises:
        ValueError: If session is missing, expired, or invalid.
    """
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """
            select storage_state, status, expires_at, auth_flow, last_updated
            from nb_sessions
            where user_id = %s
            """,
            (uid,),
        )
        data = cur.fetchone()

    if not data:
        raise ValueError("NB session not found")

    status = derive_nb_session_status(data.get("expires_at"), data.get("status", ""))
    if status == "expired":
        raise ValueError("NB session expired (status)")

    expires_at = data.get("expires_at")
    if expires_at is not None:
        if hasattr(expires_at, "timestamp"):
            exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
            if exp <= datetime.now(timezone.utc):
                raise ValueError("NB session expired (expiresAt)")

    encrypted = data.get("storage_state", "")
    if not encrypted:
        raise ValueError("NB session storage state is empty")

    storage_state = decrypt_storage_state(encrypted)
    return {
        "storageState": storage_state,
        "status": status,
        "expiresAt": expires_at,
        "authFlow": data.get("auth_flow", ""),
        "lastUpdated": data.get("last_updated"),
    }


class NotebookLMClient:
    """Wrapper around notebooklm-py for notebook operations."""

    def __init__(self, storage_state: dict):
        self._storage_state = storage_state
        self._client = None
        self._entered = False
        self._state_file = None

    async def _get_client(self):
        """Lazily initialize the notebooklm-py client."""
        if self._client is not None:
            return self._client

        from notebooklm import NotebookLMClient as NotebookLMServiceClient

        # Write storage state to temp file for notebooklm-py
        self._state_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        json.dump(self._storage_state, self._state_file)
        self._state_file.close()

        self._client = await NotebookLMServiceClient.from_storage(self._state_file.name)
        if hasattr(self._client, "__aenter__"):
            await self._client.__aenter__()
            self._entered = True
        return self._client

    async def create_notebook(self, title: str = "Daily Podcast") -> str:
        """Create a new notebook. Returns notebook ID."""
        client = await self._get_client()
        notebook = await client.notebooks.create(title)
        notebook_id = notebook.id if hasattr(notebook, "id") else str(notebook)
        logger.info("Created notebook: %s", notebook_id)
        return notebook_id

    async def add_source(self, notebook_id: str, pdf_path: str) -> None:
        """Add a local PDF file as source to notebook."""
        client = await self._get_client()
        await client.sources.add_file(notebook_id, Path(pdf_path))
        logger.info("Added source to notebook %s: %s", notebook_id, pdf_path)

    async def generate_audio(self, notebook_id: str, instructions: str) -> bytes:
        """Generate audio overview and return mp3 bytes.

        Args:
            notebook_id: Target notebook ID.
            instructions: Personalized generation instructions.

        Returns:
            MP3 audio bytes.
        """
        client = await self._get_client()
        generation = await client.artifacts.generate_audio(
            notebook_id,
            instructions=instructions,
        )
        final = await client.artifacts.wait_for_completion(
            notebook_id,
            generation.task_id,
            timeout=AUDIO_TIMEOUT_SECONDS,
            poll_interval=5,
        )

        if not getattr(final, "is_complete", False):
            status = getattr(final, "status", "unknown")
            raise RuntimeError(f"audio_generation_incomplete:{status}")

        output_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        output_file.close()
        try:
            output_path = await client.artifacts.download_audio(notebook_id, output_file.name)
            with open(output_path, "rb") as f:
                return f.read()
        finally:
            try:
                os.unlink(output_file.name)
            except OSError:
                pass

    async def delete_notebook(self, notebook_id: str) -> None:
        """Delete a notebook (cleanup after generation)."""
        try:
            client = await self._get_client()
            await client.notebooks.delete(notebook_id)
            logger.info("Deleted notebook: %s", notebook_id)
        except Exception as e:
            logger.warning("Failed to delete notebook %s: %s", notebook_id, e)

    async def close(self) -> None:
        """Clean up resources."""
        if self._client and self._entered and hasattr(self._client, "__aexit__"):
            try:
                await self._client.__aexit__(None, None, None)
            except Exception:
                pass
            finally:
                self._entered = False
        elif self._client and hasattr(self._client, "close"):
            try:
                await self._client.close()
            except Exception:
                pass

        if hasattr(self, "_state_file") and self._state_file:
            try:
                os.unlink(self._state_file.name)
            except OSError:
                pass
        self._state_file = None
        self._client = None
