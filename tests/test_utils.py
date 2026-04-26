from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

from aioimaplib import Response  # type: ignore[import-untyped]
from anyio import Path as AsyncPath
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
from niquests import HTTPError
import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


def test_generate_oauth2_str_basic() -> None:
    username = 'testuser@gmail.com'
    access_token = 'ya29.a0AfH6SMBEXAMPLETOKEN'
    expected = f'user={username}\1auth=Bearer {access_token}\1\1'
    result = generate_oauth2_str(username, access_token)
    assert result == expected


async def test_authorize_tokens_success(mocker: MockerFixture) -> None:
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
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = expected_response
    mock_session = AsyncMock()
    mock_session.post.return_value = mock_response
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mocker.patch('gmail_archiver.utils.niquests.AsyncSession', return_value=mock_session)
    result = await authorize_tokens(url, client_id, client_secret, authorization_code, '', '')
    assert result == expected_response


async def test_authorize_tokens_http_error(mocker: MockerFixture) -> None:
    client_id = 'test-client-id'
    client_secret = 'test-client-secret'
    authorization_code = 'test-auth-code'
    url = 'https://test-oauth/token'
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = HTTPError()
    mock_session = AsyncMock()
    mock_session.post.return_value = mock_response
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mocker.patch('gmail_archiver.utils.niquests.AsyncSession', return_value=mock_session)
    with pytest.raises(HTTPError):
        await authorize_tokens(url, client_id, client_secret, authorization_code, '', '')


def test_dq_quotes_simple_string() -> None:
    s = 'hello'
    result = dq(s)
    assert result == '"hello"'


