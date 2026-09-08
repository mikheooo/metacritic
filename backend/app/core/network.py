"""Network utilities including dual-stack / IPv6 preference for outbound connections."""

import logging
import socket
from typing import Any

logger = logging.getLogger(__name__)

_gai_patched = False


def setup_ipv6_preference() -> None:
    """Ensure socket.getaddrinfo returns IPv6 addresses before IPv4.

    This ensures environments with IPv6-only egress (such as GCP single-stack VMs)
    resolve dual-stack endpoints (e.g. OpenRouter, Cloudflare, YouTube) via IPv6 first,
    avoiding IPv4 connection timeouts.
    """
    global _gai_patched
    if _gai_patched:
        return

    orig_getaddrinfo = socket.getaddrinfo

    def ipv6_first_getaddrinfo(  # type: ignore[no-untyped-def]
        host: Any,
        port: Any,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> Any:
        res = orig_getaddrinfo(host, port, family, type, proto, flags)
        if family == 0:
            return sorted(res, key=lambda x: 0 if x[0] == socket.AF_INET6 else 1)
        return res

    socket.getaddrinfo = ipv6_first_getaddrinfo
    _gai_patched = True
