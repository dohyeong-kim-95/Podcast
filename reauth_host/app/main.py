from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from datetime import timezone
from urllib.parse import quote

import websockets
from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.websockets import WebSocketDisconnect

from .session_manager import SessionCapacityError, SessionLaunchError, SessionManager

logger = logging.getLogger(__name__)

AUTH_FLOW = "remote_vnc"
manager = SessionManager()


def _verify_api_key(authorization: str = Header(default="")) -> None:
    expected = os.getenv("REAUTH_HOST_API_KEY", "").strip()
    if not expected:
        raise HTTPException(status_code=500, detail="REAUTH_HOST_API_KEY not configured")
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid API key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    session_ids = list(manager._sessions.keys())  # noqa: SLF001 - controlled shutdown cleanup
    for session_id in session_ids:
        await manager.cleanup_session(session_id)


app = FastAPI(title="Podcast Reauth Host", version="0.1.0", lifespan=lifespan)
app.mount("/novnc", StaticFiles(directory=manager.novnc_static_dir), name="novnc")


class CreateSessionRequest(BaseModel):
    sessionId: str = Field(min_length=1)
    targetUrl: str = Field(min_length=1)
    ttlSeconds: int = Field(default=300, ge=60, le=1800)
    callbackUrl: str = Field(min_length=1)
    callbackToken: str = Field(min_length=1)
    userId: str | None = None
    userEmail: str | None = None
    userName: str | None = None


class CreateSessionResponse(BaseModel):
    sessionId: str
    viewerUrl: str
    status: str
    authFlow: str = AUTH_FLOW
    expiresAt: str


class SessionStatusResponse(BaseModel):
    sessionId: str
    status: str
    authFlow: str = AUTH_FLOW
    expiresAt: str
    error: str | None = None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/internal/sessions", response_model=CreateSessionResponse, dependencies=[Depends(_verify_api_key)])
async def create_session(body: CreateSessionRequest):
    try:
        session = await manager.create_session(
            session_id=body.sessionId,
            target_url=body.targetUrl,
            ttl_seconds=body.ttlSeconds,
            callback_url=body.callbackUrl,
            callback_token=body.callbackToken,
        )
    except SessionCapacityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SessionLaunchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return CreateSessionResponse(
        sessionId=session.session_id,
        viewerUrl=session.viewer_url,
        status=session.status,
        expiresAt=session.expires_at.astimezone(timezone.utc).isoformat(),
    )


