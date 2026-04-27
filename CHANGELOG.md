<!-- markdownlint-configure-file {"MD024": { "siblings_only": true } } -->

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.1/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [unreleased]

## [0.1.0] - 2026-04-27

### Changed

- Migrated from synchronous to asynchronous architecture. Public API functions
  (`archive_emails`, `authorize_tokens`, `refresh_token`) are now coroutines and must be awaited.
  HTTP requests now use `niquests` instead of `requests`, and IMAP operations use `aioimaplib`
  instead of the standard library IMAP client. The CLI entry point remains synchronous and bridges
  to the async implementation internally.

### Fixed

- Restored the IMAP connection debug level after `archive_emails` when debug mode is enabled.

## [0.0.5]

### Added

- Attestation.

## [0.0.4]

### Fixed

- Handle file collisions.

## [0.0.2]

### Added

- Added `-D`/`--days` option.

## [0.0.1] - 2025-00-00

First version.

[unreleased]: https://github.com/Tatsh/gmail-archiver/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Tatsh/gmail-archiver/compare/v0.0.5...v0.1.0
[0.0.5]: https://github.com/Tatsh/gmail-archiver/compare/v0.0.4...v0.0.5
[0.0.4]: https://github.com/Tatsh/gmail-archiver/compare/v0.0.3...v0.0.4
[0.0.2]: https://github.com/Tatsh/gmail-archiver/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/Tatsh/gmail-archiver/releases/tag/v0.0.1
