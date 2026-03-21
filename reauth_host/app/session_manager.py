from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import secrets
import shutil
import socket
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from playwright.async_api import Browser, BrowserContext, Error as PlaywrightError, async_playwright

logger = logging.getLogger(__name__)

_COOKIE_CHECK_URLS = [
    "https://notebooklm.google.com",
    "https://accounts.google.com",
    "https://www.google.com",
]
_REQUIRED_COOKIE_NAMES = frozenset({"SID"})


@dataclass
class ReauthSession:
    session_id: str
    viewer_token: str
    viewer_url: str
    target_url: str
    callback_url: str
    callback_token: str
    created_at: datetime
    expires_at: datetime
    ttl_seconds: int
    display_id: int
    vnc_port: int
    ws_port: int
    cdp_port: int
    workdir: Path
    status: str = "pending"
    error: str | None = None
    processes: list[asyncio.subprocess.Process] = field(default_factory=list)
    watcher_task: asyncio.Task | None = None
    callback_sent: bool = False


class SessionCapacityError(RuntimeError):
    pass


class SessionLaunchError(RuntimeError):
    pass


class SessionManager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._sessions: dict[str, ReauthSession] = {}
        self._session_root = Path(os.getenv("REAUTH_HOST_SESSION_ROOT", "/tmp/reauth-host")).resolve()
        self._session_root.mkdir(parents=True, exist_ok=True)
        self._public_base_url = self._required_env("REAUTH_HOST_PUBLIC_BASE_URL").rstrip("/")
        self._chromium_executable = os.getenv("REAUTH_CHROMIUM_EXECUTABLE", "/usr/bin/chromium")
        self._novnc_static_dir = os.getenv("REAUTH_NOVNC_STATIC_DIR", "/usr/share/novnc")
        self._max_sessions = int(os.getenv("REAUTH_HOST_MAX_SESSIONS", "1"))
        self._display_base = int(os.getenv("REAUTH_HOST_DISPLAY_BASE", "90"))
        self._watch_poll_seconds = float(os.getenv("REAUTH_HOST_WATCH_POLL_SECONDS", "2"))

    @property
    def novnc_static_dir(self) -> str:
        return self._novnc_static_dir

    def _required_env(self, name: str) -> str:
        value = os.getenv(name, "").strip()
        if not value:
            raise RuntimeError(f"{name} not configured")
        return value

    def _allocate_port(self) -> int:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        try:
            return int(sock.getsockname()[1])
        finally:
            sock.close()

    def _allocate_display_id(self) -> int:
        used = {session.display_id for session in self._sessions.values()}
        display_id = self._display_base
        while display_id in used:
            display_id += 1
        return display_id

    def _build_viewer_url(self, session_id: str, viewer_token: str) -> str:
        return f"{self._public_base_url}/session/{session_id}?token={viewer_token}"

    async def create_session(
        self,
        *,
        session_id: str,
        target_url: str,
        ttl_seconds: int,
        callback_url: str,
        callback_token: str,
    ) -> ReauthSession:
        async with self._lock:
            active_sessions = [session for session in self._sessions.values() if session.status == "pending"]
            if len(active_sessions) >= self._max_sessions:
                raise SessionCapacityError("Another re-auth session is already active")

            viewer_token = secrets.token_urlsafe(24)
            created_at = datetime.now(timezone.utc)
            expires_at = created_at + timedelta(seconds=ttl_seconds)
            workdir = Path(tempfile.mkdtemp(prefix=f"reauth-{session_id}-", dir=self._session_root))
            session = ReauthSession(
                session_id=session_id,
                viewer_token=viewer_token,
                viewer_url=self._build_viewer_url(session_id, viewer_token),
                target_url=target_url,
                callback_url=callback_url,
                callback_token=callback_token,
                created_at=created_at,
                expires_at=expires_at,
                ttl_seconds=ttl_seconds,
                display_id=self._allocate_display_id(),
                vnc_port=self._allocate_port(),
                ws_port=self._allocate_port(),
                cdp_port=self._allocate_port(),
                workdir=workdir,
            )
            self._sessions[session_id] = session

        try:
            await self._start_processes(session)
            session.watcher_task = asyncio.create_task(self._watch_session(session.session_id))
            return session
        except Exception:
            await self.cleanup_session(session.session_id)
            raise

    async def get_session(self, session_id: str) -> ReauthSession | None:
        async with self._lock:
            return self._sessions.get(session_id)

    async def cleanup_session(self, session_id: str, *, from_watcher: bool = False) -> None:
        async with self._lock:
            session = self._sessions.pop(session_id, None)

        if not session:
            return

        if session.watcher_task and not from_watcher:
            session.watcher_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await session.watcher_task

        for process in reversed(session.processes):
            await self._terminate_process(process)

        shutil.rmtree(session.workdir, ignore_errors=True)

    async def _terminate_process(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()
            with contextlib.suppress(Exception):
                await process.wait()

    async def _start_processes(self, session: ReauthSession) -> None:
        display = f":{session.display_id}"
        profile_dir = session.workdir / "profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        browser_home = session.workdir / "home"
        browser_home.mkdir(parents=True, exist_ok=True)

        base_env = os.environ.copy()
        base_env["DISPLAY"] = display
        base_env["HOME"] = str(browser_home)

        session.processes.append(
            await asyncio.create_subprocess_exec(
                "Xvfb",
                display,
                "-screen",
                "0",
                "1440x900x24",
                "-nolisten",
                "tcp",
                "-ac",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                env=base_env,
            )
        )
        await asyncio.sleep(0.5)

        session.processes.append(
            await asyncio.create_subprocess_exec(
                "openbox",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                env=base_env,
            )
        )

        session.processes.append(
            await asyncio.create_subprocess_exec(
                "x11vnc",
                "-display",
                display,
                "-rfbport",
                str(session.vnc_port),
                "-localhost",
                "-forever",
                "-shared",
                "-nopw",
                "-xkb",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                env=base_env,
            )
        )

        session.processes.append(
            await asyncio.create_subprocess_exec(
                "websockify",
                "--web",
                self._novnc_static_dir,
                str(session.ws_port),
                f"127.0.0.1:{session.vnc_port}",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                env=base_env,
            )
        )

        chromium_args = [
            self._chromium_executable,
            f"--user-data-dir={profile_dir}",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--window-size=1280,900",
            "--start-maximized",
            f"--remote-debugging-port={session.cdp_port}",
            session.target_url,
        ]
        session.processes.append(
            await asyncio.create_subprocess_exec(
                *chromium_args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                env=base_env,
            )
        )

        await asyncio.sleep(2)
        for process in session.processes:
            if process.returncode not in (None, 0):
                raise SessionLaunchError(f"Session process exited early with code {process.returncode}")

    async def _watch_session(self, session_id: str) -> None:
        session = await self.get_session(session_id)
        if not session:
            return

        browser: Browser | None = None
        playwright = None

        try:
            while datetime.now(timezone.utc) < session.expires_at:
                if not browser:
                    try:
                        playwright = await async_playwright().start()
                        browser = await playwright.chromium.connect_over_cdp(
                            f"http://127.0.0.1:{session.cdp_port}"
                        )
                    except Exception:
                        browser = None
                        if playwright:
                            await playwright.stop()
                            playwright = None
                        await asyncio.sleep(self._watch_poll_seconds)
                        continue

                context = await self._find_logged_in_context(browser, session.target_url)
                if context:
                    storage_state = await self._build_storage_state(context)
                    missing = self._missing_required_cookie_names(storage_state)
                    if missing:
                        logger.info(
                            "Reauth session %s reached target page but is still missing cookies: %s",
                            session.session_id,
                            ", ".join(missing),
                        )
                        await asyncio.sleep(self._watch_poll_seconds)
                        continue

                    session.status = "completed"
                    await self._notify_backend(
                        session,
                        {
                            "sessionId": session.session_id,
                            "status": "completed",
                            "storageState": storage_state,
                        },
                    )
                    return

                await asyncio.sleep(self._watch_poll_seconds)

            session.status = "timed_out"
            session.error = "NotebookLM login timed out"
            await self._notify_backend(
                session,
                {
                    "sessionId": session.session_id,
                    "status": "timed_out",
                    "error": session.error,
                },
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Reauth watcher failed for session %s", session.session_id)
            session.status = "failed"
            session.error = str(exc)
            with contextlib.suppress(Exception):
                await self._notify_backend(
                    session,
                    {
                        "sessionId": session.session_id,
                        "status": "failed",
                        "error": session.error,
                    },
                )
        finally:
            if browser:
                with contextlib.suppress(Exception):
                    await browser.close()
            if playwright:
                with contextlib.suppress(Exception):
                    await playwright.stop()
            await self.cleanup_session(session.session_id, from_watcher=True)

    async def _find_logged_in_context(self, browser: Browser, target_url: str) -> BrowserContext | None:
        target_host = target_url.split("/")[2] if "://" in target_url else target_url

        for context in browser.contexts:
            for page in context.pages:
                try:
                    current_url = page.url
                except PlaywrightError:
                    continue

                if target_host in current_url and "/login" not in current_url:
                    return context

        return None

    async def _build_storage_state(self, context: BrowserContext) -> dict[str, Any]:
        storage_state = await context.storage_state()
        explicit_cookies = await context.cookies(_COOKIE_CHECK_URLS)

        merged = {}
        for cookie in storage_state.get("cookies", []):
            if isinstance(cookie, dict):
                merged[(cookie.get("name"), cookie.get("domain"), cookie.get("path"))] = cookie
        for cookie in explicit_cookies:
            if isinstance(cookie, dict):
                merged[(cookie.get("name"), cookie.get("domain"), cookie.get("path"))] = cookie

        storage_state["cookies"] = list(merged.values())
        return storage_state

    def _missing_required_cookie_names(self, storage_state: dict[str, Any]) -> list[str]:
        cookies = storage_state.get("cookies")
        if not isinstance(cookies, list):
            return sorted(_REQUIRED_COOKIE_NAMES)

        present = {
            str(cookie.get("name"))
            for cookie in cookies
            if isinstance(cookie, dict) and cookie.get("name")
        }
        return sorted(_REQUIRED_COOKIE_NAMES - present)

    async def _notify_backend(self, session: ReauthSession, payload: dict[str, Any]) -> None:
        if session.callback_sent:
            return
        session.callback_sent = True

        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            response = await client.post(
                session.callback_url,
                headers={"Authorization": f"Bearer {session.callback_token}"},
                json=payload,
            )
            response.raise_for_status()
