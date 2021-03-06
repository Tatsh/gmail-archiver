from datetime import date, datetime, timedelta
from email import message_from_bytes
from email.utils import parsedate_tz
from functools import lru_cache
from os import environ, makedirs
from os.path import basename, expanduser, join, realpath
from typing import Callable, Dict, Final, List, Optional, Tuple, TypeVar, cast
from typing import TypedDict
from urllib.parse import urlencode, urlunparse
import argparse
import imaplib
import json
import logging
import sys

import requests

CLIENT_ID: Final[str] = environ['CLIENT_ID']
CLIENT_SECRET: Final[str] = environ['CLIENT_SECRET']

GOOGLE_ACCOUNTS_DOMAIN: Final[str] = 'accounts.google.com'
GOOGLE_OAUTH2_DOMAIN: Final[str] = 'oauth2.googleapis.com'
REDIRECT_URI: Final[str] = 'urn:ietf:wg:oauth:2.0:oob'

OAUTH_FILE: Final[str] = expanduser('~/.cache/gmail-archiver-oauth.json')


class AuthInfo(TypedDict, total=False):
    access_token: str
    expiration_time: str
    expires_in: int
    refresh_token: str


AuthDataDB = Dict[str, AuthInfo]


@lru_cache()
def setup_logging_stderr(name: Optional[str] = None,
                         verbose: bool = False) -> logging.Logger:
    name = name if name else basename(sys.argv[0])
    log = logging.getLogger(name)
    log.setLevel(logging.DEBUG if verbose else logging.INFO)
    channel = logging.StreamHandler(sys.stderr)
    channel.setFormatter(logging.Formatter('%(message)s'))
    channel.setLevel(logging.DEBUG if verbose else logging.INFO)
    log.addHandler(channel)
    return log


@lru_cache()
def generate_oauth2_str(username: str, access_token: str) -> str:
    return f'user={username}\1auth=Bearer {access_token}\1\1'


@lru_cache()
def generate_permission_url(client_id: str,
                            scope: str = 'https://mail.google.com/') -> str:
    return urlunparse(
        ('https', GOOGLE_ACCOUNTS_DOMAIN, '/o/oauth2/v2/auth', '',
         urlencode(
             dict(
                 client_id=client_id,
                 redirect_uri=REDIRECT_URI,
                 scope=scope,
                 response_type='code',
             )), ''))


def generate_oauth_token() -> str:
    print(f'Go to this URL: {generate_permission_url(CLIENT_ID)}\n')
    return input('Enter verification code: ')


def authorize_tokens(client_id: str, client_secret: str,
                     authorization_code: str) -> AuthInfo:
    response = requests.post(urlunparse(
        ('https', GOOGLE_OAUTH2_DOMAIN, '/token', '', '', '')),
                             params=dict(client_id=client_id,
                                         client_secret=client_secret,
                                         code=authorization_code,
                                         redirect_uri=REDIRECT_URI,
                                         grant_type='authorization_code'))
    response.raise_for_status()
    return cast(AuthInfo, response.json())


def refresh_token(client_id: str, client_secret: str,
                  refresh_token: str) -> AuthInfo:
    response = requests.post(urlunparse(
        ('https', GOOGLE_OAUTH2_DOMAIN, '/token', '', '', '')),
                             params=dict(
                                 client_id=client_id,
                                 client_secret=client_secret,
                                 refresh_token=refresh_token,
                                 grant_type='refresh_token',
                             ))
    response.raise_for_status()
    return cast(AuthInfo, response.json())


@lru_cache()
def dq(s: str) -> str:
    return f'"{s}"'


T = TypeVar('T')


def assert_not_none(x: Optional[T], message: str = 'Expected value') -> T:
    assert x is not None, message
    return x


