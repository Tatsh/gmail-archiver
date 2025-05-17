from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gmail_archiver.utils import (
    GoogleOAuthClient,
    archive_emails,
    authorize_tokens,
    dq,
    generate_oauth2_str,
    get_auth_http_handler,
    get_localhost_redirect_uri,
    log_oauth2_error,
    refresh_token,
)
from requests import HTTPError
import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture
    from requests_mock import Mocker


def test_generate_oauth2_str_basic() -> None:
    username = 'testuser@gmail.com'
    access_token = 'ya29.a0AfH6SMBEXAMPLETOKEN'
    expected = f'user={username}\1auth=Bearer {access_token}\1\1'
    result = generate_oauth2_str(username, access_token)
    assert result == expected


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
    url = 'https://test-oauth/token'
    requests_mock.post(url, json=expected_response, status_code=200)
    result = authorize_tokens(url, client_id, client_secret, authorization_code, '', '')
    assert result == expected_response


def test_authorize_tokens_http_error(requests_mock: Mocker) -> None:
    client_id = 'test-client-id'
    client_secret = 'test-client-secret'
    authorization_code = 'test-auth-code'
    url = 'https://test-oauth/token'
    requests_mock.post(url, status_code=400, json={'error': 'invalid_grant'})
    with pytest.raises(HTTPError):
        authorize_tokens(url, client_id, client_secret, authorization_code, '', '')


def test_dq_quotes_simple_string() -> None:
    s = 'hello'
    result = dq(s)
    assert result == '"hello"'


