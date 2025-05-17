from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock
import json

from gmail_archiver.main import main
from typing_extensions import Self
import pytest

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from click.testing import CliRunner
    from pytest_mock import MockerFixture
    from requests_mock import Mocker


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    config = {'client_id': 'test_client_id', 'client_secret': 'test_client_secret'}
    config_path = tmp_path / 'config.toml'
    config_path.write_text(
        f'client_id = "{config["client_id"]}"\nclient_secret = "{config["client_secret"]}"\n')
    return config_path


@pytest.fixture
def oauth_file(tmp_path: Path) -> Path:
    return tmp_path / 'oauth.json'


@pytest.fixture
def patch_platformdirs(mocker: MockerFixture, tmp_path: Path, oauth_file: Path,
                       config_file: Path) -> tuple[Path, Path]:
    mocker.patch('gmail_archiver.main.user_cache_path', return_value=tmp_path)
    mocker.patch('gmail_archiver.main.user_config_path', return_value=tmp_path)
    return oauth_file, config_file


def make_auth_data(*, expired: bool = False) -> dict[str, Any]:
    expiration_time = (datetime.now(timezone.utc) -
                       timedelta(seconds=10) if expired else datetime.now(timezone.utc) +
                       timedelta(hours=1))
    return {
        'access_token': 'access_token_value',
        'refresh_token': 'refresh_token_value',
        'expires_in': 3600,
        'expiration_time': expiration_time.isoformat()
    }


def test_main_auth_only_existing_token(mocker: MockerFixture, patch_platformdirs: tuple[Path, Path],
                                       tmp_path: Path, runner: CliRunner) -> None:
    oauth_file, _ = patch_platformdirs
    email = 'test@example.com'
    auth_data = make_auth_data()
    oauth_file.write_text(json.dumps({email: auth_data}))
    mocker.patch('gmail_archiver.main.tomlkit.loads').return_value.unwrap.return_value = {
        'tool': {
            'gmail-archiver': {
                'client_id': 'test_client_id',
                'client_secret': 'test_client_secret'
            }
        }
    }
    setup_logging = mocker.patch('gmail_archiver.main.setup_logging')
    imap_ssl = mocker.patch('gmail_archiver.main.imaplib.IMAP4_SSL')
    result = runner.invoke(main, [email, str(tmp_path), '--auth-only'])
    assert result.exit_code == 0
    setup_logging.assert_called()
    imap_ssl.assert_not_called()


def test_main_auth_json_loads_return_empty(mocker: MockerFixture, tmp_path: Path,
                                           runner: CliRunner) -> None:
    email = 'test@example.com'
    mocker.patch('gmail_archiver.main.user_config_path'
                 ).return_value.__truediv__.return_value.exists.return_value = True
    mocker.patch('gmail_archiver.main.tomlkit.loads').return_value.unwrap.return_value = {
        'client_id': 'test_client_id',
        'client_secret': 'test_client_secret'
    }
    mocker.patch('gmail_archiver.main.json.loads', return_value=[])
    mocker.patch('gmail_archiver.main.setup_logging')
    imap_ssl = mocker.patch('gmail_archiver.main.imaplib.IMAP4_SSL')
    result = runner.invoke(main, [email, str(tmp_path), '--auth-only'])
    assert result.exit_code == 1
    imap_ssl.assert_not_called()


def test_main_auth_json_loads_return_invalid_type(mocker: MockerFixture, tmp_path: Path,
                                                  runner: CliRunner) -> None:
    email = 'test@example.com'
    mocker.patch('gmail_archiver.main.user_config_path'
                 ).return_value.__truediv__.return_value.exists.return_value = True
    mocker.patch('gmail_archiver.main.tomlkit.loads').return_value.unwrap.return_value = {
        'tool': {
            'gmail-archiver': {
                'client_id': 'test_client_id',
                'client_secret': 'test_client_secret'
            }
        }
    }
    mocker.patch('gmail_archiver.main.json.loads', return_value=1)
    mocker.patch('gmail_archiver.main.setup_logging')
    imap_ssl = mocker.patch('gmail_archiver.main.imaplib.IMAP4_SSL')
    result = runner.invoke(main, [email, str(tmp_path), '--auth-only'])
    assert result.exit_code == 1
    imap_ssl.assert_not_called()


