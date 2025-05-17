"""Main script."""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, cast
import imaplib
import json
import logging

from platformdirs import user_cache_path, user_config_path
import click
import tomlkit

from .utils import (
    archive_emails,
    authorize_tokens,
    generate_oauth_token,
    refresh_token,
    setup_logging,
)

if TYPE_CHECKING:
    from .typing import Config

__all__ = ('main',)

log = logging.getLogger(__name__)


@click.command(context_settings={'help_option_names': ('-h', '--help')})
@click.argument('email')
@click.argument('out_dir',
                type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
                required=False)
@click.option('--no-delete', help='Do not move emails to trash.', is_flag=True)
@click.option('-a', '--auth-only', help='Only authorise the user.', is_flag=True)
@click.option('-d', '--debug', help='Enable debug level logging.', is_flag=True)
@click.option('-r', '--force-refresh', help='Force refresh the token.', is_flag=True)
def main(email: str,
         out_dir: Path | None = None,
         *,
         auth_only: bool = False,
         debug: bool = False,
         force_refresh: bool = False,
         no_delete: bool = False) -> None:
    """Archive Gmail emails and delete them from the server."""  # noqa: DOC501
    setup_logging(debug=debug)
    oauth_file = user_cache_path('gmail-archiver') / 'oauth.json'
    config_file = user_config_path('gmail-archiver') / 'config.toml'
    try:
        auth_data_db = json.loads(oauth_file.read_text(
            encoding='utf-8')) if oauth_file.exists() else {}
    except json.JSONDecodeError:
        auth_data_db = {}
    config: Config = {}
    if config_file.exists():
        config = cast('Config', tomlkit.loads(config_file.read_text()).unwrap())
    if 'client_id' not in config or 'client_secret' not in config:
        click.echo('client_id and client_secret must be set in the config file.', err=True)
        raise click.Abort
    out_dir = out_dir or Path() / email
    expiration_time = (auth_data_db.get(email, {}).get('expiration_time')
                       if auth_data_db and isinstance(auth_data_db, Mapping) else None)
    if (not auth_data_db or not isinstance(auth_data_db, Mapping) or email not in auth_data_db
            or 'refresh_token' not in auth_data_db[email]
            or 'expiration_time' not in auth_data_db[email]):
        if not auth_data_db or not isinstance(auth_data_db, Mapping):
            log.debug('Empty authorisation database or is not a mapping.')
            auth_data_db = {}
        auth_data = authorize_tokens(config['client_id'], config['client_secret'],
                                     generate_oauth_token())
        expires_in = auth_data['expires_in']
        auth_data['expiration_time'] = (datetime.now(tz=timezone.utc) +
                                        timedelta(seconds=expires_in)).isoformat()
        log.debug('New auth data for %s: %s', email, auth_data)
        assert isinstance(auth_data_db, MutableMapping)
        auth_data_db[email] = auth_data
        assert 'refresh_token' in auth_data_db[email], 'refresh_token not in auth_data_db[email]'
        oauth_file.write_text(json.dumps(auth_data_db, allow_nan=False, sort_keys=True, indent=2))
    elif ((expiration_time and
           (datetime.fromisoformat(expiration_time) <= datetime.now(timezone.utc)))
          or force_refresh):
        log.debug('Refreshing token.')
        ref_token = auth_data_db[email]['refresh_token']
        auth_data = refresh_token(config['client_id'], config['client_secret'], ref_token)
        expires_in = auth_data['expires_in']
        auth_data['expiration_time'] = (datetime.now(timezone.utc) +
                                        timedelta(seconds=expires_in)).isoformat()
        assert isinstance(auth_data_db, MutableMapping)
        auth_data_db[email] = auth_data
        log.debug('New auth data for %s: %s', email, auth_data)
        auth_data_db[email]['refresh_token'] = ref_token
        oauth_file.write_text(json.dumps(auth_data_db, allow_nan=False, sort_keys=True, indent=2))
    log.info('Logging in.')
    if auth_only:
        return
    imap_conn = imaplib.IMAP4_SSL('imap.gmail.com')
    try:
        ret = archive_emails(imap_conn,
                             email,
                             auth_data_db[email]['access_token'],
                             out_dir,
                             debug=debug,
                             delete=not no_delete)
    finally:
        log.debug('Closing.')
        try:
            imap_conn.close()
        except imaplib.IMAP4.error:  # pragma: no cover
            log.exception('Exception caught while closing.')
        log.debug('Logging out')
        imap_conn.logout()
    if ret != 0:
        raise click.exceptions.Exit(ret)