def process(imap_conn: imaplib.IMAP4_SSL, email: str, auth_data_db: AuthDataDB,
            log: logging.Logger, out_dir: str) -> int:
    # imap_conn.debug = 4
    auth_str = generate_oauth2_str(
        email,
        assert_not_none(auth_data_db[email].get('access_token'),
                        'access_token cannot be None'))
    imap_conn.authenticate('XOAUTH2', lambda _: auth_str.encode())
    imap_conn.select(dq('[Gmail]/All Mail'))
    before_date = (date.today() - timedelta(days=90)).strftime('%d-%b-%Y')
    rv, result = cast(Callable[[Optional[str], str], Tuple[str, List[bytes]]],
                      imap_conn.search)(None, f'(BEFORE {dq(before_date)})')
    if rv != 'OK':
        log.info('No messages matched criteria')
        return 0
    assert len(result) > 0, 'Search returned zero results'
    for num in result[0].decode().split():
        rv, data = imap_conn.fetch(num, '(RFC822)')
        if rv != 'OK':
            log.error(f'Error getting message #%d', num)
            return 1
        v = data[0]
        assert v is not None, 'Unexpected data[0] == None'
        assert isinstance(v, tuple), 'Unexpected non-tuple type of v'
        msg = message_from_bytes(v[1])
        date_tuple = parsedate_tz(cast(str, msg['Date']))
        if not date_tuple:
            log.error('Error converting date: %s', msg['Date'])
            return 1
        the_date = datetime(*cast(Tuple[int, int, int, int, int,
                                        int], date_tuple[0:7]))
        month = the_date.strftime('%m-%b')
        day = the_date.strftime('%d-%a')
        path = f'{realpath(out_dir)}/{email}/{date_tuple[0]}/{month}/{day}'
        try:
            makedirs(path)
        except FileExistsError:
            pass
        number = int(num)
        eml_filename = f'{number:010d}.eml'
        rv, labels_raw = imap_conn.fetch(num, '(X-GM-LABELS)')
        labels = None
        labels_filename = f'{number:010d}.labels.json'
        if rv == 'OK' and labels_raw:
            labels = [x.decode() for x in cast(List[bytes], labels_raw)]
        out_path = join(path, eml_filename)
        log.debug('Writing %s to %s', num, out_path)
        with open(out_path, 'wb+') as g:
            g.write(v[1])
            g.write(b'\n')
        if labels:
            with open(join(path, labels_filename), 'w+') as f:
                json.dump(labels, f)
                f.write('\n')
        imap_conn.store(num, '+X-GM-LABELS', '\\Trash')
    return 0


class Namespace(argparse.Namespace):
    email: str
    out_dir: str


def main() -> int:
    auth_data_db: Optional[AuthDataDB] = None
    parser = argparse.ArgumentParser()
    parser.add_argument('email')
    parser.add_argument('out_dir')
    parser.add_argument('-a', '--auth-only', action='store_true')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-r', '--force-refresh', action='store_true')
    args = cast(Namespace, parser.parse_args())
    log = setup_logging_stderr(verbose=args.verbose)
    email = args.email
    try:
        with open(OAUTH_FILE, 'r') as f:
            auth_data_db = json.load(f)
    except (FileNotFoundError, json.decoder.JSONDecodeError):
        pass
    if (not auth_data_db or email not in auth_data_db
            or 'refresh_token' not in auth_data_db[email]
            or 'expiration_time' not in auth_data_db[email]):
        if not auth_data_db:
            log.debug('Empty authorisation database')
            auth_data_db = {}
        auth_data = authorize_tokens(CLIENT_ID, CLIENT_SECRET,
                                     generate_oauth_token())
        auth_data['expiration_time'] = (datetime.now() + timedelta(
            seconds=assert_not_none(auth_data.get('expires_in'),
                                    'expires_in value cannot be None'))
                                        ).isoformat()
        log.debug('New auth data for %s: %s', email, auth_data)
        auth_data_db[email] = auth_data
        assert (
            'refresh_token'
            in auth_data_db[email]), 'refresh_token not in auth_data_db[email]'
        with open(OAUTH_FILE, 'w+') as f:
            json.dump(auth_data_db,
                      f,
                      allow_nan=False,
                      sort_keys=True,
                      indent=2)
            f.write('\n')
    elif (datetime.fromisoformat(
            assert_not_none(auth_data_db[email].get('expiration_time'),
                            'expiration_time cannot be None')) <=
          datetime.now() or args.force_refresh):
        log.debug('Refreshing token')
        ref_token = assert_not_none(auth_data_db[email].get('refresh_token'),
                                    'refresh_token cannot be None')
        auth_data = refresh_token(CLIENT_ID, CLIENT_SECRET, ref_token)
        auth_data['expiration_time'] = (datetime.now() + timedelta(
            seconds=assert_not_none(auth_data.get('expires_in')))).isoformat()
        auth_data_db[email] = auth_data
        log.debug('New auth data for %s: %s', email, auth_data)
        auth_data_db[email]['refresh_token'] = ref_token
        with open(OAUTH_FILE, 'w+') as f:
            json.dump(auth_data_db,
                      f,
                      allow_nan=False,
                      sort_keys=True,
                      indent=2)
            f.write('\n')
    assert auth_data_db is not None, 'auth_data_db is None'
    assert email in auth_data_db, 'This email is not in auth_data_db'
    log.info('Logging in')
    imap_conn = imaplib.IMAP4_SSL('imap.gmail.com')
    try:
        if not args.auth_only:
            process(imap_conn, email, auth_data_db, log, args.out_dir)
    finally:
        log.debug('Closing')
        try:
            imap_conn.close()
        except imaplib.IMAP4.error as e:
            log.error(e)
        log.debug('Logging out')
        imap_conn.logout()
    return 0


if __name__ == '__main__':
    sys.exit(main())
