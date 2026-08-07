import logging

import httpx

from app.core.config import settings

logger = logging.getLogger("app.captcha")

_VALIDATE_URL = "https://smartcaptcha.yandexcloud.net/validate"


async def verify_captcha(token: str | None, ip: str | None) -> bool:
    """Validate a Yandex SmartCaptcha token server-side.

    Returns True when captcha is disabled (no keys configured) so dev/tests
    never need a real challenge. On any transport/parse error we fail closed
    (return False) — a captcha outage should block, not silently wave traffic
    through. Callers only reach here once the adaptive gate has decided a
    challenge is warranted, so the blast radius of an outage is small.
    """
    if not settings.captcha_enabled:
        return True
    if not token:
        return False
    params = {"secret": settings.smartcaptcha_server_key, "token": token}
    if ip:
        params["ip"] = ip
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(_VALIDATE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        logger.exception("SmartCaptcha validation request failed")
        return False
    return bool(data.get("status") == "ok")
