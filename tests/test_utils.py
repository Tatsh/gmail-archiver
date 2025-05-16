from __future__ import annotations

from typing import TYPE_CHECKING

from gmail_archiver.constants import GOOGLE_OAUTH2_DOMAIN
from gmail_archiver.utils import (
    authorize_tokens,
    dq,
    generate_oauth2_str,
    generate_permission_url,
    process,
    refresh_token,
)
from requests import HTTPError
import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from gmail_archiver.typing import AuthDataDB
    from pytest_mock import MockerFixture
    from requests_mock import Mocker


def test_generate_oauth2_str_basic() -> None:
    username = 'testuser@gmail.com'
    access_token = 'ya29.a0AfH6SMBEXAMPLETOKEN'
    expected = f'user={username}\1auth=Bearer {access_token}\1\1'
    result = generate_oauth2_str(username, access_token)
    assert result == expected


def test_generate_permission_url_default_scope() -> None:
    client_id = 'test-client-id.apps.googleusercontent.com'
    url = generate_permission_url(client_id)
    assert 'client_id=test-client-id.apps.googleusercontent.com' in url
    assert 'scope=https%3A%2F%2Fmail.google.com' in url
    assert url.startswith('https://')
    assert '/o/oauth2/v2/auth' in url
    assert 'response_type=code' in url


def test_generate_permission_url_custom_scope() -> None:
    client_id = 'test-client-id.apps.googleusercontent.com'
    custom_scope = 'https://www.googleapis.com/auth/gmail.readonly'
    url = generate_permission_url(client_id, scope=custom_scope)
    assert 'scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fgmail.readonly' in url
    assert 'client_id=test-client-id.apps.googleusercontent.com' in url
    assert 'response_type=code' in url


def test_authorize_tokens_success(requests_mock: Mocker) -> None:
    # Arrange
    client_id = 'test-client-id'
    client_secret = 'test-client-secret'
    authorization_code = 'test-auth-code'
    expected_response = {
        'access_token': 'ya29.a0AfH6SMBEXAMPLETOKEN',
        'expires_in': 3599,
        'refresh_token': '1//0gEXAMPLEREFRESHTOKEN',
        'scope': 'https://mail.google.com/',
        'token_type': 'Bearer'
    }
    url = f'https://{GOOGLE_OAUTH2_DOMAIN}/token'
    requests_mock.post(url, json=expected_response, status_code=200)
    result = authorize_tokens(client_id, client_secret, authorization_code)
    assert result == expected_response


def test_authorize_tokens_http_error(requests_mock: Mocker) -> None:
    client_id = 'test-client-id'
    client_secret = 'test-client-secret'
    authorization_code = 'test-auth-code'
    url = f'https://{GOOGLE_OAUTH2_DOMAIN}/token'
    requests_mock.post(url, status_code=400, json={'error': 'invalid_grant'})
    with pytest.raises(HTTPError):
        authorize_tokens(client_id, client_secret, authorization_code)


def test_dq_quotes_simple_string() -> None:
    s = 'hello'
    result = dq(s)
    assert result == '"hello"'


