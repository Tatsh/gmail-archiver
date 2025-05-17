"""Utilities."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from email.utils import parsedate_tz
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
import http
import http.server
import json
import logging
import logging.config
import socket
import urllib
import urllib.parse

import requests

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
            },
            'simple': {
                'format': '%(levelname)s: %(message)s',
            }
        },
        'handlers': {
            'console': {
                'class': 'colorlog.StreamHandler',
                'formatter': 'default' if debug else 'simple',
            }
        },
        'loggers': {
            'gmail_archiver': {
                'level': 'INFO' if not debug else 'DEBUG',
                'handlers': ['console'],
                'propagate': False,
            },
            'urllib3': {
                'level': 'WARNING' if not debug else 'DEBUG',
                'handlers': ['console'],
                'propagate': False,
            },
        },
        'version': 1
    })


@cache
def generate_oauth2_str(username: str, access_token: str) -> str:
    """Generate the OAuth2 string for IMAP authentication."""
    return f'user={username}\1auth=Bearer {access_token}\1\1'


def authorize_tokens(url: str,
                     client_id: str,
                     client_secret: str,
                     authorization_code: str,
                     verifier: str,
                     redirect_uri: str,
                     scope: str = 'https://mail.google.com/') -> AuthInfo:
    """Exchange the authorisation code for an access token."""
    response = requests.post(url,
                             params={
                                 'client_id': client_id,
                                 'client_secret': client_secret,
                                 'code': authorization_code,
                                 'code_verifier': verifier,
                                 'grant_type': 'authorization_code',
                                 'redirect_uri': redirect_uri,
                                 'scope': scope
                             },
                             timeout=15)
    response.raise_for_status()
    return cast('AuthInfo', response.json())


def refresh_token(url: str, client_id: str, client_secret: str, refresh_token: str) -> AuthInfo:
    """Refresh the access token using the refresh token."""
    response = requests.post(url,
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
    """Download emails and optionally move them to the trash."""
    if debug:
        imap_conn.debug = 4
    log.info('Deleting emails: %s', delete)
    auth_str = generate_oauth2_str(email, access_token)
    imap_conn.authenticate('XOAUTH2', lambda _: auth_str.encode())
    imap_conn.select(dq('[Gmail]/All Mail'))
    before_date = (datetime.now(tz=timezone.utc).date() - timedelta(days=90)).strftime('%d-%b-%Y')
    log.debug('Searching for emails before %s.', before_date)
    rv, result = cast('Callable[[str | None, str], tuple[str, list[bytes]]]',
                      imap_conn.search)(None, f'(BEFORE {dq(before_date)})')
    if rv != 'OK' or not result:
        log.info('No messages matched criteria.')
        return 0
    messages = result[0].decode().split()
    log.info('Archiving %d messages.', len(messages))
    for num in result[0].decode().split():
        rv, data = imap_conn.fetch(num, '(RFC822)')
        if rv != 'OK':
            log.error('Error getting message #%s.', num)
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
        log.debug('Writing %s to %s.', num, out_path)
        out_path.write_bytes(v[1] + b'\n')
        if labels:
            (path / labels_filename).write_text(json.dumps(labels, indent=2, sort_keys=True))
        if delete:
            imap_conn.store(num, '+X-GM-LABELS', '\\Trash')
    return 0


def log_oauth2_error(data: dict[str, Any]) -> None:
    """Log OAuth2 error information."""
    if 'error' in data:
        log.error('Error type: %s', data['error'])
        if 'error_description' in data:
            log.error('Description: %s', data['error_description'])


class OAuth2Error(Exception):
    """OAuth2 error."""


class GoogleOAuthClient:
    """Uses discovery to get the appropriate endpoint URIs."""
    def __init__(self, client_id: str, client_secret: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.session = requests.Session()
        r = self.session.get('https://accounts.google.com/.well-known/openid-configuration')
        r.raise_for_status()
        data = r.json()
        self.token_endpoint = data['token_endpoint']
        self.device_authorization_endpoint = data['device_authorization_endpoint']
        self.authorization_endpoint = data['authorization_endpoint']


def get_localhost_redirect_uri() -> tuple[int, str]:
    """Find an available port and return a localhost URI."""
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    listen_port = s.getsockname()[1]
    assert isinstance(listen_port, int), 'listen_port is not an int.'
    s.close()
    return listen_port, f'http://localhost:{listen_port}/'


def get_auth_http_handler(
        auth_code_callback: Callable[[str], None]) -> type[http.server.BaseHTTPRequestHandler]:
    """Get a handler for the HTTP server."""
    class MyHandler(http.server.BaseHTTPRequestHandler):
        def do_HEAD(self) -> None:  # noqa: N802
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            querydict = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if 'code' in querydict:  # pragma: no cover
                auth_code_callback(querydict['code'][0])
            self.do_HEAD()
            self.wfile.write(b'<html><head><title>Authorisation result</title></head>'
                             b'<body><p>Authorisation redirect completed. You may '
                             b'close this window.</p></body></html>')

    return MyHandler
