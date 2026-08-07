from fastapi import Request


def client_ip(request: Request) -> str | None:
    """The real client IP behind our nginx.

    nginx sets `X-Real-IP` from `$remote_addr` (the actual TCP peer), which a
    client can't spoof — unlike the first entry of `X-Forwarded-For`. In dev
    (no proxy) the header is absent, so fall back to the socket peer.
    """
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else None
