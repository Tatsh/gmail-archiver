"""Utilities."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from email.utils import parsedate_tz
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.parse import urlencode, urlunparse
import json
import logging
import logging.config

import requests

from .constants import GOOGLE_ACCOUNTS_DOMAIN, GOOGLE_OAUTH2_DOMAIN, REDIRECT_URI

if TYPE_CHECKING:
    from collections.abc import Callable
    import imaplib

    from .typing import AuthInfo

log = logging.getLogger(__name__)


def setup_logging(*,
                  debug: bool = False,
                  force_color: bool = False,
                  no_color: bool = False) -> None:  # pragma: no cover
    """Set up logging configuration."""
    logging.config.dictConfig({
        'disable_existing_loggers': True,
        'root': {
            'level': 'DEBUG' if debug else 'INFO',
            'handlers': ['console'],
        },
        'formatters': {
            'default': {
                '()': 'colorlog.ColoredFormatter',
                'force_color': force_color,
                'format': (
                    '%(light_cyan)s%(asctime)s%(reset)s | %(log_color)s%(levelname)-8s%(reset)s | '
                    '%(light_green)s%(name)s%(reset)s:%(light_red)s%(funcName)s%(reset)s:'
                    '%(blue)s%(lineno)d%(reset)s - %(message)s'),
                'no_color': no_color,
            }
        },
        'handlers': {
            'console': {
                'class': 'colorlog.StreamHandler',
                'formatter': 'default',
            }
        },
        'version': 1
    })


@cache
def generate_oauth2_str(username: str, access_token: str) -> str:
    """Generate the OAuth2 string for IMAP authentication."""
    return f'user={username}\1auth=Bearer {access_token}\1\1'


@cache
def generate_permission_url(client_id: str, scope: str = 'https://mail.google.com/') -> str:
    """Generate the URL for the OAuth2 permission request."""
    return urlunparse(('https', GOOGLE_ACCOUNTS_DOMAIN, '/o/oauth2/v2/auth', '',
                       urlencode({
                           'client_id': client_id,
                           'redirect_uri': REDIRECT_URI,
                           'scope': scope,
                           'response_type': 'code',
                       }), ''))


def generate_oauth_token() -> str:  # pragma: no cover
    """Generate an OAuth token."""
    return input('Enter verification code: ')


def authorize_tokens(client_id: str, client_secret: str, authorization_code: str) -> AuthInfo:
    """Exchange the authorization code for an access token."""
    response = requests.post(urlunparse(('https', GOOGLE_OAUTH2_DOMAIN, '/token', '', '', '')),
                             params={
                                 'client_id': client_id,
                                 'client_secret': client_secret,
                                 'code': authorization_code,
                                 'redirect_uri': REDIRECT_URI,
                                 'grant_type': 'authorization_code'
                             },
                             timeout=15)
    response.raise_for_status()
    return cast('AuthInfo', response.json())


def refresh_token(client_id: str, client_secret: str, refresh_token: str) -> AuthInfo:
    """Refresh the access token using the refresh token."""
    response = requests.post(urlunparse(('https', GOOGLE_OAUTH2_DOMAIN, '/token', '', '', '')),
                             params={
                                 'client_id': client_id,
                                 'client_secret': client_secret,
                                 'refresh_token': refresh_token,
                                 'grant_type': 'refresh_token',
                             },
                             timeout=15)
    response.raise_for_status()
    return cast('AuthInfo', response.json())


@cache
def dq(s: str) -> str:
    """Quote a string for use in an IMAP search."""
    return f'"{s}"'


def archive_emails(imap_conn: imaplib.IMAP4_SSL,
                   email: str,
                   access_token: str,
                   out_dir: Path,
                   *,
                   debug: bool = False,
                   delete: bool = False) -> int:
    """Download emails then delete them on the server."""
    if debug:
        imap_conn.debug = 4
    auth_str = generate_oauth2_str(email, access_token)
    imap_conn.authenticate('XOAUTH2', lambda _: auth_str.encode())
    imap_conn.select(dq('[Gmail]/All Mail'))
    before_date = (datetime.now(tz=timezone.utc).date() - timedelta(days=90)).strftime('%d-%b-%Y')
    rv, result = cast('Callable[[str | None, str], tuple[str, list[bytes]]]',
                      imap_conn.search)(None, f'(BEFORE {dq(before_date)})')
    if rv != 'OK' or not result:
        log.info('No messages matched criteria.')
        return 0
    for num in result[0].decode().split():
        rv, data = imap_conn.fetch(num, '(RFC822)')
        if rv != 'OK':
            log.error('Error getting message #%d.', num)
            return 1
        v = data[0]
        assert v is not None, 'Unexpected data[0] == None'
        assert isinstance(v, tuple), 'Unexpected non-tuple type of v'
        msg = message_from_bytes(v[1])
        date_tuple = parsedate_tz(cast('str', msg['Date']))
        if not date_tuple:
            log.error('Error converting date: %s', msg['Date'])
            return 1
        the_date = datetime(*cast('tuple[int, int, int, int, int, int]', date_tuple[0:7]),
                            tzinfo=timezone.utc)
        month = the_date.strftime('%m-%b')
        day = the_date.strftime('%d-%a')
        path = Path(out_dir).resolve(strict=True) / email / str(date_tuple[0]) / month / day
        path.mkdir(parents=True, exist_ok=True)
        number = int(num)
        eml_filename = f'{number:010d}.eml'
        rv, labels_raw = imap_conn.fetch(num, '(X-GM-LABELS)')
        labels = None
        labels_filename = f'{number:010d}.labels.json'
        if rv == 'OK' and labels_raw:
            labels = [x.decode() for x in cast('list[bytes]', labels_raw)]
        out_path = path / eml_filename
        log.debug('Writing %s to %s', num, out_path)
        out_path.write_bytes(v[1] + b'\n')
        if labels:
            (path / labels_filename).write_text(json.dumps(labels, indent=2, sort_keys=True))
        if delete:
            imap_conn.store(num, '+X-GM-LABELS', '\\Trash')
    return 0
