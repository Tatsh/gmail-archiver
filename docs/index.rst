gmail-archiver
==============

.. only:: html

   .. image:: https://img.shields.io/pypi/pyversions/gmail-archiver.svg?color=blue&logo=python&logoColor=white
      :target: https://www.python.org/
      :alt: Python versions

   .. image:: https://img.shields.io/pypi/v/gmail-archiver
      :target: https://pypi.org/project/gmail-archiver/
      :alt: PyPI Version

   .. image:: https://img.shields.io/github/v/tag/Tatsh/gmail-archiver
      :target: https://github.com/Tatsh/gmail-archiver/tags
      :alt: GitHub tag (with filter)

   .. image:: https://img.shields.io/github/license/Tatsh/gmail-archiver
      :target: https://github.com/Tatsh/gmail-archiver/blob/master/LICENSE.txt
      :alt: License

   .. image:: https://img.shields.io/github/commits-since/Tatsh/gmail-archiver/v0.0.4/master
      :target: https://github.com/Tatsh/gmail-archiver/compare/v0.0.4...master
      :alt: GitHub commits since latest release (by SemVer including pre-releases)

   .. image:: https://github.com/Tatsh/gmail-archiver/actions/workflows/codeql.yml/badge.svg
      :target: https://github.com/Tatsh/gmail-archiver/actions/workflows/codeql.yml
      :alt: CodeQL

   .. image:: https://github.com/Tatsh/gmail-archiver/actions/workflows/qa.yml/badge.svg
      :target: https://github.com/Tatsh/gmail-archiver/actions/workflows/qa.yml
      :alt: QA

   .. image:: https://github.com/Tatsh/gmail-archiver/actions/workflows/tests.yml/badge.svg
      :target: https://github.com/Tatsh/gmail-archiver/actions/workflows/tests.yml
      :alt: Tests

   .. image:: https://coveralls.io/repos/github/Tatsh/gmail-archiver/badge.svg?branch=master
      :target: https://coveralls.io/github/Tatsh/gmail-archiver?branch=master
      :alt: Coverage Status

   .. image:: https://readthedocs.org/projects/gmail-archiver/badge/?version=latest
      :target: https://gmail-archiver.readthedocs.org/?badge=latest
      :alt: Documentation Status

   .. image:: https://www.mypy-lang.org/static/mypy_badge.svg
      :target: http://mypy-lang.org/
      :alt: mypy

   .. image:: https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white
      :target: https://github.com/pre-commit/pre-commit
      :alt: pre-commit

   .. image:: https://img.shields.io/badge/pydocstyle-enabled-AD4CD3
      :target: http://www.pydocstyle.org/en/stable/
      :alt: pydocstyle

   .. image:: https://img.shields.io/badge/pytest-zz?logo=Pytest&labelColor=black&color=black
      :target: https://docs.pytest.org/en/stable/
      :alt: pytest

   .. image:: https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json
      :target: https://github.com/astral-sh/ruff
      :alt: Ruff

   .. image:: https://static.pepy.tech/badge/gmail-archiver/month
      :target: https://pepy.tech/project/gmail-archiver
      :alt: Downloads

   .. image:: https://img.shields.io/github/stars/Tatsh/gmail-archiver?logo=github&style=flat
      :target: https://github.com/Tatsh/gmail-archiver/stargazers
      :alt: Stargazers

   .. image:: https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fpublic.api.bsky.app%2Fxrpc%2Fapp.bsky.actor.getProfile%2F%3Factor%3Ddid%3Aplc%3Auq42idtvuccnmtl57nsucz72%26query%3D%24.followersCount%26style%3Dsocial%26logo%3Dbluesky%26label%3DFollow%2520%40Tatsh&query=%24.followersCount&style=social&logo=bluesky&label=Follow%20%40Tatsh
      :target: https://bsky.app/profile/Tatsh.bsky.social
      :alt: Follow @Tatsh

   .. image:: https://img.shields.io/mastodon/follow/109370961877277568?domain=hostux.social&style=social
      :target: https://hostux.social/@Tatsh
      :alt: Mastodon Follow

Locally archive Gmail emails.

Commands
--------

.. click:: gmail_archiver.main:main
   :prog: gmail-archiver
   :nested: full

Configuration
-------------

Create a file at ``${CONFIG_DIR}/gmail-archiver/config.toml``. On Linux this is typically
``~/.config/gmail-archiver/config.toml``. The application will print the configuration file path on
every run.

The file must contain the following:

.. code-block:: toml

   [tool.gmail-archiver]
   client_id = 'client-id.apps.googleusercontent.com'
   client_secret = 'client-secret'

You must set up a project on `Google Cloud <https://console.cloud.google.com/cloud-resource-manager>`_
and it must have the `Gmail API <https://console.cloud.google.com/apis/library/gmail.googleapis.com>`_
enabled.

Then in **APIs and services**, choose **Credentials**, **+ Create credentials** and
**OAuth client ID**.

- **Application type**: Web application
- **Name**: any name

Copy and paste the client ID and secret into the above file.

You should protect the above file. Set it to as limited of a permission set as possible. Example:
``chmod 0400 ~/.config/gmail-archiver/config.toml``.

Why not use Keyring? Keyring is inappropriate for automated scenarios, unless it is purposely made
insecure.

Authorisation
-------------

When run, if anything is invalid about the OAuth data, you will be prompted to create it.

.. code-block:: console

   $ gmail-archiver email@gmail.com
   Using authorisation database: /home/user/.cache/gmail-archiver/oauth.json
   Using authorisation file: /home/user/.config/gmail-archiver/config.toml

   https://accounts.google.com/o/oauth2/v2/auth?client_id=....

   Visit displayed URL to authorize this application. Waiting...

In your browser, click **Continue** and then in the browser you will see the text:
*Authorisation redirect completed. You may close this window*. At that point the archiving will
begin.

.. code-block:: console

   Visit displayed URL to authorize this application. Waiting...
   127.0.0.4 - - [17/May/2025 00:50:21] "GET /?code=...&scope=https://mail.google.com/ HTTP/1.1" 200 -
   INFO: Logging in.
   INFO: Deleting emails: False
   INFO: Archiving 200 messages.

Due to the `method of authorisation <https://developers.google.com/identity/protocols/oauth2/native-app#redirect-uri_loopback>`_
for OAuth, if you need to run this on a server that does not have a fully-featured browser (such as
a headless machine), you must run this tool on a machine with one (and the ability to run a localhost
server) to get the first access token. Once this is done, transfer configuration and the OAuth
authorisation data to the server. From that point, the access token will be refreshed when
necessary. You must do this for every email you plan to archive.

The OAuth authorisation file is also printed at startup. Example on Linux:
``~/.config/cache/gmail-archiver/oauth.json``. It will be stored with mode ``0600``.

.. only:: html

   Library
   -------

   .. automodule:: gmail_archiver
      :members:

   .. automodule:: gmail_archiver.typing
      :members:

   .. automodule:: gmail_archiver.utils
      :members:
      :exclude-members: setup_logging, archive_emails, authorize_tokens, refresh_token

   Indices and tables
   ==================
   * :ref:`genindex`
   * :ref:`modindex`
