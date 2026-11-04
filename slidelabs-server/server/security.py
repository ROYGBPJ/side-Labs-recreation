import ipaddress
import socket
from urllib.parse import urlparse


class UrlRejected(ValueError):
    """Raised with a user-safe message when a link is not acceptable."""


def validate_public_url(url, allow_private=False, host_allowlist=None) -> str:
    if not isinstance(url, str) or not url.strip() or len(url) > 2048:
        raise UrlRejected("Enter a valid link.")
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UrlRejected("Only http:// and https:// links are supported.")
    host = parsed.hostname.lower()
    if host_allowlist and "*" not in host_allowlist:
        if not any(host == h or host.endswith("." + h) for h in host_allowlist):
            raise UrlRejected("This tool only accepts links from: " + ", ".join(host_allowlist) + ".")
    if not allow_private:
        try:
            infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
        except socket.gaierror:
            raise UrlRejected("Could not resolve that link's host.")
        for info in infos:
            if not ipaddress.ip_address(info[4][0]).is_global:
                raise UrlRejected("Links to private or local network addresses are not allowed.")
    return parsed.geturl()
