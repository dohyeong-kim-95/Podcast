import asyncio
from unittest.mock import patch

from app.services.browserless import create_browserless_session


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, params=None, json=None):
        self.calls.append({"url": url, "params": params, "json": json})
        return self._responses.pop(0)


class _FakeWebSocket:
    def __init__(self, messages):
        self._messages = list(messages)
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def send(self, payload):
        self.sent.append(payload)

    async def recv(self):
        return self._messages.pop(0)


def test_create_browserless_session_uses_session_api_and_liveurl_cdp():
    fake_client = _FakeAsyncClient(
        [
            _FakeResponse(
                {
                    "id": "session-123",
                    "connect": "wss://production-sfo.browserless.io/session/session-123?token=api-token",
                    "stop": "https://production-sfo.browserless.io/session/session-123?token=api-token",
                }
            ),
        ]
    )
    fake_websocket = _FakeWebSocket(
        [
            '{"id": 1, "result": {"targetInfos": [{"targetId": "target-1", "type": "page"}]}}',
            '{"id": 2, "result": {"sessionId": "cdp-session-1"}}',
            '{"id": 3, "result": {}}',
            '{"id": 4, "result": {"frameId": "frame-1"}}',
            '{"id": 5, "result": {"liveURL": "https://browserless.live/session-123"}}',
        ]
    )

    with patch.dict(
        "os.environ",
        {
            "BROWSERLESS_TOKEN": "api-token",
            "BROWSERLESS_CONNECT_URL_TEMPLATE": "wss://production-sfo.browserless.io?token={token}&sessionId={session_id}",
            "NB_AUTH_TIMEOUT_SECONDS": "300",
        },
        clear=False,
    ), patch("app.services.browserless.httpx.AsyncClient", return_value=fake_client), \
         patch("app.services.browserless.websockets.connect", return_value=fake_websocket):
        session = asyncio.run(create_browserless_session())

    assert fake_client.calls[0]["url"] == "https://production-sfo.browserless.io/session"
    assert fake_client.calls[0]["params"] == {"token": "api-token"}
    assert fake_client.calls[0]["json"]["processKeepAlive"] == 300000
    assert fake_client.calls[0]["json"]["url"] == "https://notebooklm.google.com"
    assert session.session_id == "session-123"
    assert session.connect_url == "wss://production-sfo.browserless.io/session/session-123?token=api-token"
    assert session.viewer_url == "https://browserless.live/session-123"
    assert session.stop_url == "https://production-sfo.browserless.io/session/session-123?token=api-token"
    assert len(fake_websocket.sent) == 5
    assert '"method": "Browserless.liveURL"' in fake_websocket.sent[-1]


def test_create_browserless_session_creates_target_when_missing():
    fake_client = _FakeAsyncClient(
        [
            _FakeResponse(
                {
                    "id": "session-456",
                    "connect": "wss://production-sfo.browserless.io/session/session-456?token=api-token",
                    "stop": "https://production-sfo.browserless.io/session/session-456?token=api-token",
                }
            ),
        ]
    )
    fake_websocket = _FakeWebSocket(
        [
            '{"id": 1, "result": {"targetInfos": []}}',
            '{"id": 2, "result": {"targetId": "target-456"}}',
            '{"id": 3, "result": {"sessionId": "cdp-session-456"}}',
            '{"id": 4, "result": {}}',
            '{"id": 5, "result": {"frameId": "frame-456"}}',
            '{"id": 6, "result": {"liveURL": "https://browserless.live/session-456"}}',
        ]
    )

    with patch.dict(
        "os.environ",
        {
            "BROWSERLESS_TOKEN": "api-token",
            "BROWSERLESS_CONNECT_URL_TEMPLATE": "wss://production-sfo.browserless.io?token={token}&sessionId={session_id}",
            "NB_AUTH_TIMEOUT_SECONDS": "300",
        },
        clear=False,
    ), patch("app.services.browserless.httpx.AsyncClient", return_value=fake_client), \
         patch("app.services.browserless.websockets.connect", return_value=fake_websocket):
        session = asyncio.run(create_browserless_session())

    assert session.viewer_url == "https://browserless.live/session-456"
    assert '"method": "Target.createTarget"' in fake_websocket.sent[1]
