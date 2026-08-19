"""Proxy capability: signed egress authorisation between agents (#1036)."""

from .grants import GrantError, issue_grant, issue_delegation, renew_grant, verify

__all__ = ["GrantError", "issue_grant", "issue_delegation", "renew_grant", "verify"]
