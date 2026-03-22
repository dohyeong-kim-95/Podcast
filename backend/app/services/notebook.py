"""T-030: notebooklm-py integration service.

Wraps the notebooklm-py library for notebook CRUD and audio generation.
"""

import json
import logging
import os
import tempfile
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
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


def _load_source_ready_timeout_seconds() -> int:
    raw = os.getenv("SOURCE_READY_TIMEOUT_SECONDS", "300")
    try:
        return max(30, int(raw))
    except ValueError:
        logger.warning("Invalid SOURCE_READY_TIMEOUT_SECONDS=%r, falling back to 300", raw)
        return 300


SOURCE_READY_TIMEOUT_SECONDS = _load_source_ready_timeout_seconds()


def _load_operation_retry_count() -> int:
    raw = os.getenv("NOTEBOOKLM_OPERATION_RETRY_COUNT", "3")
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning("Invalid NOTEBOOKLM_OPERATION_RETRY_COUNT=%r, falling back to 3", raw)
        return 3


def _load_operation_retry_delay_seconds() -> float:
    raw = os.getenv("NOTEBOOKLM_OPERATION_RETRY_DELAY_SECONDS", "1.5")
    try:
        return max(0.1, float(raw))
    except ValueError:
        logger.warning("Invalid NOTEBOOKLM_OPERATION_RETRY_DELAY_SECONDS=%r, falling back to 1.5", raw)
        return 1.5


NOTEBOOKLM_OPERATION_RETRY_COUNT = _load_operation_retry_count()
NOTEBOOKLM_OPERATION_RETRY_DELAY_SECONDS = _load_operation_retry_delay_seconds()


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

    def _format_client_error(self, exc: Exception, operation: str) -> str:
        parts = [str(exc).strip() or exc.__class__.__name__]
        parts.append(f"error_type={exc.__class__.__name__}")

        method_id = getattr(exc, "method_id", None)
        if method_id:
            parts.append(f"method_id={method_id}")

        rpc_code = getattr(exc, "rpc_code", None)
        if rpc_code not in (None, ""):
            parts.append(f"rpc_code={rpc_code}")

        status_code = getattr(exc, "status_code", None)
        if status_code:
            parts.append(f"status_code={status_code}")

        found_ids = getattr(exc, "found_ids", None)
        if found_ids:
            parts.append(f"found_ids={found_ids}")

        raw_response = getattr(exc, "raw_response", None)
        if raw_response:
            compact = " ".join(str(raw_response).split())
            parts.append(f"raw_response={compact[:240]}")

        original_error = getattr(exc, "original_error", None)
        if original_error:
            parts.append(f"original_error_type={original_error.__class__.__name__}")
            parts.append(f"original_error_repr={original_error!r}")

        return f"{operation}: " + " | ".join(parts)

    def _is_retryable_client_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        error_type = exc.__class__.__name__.lower()

        if any(token in text for token in ("request failed calling", "readerror", "timed out", "timeout")):
            return True
        if error_type in {"networkerror", "readerror", "connecterror", "timeoutexception"}:
            return True

        original_error = getattr(exc, "original_error", None)
        if original_error is not None:
            original_text = repr(original_error).lower()
            original_type = original_error.__class__.__name__.lower()
            if any(token in original_text for token in ("readerror", "connecterror", "timeout")):
                return True
            if original_type in {"readerror", "connecterror", "timeoutexception"}:
                return True

        return False

    async def _refresh_auth_if_possible(self) -> None:
        if self._client and hasattr(self._client, "refresh_auth"):
            try:
                await self._client.refresh_auth()
            except Exception as exc:
                logger.warning("NotebookLM auth refresh failed during retry: %s", exc)

    async def _run_with_retry(self, operation: str, func):
        last_exc = None
        for attempt in range(1, NOTEBOOKLM_OPERATION_RETRY_COUNT + 1):
            try:
                return await func()
            except Exception as exc:
                last_exc = exc
                if attempt >= NOTEBOOKLM_OPERATION_RETRY_COUNT or not self._is_retryable_client_error(exc):
                    raise

                logger.warning(
                    "Retrying NotebookLM %s after attempt %s/%s: %s",
                    operation,
                    attempt,
                    NOTEBOOKLM_OPERATION_RETRY_COUNT,
                    self._format_client_error(exc, f"{operation}_retry"),
                )
                await self._refresh_auth_if_possible()
                await asyncio.sleep(NOTEBOOKLM_OPERATION_RETRY_DELAY_SECONDS * attempt)

        if last_exc:
            raise last_exc

    async def _upload_source_from_memory(self, client, notebook_id: str, pdf_path: Path) -> None:
        sources_api = client.sources
        filename = pdf_path.name
        file_size = pdf_path.stat().st_size

        try:
            source_id = await sources_api._register_file_source(notebook_id, filename)
            upload_url = await sources_api._start_resumable_upload(
                notebook_id,
                filename,
                file_size,
                source_id,
            )
        except Exception as exc:
            raise RuntimeError(self._format_client_error(exc, "register_source_failed")) from exc

        headers = {
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
            "Cookie": client.auth.cookie_header,
            "Origin": "https://notebooklm.google.com",
            "Referer": "https://notebooklm.google.com/",
            "x-goog-authuser": "0",
            "x-goog-upload-command": "upload, finalize",
            "x-goog-upload-offset": "0",
        }

        try:
            payload = pdf_path.read_bytes()
        except OSError as exc:
            raise RuntimeError(f"read_source_file_failed: {exc}") from exc

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as upload_client:
                response = await upload_client.post(upload_url, headers=headers, content=payload)
                response.raise_for_status()
        except Exception as exc:
            raise RuntimeError(self._format_client_error(exc, "upload_source_failed")) from exc

        try:
            await sources_api.wait_until_ready(
                notebook_id,
                source_id,
                timeout=SOURCE_READY_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            raise RuntimeError(self._format_client_error(exc, "source_ready_wait_failed")) from exc

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
        try:
            notebook = await self._run_with_retry(
                "create_notebook",
                lambda: client.notebooks.create(title),
            )
        except Exception as exc:
            raise RuntimeError(self._format_client_error(exc, "create_notebook_failed")) from exc
        notebook_id = notebook.id if hasattr(notebook, "id") else str(notebook)
        logger.info("Created notebook: %s", notebook_id)
        return notebook_id

    async def add_source(self, notebook_id: str, pdf_path: str) -> None:
        """Add a local PDF file as source to notebook."""
        client = await self._get_client()
        try:
            await self._run_with_retry(
                "add_source",
                lambda: self._upload_source_from_memory(client, notebook_id, Path(pdf_path).resolve()),
            )
        except Exception as exc:
            raise RuntimeError(self._format_client_error(exc, "add_source_failed")) from exc
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
        try:
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
        except Exception as exc:
            raise RuntimeError(self._format_client_error(exc, "generate_audio_failed")) from exc

        if not getattr(final, "is_complete", False):
            status = getattr(final, "status", "unknown")
            raise RuntimeError(f"audio_generation_incomplete:{status}")

        output_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        output_file.close()
        try:
            try:
                output_path = await client.artifacts.download_audio(notebook_id, output_file.name)
            except Exception as exc:
                raise RuntimeError(self._format_client_error(exc, "download_audio_failed")) from exc
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