def test_main_new_token_authorization(mocker: MockerFixture, patch_platformdirs: tuple[Path, Path],
                                      tmp_path: Path, runner: CliRunner,
                                      requests_mock: Mocker) -> None:
    oauth_file, _config_file = patch_platformdirs
    email = 'test2@example.com'
    oauth_file.write_text(json.dumps({}))
    mocker.patch('gmail_archiver.main.tomlkit.loads').return_value.unwrap.return_value = {
        'tool': {
            'gmail-archiver': {
                'client_id': 'test_client_id',
                'client_secret': 'test_client_secret'
            }
        }
    }
    requests_mock.get(
        'https://accounts.google.com/.well-known/openid-configuration',
        json={
            'token_endpoint': 'https://oauth2.googleapis.com/token',
            'device_authorization_endpoint': 'https://oauth2.googleapis.com/device/code',
            'authorization_endpoint': 'https://accounts.google.com/o/oauth2/v2/auth'
        },
        status_code=200)
    authorize_tokens = mocker.patch('gmail_archiver.main.authorize_tokens',
                                    return_value={
                                        'refresh_token': 'refresh_token_value',
                                        'expires_in': 3600
                                    })
    setup_logging = mocker.patch('gmail_archiver.main.setup_logging')
    mocker.patch('gmail_archiver.main.get_localhost_redirect_uri',
                 return_value=(1234, 'http://localhost:1234'))
    callback: Callable[..., Any] | None = None

    def get_handler(auth_code_callback: Callable[[str], None]) -> Any:
        nonlocal callback
        callback = auth_code_callback
        return MagicMock()

    mocker.patch('gmail_archiver.main.get_auth_http_handler', get_handler)
    callback_called = False

    class MockHTTPServer:
        def __init__(self, _: tuple[int, str], __: Callable[..., Any]) -> None:
            pass

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def handle_request(self) -> None:
            nonlocal callback, callback_called
            assert callback is not None
            callback('auth_code')
            callback_called = True

    mocker.patch('gmail_archiver.main.http.server.HTTPServer', new=MockHTTPServer)
    imap_ssl = mocker.patch('gmail_archiver.main.imaplib.IMAP4_SSL')
    result = runner.invoke(main, [email, str(tmp_path), '--auth-only'])
    assert result.exit_code == 0
    authorize_tokens.assert_called()
    setup_logging.assert_called()
    imap_ssl.assert_not_called()
    data = json.loads(oauth_file.read_text())
    assert email in data
    assert callback_called


def test_main_new_token_authorization_invalid_db(mocker: MockerFixture,
                                                 patch_platformdirs: tuple[Path, Path],
                                                 tmp_path: Path, runner: CliRunner) -> None:
    oauth_file, _config_file = patch_platformdirs
    email = 'test2@example.com'
    auth_db = make_auth_data()
    del auth_db['refresh_token']
    oauth_file.write_text(json.dumps({email: auth_db}))
    mocker.patch('gmail_archiver.main.tomlkit.loads').return_value.unwrap.return_value = {
        'tool': {
            'gmail-archiver': {
                'client_id': 'test_client_id',
                'client_secret': 'test_client_secret'
            }
        }
    }
    authorize_tokens = mocker.patch('gmail_archiver.main.authorize_tokens',
                                    return_value={
                                        'refresh_token': 'refresh_token_value',
                                        'expires_in': 3600
                                    })
    setup_logging = mocker.patch('gmail_archiver.main.setup_logging')
    mocker.patch('gmail_archiver.main.get_localhost_redirect_uri',
                 return_value=(1234, 'http://localhost:1234'))
    callback: Callable[..., Any] | None = None

    def get_handler(auth_code_callback: Callable[[str], None]) -> Any:
        nonlocal callback
        callback = auth_code_callback
        return MagicMock()

    mocker.patch('gmail_archiver.main.get_auth_http_handler', get_handler)
    callback_called = False

    class MockHTTPServer:
        def __init__(self, _: tuple[int, str], __: Callable[..., Any]) -> None:
            pass

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def handle_request(self) -> None:
            nonlocal callback, callback_called
            assert callback is not None
            callback('auth_code')
            callback_called = True

    mocker.patch('gmail_archiver.main.http.server.HTTPServer', new=MockHTTPServer)
    imap_ssl = mocker.patch('gmail_archiver.main.imaplib.IMAP4_SSL')
    result = runner.invoke(main, [email, str(tmp_path), '--auth-only'])
    assert result.exit_code == 0
    authorize_tokens.assert_called()
    setup_logging.assert_called()
    imap_ssl.assert_not_called()
    data = json.loads(oauth_file.read_text())
    assert email in data


