"""Exchange Google OAuth access_token for NotebookLM session cookies.

Uses Google's OAuthLogin and MergeSession endpoints (same mechanism Chromium
uses for account sign-in) to convert an OAuth access_token into browser-session
cookies (SID, HSID, SSID, etc.) that notebooklm-py can use.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_MERGE_CONTINUE_URL = "https://notebooklm.google.com"

# Domains whose cookies we want to keep in the storage state.
_ALLOWED_COOKIE_DOMAINS = frozenset({
    ".google.com",
    "notebooklm.google.com",
    ".googleusercontent.com",
    ".usercontent.google.com",
    ".youtube.com",
    "accounts.google.com",
})


def _is_allowed_domain(domain: str) -> bool:
    if domain in _ALLOWED_COOKIE_DOMAINS:
        return True
    if domain.startswith(".google."):
        return True
    if domain.endswith(".google.com") or domain.endswith(".googleusercontent.com"):
        return True
    return False


def _build_storage_state_from_jar(jar: httpx.Cookies) -> dict[str, Any]:
    """Convert an httpx cookie jar into Playwright-compatible storage_state."""
    cookies = []
    for cookie in jar.jar:
        domain = cookie.domain or ""
        if not _is_allowed_domain(domain):
            logger.debug("[cookie_exchange] Skipping cookie %s from non-Google domain %s", cookie.name, domain)
            continue
        cookies.append({
            "name": cookie.name,
            "value": cookie.value or "",
            "domain": domain,
            "path": cookie.path or "/",
            "httpOnly": bool(cookie.has_nonstandard_attr("HttpOnly")),
            "secure": bool(cookie.secure),
            "sameSite": "None",
        })
    logger.info(
        "[cookie_exchange] Built storage_state: %d cookies from jar (%d total in jar)",
        len(cookies), len(list(jar.jar)),
    )
    return {"cookies": cookies, "origins": []}


async def exchange_access_token_for_cookies(
    access_token: str,
) -> dict[str, Any]:
    """Exchange a Google access_token for a Playwright-format storage_state.

    Steps:
    1. GET /OAuthLogin → uberauth token
    2. GET /MergeSession → browser cookies (SID, etc.)

    Returns:
        dict: Playwright-compatible storage_state with cookies.

    Raises:
        ValueError: If the exchange produces invalid/empty results.
        RuntimeError: If an HTTP request fails.
    """
    logger.info("[cookie_exchange] Starting exchange (access_token len=%d)", len(access_token))
    jar = httpx.Cookies()

    async with httpx.AsyncClient(
        cookies=jar,
        follow_redirects=True,
        timeout=httpx.Timeout(30.0),
    ) as client:
        # Step 1: access_token → uberauth
        logger.info("[cookie_exchange] Step 1: OAuthLogin — requesting uberauth token")
        try:
            uber_resp = await client.get(
                "https://accounts.google.com/OAuthLogin",
                params={
                    "source": "ChromiumBrowser",
                    "issueuberauth": "1",
                },
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except Exception as exc:
            logger.error("[cookie_exchange] OAuthLogin request failed: %s", exc)
            raise RuntimeError(f"OAuthLogin request failed: {exc}") from exc

        logger.info(
            "[cookie_exchange] OAuthLogin response: HTTP %d, content-type=%s, body_len=%d, final_url=%s",
            uber_resp.status_code,
            uber_resp.headers.get("content-type", "?"),
            len(uber_resp.text),
            str(uber_resp.url)[:200],
        )

        if uber_resp.status_code != 200:
            body = uber_resp.text[:500]
            logger.error("[cookie_exchange] OAuthLogin FAILED: HTTP %d, body=%s", uber_resp.status_code, body)
            raise RuntimeError(
                f"OAuthLogin failed (HTTP {uber_resp.status_code}): {body}"
            )

        uberauth = uber_resp.text.strip()
        logger.info("[cookie_exchange] OAuthLogin uberauth: len=%d, preview=%s", len(uberauth), uberauth[:30] + "...")

        if not uberauth or len(uberauth) < 10:
            logger.error("[cookie_exchange] OAuthLogin returned invalid uberauth: %s", uberauth[:200])
            raise ValueError(
                f"OAuthLogin returned invalid uberauth: {uberauth[:100]}"
            )

        # Log cookies collected so far
        jar_names_after_step1 = sorted({c.name for c in jar.jar})
        logger.info("[cookie_exchange] Cookies after OAuthLogin: %d cookies, names=%s", len(list(jar.jar)), jar_names_after_step1)

        # Step 2: uberauth → session cookies via MergeSession
        logger.info("[cookie_exchange] Step 2: MergeSession — exchanging uberauth for cookies")
        try:
            merge_resp = await client.get(
                "https://accounts.google.com/MergeSession",
                params={
                    "uberauth": uberauth,
                    "continue": _MERGE_CONTINUE_URL,
                    "source": "ChromiumBrowser",
                },
            )
        except Exception as exc:
            logger.error("[cookie_exchange] MergeSession request failed: %s", exc)
            raise RuntimeError(f"MergeSession request failed: {exc}") from exc

        logger.info(
            "[cookie_exchange] MergeSession response: HTTP %d, final_url=%s, body_len=%d",
            merge_resp.status_code,
            str(merge_resp.url)[:200],
            len(merge_resp.text),
        )

        # Log all redirect history
        if merge_resp.history:
            logger.info("[cookie_exchange] MergeSession redirect chain (%d hops):", len(merge_resp.history))
            for i, resp in enumerate(merge_resp.history):
                logger.info(
                    "[cookie_exchange]   hop %d: HTTP %d → %s",
                    i, resp.status_code, str(resp.url)[:200],
                )

        # Log cookies collected after MergeSession
        jar_names_after_step2 = sorted({c.name for c in jar.jar})
        jar_domains = sorted({c.domain for c in jar.jar})
        logger.info(
            "[cookie_exchange] Cookies after MergeSession: %d cookies, names=%s, domains=%s",
            len(list(jar.jar)), jar_names_after_step2, jar_domains,
        )

    storage_state = _build_storage_state_from_jar(jar)

    cookie_names = {c["name"] for c in storage_state["cookies"]}
    cookie_domains = {c["domain"] for c in storage_state["cookies"]}

    logger.info(
        "[cookie_exchange] Final storage_state: %d cookies, names=%s, domains=%s",
        len(storage_state["cookies"]),
        sorted(cookie_names),
        sorted(cookie_domains),
    )

    if "SID" not in cookie_names:
        logger.error(
            "[cookie_exchange] SID cookie NOT found! Got cookies: %s from domains: %s",
            sorted(cookie_names), sorted(cookie_domains),
        )
        raise ValueError(
            f"Cookie exchange failed: SID cookie not found. "
            f"Got {len(cookie_names)} cookies: {sorted(cookie_names)[:15]}"
        )

    logger.info("[cookie_exchange] Cookie exchange SUCCESSFUL — SID present")
    return storage_state
