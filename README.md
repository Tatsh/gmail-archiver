# gmail-archiver

[![Python versions](https://img.shields.io/pypi/pyversions/gmail-archiver.svg?color=blue&logo=python&logoColor=white)](https://www.python.org/)
[![PyPI - Version](https://img.shields.io/pypi/v/gmail-archiver)](https://pypi.org/project/gmail-archiver/)
[![GitHub tag (with filter)](https://img.shields.io/github/v/tag/Tatsh/gmail-archiver)](https://github.com/Tatsh/gmail-archiver/tags)
[![License](https://img.shields.io/github/license/Tatsh/gmail-archiver)](https://github.com/Tatsh/gmail-archiver/blob/master/LICENSE.txt)
[![GitHub commits since latest release (by SemVer including pre-releases)](https://img.shields.io/github/commits-since/Tatsh/gmail-archiver/v0.0.2/master)](https://github.com/Tatsh/gmail-archiver/compare/v0.0.2...master)
[![QA](https://github.com/Tatsh/gmail-archiver/actions/workflows/qa.yml/badge.svg)](https://github.com/Tatsh/gmail-archiver/actions/workflows/qa.yml)
[![Tests](https://github.com/Tatsh/gmail-archiver/actions/workflows/tests.yml/badge.svg)](https://github.com/Tatsh/gmail-archiver/actions/workflows/tests.yml)
[![Coverage Status](https://coveralls.io/repos/github/Tatsh/gmail-archiver/badge.svg?branch=master)](https://coveralls.io/github/Tatsh/gmail-archiver?branch=master)
[![Documentation Status](https://readthedocs.org/projects/gmail-archiver/badge/?version=latest)](https://gmail-archiver.readthedocs.org/?badge=latest)
[![mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![pydocstyle](https://img.shields.io/badge/pydocstyle-enabled-AD4CD3)](http://www.pydocstyle.org/en/stable/)
[![pytest](https://img.shields.io/badge/pytest-zz?logo=Pytest&labelColor=black&color=black)](https://docs.pytest.org/en/stable/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Downloads](https://static.pepy.tech/badge/gmail-archiver/month)](https://pepy.tech/project/gmail-archiver)
[![Stargazers](https://img.shields.io/github/stars/Tatsh/gmail-archiver?logo=github&style=flat)](https://github.com/Tatsh/gmail-archiver/stargazers)

[![@Tatsh](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fpublic.api.bsky.app%2Fxrpc%2Fapp.bsky.actor.getProfile%2F%3Factor%3Ddid%3Aplc%3Auq42idtvuccnmtl57nsucz72%26query%3D%24.followersCount%26style%3Dsocial%26logo%3Dbluesky%26label%3DFollow%2520%40Tatsh&query=%24.followersCount&style=social&logo=bluesky&label=Follow%20%40Tatsh)](https://bsky.app/profile/Tatsh.bsky.social)
[![Mastodon Follow](https://img.shields.io/mastodon/follow/109370961877277568?domain=hostux.social&style=social)](https://hostux.social/@Tatsh)

Locally archive Gmail emails.

## Installation

### Pip

```shell
pip install gmail-archiver
```

## Configuration

Create a file at `${CONFIG_DIR}/gmail-archiver/config.toml`. On Linux this is typically
`~/.config/gmail-archiver/config.toml`. The application will print the configuration file path on
every run.

The file must contain the following:

```toml
[tool.gmail-archiver]
client_id = 'client-id.apps.googleusercontent.com'
client_secret = 'client-secret'
```

You must set up a project on [Google Cloud](https://console.cloud.google.com/cloud-resource-manager)
and it must have the [Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com)
enabled.

Then in **APIs and services**, choose **Credentials**, **+ Create credentials** and
**OAuth client ID**.

- **Application type**: Web application
- **Name**: any name

Copy and paste the client ID and secret into the above file.

You should protect the above file. Set it to as limited of a permission set as possible. Example:
`chmod 0400 ~/.config/gmail-archiver/config.toml`.

Why not use Keyring? Keyring is inappropriate for automated scenarios, unless it is purposely made
insecure.

## Authorisation

When run, if anything is invalid about the OAuth data, you will be prompted to create it.

```plain
$ gmail-archiver email@gmail.com
Using authorisation database: /home/user/.cache/gmail-archiver/oauth.json
Using authorisation file: /home/user/.config/gmail-archiver/config.toml

https://accounts.google.com/o/oauth2/v2/auth?client_id=....

Visit displayed URL to authorize this application. Waiting...
```

In your browser, click **Continue** and then in the browser you will see the text:
_Authorisation redirect completed. You may close this window_. At that point the archiving will
begin.

```plain
Visit displayed URL to authorize this application. Waiting...
127.0.0.2 - - [17/May/2025 00:50:21] "GET /?code=...&scope=https://mail.google.com/ HTTP/1.1" 200 -
INFO: Logging in.
INFO: Deleting emails: False
INFO: Archiving 200 messages.
```

Due to the [method of authorisation](https://developers.google.com/identity/protocols/oauth2/native-app#redirect-uri_loopback)
for OAuth, if you need to run this on a server that does not have a fully-featured browser (such as
a headless machine), you must run this tool on a machine with one (and the ability to run a localhost
server) to get the first access token. Once this is done, transfer configuration and the OAuth
authorisation data to the server. From that point, the access token will be refreshed when
necessary. You must do this for every email you plan to archive.

The OAuth authorisation file is also printed at startup. Example on Linux:
`~/.config/cache/gmail-archiver/oauth.json`. It will be stored with mode `0600`.

## Usage

```shell
Usage: gmail-archiver [OPTIONS] EMAIL [OUT_DIR]

  Archive Gmail emails and move them to the trash.

Options:
  --no-delete          Do not move emails to trash.
  -a, --auth-only      Only authorise the user.
  -d, --debug          Enable debug level logging.
  --debug-imap         Enable debug level logging for IMAP.
  -r, --force-refresh  Force refresh the token.
  -h, --help           Show this message and exit.
```