def test_process_success(mocker: MockerFixture, tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    out_dir = tmp_path
    imap_conn = mocker.Mock()
    imap_conn.debug = 0
    mocker.patch('gmail_archiver.utils.generate_oauth2_str', return_value='oauth_str')
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
    result = archive_emails(imap_conn, email, access_token, out_dir, delete=True)
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


def test_process_no_delete(mocker: MockerFixture, tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    out_dir = tmp_path
    imap_conn = mocker.Mock()
    imap_conn.debug = 0
    mocker.patch('gmail_archiver.utils.generate_oauth2_str', return_value='oauth_str')
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
    result = archive_emails(imap_conn, email, access_token, out_dir)
    assert result == 0
    assert imap_conn.authenticate.called
    assert imap_conn.select.called
    assert imap_conn.search.called
    assert imap_conn.fetch.call_count == 4
    assert imap_conn.store.call_count == 0
    written_files = list(tmp_path.rglob('*.eml'))
    assert len(written_files) == 2
    written_labels = list(tmp_path.rglob('*.labels.json'))
    assert len(written_labels) == 2


def test_process_invalid_date_tuple(mocker: MockerFixture, tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    out_dir = tmp_path
    imap_conn = mocker.Mock()
    imap_conn.debug = 0
    mocker.patch('gmail_archiver.utils.generate_oauth2_str', return_value='oauth_str')
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
    mocker.patch('gmail_archiver.utils.parsedate_tz', return_value=None)
    result = archive_emails(imap_conn, email, access_token, out_dir)
    assert result == 1
    assert imap_conn.authenticate.called
    assert imap_conn.select.called
    assert imap_conn.search.called
    assert imap_conn.fetch.call_count == 1
    assert imap_conn.store.call_count == 0
    written_files = list(tmp_path.rglob('*.eml'))
    assert len(written_files) == 0
    written_labels = list(tmp_path.rglob('*.labels.json'))
    assert len(written_labels) == 0


def test_process_no_labels(mocker: MockerFixture, tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    out_dir = tmp_path
    imap_conn = mocker.Mock()
    imap_conn.debug = 0
    mocker.patch('gmail_archiver.utils.generate_oauth2_str', return_value='oauth_str')
    # Simulate search returns two messages
    imap_conn.search.return_value = ('OK', [b'1 2'])
    imap_conn.select.return_value = ('OK', [b''])
    # Simulate fetch for RFC822 and X-GM-LABELS
    msg_bytes = b'From: test@example.com\r\nDate: Fri, 01 Jan 2021 12:00:00 +0000\r\n\r\nBody'
    fetch_rfc822 = ('OK', [(b'1 (RFC822 {123}', msg_bytes)])
    fetch_labels: tuple[str, list[Any]] = ('OK', [])
    imap_conn.fetch.side_effect = [fetch_rfc822, fetch_labels, fetch_rfc822, fetch_labels]
    imap_conn.store.return_value = ('OK', [b''])
    mocker.patch('gmail_archiver.utils.message_from_bytes',
                 return_value={'Date': 'Fri, 01 Jan 2021 12:00:00 +0000'})
    mocker.patch('gmail_archiver.utils.parsedate_tz', return_value=(2021, 1, 1, 12, 0, 0, 0, 0, 0))
    result = archive_emails(imap_conn, email, access_token, out_dir)
    assert result == 0
    assert imap_conn.authenticate.called
    assert imap_conn.select.called
    assert imap_conn.search.called
    assert imap_conn.fetch.call_count == 4
    assert imap_conn.store.call_count == 0
    written_files = list(tmp_path.rglob('*.eml'))
    assert len(written_files) == 2
    written_labels = list(tmp_path.rglob('*.labels.json'))
    assert len(written_labels) == 0


def test_process_no_messages(mocker: MockerFixture, tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    out_dir = tmp_path
    imap_conn = mocker.Mock()
    imap_conn.debug = 0
    mocker.patch('gmail_archiver.utils.generate_oauth2_str', return_value='oauth_str')
    imap_conn.select.return_value = ('OK', [b''])
    imap_conn.search.return_value = ('NO', [b''])
    logger = mocker.patch('gmail_archiver.utils.log')
    result = archive_emails(imap_conn, email, access_token, out_dir)
    assert result == 0
    logger.info.assert_called_with('No messages matched criteria.')


def test_process_search_zero_results(mocker: MockerFixture, tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    out_dir = tmp_path
    imap_conn = mocker.Mock()
    imap_conn.debug = 0
    mocker.patch('gmail_archiver.utils.generate_oauth2_str', return_value='oauth_str')
    mock_log_info = mocker.patch('gmail_archiver.utils.log.info')
    imap_conn.search.return_value = ('OK', [])
    ret = archive_emails(imap_conn, email, access_token, out_dir)
    assert ret == 0
    mock_log_info.assert_any_call('No messages matched criteria.')


def test_process_fetch_error(mocker: MockerFixture, tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    logger = mocker.patch('gmail_archiver.utils.log')
    out_dir = tmp_path
    imap_conn = mocker.Mock()
    imap_conn.debug = 0
    mocker.patch('gmail_archiver.utils.generate_oauth2_str', return_value='oauth_str')
    imap_conn.select.return_value = ('OK', [b''])
    imap_conn.search.return_value = ('OK', [b'1'])
    imap_conn.fetch.return_value = ('NO', [])
    result = archive_emails(imap_conn, email, access_token, out_dir, debug=True)
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
    url = 'https://test-domain/token'
    requests_mock.post(url, json=expected_response, status_code=200)
    result = refresh_token(url, client_id, client_secret, refresh_token_value)
    assert result == expected_response


def test_refresh_token_http_error(requests_mock: Mocker) -> None:
    client_id = 'test-client-id'
    client_secret = 'test-client-secret'
    refresh_token_value = 'test-refresh-token'
    url = 'https://test-domain/token'
    requests_mock.post(url, status_code=400, json={'error': 'invalid_grant'})
    with pytest.raises(HTTPError):
        refresh_token(url, client_id, client_secret, refresh_token_value)


def test_log_oauth2_error_logs_error_and_description(mocker: MockerFixture) -> None:
    log_mock = mocker.patch('gmail_archiver.utils.log')
    data = {
        'error': 'invalid_grant',
        'error_description': 'The provided authorization grant is invalid.'
    }
    log_oauth2_error(data)
    log_mock.error.assert_any_call('Error type: %s', 'invalid_grant')
    log_mock.error.assert_any_call('Description: %s',
                                   'The provided authorization grant is invalid.')


def test_log_oauth2_error_logs_error_without_description(mocker: MockerFixture) -> None:
    log_mock = mocker.patch('gmail_archiver.utils.log')
    data = {'error': 'invalid_client'}
    log_oauth2_error(data)
    log_mock.error.assert_called_once_with('Error type: %s', 'invalid_client')


def test_log_oauth2_error_no_error_key(mocker: MockerFixture) -> None:
    log_mock = mocker.patch('gmail_archiver.utils.log')
    data = {'not_error': 'something'}
    log_oauth2_error(data)
    log_mock.error.assert_not_called()


def test_google_oauth_client_initializes_endpoints(requests_mock: Mocker) -> None:
    discovery_url = 'https://accounts.google.com/.well-known/openid-configuration'
    endpoints = {
        'token_endpoint': 'https://oauth2.googleapis.com/token',
        'device_authorization_endpoint': 'https://oauth2.googleapis.com/device/code',
        'authorization_endpoint': 'https://accounts.google.com/o/oauth2/v2/auth'
    }
    requests_mock.get(discovery_url, json=endpoints, status_code=200)
    client = GoogleOAuthClient('cid', 'secret')
    assert client.token_endpoint == endpoints['token_endpoint']
    assert client.device_authorization_endpoint == endpoints['device_authorization_endpoint']
    assert client.authorization_endpoint == endpoints['authorization_endpoint']
    assert client.client_id == 'cid'
    assert client.client_secret == 'secret'
    assert hasattr(client, 'session')


def test_get_localhost_redirect_uri_returns_valid_port_and_url(mocker: MockerFixture) -> None:
    mock_socket = mocker.patch('gmail_archiver.utils.socket.socket')
    mock_sock_instance = mock_socket.return_value
    mock_sock_instance.getsockname.return_value = ('127.0.0.1', 54321)
    listen_port, url = get_localhost_redirect_uri()
    assert listen_port == 54321
    assert url == 'http://localhost:54321/'
    mock_sock_instance.bind.assert_called_once_with(('127.0.0.1', 0))
    mock_sock_instance.close.assert_called_once()


def test_get_auth_http_handler_calls_callback_with_code(mocker: MockerFixture) -> None:
    class MockBaseHTTPRequestHandler:
        path = ''
        send_response = mocker.MagicMock()
        send_header = mocker.MagicMock()
        end_headers = mocker.MagicMock()
        wfile = mocker.MagicMock()

    mocker.patch('gmail_archiver.utils.urllib.parse.urlparse')
    mocker.patch('gmail_archiver.utils.http.server.BaseHTTPRequestHandler',
                 new=MockBaseHTTPRequestHandler)
    mock_parse_qs = mocker.patch('gmail_archiver.utils.urllib.parse.parse_qs')
    mock_parse_qs.return_value = {'code': ['abc123']}

    callback = mocker.MagicMock()
    handler_cls = get_auth_http_handler(callback)
    mocker.MagicMock()
    handler = handler_cls()  # type: ignore[call-arg]
    handler.do_GET()  # type: ignore[attr-defined]
    handler.send_response.assert_called_once_with(200)  # type: ignore[attr-defined]
    handler.send_header.assert_called_once_with(  # type: ignore[attr-defined]
        'Content-type', 'text/html')
