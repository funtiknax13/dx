"""Self-hosted Altcha (proof-of-work) captcha — no external service, no signup.

Flow (see https://altcha.org): the server issues a challenge = SHA-256(salt +
secret_number) plus an HMAC signature over that challenge. The browser widget
brute-forces `secret_number` (the proof of work) and posts back a solution. We
verify the solution reproduces the challenge AND that the challenge carries our
own signature (so it can't be forged), hasn't expired, and hasn't been reused.

Implemented with the stdlib — the algorithm is small and this avoids a runtime
dependency. The HMAC key is our shared secret (settings.altcha_hmac_key).
"""

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time

from app.core.config import settings

_ALGORITHM = "SHA-256"
_EXPIRY_SECONDS = 600

# Solved challenges already spent, so a single proof of work can't be replayed
# for multiple gated submissions within its lifetime. Single prod worker → a
# plain dict is fine; pruned lazily.
_used: dict[str, float] = {}


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _sign(challenge: str) -> str:
    return hmac.new(
        settings.altcha_hmac_key.encode(), challenge.encode(), hashlib.sha256
    ).hexdigest()


def create_challenge() -> dict[str, object]:
    """Build a fresh challenge for the widget to solve."""
    expires = int(time.time()) + _EXPIRY_SECONDS
    salt = f"{secrets.token_hex(12)}?expires={expires}"
    max_number = settings.altcha_max_number
    number = secrets.randbelow(max_number + 1)
    challenge = _sha256_hex(salt + str(number))
    return {
        "algorithm": _ALGORITHM,
        "challenge": challenge,
        "maxnumber": max_number,
        "salt": salt,
        "signature": _sign(challenge),
    }


def _salt_expires(salt: str) -> float | None:
    _, _, query = salt.partition("?expires=")
    if not query:
        return None
    try:
        return float(query.split("&")[0])
    except ValueError:
        return None


def _prune_used(now: float) -> None:
    for key, exp in list(_used.items()):
        if exp < now:
            del _used[key]


async def verify_captcha(token: str | None, ip: str | None = None) -> bool:
    """Verify an Altcha solution payload (base64 JSON produced by the widget).

    Returns True when captcha is disabled (no key configured) so dev/tests need
    no challenge. `ip` is accepted for a uniform call signature but unused here.
    """
    if not settings.captcha_enabled:
        return True
    if not token:
        return False
    try:
        data = json.loads(base64.b64decode(token))
    except (binascii.Error, ValueError, TypeError):
        return False
    if not isinstance(data, dict) or data.get("algorithm") != _ALGORITHM:
        return False

    salt = data.get("salt")
    number = data.get("number")
    challenge = data.get("challenge")
    signature = data.get("signature")
    if not (isinstance(salt, str) and isinstance(number, int) and isinstance(challenge, str)):
        return False
    if not isinstance(signature, str):
        return False

    now = time.time()
    expires = _salt_expires(salt)
    if expires is not None and now > expires:
        return False

    # The PoW actually solves this challenge...
    if not hmac.compare_digest(_sha256_hex(salt + str(number)), challenge):
        return False
    # ...and the challenge is one we issued (not attacker-forged).
    if not hmac.compare_digest(_sign(challenge), signature):
        return False

    _prune_used(now)
    if challenge in _used:  # replay
        return False
    _used[challenge] = expires if expires is not None else now + _EXPIRY_SECONDS
    return True


def clear_used() -> None:
    """Test helper — reset the replay store between cases."""
    _used.clear()
