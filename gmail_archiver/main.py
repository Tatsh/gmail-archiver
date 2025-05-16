"""Main script."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast
import imaplib
import json
import logging

from platformdirs import user_cache_path, user_config_path
import click
import tomlkit

from .typing import AuthDataDB, Config, assert_not_none
from .utils import authorize_tokens, generate_oauth_token, process, refresh_token, setup_logging

__all__ = ('main',)

log = logging.getLogger(__name__)


@click.command(context_settings={'help_option_names': ('-h', '--help')})
@click.argument('email')
@click.argument('out_dir',
                type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
                required=False)
@click.option('-a', '--auth-only', help='Only authorise the user.', is_flag=True)
@click.option('-d', '--debug', help='Enable debug level logging.', is_flag=True)
@click.option('-r', '--force-refresh', help='Force refresh the token.', is_flag=True)
def main(email: str,
         out_dir: Path | None = None,
         *,
         auth_only: bool = False,
         debug: bool = False,
         force_refresh: bool = False) -> None:
    """Archive Gmail emails and delete them from the server."""  # noqa: DOC501
    setup_logging(debug=debug)
    oauth_file = user_cache_path('gmail-archiver') / 'oauth.json'
    config_file = user_config_path('gmail-archiver') / 'config.toml'
    try:
        auth_data_db: AuthDataDB = json.loads(oauth_file.read_text(
            encoding='utf-8')) if oauth_file.exists() else {}
    except json.JSONDecodeError:
        auth_data_db = {}
    if email not in auth_data_db:
        click.echo(f'Email {email} not in auth_data_db.', err=True)
        raise click.Abort
    config: Config = cast('Config', tomlkit.loads(config_file.read_text()).unwrap())
    if 'client_id' not in config or 'client_secret' not in config:
        click.echo('client_id and client_secret must be set in the config file.', err=True)
        raise click.Abort
    out_dir = out_dir or Path() / email
    if (not auth_data_db or email not in auth_data_db or 'refresh_token' not in auth_data_db[email]
            or 'expiration_time' not in auth_data_db[email]):
        if not auth_data_db:
            log.debug('Empty authorisation database.')
            auth_data_db = {}
        auth_data = authorize_tokens(config['client_id'], config['client_secret'],
                                     generate_oauth_token())
        auth_data['expiration_time'] = (datetime.now(tz=timezone.utc) + timedelta(
            seconds=assert_not_none(auth_data.get('expires_in'), 'expires_in value cannot be None'))
                                        ).isoformat()
        log.debug('New auth data for %s: %s', email, auth_data)
        auth_data_db[email] = auth_data
        assert 'refresh_token' in auth_data_db[email], 'refresh_token not in auth_data_db[email]'
        oauth_file.write_text(json.dumps(auth_data_db, allow_nan=False, sort_keys=True, indent=2))
    elif (datetime.fromisoformat(
            assert_not_none(auth_data_db[email].get('expiration_time'),
                            'expiration_time cannot be None')) <= datetime.now(timezone.utc)
          or force_refresh):
        log.debug('Refreshing token.')
        ref_token: str = assert_not_none(auth_data_db[email].get('refresh_token'),
                                         'refresh_token cannot be None')
        auth_data = refresh_token(config['client_id'], config['client_secret'], ref_token)
        auth_data['expiration_time'] = (
            datetime.now(timezone.utc) +
            timedelta(seconds=assert_not_none(auth_data.get('expires_in')))).isoformat()
        auth_data_db[email] = auth_data
        log.debug('New auth data for %s: %s', email, auth_data)
        auth_data_db[email]['refresh_token'] = ref_token
        oauth_file.write_text(json.dumps(auth_data_db, allow_nan=False, sort_keys=True, indent=2))
    log.info('Logging in.')
    if auth_only:
        return
    imap_conn = imaplib.IMAP4_SSL('imap.gmail.com')
    try:
        ret = process(imap_conn, email, auth_data_db, out_dir, debug=debug)
    finally:
        log.debug('Closing.')
        try:
            imap_conn.close()
        except imaplib.IMAP4.error:
            log.exception('Exception caught while closing.')
        log.debug('Logging out')
        imap_conn.logout()
    if ret != 0:
        raise click.exceptions.Exit(ret)
