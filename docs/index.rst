gmail-archiver
==============

.. include:: badges.rst

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
   127.0.0.5 - - [17/May/2025 00:50:21] "GET /?code=...&scope=https://mail.google.com/ HTTP/1.1" 200 -
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