async def test_process_success(mocker: MockerFixture, tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    out_dir = AsyncPath(tmp_path)
    imap_conn = AsyncMock()
    imap_conn.xoauth2.return_value = Response('OK', [])
    imap_conn.search.return_value = Response('OK', [b'1 2'])
    imap_conn.select.return_value = Response('OK', [b''])
    msg_bytes = b'From: test@example.com\r\nDate: Fri, 01 Jan 2021 12:00:00 +0000\r\n\r\nBody'
    fetch_rfc822 = Response('OK', [b'1 FETCH (RFC822 {123}', bytearray(msg_bytes), b')'])
    fetch_labels = Response('OK', [b'\\Inbox'])
    imap_conn.fetch.side_effect = [fetch_rfc822, fetch_labels, fetch_rfc822, fetch_labels]
    imap_conn.store.return_value = Response('OK', [b''])
    mocker.patch('gmail_archiver.utils.message_from_bytes',
                 return_value={'Date': 'Fri, 01 Jan 2021 12:00:00 +0000'})
    mocker.patch('gmail_archiver.utils.parsedate_tz', return_value=(2021, 1, 1, 12, 0, 0, 0, 0, 0))
    result = await archive_emails(imap_conn, email, access_token, out_dir, delete=True)
    assert result == 0
    assert imap_conn.xoauth2.called
    assert imap_conn.select.called
    assert imap_conn.search.called
    assert imap_conn.fetch.call_count == 4
    assert imap_conn.store.call_count == 2
    written_files = list(tmp_path.rglob('*.eml'))
    assert len(written_files) == 2
    written_labels = list(tmp_path.rglob('*.labels.json'))
    assert len(written_labels) == 2


async def test_process_no_delete(mocker: MockerFixture, tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    out_dir = AsyncPath(tmp_path)
    imap_conn = AsyncMock()
    imap_conn.xoauth2.return_value = Response('OK', [])
    imap_conn.search.return_value = Response('OK', [b'1 2'])
    imap_conn.select.return_value = Response('OK', [b''])
    msg_bytes = b'From: test@example.com\r\nDate: Fri, 01 Jan 2021 12:00:00 +0000\r\n\r\nBody'
    fetch_rfc822 = Response('OK', [b'1 FETCH (RFC822 {123}', bytearray(msg_bytes), b')'])
    fetch_labels = Response('OK', [b'\\Inbox'])
    imap_conn.fetch.side_effect = [fetch_rfc822, fetch_labels, fetch_rfc822, fetch_labels]
    imap_conn.store.return_value = Response('OK', [b''])
    mocker.patch('gmail_archiver.utils.message_from_bytes',
                 return_value={'Date': 'Fri, 01 Jan 2021 12:00:00 +0000'})
    mocker.patch('gmail_archiver.utils.parsedate_tz', return_value=(2021, 1, 1, 12, 0, 0, 0, 0, 0))
    result = await archive_emails(imap_conn, email, access_token, out_dir)
    assert result == 0
    assert imap_conn.xoauth2.called
    assert imap_conn.select.called
    assert imap_conn.search.called
    assert imap_conn.fetch.call_count == 4
    assert imap_conn.store.call_count == 0
    written_files = list(tmp_path.rglob('*.eml'))
    assert len(written_files) == 2
    written_labels = list(tmp_path.rglob('*.labels.json'))
    assert len(written_labels) == 2


async def test_process_invalid_date_tuple(mocker: MockerFixture, tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    out_dir = AsyncPath(tmp_path)
    imap_conn = AsyncMock()
    imap_conn.xoauth2.return_value = Response('OK', [])
    imap_conn.search.return_value = Response('OK', [b'1 2'])
    imap_conn.select.return_value = Response('OK', [b''])
    msg_bytes = b'From: test@example.com\r\nDate: Fri, 01 Jan 2021 12:00:00 +0000\r\n\r\nBody'
    fetch_rfc822 = Response('OK', [b'1 FETCH (RFC822 {123}', bytearray(msg_bytes), b')'])
    fetch_labels = Response('OK', [b'\\Inbox'])
    imap_conn.fetch.side_effect = [fetch_rfc822, fetch_labels, fetch_rfc822, fetch_labels]
    imap_conn.store.return_value = Response('OK', [b''])
    mocker.patch('gmail_archiver.utils.message_from_bytes',
                 return_value={'Date': 'Fri, 01 Jan 2021 12:00:00 +0000'})
    mocker.patch('gmail_archiver.utils.parsedate_tz', return_value=None)
    result = await archive_emails(imap_conn, email, access_token, out_dir)
    assert result == 1
    assert imap_conn.xoauth2.called
    assert imap_conn.select.called
    assert imap_conn.search.called
    assert imap_conn.fetch.call_count == 1
    assert imap_conn.store.call_count == 0
    written_files = list(tmp_path.rglob('*.eml'))
    assert len(written_files) == 0
    written_labels = list(tmp_path.rglob('*.labels.json'))
    assert len(written_labels) == 0


async def test_process_no_labels(mocker: MockerFixture, tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    out_dir = AsyncPath(tmp_path)
    imap_conn = AsyncMock()
    imap_conn.xoauth2.return_value = Response('OK', [])
    imap_conn.search.return_value = Response('OK', [b'1 2'])
    imap_conn.select.return_value = Response('OK', [b''])
    msg_bytes = b'From: test@example.com\r\nDate: Fri, 01 Jan 2021 12:00:00 +0000\r\n\r\nBody'
    fetch_rfc822 = Response('OK', [b'1 FETCH (RFC822 {123}', bytearray(msg_bytes), b')'])
    fetch_labels: Response = Response('OK', [])
    imap_conn.fetch.side_effect = [fetch_rfc822, fetch_labels, fetch_rfc822, fetch_labels]
    imap_conn.store.return_value = Response('OK', [b''])
    mocker.patch('gmail_archiver.utils.message_from_bytes',
                 return_value={'Date': 'Fri, 01 Jan 2021 12:00:00 +0000'})
    mocker.patch('gmail_archiver.utils.parsedate_tz', return_value=(2021, 1, 1, 12, 0, 0, 0, 0, 0))
    result = await archive_emails(imap_conn, email, access_token, out_dir)
    assert result == 0
    assert imap_conn.xoauth2.called
    assert imap_conn.select.called
    assert imap_conn.search.called
    assert imap_conn.fetch.call_count == 4
    assert imap_conn.store.call_count == 0
    written_files = list(tmp_path.rglob('*.eml'))
    assert len(written_files) == 2
    written_labels = list(tmp_path.rglob('*.labels.json'))
    assert len(written_labels) == 0


async def test_archive_emails_out_path_exists(mocker: MockerFixture, tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    imap_conn = AsyncMock()
    imap_conn.xoauth2.return_value = Response('OK', [])
    imap_conn.search.return_value = Response('OK', [b'1'])
    imap_conn.select.return_value = Response('OK', [b''])
    msg_bytes = b'From: test@example.com\r\nDate: Fri, 01 Jan 2021 12:00:00 +0000\r\n\r\nBody'
    fetch_rfc822 = Response('OK', [b'1 FETCH (RFC822 {123}', bytearray(msg_bytes), b')'])
    fetch_labels = Response('OK', [b'\\Inbox'])
    imap_conn.fetch.side_effect = [fetch_rfc822, fetch_labels]
    imap_conn.store.return_value = Response('OK', [b''])
    mocker.patch('gmail_archiver.utils.message_from_bytes',
                 return_value={'Date': 'Fri, 01 Jan 2021 12:00:00 +0000'})
    mocker.patch('gmail_archiver.utils.parsedate_tz', return_value=(2021, 1, 1, 12, 0, 0, 0, 0, 0))
    year = '2021'
    month = '01-Jan'
    day = '01-Fri'
    out_dir_path = tmp_path / email / year / month / day
    out_dir_path.mkdir(parents=True, exist_ok=True)
    eml_filename = '0000000001.eml'
    eml_path = out_dir_path / eml_filename
    eml_path.write_bytes(b'existing content')
    mocker.patch('gmail_archiver.utils.sha1', autospec=True)
    gmail_archiver_sha1 = mocker.patch('gmail_archiver.utils.sha1')
    gmail_archiver_sha1.return_value.hexdigest.return_value = 'abcdef1234567890'
    result = await archive_emails(imap_conn, email, access_token, AsyncPath(tmp_path))
    assert result == 0
    written_files = list(out_dir_path.glob('*.eml'))
    assert any('-abcde.eml' in str(f) or '-abcdef1.eml' in str(f) for f in written_files)
    assert (out_dir_path / eml_filename).read_bytes() == b'existing content'


async def test_process_no_messages(mocker: MockerFixture, tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    out_dir = AsyncPath(tmp_path)
    imap_conn = AsyncMock()
    imap_conn.xoauth2.return_value = Response('OK', [])
    imap_conn.select.return_value = Response('OK', [b''])
    imap_conn.search.return_value = Response('NO', [b''])
    logger = mocker.patch('gmail_archiver.utils.log')
    result = await archive_emails(imap_conn, email, access_token, out_dir)
    assert result == 0
    logger.info.assert_called_with('No messages matched criteria.')


async def test_process_search_zero_results(mocker: MockerFixture, tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    out_dir = AsyncPath(tmp_path)
    imap_conn = AsyncMock()
    imap_conn.xoauth2.return_value = Response('OK', [])
    mock_log_info = mocker.patch('gmail_archiver.utils.log.info')
    imap_conn.search.return_value = Response('OK', [])
    result = await archive_emails(imap_conn, email, access_token, out_dir)
    assert result == 0
    mock_log_info.assert_any_call('No messages matched criteria.')


async def test_process_search_empty_id_string(mocker: MockerFixture, tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    out_dir = AsyncPath(tmp_path)
    imap_conn = AsyncMock()
    imap_conn.xoauth2.return_value = Response('OK', [])
    mock_log_info = mocker.patch('gmail_archiver.utils.log.info')
    imap_conn.search.return_value = Response('OK', [b' '])
    result = await archive_emails(imap_conn, email, access_token, out_dir)
    assert result == 0
    mock_log_info.assert_any_call('No messages matched criteria.')


async def test_archive_emails_fetch_payload_none(mocker: MockerFixture, tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    logger = mocker.patch('gmail_archiver.utils.log')
    out_dir = AsyncPath(tmp_path)
    imap_conn = AsyncMock()
    imap_conn.xoauth2.return_value = Response('OK', [])
    imap_conn.select.return_value = Response('OK', [b''])
    imap_conn.search.return_value = Response('OK', [b'1'])
    imap_conn.fetch.return_value = Response('OK', [b'1 FETCH (RFC822 {0}'])
    result = await archive_emails(imap_conn, email, access_token, out_dir)
    assert result == 1
    logger.error.assert_called_with('Unexpected empty message data for message #%s.', '1')


async def test_archive_emails_fetch_payload_not_tuple(mocker: MockerFixture,
                                                      tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    logger = mocker.patch('gmail_archiver.utils.log')
    out_dir = AsyncPath(tmp_path)
    imap_conn = AsyncMock()
    imap_conn.xoauth2.return_value = Response('OK', [])
    imap_conn.select.return_value = Response('OK', [b''])
    imap_conn.search.return_value = Response('OK', [b'1'])
    imap_conn.fetch.return_value = Response('OK', [b'1 FETCH (RFC822 {5}', 'not-bytes', b')'])
    result = await archive_emails(imap_conn, email, access_token, out_dir)
    assert result == 1
    logger.error.assert_called_with('Unexpected message data type for message #%s.', '1')


async def test_process_fetch_error(mocker: MockerFixture, tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    logger = mocker.patch('gmail_archiver.utils.log')
    out_dir = AsyncPath(tmp_path)
    imap_conn = AsyncMock()
    imap_conn.xoauth2.return_value = Response('OK', [])
    imap_conn.select.return_value = Response('OK', [b''])
    imap_conn.search.return_value = Response('OK', [b'1'])
    imap_conn.fetch.return_value = Response('NO', [])
    result = await archive_emails(imap_conn, email, access_token, out_dir, debug=True)
    assert result == 1
    logger.error.assert_called()


async def test_archive_emails_restores_imap_debug_when_no_matches(mocker: MockerFixture,
                                                                  tmp_path: Path) -> None:
    email = 'user@example.com'
    access_token = 'token'
    out_dir = AsyncPath(tmp_path)
    imap_conn = AsyncMock()
    imap_conn.xoauth2.return_value = Response('OK', [])
    imap_conn.select.return_value = Response('OK', [b''])
    imap_conn.search.return_value = Response('OK', [])
    ret = await archive_emails(imap_conn, email, access_token, out_dir, debug=True)
    assert ret == 0


async def test_refresh_token_success(mocker: MockerFixture) -> None:
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
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = expected_response
    mock_session = AsyncMock()
    mock_session.post.return_value = mock_response
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mocker.patch('gmail_archiver.utils.niquests.AsyncSession', return_value=mock_session)
    result = await refresh_token(url, client_id, client_secret, refresh_token_value)
    assert result == expected_response


async def test_refresh_token_http_error(mocker: MockerFixture) -> None:
    client_id = 'test-client-id'
    client_secret = 'test-client-secret'
    refresh_token_value = 'test-refresh-token'
    url = 'https://test-domain/token'
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = HTTPError()
    mock_session = AsyncMock()
    mock_session.post.return_value = mock_response
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mocker.patch('gmail_archiver.utils.niquests.AsyncSession', return_value=mock_session)
    with pytest.raises(HTTPError):
        await refresh_token(url, client_id, client_secret, refresh_token_value)


def test_log_oauth2_error_logs_error_and_description(mocker: MockerFixture) -> None:
    log_mock = mocker.patch('gmail_archiver.utils.log')
    data: dict[str, Any] = {
        'error': 'invalid_grant',
        'error_description': 'The provided authorisation grant is invalid.'
    }
    log_oauth2_error(data)
    log_mock.error.assert_any_call('Error type: %s', 'invalid_grant')
    log_mock.error.assert_any_call('Description: %s',
                                   'The provided authorisation grant is invalid.')


def test_log_oauth2_error_logs_error_without_description(mocker: MockerFixture) -> None:
    log_mock = mocker.patch('gmail_archiver.utils.log')
    data: dict[str, Any] = {'error': 'invalid_client'}
    log_oauth2_error(data)
    log_mock.error.assert_called_once_with('Error type: %s', 'invalid_client')


def test_log_oauth2_error_no_error_key(mocker: MockerFixture) -> None:
    log_mock = mocker.patch('gmail_archiver.utils.log')
    data: dict[str, Any] = {'not_error': 'something'}
    log_oauth2_error(data)
    log_mock.error.assert_not_called()


async def test_google_oauth_client_initializes_endpoints(mocker: MockerFixture) -> None:
    discovery_url = 'https://accounts.google.com/.well-known/openid-configuration'
    endpoints = {
        'authorization_endpoint': 'https://accounts.google.com/o/oauth2/v2/auth',
        'device_authorization_endpoint': 'https://oauth2.googleapis.com/device/code',
        'token_endpoint': 'https://oauth2.googleapis.com/token'
    }
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = endpoints
    mock_session = AsyncMock()
    mock_session.get.return_value = mock_response
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mocker.patch('gmail_archiver.utils.niquests.AsyncSession', return_value=mock_session)
    client = GoogleOAuthClient('cid', 'secret')
    await client.discover()
    assert client.token_endpoint == endpoints['token_endpoint']
    assert client.device_authorization_endpoint == endpoints['device_authorization_endpoint']
    assert client.authorization_endpoint == endpoints['authorization_endpoint']
    assert client.client_id == 'cid'
    assert client.client_secret == 'secret'
    mock_session.get.assert_called_once_with(discovery_url)


def test_get_localhost_redirect_uri_returns_valid_port_and_url(mocker: MockerFixture) -> None:
    mock_socket = mocker.patch('gmail_archiver.utils.socket.socket')
    mock_sock_instance = mock_socket.return_value
    mock_sock_instance.getsockname.return_value = ('127.0.0.1', 54321)
    listen_port, url = get_localhost_redirect_uri()
    assert listen_port == 54321
    assert url == 'http://localhost:54321/'
    mock_sock_instance.bind.assert_called_once_with(('127.0.0.1', 0))
    mock_sock_instance.close.assert_called_once()


def test_get_localhost_redirect_uri_raises_when_port_not_int(mocker: MockerFixture) -> None:
    mock_socket = mocker.patch('gmail_archiver.utils.socket.socket')
    mock_sock_instance = mock_socket.return_value
    mock_sock_instance.getsockname.return_value = ('127.0.0.1', 'not-an-int')
    with pytest.raises(TypeError, match='integer listen port'):
        get_localhost_redirect_uri()
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
    handler = handler_cls()  # type: ignore[call-arg]  # ty: ignore[missing-argument]
    handler.do_GET()  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
    handler.send_response.assert_called_once_with(  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        200)
    handler.send_header.assert_called_once_with(  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]
        'Content-type', 'text/html')
