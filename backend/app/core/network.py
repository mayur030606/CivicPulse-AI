"""Client IP resolution and trusted-proxy parsing.

Forwarded headers are considered only when the direct peer is an explicitly
configured trusted proxy. This prevents clients from spoofing
``X-Forwarded-For`` to bypass rate limits or to forge the IP recorded on a
session.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable

from starlette.requests import Request

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


def parse_trusted_proxy_networks(value: str) -> tuple[IPNetwork, ...]:
    """Parse a comma-separated list of trusted proxy IPs/CIDR ranges."""
    networks: list[IPNetwork] = []
    for token in (value or "").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            networks.append(ipaddress.ip_network(token, strict=False))
        except ValueError as exc:
            raise ValueError(
                "RATE_LIMIT_TRUSTED_PROXIES must contain IP addresses or CIDR "
                f"ranges; invalid entry: {token!r}."
            ) from exc
    return tuple(networks)


def _parse_ip(value: str) -> IPAddress | None:
    value = (value or "").strip()
    if not value:
        return None

    # Accept bracketed IPv6 and optional ports in forwarded headers.
    if value.startswith("["):
        end = value.find("]")
        if end != -1:
            value = value[1:end]
    elif value.count(":") == 1:
        host, _, port = value.partition(":")
        if port.isdigit():
            value = host

    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _is_trusted(ip: IPAddress, networks: Iterable[IPNetwork]) -> bool:
    return any(ip in network for network in networks)


def resolve_client_ip(
    request: Request,
    trusted_proxies: str | Iterable[IPNetwork],
) -> str:
    """Return the best available client IP without trusting spoofed headers.

    The direct peer is used unless it is a configured trusted proxy. In that
    case ``X-Forwarded-For`` is walked from right to left (closest hop first),
    skipping trusted proxies, and the first untrusted address is returned.
    ``X-Real-IP`` is considered only when no usable forwarded chain exists.
    """

    peer = request.client.host if request.client else "unknown"
    networks = (
        parse_trusted_proxy_networks(trusted_proxies)
        if isinstance(trusted_proxies, str)
        else tuple(trusted_proxies)
    )

    peer_ip = _parse_ip(peer)
    if peer_ip is None or not _is_trusted(peer_ip, networks):
        return peer

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        chain = [
            parsed
            for part in forwarded.split(",")
            if (parsed := _parse_ip(part)) is not None
        ]
        for candidate in reversed(chain):
            if not _is_trusted(candidate, networks):
                return str(candidate)
        if chain:
            # Every hop is trusted; use the left-most address as the origin.
            return str(chain[0])

    real_ip = _parse_ip(request.headers.get("x-real-ip", ""))
    if real_ip is not None:
        return str(real_ip)

    return peer
