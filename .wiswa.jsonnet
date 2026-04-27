local utils = import 'utils.libjsonnet';

{
  uses_user_defaults: true,
  description: 'Locally archive Gmail emails.',
  keywords: ['backup', 'email', 'google', 'gmail'],
  project_name: 'gmail-archiver',
  version: '0.1.0',
  want_main: true,
  want_flatpak: true,
  publishing+: { flathub: 'sh.tat.gmail-archiver' },
  tests_pyproject+: {
    tool+: {
      ruff+: {
        lint+: {
          'extend-ignore'+: ['ASYNC240', 'RUF029'],
        },
      },
    },
  },
  pyproject+: {
    project+: {
      scripts: {
        'gmail-archiver': 'gmail_archiver.main:main',
      },
    },
    tool+: {
      coverage+: {
        report+: { omit+: ['typing.py'] },
        run+: { omit+: ['typing.py'] },
      },
      pytest+: {
        ini_options+: {
          asyncio_mode: 'auto',
        },
      },
      ruff+: {
        lint+: {
          'per-file-ignores'+: {
            'gmail_archiver/main.py'+: ['PLR0914'],
          },
        },
      },
      poetry+: {
        dependencies+: {
          aioimaplib: utils.latestPypiPackageVersionCaret('aioimaplib'),
          anyio: utils.latestPypiPackageVersionCaret('anyio'),
          niquests: utils.latestPypiPackageVersionCaret('niquests'),
          platformdirs: utils.latestPypiPackageVersionCaret('platformdirs'),
          tomlkit: utils.latestPypiPackageVersionCaret('tomlkit'),
        },
        group+: {
          tests+: {
            dependencies+: {
              'pytest-asyncio': utils.latestPypiPackageVersionCaret('pytest-asyncio'),
              mock: utils.latestPypiPackageVersionCaret('mock'),
            },
          },
        },
      },
    },
  },
}
