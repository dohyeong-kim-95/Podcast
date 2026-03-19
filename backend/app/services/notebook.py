"""T-030: notebooklm-py integration service.

Wraps the notebooklm-py library for notebook CRUD and audio generation.
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.services.firebase import get_firestore_client

logger = logging.getLogger(__name__)

# Audio generation timeout: 20 minutes
AUDIO_TIMEOUT_SECONDS = 20 * 60


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


async def load_nb_session(uid: str) -> dict[str, Any]:
    """Load and validate NB session from Firestore.

    Returns:
        Dict with 'storageState' (decrypted) and session metadata.

    Raises:
        ValueError: If session is missing, expired, or invalid.
    """
    db = get_firestore_client()
    doc_ref = db.collection("users").document(uid).collection("nb_session").document("current")
    doc = doc_ref.get()

    if not doc.exists:
        raise ValueError("NB session not found")

    data = doc.to_dict()
    status = data.get("status", "")
    if status == "expired":
        raise ValueError("NB session expired (status)")

    # T-035: Check expiresAt server-side regardless of status field
    expires_at = data.get("expiresAt")
    if expires_at is not None:
        # Firestore timestamps come as datetime objects
        if hasattr(expires_at, "timestamp"):
            exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
            if exp <= datetime.now(timezone.utc):
                raise ValueError("NB session expired (expiresAt)")

    encrypted = data.get("storageState", "")
    if not encrypted:
        raise ValueError("NB session storage state is empty")

    # T-036: decrypt_storage_state now normalizes all decryption errors to ValueError
    storage_state = decrypt_storage_state(encrypted)
    return {
        "storageState": storage_state,
        "status": status,
        "expiresAt": expires_at,
    }


class NotebookLMClient:
    """Wrapper around notebooklm-py for notebook operations."""

    def __init__(self, storage_state: dict):
        self._storage_state = storage_state
        self._client = None

    async def _get_client(self):
        """Lazily initialize the notebooklm-py client."""
        if self._client is not None:
            return self._client

        from notebooklm import NotebookLM

        # Write storage state to temp file for notebooklm-py
        self._state_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        json.dump(self._storage_state, self._state_file)
        self._state_file.close()

        self._client = NotebookLM(storage_state=self._state_file.name)
        return self._client

    async def create_notebook(self, title: str = "Daily Podcast") -> str:
        """Create a new notebook. Returns notebook ID."""
        client = await self._get_client()
        notebook = await client.create_notebook(title=title)
        notebook_id = notebook.id if hasattr(notebook, "id") else str(notebook)
        logger.info("Created notebook: %s", notebook_id)
        return notebook_id

    async def add_source(self, notebook_id: str, pdf_path: str) -> None:
        """Add a local PDF file as source to notebook."""
        client = await self._get_client()
        await client.add_source(notebook_id=notebook_id, file_path=pdf_path)
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
        audio = await client.generate_audio(
            notebook_id=notebook_id,
            instructions=instructions,
        )
        # audio may be bytes directly or an object with .content / .data
        if isinstance(audio, bytes):
            return audio
        if hasattr(audio, "content"):
            return audio.content
        if hasattr(audio, "data"):
            return audio.data
        # Try reading as file path
        if isinstance(audio, str):
            with open(audio, "rb") as f:
                return f.read()
        raise RuntimeError(f"Unexpected audio response type: {type(audio)}")

    async def delete_notebook(self, notebook_id: str) -> None:
        """Delete a notebook (cleanup after generation)."""
        try:
            client = await self._get_client()
            await client.delete_notebook(notebook_id=notebook_id)
            logger.info("Deleted notebook: %s", notebook_id)
        except Exception as e:
            logger.warning("Failed to delete notebook %s: %s", notebook_id, e)

    async def close(self) -> None:
        """Clean up resources."""
        if hasattr(self, "_state_file") and self._state_file:
            try:
                os.unlink(self._state_file.name)
            except OSError:
                pass
        if self._client and hasattr(self._client, "close"):
            try:
                await self._client.close()
            except Exception:
                pass
