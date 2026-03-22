"""Exchange Google OAuth access_token for NotebookLM session cookies.

Tries multiple approaches to convert an OAuth access_token into browser-session
cookies (SID, HSID, SSID, etc.) that notebooklm-py can use.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

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
    return {"cookies": cookies, "origins": []}


def _log_jar(label: str, jar: httpx.Cookies) -> None:
    names = sorted({c.name for c in jar.jar})
    domains = sorted({c.domain for c in jar.jar})
    logger.info("[cookie_exchange] %s: %d cookies, names=%s, domains=%s",
                label, len(list(jar.jar)), names, domains)


async def exchange_access_token_for_cookies(
    access_token: str,
) -> dict[str, Any]:
    """Try multiple approaches to exchange access_token for session cookies.

    Returns Playwright-compatible storage_state dict on success.
    Raises ValueError/RuntimeError on failure.
    """
    logger.info("[cookie_exchange] === START === access_token len=%d", len(access_token))

    # ── Step 0: Validate token via tokeninfo ──
    logger.info("[cookie_exchange] Step 0: tokeninfo check")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as c:
            ti = await c.get("https://oauth2.googleapis.com/tokeninfo",
                             params={"access_token": access_token})
            logger.info("[cookie_exchange] tokeninfo: HTTP %d, body=%s",
                        ti.status_code, ti.text[:500])
    except Exception as exc:
        logger.warning("[cookie_exchange] tokeninfo failed (non-fatal): %s", exc)

    # ── Approach A: Bearer token on NotebookLM directly ──
    # Test if Google sets session cookies when we access NotebookLM with a bearer token
    logger.info("[cookie_exchange] --- Approach A: Bearer token on notebooklm.google.com ---")
    try:
        jar_a = httpx.Cookies()
        async with httpx.AsyncClient(cookies=jar_a, follow_redirects=True,
                                     timeout=httpx.Timeout(30.0)) as c:
            resp_a = await c.get(
                "https://notebooklm.google.com/",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            has_snlm0e = "SNlM0e" in resp_a.text
            logger.info(
                "[cookie_exchange] A result: HTTP %d, final_url=%s, has_SNlM0e=%s, body_len=%d, body_preview=%s",
                resp_a.status_code, str(resp_a.url)[:200], has_snlm0e,
                len(resp_a.text), resp_a.text[:300].replace('\n', ' '),
            )
            _log_jar("A cookies", jar_a)
            if resp_a.history:
                logger.info("[cookie_exchange] A redirects: %s",
                            [f"{r.status_code}→{str(r.url)[:100]}" for r in resp_a.history])

            # Check Set-Cookie headers from ALL responses in the chain
            all_set_cookies = []
            for r in [*resp_a.history, resp_a]:
                sc = r.headers.get_list("set-cookie")
                if sc:
                    all_set_cookies.extend(sc)
            if all_set_cookies:
                logger.info("[cookie_exchange] A set-cookie headers (%d): %s",
                            len(all_set_cookies),
                            [s[:80] for s in all_set_cookies[:10]])

            # If we got SID cookie from this approach, use it!
            storage_a = _build_storage_state_from_jar(jar_a)
            cookie_names_a = {c["name"] for c in storage_a["cookies"]}
            if "SID" in cookie_names_a and has_snlm0e:
                logger.info("[cookie_exchange] Approach A WORKED! SID + SNlM0e present")
                return storage_a
    except Exception as exc:
        logger.warning("[cookie_exchange] Approach A failed: %s", exc)

    # ── Approach B: Bearer token on accounts.google.com ──
    # See if Google's account page sets cookies when given a bearer token
    logger.info("[cookie_exchange] --- Approach B: Bearer token on accounts.google.com ---")
    try:
        jar_b = httpx.Cookies()
        async with httpx.AsyncClient(cookies=jar_b, follow_redirects=True,
                                     timeout=httpx.Timeout(30.0)) as c:
            resp_b = await c.get(
                "https://accounts.google.com/",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            logger.info(
                "[cookie_exchange] B result: HTTP %d, final_url=%s, body_len=%d",
                resp_b.status_code, str(resp_b.url)[:200], len(resp_b.text),
            )
            _log_jar("B cookies", jar_b)
    except Exception as exc:
        logger.warning("[cookie_exchange] Approach B failed: %s", exc)

    # ── Approach C: OAuthLogin without ChromiumBrowser source ──
    # Try OAuthLogin with different/no source parameter
    logger.info("[cookie_exchange] --- Approach C: OAuthLogin (no source) ---")
    try:
        jar_c = httpx.Cookies()
        async with httpx.AsyncClient(cookies=jar_c, follow_redirects=True,
                                     timeout=httpx.Timeout(30.0)) as c:
            resp_c = await c.get(
                "https://accounts.google.com/OAuthLogin",
                params={"issueuberauth": "1"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            logger.info(
                "[cookie_exchange] C result: HTTP %d, body=%s",
                resp_c.status_code, resp_c.text[:300],
            )
            _log_jar("C cookies", jar_c)
    except Exception as exc:
        logger.warning("[cookie_exchange] Approach C failed: %s", exc)

    # ── Approach D: OAuthLogin with source=ChromiumBrowser (original) ──
    logger.info("[cookie_exchange] --- Approach D: OAuthLogin (ChromiumBrowser source) ---")
    try:
        jar_d = httpx.Cookies()
        async with httpx.AsyncClient(cookies=jar_d, follow_redirects=True,
                                     timeout=httpx.Timeout(30.0)) as c:
            resp_d = await c.get(
                "https://accounts.google.com/OAuthLogin",
                params={"source": "ChromiumBrowser", "issueuberauth": "1"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            uberauth = resp_d.text.strip()
            logger.info(
                "[cookie_exchange] D result: HTTP %d, body_len=%d, body=%s",
                resp_d.status_code, len(uberauth), uberauth[:200],
            )
            _log_jar("D cookies", jar_d)

            # If D succeeded (HTTP 200 + valid uberauth), try MergeSession
            if resp_d.status_code == 200 and len(uberauth) > 10 and "Error" not in uberauth:
                logger.info("[cookie_exchange] D got uberauth, trying MergeSession...")
                merge_resp = await c.get(
                    "https://accounts.google.com/MergeSession",
                    params={
                        "uberauth": uberauth,
                        "continue": "https://notebooklm.google.com",
                        "source": "ChromiumBrowser",
                    },
                )
                logger.info("[cookie_exchange] D MergeSession: HTTP %d, final_url=%s",
                            merge_resp.status_code, str(merge_resp.url)[:200])
                _log_jar("D after MergeSession", jar_d)

                storage_d = _build_storage_state_from_jar(jar_d)
                cookie_names_d = {c["name"] for c in storage_d["cookies"]}
                if "SID" in cookie_names_d:
                    logger.info("[cookie_exchange] Approach D WORKED!")
                    return storage_d
    except Exception as exc:
        logger.warning("[cookie_exchange] Approach D failed: %s", exc)

    # ── Approach E: Google's programmatic_auth endpoint ──
    logger.info("[cookie_exchange] --- Approach E: programmatic_auth ---")
    try:
        jar_e = httpx.Cookies()
        async with httpx.AsyncClient(cookies=jar_e, follow_redirects=True,
                                     timeout=httpx.Timeout(30.0)) as c:
            resp_e = await c.get(
                "https://accounts.google.com/o/oauth2/programmatic_auth",
                params={"access_token": access_token},
            )
            logger.info(
                "[cookie_exchange] E result: HTTP %d, final_url=%s, body_len=%d",
                resp_e.status_code, str(resp_e.url)[:200], len(resp_e.text),
            )
            _log_jar("E cookies", jar_e)

            storage_e = _build_storage_state_from_jar(jar_e)
            cookie_names_e = {c["name"] for c in storage_e["cookies"]}
            if "SID" in cookie_names_e:
                logger.info("[cookie_exchange] Approach E WORKED!")
                return storage_e
    except Exception as exc:
        logger.warning("[cookie_exchange] Approach E failed: %s", exc)

    # ── All approaches failed ──
    logger.error("[cookie_exchange] === ALL APPROACHES FAILED ===")
    raise RuntimeError(
        "All cookie exchange approaches failed. "
        "Google blocks third-party OAuthLogin scope. "
        "Check Cloud Run logs for [cookie_exchange] details."
    )