def test_main_new_token_authorization_no_code_returned(mocker: MockerFixture,
                                                       patch_platformdirs: tuple[Path, Path],
                                                       tmp_path: Path, runner: CliRunner) -> None:
    oauth_file, _config_file = patch_platformdirs
    email = 'test2@example.com'
    auth_db = make_auth_data()
    del auth_db['refresh_token']
    oauth_file.write_text(json.dumps({email: auth_db}))
    mocker.patch('gmail_archiver.main.tomlkit.loads').return_value.unwrap.return_value = {
        'tool': {
            'gmail-archiver': {
                'client_id': 'test_client_id',
                'client_secret': 'test_client_secret'
            }
        }
    }
    mocker.patch('gmail_archiver.main.authorize_tokens',
                 return_value={
                     'refresh_token': 'refresh_token_value',
                     'expires_in': 3600
                 })
    setup_logging = mocker.patch('gmail_archiver.main.setup_logging')
    mocker.patch('gmail_archiver.main.get_localhost_redirect_uri',
                 return_value=(1234, 'http://localhost:1234'))
    callback: Callable[..., Any] | None = None

    def get_handler(auth_code_callback: Callable[[str], None]) -> Any:
        nonlocal callback
        callback = auth_code_callback
        return MagicMock()

    mocker.patch('gmail_archiver.main.get_auth_http_handler', get_handler)

    class MockHTTPServer:
        def __init__(self, _: tuple[int, str], __: Callable[..., Any]) -> None:
            pass

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def handle_request(self) -> None:
            pass

    mocker.patch('gmail_archiver.main.http.server.HTTPServer', new=MockHTTPServer)
    imap_ssl = mocker.patch('gmail_archiver.main.imaplib.IMAP4_SSL')
    result = runner.invoke(main, [email, str(tmp_path), '--auth-only'])
    assert result.exit_code == 1
    setup_logging.assert_called()
    imap_ssl.assert_not_called()
    data = json.loads(oauth_file.read_text())
    assert email in data
    assert 'Did not obtain an authorisation code.' in result.output


def test_main_refresh_token(mocker: MockerFixture, patch_platformdirs: tuple[Path, Path],
                            tmp_path: Path, runner: CliRunner) -> None:
    oauth_file, _config_file = patch_platformdirs
    email = 'test3@example.com'
    expired_auth_data = make_auth_data(expired=True)
    oauth_file.write_text(json.dumps({email: expired_auth_data}))
    mocker.patch('gmail_archiver.main.tomlkit.loads').return_value.unwrap.return_value = {
        'tool': {
            'gmail-archiver': {
                'client_id': 'test_client_id',
                'client_secret': 'test_client_secret'
            }
        }
    }
    refresh_token_mock = mocker.patch('gmail_archiver.main.refresh_token',
                                      return_value={
                                          'refresh_token': 'refresh_token_value',
                                          'expires_in': 3600
                                      })
    setup_logging = mocker.patch('gmail_archiver.main.setup_logging')
    imap_ssl = mocker.patch('gmail_archiver.main.imaplib.IMAP4_SSL')
    result = runner.invoke(main, [email, str(tmp_path), '--auth-only'])
    assert result.exit_code == 0
    refresh_token_mock.assert_called()
    setup_logging.assert_called()
    imap_ssl.assert_not_called()


