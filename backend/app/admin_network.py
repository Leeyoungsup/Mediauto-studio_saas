"""Restrict administrator pages and APIs using the ASGI client address, never headers."""
import ipaddress
import os
import posixpath
from urllib.parse import unquote
from starlette.responses import JSONResponse

DEFAULT_ADMIN_NETWORKS = "192.168.0.0/24,127.0.0.1/32,::1/128"


def administrator_path(path: str) -> bool:
    path = posixpath.normpath(unquote(path)).rstrip('/') or '/'
    if path in {"/api/users/me", "/api/users/me/preferences"}:
        return False
    return (path in {"/admin", "/admin.html", "/api/slides/open-local"}
            or path == "/api/admin" or path.startswith("/api/admin/")
            or path == "/api/users" or path.startswith("/api/users/"))


class AdminNetworkMiddleware:
    def __init__(self, app, allowed_networks: str | None = None):
        self.app = app
        value = os.environ.get("ADMIN_ALLOWED_NETWORKS", DEFAULT_ADMIN_NETWORKS) if allowed_networks is None else allowed_networks
        self.networks = tuple(ipaddress.ip_network(item.strip(), strict=False)
                              for item in value.split(',') if item.strip())
        if not self.networks or any(net.prefixlen == 0 for net in self.networks):
            raise ValueError("ADMIN_ALLOWED_NETWORKS requires explicit restricted CIDRs")

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not administrator_path(scope.get('path', '/')):
            return await self.app(scope, receive, send)
        try:
            peer = ipaddress.ip_address((scope.get('client') or ('', 0))[0])
            if isinstance(peer, ipaddress.IPv6Address) and peer.ipv4_mapped:
                peer = peer.ipv4_mapped
            allowed = any(peer.version == net.version and peer in net for net in self.networks)
        except ValueError:
            allowed = False
        if not allowed:
            return await JSONResponse({'detail': 'Administrator access is not allowed from this address'}, status_code=403)(scope, receive, send)
        await self.app(scope, receive, send)
