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


def test_create_browserless_session_uses_session_api_and_graphql():
    fake_client = _FakeAsyncClient(
        [
            _FakeResponse(
                {
                    "id": "session-123",
                    "connect": "wss://production-sfo.browserless.io/session/session-123?token=api-token",
                    "stop": "https://production-sfo.browserless.io/session/session-123?token=api-token",
                }
            ),
            _FakeResponse(
                {
                    "data": {
                        "sessions": [
                            {
                                "devtoolsFrontendUrl": "https://production-sfo.browserless.io/devtools/inspector.html?ws=production-sfo.browserless.io/session/session-123"
                            }
                        ]
                    }
                }
            ),
        ]
    )

    with patch.dict(
        "os.environ",
        {
            "BROWSERLESS_TOKEN": "api-token",
            "BROWSERLESS_CONNECT_URL_TEMPLATE": "wss://production-sfo.browserless.io?token={token}&sessionId={session_id}",
            "BROWSERLESS_VIEWER_URL_TEMPLATE": "https://production-sfo.browserless.io/sessions/{session_id}?token={token}",
            "NB_AUTH_TIMEOUT_SECONDS": "300",
        },
        clear=False,
    ), patch("app.services.browserless.httpx.AsyncClient", return_value=fake_client):
        session = asyncio.run(create_browserless_session())

    assert fake_client.calls[0]["url"] == "https://production-sfo.browserless.io/session"
    assert fake_client.calls[0]["params"] == {"token": "api-token"}
    assert fake_client.calls[1]["url"] == "https://api.browserless.io/graphql"
    assert session.session_id == "session-123"
    assert session.connect_url == "wss://production-sfo.browserless.io/session/session-123?token=api-token"
    assert session.viewer_url == (
        "https://production-sfo.browserless.io/devtools/inspector.html"
        "?ws=production-sfo.browserless.io/session/session-123&token=api-token"
    )
    assert session.stop_url == "https://production-sfo.browserless.io/session/session-123?token=api-token"


def test_create_browserless_session_prefixes_relative_devtools_url():
    fake_client = _FakeAsyncClient(
        [
            _FakeResponse(
                {
                    "id": "session-456",
                    "connect": "wss://production-sfo.browserless.io/session/session-456?token=api-token",
                    "stop": "https://production-sfo.browserless.io/session/session-456?token=api-token",
                }
            ),
            _FakeResponse(
                {
                    "data": {
                        "sessions": [
                            {
                                "devtoolsFrontendUrl": "/devtools/inspector.html?ws=production-sfo.browserless.io/session/session-456"
                            }
                        ]
                    }
                }
            ),
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
    ), patch("app.services.browserless.httpx.AsyncClient", return_value=fake_client):
        session = asyncio.run(create_browserless_session())

    assert session.viewer_url == (
        "https://production-sfo.browserless.io/devtools/inspector.html"
        "?ws=production-sfo.browserless.io/session/session-456&token=api-token"
    )
