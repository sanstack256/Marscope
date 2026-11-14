"""
Shared TLS-Verified HTTP Client Factory
Ensures HTTPS verification uses Python's certifi CA bundle consistently across macOS/Linux.
"""

import ssl
from typing import Union
import httpx

try:
    import certifi
except ImportError:
    certifi = None


def get_verified_ssl_context() -> Union[ssl.SSLContext, bool]:
    """Return a default SSL context backed by certifi CA roots when installed."""
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return True


def create_async_http_client(timeout_seconds: float = 30.0) -> httpx.AsyncClient:
    """Create an httpx.AsyncClient configured with verified TLS certificates and redirects."""
    return httpx.AsyncClient(
        timeout=timeout_seconds,
        follow_redirects=True,
        verify=get_verified_ssl_context(),
    )
