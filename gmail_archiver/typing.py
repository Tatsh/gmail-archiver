"""Typing helpers."""
from __future__ import annotations

from typing import TypedDict


class Config(TypedDict, total=False):
    """Configuration for the archiver."""
    client_id: str
    """Client ID for OAuth2."""
    client_secret: str
    """Client secret for OAuth2."""


class AuthInfo(TypedDict, total=False):
    """OAuth information."""
    access_token: str
    """Access token."""
    expiration_time: str
    """Expiration time of the access token."""
    expires_in: int
    """Time in seconds until the access token expires."""
    refresh_token: str
    """Refresh token."""


AuthDataDB = dict[str, AuthInfo]
"""Dictionary of OAuth information for different users."""