def test_process_success(mocker: MockerFixture, tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    auth_data_db: AuthDataDB = {email: {'access_token': access_token}}
    out_dir = tmp_path
    imap_conn = mocker.Mock()
    imap_conn.debug = 0
    mocker.patch('gmail_archiver.utils.generate_oauth2_str', return_value='oauth_str')
    mocker.patch('gmail_archiver.utils.assert_not_none', side_effect=lambda v, _: v)
    # Simulate search returns two messages
    imap_conn.search.return_value = ('OK', [b'1 2'])
    imap_conn.select.return_value = ('OK', [b''])
    # Simulate fetch for RFC822 and X-GM-LABELS
    msg_bytes = b'From: test@example.com\r\nDate: Fri, 01 Jan 2021 12:00:00 +0000\r\n\r\nBody'
    fetch_rfc822 = ('OK', [(b'1 (RFC822 {123}', msg_bytes)])
    fetch_labels = ('OK', [b'\\Inbox'])
    imap_conn.fetch.side_effect = [fetch_rfc822, fetch_labels, fetch_rfc822, fetch_labels]
    imap_conn.store.return_value = ('OK', [b''])
    mocker.patch('gmail_archiver.utils.message_from_bytes',
                 return_value={'Date': 'Fri, 01 Jan 2021 12:00:00 +0000'})
    mocker.patch('gmail_archiver.utils.parsedate_tz', return_value=(2021, 1, 1, 12, 0, 0, 0, 0, 0))
    result = process(imap_conn, email, auth_data_db, out_dir)
    assert result == 0
    assert imap_conn.authenticate.called
    assert imap_conn.select.called
    assert imap_conn.search.called
    assert imap_conn.fetch.call_count == 4
    assert imap_conn.store.call_count == 2
    written_files = list(tmp_path.rglob('*.eml'))
    assert len(written_files) == 2
    written_labels = list(tmp_path.rglob('*.labels.json'))
    assert len(written_labels) == 2


def test_process_no_messages(mocker: MockerFixture, tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    auth_data_db: AuthDataDB = {email: {'access_token': access_token}}
    out_dir = tmp_path
    imap_conn = mocker.Mock()
    imap_conn.debug = 0
    mocker.patch('gmail_archiver.utils.generate_oauth2_str', return_value='oauth_str')
    mocker.patch('gmail_archiver.utils.assert_not_none', side_effect=lambda v, _: v)
    imap_conn.select.return_value = ('OK', [b''])
    imap_conn.search.return_value = ('NO', [b''])
    logger = mocker.patch('gmail_archiver.utils.log')
    result = process(imap_conn, email, auth_data_db, out_dir, debug=True)
    assert result == 0
    logger.info.assert_called_with('No messages matched criteria.')


def test_process_search_zero_results(mocker: MockerFixture, tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    auth_data_db: AuthDataDB = {email: {'access_token': access_token}}
    out_dir = tmp_path
    imap_conn = mocker.Mock()
    imap_conn.debug = 0
    mocker.patch('gmail_archiver.utils.generate_oauth2_str', return_value='oauth_str')
    mocker.patch('gmail_archiver.utils.assert_not_none', side_effect=lambda v, _: v)
    mock_log_info = mocker.patch('gmail_archiver.utils.log.info')
    imap_conn.search.return_value = ('OK', [])
    ret = process(imap_conn, email, auth_data_db, out_dir)
    assert ret == 0
    mock_log_info.assert_called_once_with('No messages matched criteria.')


def test_process_fetch_error(mocker: MockerFixture, tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    auth_data_db: AuthDataDB = {email: {'access_token': access_token}}
    logger = mocker.patch('gmail_archiver.utils.log')
    out_dir = tmp_path
    imap_conn = mocker.Mock()
    imap_conn.debug = 0
    mocker.patch('gmail_archiver.utils.generate_oauth2_str', return_value='oauth_str')
    mocker.patch('gmail_archiver.utils.assert_not_none', side_effect=lambda v, _: v)
    imap_conn.select.return_value = ('OK', [b''])
    imap_conn.search.return_value = ('OK', [b'1'])
    imap_conn.fetch.return_value = ('NO', [])
    result = process(imap_conn, email, auth_data_db, out_dir)
    assert result == 1
    logger.error.assert_called()


def test_refresh_token_success(requests_mock: Mocker) -> None:
    client_id = 'test-client-id'
    client_secret = 'test-client-secret'
    refresh_token_value = 'test-refresh-token'
    expected_response = {
        'access_token': 'ya29.a0AfH6SMBREFRESHTOKEN',
        'expires_in': 3599,
        'scope': 'https://mail.google.com/',
        'token_type': 'Bearer'
    }
    url = f'https://{GOOGLE_OAUTH2_DOMAIN}/token'
    requests_mock.post(url, json=expected_response, status_code=200)
    result = refresh_token(client_id, client_secret, refresh_token_value)
    assert result == expected_response


def test_refresh_token_http_error(requests_mock: Mocker) -> None:
    client_id = 'test-client-id'
    client_secret = 'test-client-secret'
    refresh_token_value = 'test-refresh-token'
    url = f'https://{GOOGLE_OAUTH2_DOMAIN}/token'
    requests_mock.post(url, status_code=400, json={'error': 'invalid_grant'})
    with pytest.raises(HTTPError):
        refresh_token(client_id, client_secret, refresh_token_value)
