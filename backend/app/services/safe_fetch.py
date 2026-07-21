"""SSRF-safe download of a workout-export URL a runner pastes in (Suunto/Garmin/
Coros app export links), used as an alternative to uploading the file directly.

A URL from a runner is untrusted input — without safeguards it could be used to
reach an internal service (db, this api, another container) instead of a real
export link. So this: allows only https, resolves the hostname itself and
rejects private/loopback/link-local/reserved/multicast targets, does not follow
redirects, and caps the response body while streaming (a malicious server could
lie about or omit Content-Length).

DNS-rebinding note: checking a hostname's resolved IP and then handing the
hostname itself to the HTTP client would leave a gap — a second, attacker-timed
DNS lookup at connect time could return a different (private) address than the
one that was checked. `_PinnedResolutionBackend` closes that gap by resolving
exactly once and connecting to that literal address; TLS certificate/SNI
verification still targets the real hostname, since httpcore passes it
separately when starting TLS (see AnyIOBackend.connect_tcp vs start_tls).
"""

import ipaddress
import socket
from collections.abc import Iterable

import httpcore
import httpx

from app.core.config import settings

MAX_IMPORT_BYTES = settings.max_track_file_size_bytes
FETCH_TIMEOUT = httpx.Timeout(15.0, connect=10.0)


class FetchError(ValueError):
    """A workout URL couldn't be safely or successfully fetched."""


def _is_disallowed(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _resolve_safe_ip(host: str) -> str:
    """Resolve `host` and return one public address to connect to — used both
    for upfront validation and, pinned, for the actual connection, so nothing
    re-resolves the hostname a second time later (see module docstring)."""
    try:
        addrinfos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise FetchError("Could not resolve that link's host") from exc

    for *_, sockaddr in addrinfos:
        ip = ipaddress.ip_address(sockaddr[0])
        if not _is_disallowed(ip):
            return str(ip)
    raise FetchError("That link points to a disallowed address")


class _PinnedResolutionBackend(httpcore.AnyIOBackend):
    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        ip = _resolve_safe_ip(host)
        return await super().connect_tcp(
            ip, port, timeout=timeout, local_address=local_address, socket_options=socket_options
        )


class _PinnedResolutionTransport(httpx.AsyncHTTPTransport):
    """Same connection behavior as httpx.AsyncHTTPTransport, but resolution
    happens through _PinnedResolutionBackend instead of httpcore's default."""

    def __init__(self) -> None:
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(),
            network_backend=_PinnedResolutionBackend(),
            retries=0,
        )


def _validate_url(url: str) -> None:
    parsed = httpx.URL(url)
    if parsed.scheme != "https":
        raise FetchError("Link must start with https://")
    if not parsed.host:
        raise FetchError("Invalid link")
    _resolve_safe_ip(parsed.host)  # fail fast with a clear error before opening a connection


async def fetch_external_workout_file(url: str) -> tuple[bytes, str, str]:
    """Download a workout file from a URL the runner pasted in. Returns
    (content, content-type, content-disposition)."""
    _validate_url(url)

    async with httpx.AsyncClient(
        transport=_PinnedResolutionTransport(), follow_redirects=False, timeout=FETCH_TIMEOUT
    ) as client:
        try:
            async with client.stream("GET", url) as resp:
                if resp.is_redirect:
                    raise FetchError("That link redirects elsewhere, which isn't supported")
                if resp.status_code != 200:
                    raise FetchError(f"The link returned an error ({resp.status_code})")

                content_type = resp.headers.get("content-type", "")
                content_disposition = resp.headers.get("content-disposition", "")

                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > MAX_IMPORT_BYTES:
                        raise FetchError("File is too large")
                    chunks.append(chunk)
        except httpx.RequestError as exc:
            raise FetchError("Could not download the file from that link") from exc

    return b"".join(chunks), content_type, content_disposition


def detect_workout_format(
    content: bytes, content_type: str, content_disposition: str
) -> str | None:
    """Guess gpx/fit from the response headers, falling back to sniffing content."""
    ct = content_type.lower()
    cd = content_disposition.lower()

    if "gpx" in ct or ".gpx" in cd:
        return "gpx"
    if "fit" in ct or ".fit" in cd:
        return "fit"

    stripped = content.lstrip()[:200]
    if stripped.startswith(b"<?xml") or b"<gpx" in stripped:
        return "gpx"
    if len(content) > 12 and content[8:12] == b".FIT":
        return "fit"

    return None