def test_main_process_called(mocker: MockerFixture, patch_platformdirs: tuple[Path, Path],
                             tmp_path: Path, runner: CliRunner) -> None:
    oauth_file, _config_file = patch_platformdirs
    email = 'test4@example.com'
    auth_data = make_auth_data()
    oauth_file.write_text(json.dumps({email: auth_data}))
    mocker.patch('gmail_archiver.main.tomlkit.loads').return_value.unwrap.return_value = {
        'tool': {
            'gmail-archiver': {
                'client_id': 'test_client_id',
                'client_secret': 'test_client_secret'
            }
        }
    }
    setup_logging = mocker.patch('gmail_archiver.main.setup_logging')
    imap_conn_mock = mocker.Mock()
    mocker.patch('gmail_archiver.main.imaplib.IMAP4_SSL', return_value=imap_conn_mock)
    process_mock = mocker.patch('gmail_archiver.main.archive_emails', return_value=0)
    result = runner.invoke(main, [email, str(tmp_path)])
    assert result.exit_code == 0
    process_mock.assert_called_with(imap_conn_mock,
                                    email,
                                    mocker.ANY,
                                    tmp_path,
                                    days=90,
                                    debug=False,
                                    delete=True)
    imap_conn_mock.close.assert_called()
    imap_conn_mock.logout.assert_called()
    setup_logging.assert_called()


def test_main_exit_on_process_nonzero(mocker: MockerFixture, patch_platformdirs: tuple[Path, Path],
                                      tmp_path: Path, runner: CliRunner) -> None:
    oauth_file, _config_file = patch_platformdirs
    email = 'test5@example.com'
    auth_data = make_auth_data()
    oauth_file.write_text(json.dumps({email: auth_data}))
    mocker.patch('gmail_archiver.main.tomlkit.loads').return_value.unwrap.return_value = {
        'tool': {
            'gmail-archiver': {
                'client_id': 'test_client_id',
                'client_secret': 'test_client_secret'
            }
        }
    }
    setup_logging = mocker.patch('gmail_archiver.main.setup_logging')
    imap_conn_mock = mocker.Mock()
    mocker.patch('gmail_archiver.main.imaplib.IMAP4_SSL', return_value=imap_conn_mock)
    process_mock = mocker.patch('gmail_archiver.main.archive_emails', return_value=2)
    result = runner.invoke(main, [email, str(tmp_path)])
    assert result.exit_code != 0
    process_mock.assert_called()
    imap_conn_mock.close.assert_called()
    imap_conn_mock.logout.assert_called()
    setup_logging.assert_called()


def test_main_missing_client_id_secret(mocker: MockerFixture, patch_platformdirs: tuple[Path, Path],
                                       tmp_path: Path, runner: CliRunner) -> None:
    oauth_file, _config_file = patch_platformdirs
    email = 'test@example.com'
    auth_data = make_auth_data()
    oauth_file.write_text(json.dumps({email: auth_data}))
    mocker.patch('gmail_archiver.main.tomlkit.loads',
                 return_value=mocker.MagicMock(return_value={}))
    result = runner.invoke(main, [email, str(tmp_path)])
    assert result.exit_code != 0
    assert 'client_id and client_secret must be set' in result.output


def test_main_missing_client_id_secret_2(mocker: MockerFixture, tmp_path: Path,
                                         runner: CliRunner) -> None:
    mock_user_config_path = mocker.patch('gmail_archiver.main.user_config_path')
    mock_user_config_path.return_value.__truediv__.return_value.exists.return_value = False
    email = 'test@example.com'
    mocker.patch('gmail_archiver.main.tomlkit.loads',
                 return_value=mocker.MagicMock(return_value={}))
    result = runner.invoke(main, [email, str(tmp_path)])
    assert result.exit_code != 0
    assert 'client_id and client_secret must be set' in result.output


def test_main_invalid_oauth_json_and_empty_config(mocker: MockerFixture, tmp_path: Path,
                                                  runner: CliRunner) -> None:
    mock_user_config_path = mocker.patch('gmail_archiver.main.user_config_path')
    mock_user_config_path.return_value.__truediv__.return_value.exists.return_value = False
    mock_user_cache_path = mocker.patch('gmail_archiver.main.user_cache_path')
    mock_user_cache_path.return_value.__truediv__.return_value.exists.return_value = True
    mocker.patch('gmail_archiver.main.json.loads', side_effect=json.JSONDecodeError('msg', '', 0))
    email = 'test@example.com'
    mocker.patch('gmail_archiver.main.tomlkit.loads',
                 return_value=mocker.MagicMock(return_value={}))
    result = runner.invoke(main, [email, str(tmp_path)])
    assert result.exit_code != 0
    assert 'client_id and client_secret must be set' in result.output
