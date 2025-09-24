local utils = import 'utils.libjsonnet';

{
  description: 'Locally archive Gmail emails.',
  keywords: ['backup', 'email', 'google', 'gmail'],
  project_name: 'gmail-archiver',
  version: '0.0.4',
  want_main: true,
  copilot+: {
    intro: 'gmail-archiver is a tool to locally archive Gmail emails.',
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
      poetry+: {
        dependencies+: {
          platformdirs: utils.latestPypiPackageVersionCaret('platformdirs'),
          requests: utils.latestPypiPackageVersionCaret('requests'),
          tomlkit: utils.latestPypiPackageVersionCaret('tomlkit'),
        },
        group+: {
          dev+: {
            dependencies+: {
              'types-requests': utils.latestPypiPackageVersionCaret('types-requests'),
            },
          },
          tests+: {
            dependencies+: {
              'requests-mock': utils.latestPypiPackageVersionCaret('requests-mock'),
            },
          },
        },
      },
    },
  },
}