@app.get("/internal/sessions/{session_id}", response_model=SessionStatusResponse, dependencies=[Depends(_verify_api_key)])
async def get_session_status(session_id: str):
    session = await manager.get_session_status(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionStatusResponse(
        sessionId=session.session_id,
        status=session.status,
        expiresAt=session.expires_at.astimezone(timezone.utc).isoformat(),
        error=session.error,
    )


@app.get("/session/{session_id}/status", response_model=SessionStatusResponse)
async def get_public_session_status(session_id: str, token: str = Query(default="")):
    session = await manager.get_session_status(session_id)
    if not session or token != session.viewer_token:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionStatusResponse(
        sessionId=session.session_id,
        status=session.status,
        expiresAt=session.expires_at.astimezone(timezone.utc).isoformat(),
        error=session.error,
    )


@app.get("/session/{session_id}", response_class=HTMLResponse)
async def session_view(session_id: str, token: str = Query(default="")):
    session = await manager.get_session(session_id)
    if not session or token != session.viewer_token:
        raise HTTPException(status_code=404, detail="Session not found")

    ws_path = quote(f"session/{session_id}/websockify?token={token}", safe="")
    html = f"""<!doctype html>
<html lang="ko">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover" />
    <title>NotebookLM Reauth</title>
    <style>
      html, body {{
        margin: 0;
        height: 100%;
        background: #0d1117;
        color: #f5f7fa;
        font-family: system-ui, sans-serif;
      }}
      .frame {{
        border: 0;
        width: 100%;
        height: 100%;
      }}
      .banner {{
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        z-index: 2;
        padding: 10px 14px;
        background: rgba(13, 17, 23, 0.78);
        backdrop-filter: blur(8px);
        font-size: 14px;
      }}
      .banner strong {{
        display: block;
        margin-bottom: 2px;
      }}
      .status {{
        position: fixed;
        inset: 0;
        display: none;
        align-items: center;
        justify-content: center;
        background: rgba(13, 17, 23, 0.92);
        z-index: 3;
        text-align: center;
        padding: 24px;
      }}
      .status.visible {{
        display: flex;
      }}
      .status-card {{
        max-width: 420px;
        width: 100%;
        border: 1px solid rgba(255, 255, 255, 0.15);
        border-radius: 18px;
        padding: 20px;
        background: rgba(255, 255, 255, 0.04);
      }}
      .status-card h1 {{
        margin: 0 0 8px;
        font-size: 20px;
      }}
      .status-card p {{
        margin: 0;
        line-height: 1.5;
        color: rgba(245, 247, 250, 0.85);
      }}
    </style>
  </head>
  <body>
    <div class="banner">
      <strong>NotebookLM 재인증</strong>
      원격 브라우저에서 로그인을 마치면 이 세션은 자동으로 닫힙니다.
    </div>
    <div class="status" id="statusOverlay">
      <div class="status-card">
        <h1 id="statusTitle">세션 처리 중</h1>
        <p id="statusMessage">잠시만 기다려주세요.</p>
      </div>
    </div>
    <iframe
      class="frame"
      src="/novnc/vnc.html?autoconnect=1&resize=scale&show_dot=true&path={ws_path}">
    </iframe>
    <script>
      const statusUrl = "/session/{session_id}/status?token={token}";
      const overlay = document.getElementById("statusOverlay");
      const titleEl = document.getElementById("statusTitle");
      const messageEl = document.getElementById("statusMessage");

      function showTerminalState(title, message) {{
        titleEl.textContent = title;
        messageEl.textContent = message;
        overlay.classList.add("visible");
      }}

      function attemptClose() {{
        setTimeout(() => window.close(), 300);
        setTimeout(() => {{
          if (!window.closed) {{
            showTerminalState(
              titleEl.textContent,
              messageEl.textContent + " 이 탭을 닫고 앱으로 돌아가세요."
            );
          }}
        }}, 1200);
      }}

      async function pollStatus() {{
        try {{
          const response = await fetch(statusUrl, {{ cache: "no-store" }});
          if (response.status === 404) {{
            showTerminalState("세션 종료", "재인증 세션이 종료되었습니다.");
            attemptClose();
            return;
          }}

          const data = await response.json();
          if (data.status === "completed") {{
            showTerminalState("재인증 완료", "NotebookLM 세션이 저장되었습니다.");
            attemptClose();
            return;
          }}
          if (data.status === "failed" || data.status === "timed_out") {{
            showTerminalState("재인증 실패", data.error || "세션이 종료되었습니다.");
            return;
          }}
        }} catch (_error) {{
          // keep polling through transient network errors
        }}

        setTimeout(pollStatus, 2000);
      }}

      setTimeout(pollStatus, 2000);
    </script>
  </body>
</html>"""
    return HTMLResponse(html)


@app.websocket("/session/{session_id}/websockify")
async def proxy_websockify(session_id: str, websocket: WebSocket, token: str = Query(default="")):
    session = await manager.get_session(session_id)
    if not session or token != session.viewer_token:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    upstream = await websockets.connect(f"ws://127.0.0.1:{session.ws_port}")

    async def client_to_upstream():
        while True:
            message = await websocket.receive()
            message_type = message.get("type")
            if message_type == "websocket.disconnect":
                break
            if message.get("text") is not None:
                await upstream.send(message["text"])
            elif message.get("bytes") is not None:
                await upstream.send(message["bytes"])

    async def upstream_to_client():
        while True:
            data = await upstream.recv()
            if isinstance(data, bytes):
                await websocket.send_bytes(data)
            else:
                await websocket.send_text(data)

    try:
        done, pending = await asyncio.wait(
            {
                asyncio.create_task(client_to_upstream()),
                asyncio.create_task(upstream_to_client()),
            },
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        for task in done:
            with contextlib.suppress(Exception):
                await task
    except WebSocketDisconnect:
        pass
    finally:
        await upstream.close()
