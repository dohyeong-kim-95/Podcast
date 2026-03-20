"""Browserless adapter for NB re-authentication flows."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

import httpx
import websockets


DEFAULT_NB_AUTH_URL = "https://notebooklm.google.com"
DEFAULT_NB_AUTH_TIMEOUT_SECONDS = 300
DEFAULT_BROWSERLESS_QUALITY = 50


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


class _CdpConnection:
    def __init__(self, websocket):
        self.websocket = websocket
        self._next_id = 1

    async def send(self, method: str, params: dict | None = None, *, session_id: str | None = None) -> dict:
        call_id = self._next_id
        self._next_id += 1
        payload: dict[str, object] = {
            "id": call_id,
            "method": method,
        }
        if params:
            payload["params"] = params
        if session_id:
            payload["sessionId"] = session_id

        await self.websocket.send(json.dumps(payload))

        while True:
            raw = await self.websocket.recv()
            message = json.loads(raw)
            if message.get("id") != call_id:
                continue
            if "error" in message:
                details = message["error"]
                raise RuntimeError(f"{method} failed: {details}")
            return message.get("result", {})


async def _create_live_url(connect_url: str, target_url: str, timeout_seconds: int) -> str:
    async with websockets.connect(connect_url, open_timeout=20) as websocket:
        cdp = _CdpConnection(websocket)
        targets = await cdp.send("Target.getTargets")
        page_targets = [
            target for target in targets.get("targetInfos", [])
            if target.get("type") == "page"
        ]

        if page_targets:
            target_id = page_targets[0]["targetId"]
        else:
            created = await cdp.send("Target.createTarget", {"url": target_url})
            target_id = created["targetId"]

        attached = await cdp.send("Target.attachToTarget", {"targetId": target_id, "flatten": True})
        session_id = attached["sessionId"]

        await cdp.send("Page.enable", session_id=session_id)
        await cdp.send("Page.navigate", {"url": target_url}, session_id=session_id)
        response = await cdp.send(
            "Browserless.liveURL",
            {
                "showBrowserInterface": True,
                "quality": int(os.getenv("BROWSERLESS_LIVE_QUALITY", str(DEFAULT_BROWSERLESS_QUALITY))),
                "timeout": timeout_seconds * 1000,
            },
            session_id=session_id,
        )
        live_url = response.get("liveURL", "")
        if not live_url:
            raise RuntimeError("Browserless.liveURL returned no URL")
        return live_url


async def create_browserless_session(session_id: str | None = None) -> BrowserlessSession:
    """Create a Browserless session via the official Session API."""

    _ = session_id or uuid.uuid4().hex
    token = _get_required_env("BROWSERLESS_TOKEN")
    origin = _browserless_origin()
    target_url = os.getenv("NB_AUTH_TARGET_URL", DEFAULT_NB_AUTH_URL).strip() or DEFAULT_NB_AUTH_URL
    timeout_seconds = int(os.getenv("NB_AUTH_TIMEOUT_SECONDS", str(DEFAULT_NB_AUTH_TIMEOUT_SECONDS)))

    payload = {
        "ttl": timeout_seconds * 1000,
        "processKeepAlive": timeout_seconds * 1000,
        "stealth": True,
        "headless": False,
        "url": target_url,
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
    connect_url = _append_token(data["connect"], token, origin=origin)
    viewer_url = await _create_live_url(connect_url, target_url, timeout_seconds)

    return BrowserlessSession(
        session_id=session_id,
        connect_url=connect_url,
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
