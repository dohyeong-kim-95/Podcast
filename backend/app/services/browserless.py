"""Browserless adapter for NB re-authentication flows."""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

import httpx


DEFAULT_NB_AUTH_URL = "https://notebooklm.google.com"
DEFAULT_NB_AUTH_TIMEOUT_SECONDS = 300
DEFAULT_BROWSERLESS_GRAPHQL_URL = "https://api.browserless.io/graphql"
DEFAULT_BROWSERLESS_SESSION_POLL_ATTEMPTS = 10
DEFAULT_BROWSERLESS_SESSION_POLL_DELAY_SECONDS = 0.5


@dataclass(frozen=True)
class BrowserlessSession:
    session_id: str
    connect_url: str
    viewer_url: str
    target_url: str
    timeout_seconds: int
    stop_url: str | None = None


def _get_required_env(name: str) -> str:
    value = "".join(os.getenv(name, "").split()).strip("'\"")
    if not value:
        raise RuntimeError(f"{name} not configured")
    return value


def _browserless_origin() -> str:
    explicit = os.getenv("BROWSERLESS_API_BASE_URL", "")
    if explicit.strip():
        value = "".join(explicit.split()).strip("'\"")
        parsed = urlparse(value)
        if parsed.scheme and parsed.netloc:
            return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))

    for env_name in ("BROWSERLESS_CONNECT_URL_TEMPLATE", "BROWSERLESS_VIEWER_URL_TEMPLATE"):
        raw = os.getenv(env_name, "")
        if not raw.strip():
            continue
        value = "".join(raw.split()).strip("'\"")
        parsed = urlparse(value)
        if not parsed.netloc:
            continue
        scheme = parsed.scheme.lower()
        if scheme == "wss":
            scheme = "https"
        elif scheme == "ws":
            scheme = "http"
        return urlunparse((scheme, parsed.netloc, "", "", "", ""))

    raise RuntimeError("Browserless base URL not configured")


def _append_token(url: str, token: str, *, origin: str) -> str:
    raw = "".join(url.split()).strip("'\"")
    if raw.startswith("/"):
        raw = f"{origin}{raw}"
    elif not urlparse(raw).scheme:
        raw = f"{origin}/{raw.lstrip('/')}"

    parsed = urlparse(raw)
    if "token=" in parsed.query:
        return raw

    separator = "&" if parsed.query else "?"
    return f"{raw}{separator}token={token}"


async def _fetch_viewer_url(session_id: str, token: str, *, origin: str) -> str:
    payload = {
        "query": """
            query getSessions($id: String!, $apiToken: String!) {
                sessions(apiToken: $apiToken, id: $id) {
                    devtoolsFrontendUrl
                }
            }
        """,
        "variables": {
            "id": session_id,
            "apiToken": token,
        },
    }

    timeout = httpx.Timeout(20.0)
    attempts = max(1, int(os.getenv("BROWSERLESS_SESSION_POLL_ATTEMPTS", str(DEFAULT_BROWSERLESS_SESSION_POLL_ATTEMPTS))))
    delay_seconds = float(os.getenv("BROWSERLESS_SESSION_POLL_DELAY_SECONDS", str(DEFAULT_BROWSERLESS_SESSION_POLL_DELAY_SECONDS)))

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(attempts):
            response = await client.post(DEFAULT_BROWSERLESS_GRAPHQL_URL, json=payload)
            response.raise_for_status()
            sessions = response.json().get("data", {}).get("sessions", [])
            if sessions:
                viewer_url = sessions[0].get("devtoolsFrontendUrl", "")
                if viewer_url:
                    return _append_token(viewer_url, token, origin=origin)
            if attempt + 1 < attempts:
                await asyncio.sleep(delay_seconds)

    raise RuntimeError("Failed to retrieve Browserless debugger URL")


async def create_browserless_session(session_id: str | None = None) -> BrowserlessSession:
    """Create a Browserless session via the official Session API."""

    _ = session_id or uuid.uuid4().hex
    token = _get_required_env("BROWSERLESS_TOKEN")
    origin = _browserless_origin()
    target_url = os.getenv("NB_AUTH_TARGET_URL", DEFAULT_NB_AUTH_URL).strip() or DEFAULT_NB_AUTH_URL
    timeout_seconds = int(os.getenv("NB_AUTH_TIMEOUT_SECONDS", str(DEFAULT_NB_AUTH_TIMEOUT_SECONDS)))

    payload = {
        "ttl": timeout_seconds * 1000,
        "stealth": True,
        "headless": False,
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
        response = await client.post(f"{origin}/session", params={"token": token}, json=payload)
        response.raise_for_status()
        data = response.json()

    session_id = data["id"]
    viewer_url = await _fetch_viewer_url(session_id, token, origin=origin)

    return BrowserlessSession(
        session_id=session_id,
        connect_url=data["connect"],
        viewer_url=viewer_url,
        target_url=target_url,
        timeout_seconds=timeout_seconds,
        stop_url=data.get("stop"),
    )


async def wait_for_notebook_login(session: BrowserlessSession) -> dict:
    """Connect to the remote browser and wait for NotebookLM login completion."""
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(session.connect_url)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(session.target_url, wait_until="domcontentloaded")

        poll_attempts = max(1, session.timeout_seconds // 2)
        for _ in range(poll_attempts):
            await page.wait_for_timeout(2000)
            current_url = page.url
            if "notebooklm.google.com" in current_url and "/login" not in current_url:
                storage_state = await context.storage_state()
                await browser.close()
                return storage_state

        await browser.close()
        raise TimeoutError("NotebookLM login timed out")
