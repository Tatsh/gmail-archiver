"""Typing helpers."""
from __future__ import annotations

from typing import TypedDict


class Config(TypedDict, total=False):
    """Configuration for the archiver."""
    client_id: str
    client_secret: str


class AuthInfo(TypedDict, total=False):
    """OAuth information."""
    access_token: str
    expiration_time: str
    expires_in: int
    refresh_token: str


AuthDataDB = dict[str, AuthInfo]
"""Dictionary of OAuth information for different users."""
