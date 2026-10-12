"""Shared least-privilege capabilities; unknown roles/capabilities never grant access."""
from fastapi import HTTPException
from types import MappingProxyType

CAPABILITY_ROLES = MappingProxyType({
    "content.read": frozenset({"admin", "doctor", "labeler", "viewer"}),
    "content.write": frozenset({"admin", "doctor", "labeler"}),
    "project.manage": frozenset({"admin", "doctor"}),
    "project.delete": frozenset({"admin"}),
    "accounts.manage": frozenset({"admin"}),
    "server.manage": frozenset({"admin"}),
    "comparison.write": frozenset({"admin", "doctor"}),
})


def check_capability(role: str, capability: str) -> None:
    if role not in CAPABILITY_ROLES.get(capability, frozenset()):
        raise HTTPException(403, "This role cannot perform this action")
