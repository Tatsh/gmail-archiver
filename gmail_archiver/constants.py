"""Constants."""
from __future__ import annotations

from pathlib import Path

GOOGLE_ACCOUNTS_DOMAIN = 'accounts.google.com'
"""
Google accounts domain.

:meta hide-value:
"""
GOOGLE_OAUTH2_DOMAIN = 'oauth2.googleapis.com'
"""
Google OAuth domain.

:meta hide-value:
"""
REDIRECT_URI = 'urn:ietf:wg:oauth:2.0:oob'
"""
Redirect URI for OAuth.

:meta hide-value:
"""

OAUTH_FILE = Path('~/.cache/gmail-archiver-oauth.json').expanduser()
"""
Path to the OAuth credentials file.

:meta hide-value:
"""
