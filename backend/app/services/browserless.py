"""Browserless adapter for NB re-authentication flows."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass


DEFAULT_NB_AUTH_URL = "https://notebooklm.google.com"
DEFAULT_NB_AUTH_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class BrowserlessSession:
    session_id: str
    connect_url: str
    viewer_url: str
    target_url: str
    timeout_seconds: int


def _get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} not configured")
    return value


def create_browserless_session(session_id: str | None = None) -> BrowserlessSession:
    """Build a Browserless session from env-driven templates.

    Required env:
      - BROWSERLESS_CONNECT_URL_TEMPLATE: e.g. wss://...{session_id}...{token}
      - BROWSERLESS_VIEWER_URL_TEMPLATE: e.g. https://.../sessions/{session_id}?token={token}
      - BROWSERLESS_TOKEN
    """
    session_id = session_id or uuid.uuid4().hex
    token = _get_required_env("BROWSERLESS_TOKEN")
    connect_template = _get_required_env("BROWSERLESS_CONNECT_URL_TEMPLATE")
    viewer_template = _get_required_env("BROWSERLESS_VIEWER_URL_TEMPLATE")
    target_url = os.getenv("NB_AUTH_TARGET_URL", DEFAULT_NB_AUTH_URL).strip() or DEFAULT_NB_AUTH_URL
    timeout_seconds = int(os.getenv("NB_AUTH_TIMEOUT_SECONDS", str(DEFAULT_NB_AUTH_TIMEOUT_SECONDS)))

    return BrowserlessSession(
        session_id=session_id,
        connect_url=connect_template.format(session_id=session_id, token=token),
        viewer_url=viewer_template.format(session_id=session_id, token=token),
        target_url=target_url,
        timeout_seconds=timeout_seconds,
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
