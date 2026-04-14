"""Utilities."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from email.utils import parsedate_tz
from functools import cache
from hashlib import sha1
from typing import TYPE_CHECKING, Any, cast
import asyncio
import http.server
import json
import logging
import socket
import urllib.parse

from anyio import Path as AsyncPath
import niquests

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    import aioimaplib  # type: ignore[import-untyped]

    from .typing import AuthInfo


@asynccontextmanager
async def _imap_debug_session(*, debug: bool) -> AsyncIterator[None]:  # noqa: RUF029
    aioimaplib_logger = logging.getLogger('aioimaplib.aioimaplib')
    if not debug:
        yield
        return
    previous = aioimaplib_logger.level
    aioimaplib_logger.setLevel(logging.DEBUG)
    try:
        yield
    finally:
        aioimaplib_logger.setLevel(previous)


__all__ = ('GoogleOAuthClient', 'archive_emails', 'authorize_tokens', 'get_auth_http_handler',
           'get_localhost_redirect_uri', 'refresh_token')

log = logging.getLogger(__name__)

_FETCH_MIN_LINES = 2
_LISTEN_PORT_TYPE_ERROR = 'Expected an integer listen port from the bound socket.'


@cache
def generate_oauth2_str(username: str, access_token: str) -> str:
    """
    Generate the OAuth2 string for IMAP authentication.

    Parameters
    ----------
    username : str
        The account user name.
    access_token : str
        The OAuth2 access token.

    Returns
    -------
    str
        The encoded string for IMAP XOAUTH2 authentication.
    """
    return f'user={username}\1auth=Bearer {access_token}\1\1'


async def authorize_tokens(url: str,
                           client_id: str,
                           client_secret: str,
                           authorization_code: str,
                           verifier: str,
                           redirect_uri: str,
                           scope: str = 'https://mail.google.com/') -> AuthInfo:
    """
    Exchange the authorisation code for an access token.

    Parameters
    ----------
    url : str
        The token endpoint URL.
    client_id : str
        The OAuth client identifier.
    client_secret : str
        The OAuth client secret.
    authorization_code : str
        The authorisation code from the redirect.
    verifier : str
        The PKCE code verifier.
    redirect_uri : str
        The redirect URI used in the authorisation request.
    scope : str
        The requested OAuth scope.

    Returns
    -------
    AuthInfo
        Token response fields from the authorisation server.
    """
    async with niquests.AsyncSession() as session:
        response = await session.post(url,
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


async def refresh_token(url: str, client_id: str, client_secret: str,
                        refresh_token: str) -> AuthInfo:
    """
    Refresh the access token using the refresh token.

    Parameters
    ----------
    url : str
        The token endpoint URL.
    client_id : str
        The OAuth client identifier.
    client_secret : str
        The OAuth client secret.
    refresh_token : str
        The refresh token.

    Returns
    -------
    AuthInfo
        Token response fields from the authorisation server.
    """
    async with niquests.AsyncSession() as session:
        response = await session.post(url,
                                      params={
                                          'client_id': client_id,
                                          'client_secret': client_secret,
                                          'grant_type': 'refresh_token',
                                          'refresh_token': refresh_token,
                                      },
                                      timeout=15)
    response.raise_for_status()
    return cast('AuthInfo', response.json())


@cache
def dq(s: str) -> str:
    """
    Quote a string for use in an IMAP search.

    Parameters
    ----------
    s : str
        The string to quote.

    Returns
    -------
    str
        The string wrapped in double quotes for IMAP.
    """
    return f'"{s}"'


async def archive_emails(imap_conn: aioimaplib.IMAP4_SSL,
                         email: str,
                         access_token: str,
                         out_dir: AsyncPath,
                         days: int = 90,
                         *,
                         debug: bool = False,
                         delete: bool = False) -> int:
    """
    Download emails and optionally move them to the trash.

    Parameters
    ----------
    imap_conn : aioimaplib.IMAP4_SSL
        The authenticated IMAP connection.
    email : str
        The mailbox account label used in output paths.
    access_token : str
        The OAuth2 access token for authentication.
    out_dir : AsyncPath
        The root directory for archived messages.
    days : int
        Archive messages older than this many days.
    debug : bool
        When True, enable verbose IMAP protocol logging.
    delete : bool
        When True, move archived messages to trash.

    Returns
    -------
    int
        ``0`` on success, ``1`` if an error occurred while processing messages.
    """
    async with _imap_debug_session(debug=debug):
        log.info('Deleting emails: %s', delete)
        await imap_conn.xoauth2(email, access_token.encode())
        await imap_conn.select(dq('[Gmail]/All Mail'))
        before_date = (datetime.now(tz=timezone.utc).date() -
                       timedelta(days=days)).strftime('%d-%b-%Y')
        log.debug('Searching for emails before %s.', before_date)
        response = await imap_conn.search(f'BEFORE {dq(before_date)}')
        match response.result:
            case 'OK' if response.lines and response.lines[0]:
                messages = response.lines[0].decode().split()
                if not messages:
                    log.info('No messages matched criteria.')
                    return 0
            case _:
                log.info('No messages matched criteria.')
                return 0
        log.info('Archiving %d messages.', len(messages))
        resolved = await AsyncPath(out_dir).resolve()
        for num in messages:
            fetch_response = await imap_conn.fetch(num, '(RFC822)')
            if fetch_response.result != 'OK':
                log.error('Error getting message #%s.', num)
                return 1
            if len(fetch_response.lines) < _FETCH_MIN_LINES:
                log.error('Unexpected empty message data for message #%s.', num)
                return 1
            raw_message = fetch_response.lines[1]
            if not isinstance(raw_message, (bytes, bytearray)):
                log.error('Unexpected message data type for message #%s.', num)
                return 1
            msg = message_from_bytes(bytes(raw_message))
            if not (date_tuple := parsedate_tz(cast('str', msg['Date']))):
                log.error('Error converting date: %s', msg['Date'])
                return 1
            the_date = datetime(*cast('tuple[int, int, int, int, int, int]', date_tuple[0:7]),
                                tzinfo=timezone.utc)
            month = the_date.strftime('%m-%b')
            day = the_date.strftime('%d-%a')
            path = resolved / email / str(date_tuple[0]) / month / day
            await path.mkdir(parents=True, exist_ok=True)
            number = int(num)
            eml_filename = f'{number:010d}.eml'
            labels_response = await imap_conn.fetch(num, '(X-GM-LABELS)')
            labels = None
            labels_filename = f'{number:010d}.labels.json'
            if labels_response.result == 'OK' and labels_response.lines:
                labels = [
                    x.decode() if isinstance(x, (bytes, bytearray)) else str(x)
                    for x in labels_response.lines
                ]
            out_path = path / eml_filename
            if await out_path.exists():
                sha = sha1(bytes(raw_message), usedforsecurity=False).hexdigest()[:7]
                out_path = path / f'{number:010d}-{sha}.eml'
            log.debug('Writing %s to %s.', num, out_path)
            write_tasks: list[Any] = [out_path.write_bytes(bytes(raw_message) + b'\n')]
            if labels:
                write_tasks.append((path / labels_filename).write_text(
                    json.dumps(labels, indent=2, sort_keys=True)))
            await asyncio.gather(*write_tasks)
            if delete:
                await imap_conn.store(num, '+X-GM-LABELS', '\\Trash')
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
        self.authorization_endpoint = ''
        """OAuth authorisation endpoint URL populated by :py:meth:`discover`."""
        self.client_id = client_id
        """OAuth client identifier."""
        self.client_secret = client_secret
        """OAuth client secret."""
        self.device_authorization_endpoint = ''
        """Device authorisation endpoint URL populated by :py:meth:`discover`."""
        self.token_endpoint = ''
        """Token endpoint URL populated by :py:meth:`discover`."""

    async def discover(self) -> None:
        """
        Fetch OpenID Connect discovery document and populate endpoints.

        Queries Google's well-known OpenID Connect configuration and sets
        :py:attr:`authorization_endpoint`, :py:attr:`device_authorization_endpoint`,
        and :py:attr:`token_endpoint`.
        """
        async with niquests.AsyncSession() as session:
            r = await session.get('https://accounts.google.com/.well-known/openid-configuration')
        r.raise_for_status()
        data = r.json()
        self.authorization_endpoint = data['authorization_endpoint']
        self.device_authorization_endpoint = data['device_authorization_endpoint']
        self.token_endpoint = data['token_endpoint']


def get_localhost_redirect_uri() -> tuple[int, str]:
    """
    Find an available port and return a localhost URI.

    Returns
    -------
    tuple[int, str]
        The listen port and ``http://localhost:{port}/`` redirect URI.

    Raises
    ------
    TypeError
        If the bound socket does not report an integer port.
    """
    s = socket.socket()
    try:
        s.bind(('127.0.0.1', 0))
        listen_port_raw = s.getsockname()[1]
        if not isinstance(listen_port_raw, int):
            raise TypeError(_LISTEN_PORT_TYPE_ERROR)
        listen_port = listen_port_raw
    finally:
        s.close()
    return listen_port, f'http://localhost:{listen_port}/'


def get_auth_http_handler(
        auth_code_callback: Callable[[str], None]) -> type[http.server.BaseHTTPRequestHandler]:
    """
    Build a request handler class for the local authorisation redirect server.

    Parameters
    ----------
    auth_code_callback : Callable[[str], None]
        Called with the authorisation code from the query string.

    Returns
    -------
    type[http.server.BaseHTTPRequestHandler]
        The handler class to pass to :py:class:`~http.server.HTTPServer`.
    """
    class MyHandler(http.server.BaseHTTPRequestHandler):
        def do_HEAD(self) -> None:
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

        def do_GET(self) -> None:
            querydict = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if 'code' in querydict:  # pragma: no cover
                auth_code_callback(querydict['code'][0])
            self.do_HEAD()
            self.wfile.write(b'<html><head><title>Authorisation result</title></head>'
                             b'<body><p>Authorisation redirect completed. You may '
                             b'close this window.</p></body></html>')

    return MyHandler
