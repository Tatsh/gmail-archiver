(import 'defaults.libjsonnet') + {
  // Project-specific
  description: 'Locally archive Gmail emails.',
  keywords: ['backup', 'email', 'google', 'gmail'],
  project_name: 'gmail-archiver',
  version: '0.0.3',
  want_main: true,
  citation+: {
    'date-released': '2025-05-16',
  },
  pyproject+: {
    project+: {
      scripts: {
        'gmail-archiver': 'gmail_archiver.main:main',
      },
    },
    tool+: {
      poetry+: {
        dependencies+: {
          platformdirs: '^4.3.8',
          requests: '^2.32.3',
          tomlkit: '^0.13.2',
        },
        group+: {
          dev+: {
            dependencies+: {
              'types-requests': '^2.32.0.20250306',
            },
          },
          tests+: {
            dependencies+: {
              'requests-mock': '^1.12.1',
            },
          },
        },
      },
    },
  },
  // Common
  authors: [
    {
      'family-names': 'Udvare',
      'given-names': 'Andrew',
      email: 'audvare@gmail.com',
      name: '%s %s' % [self['given-names'], self['family-names']],
    },
  ],
  local funding_name = '%s2' % std.asciiLower(self.github_username),
  github_username: 'Tatsh',
  github+: {
    funding+: {
      ko_fi: funding_name,
      liberapay: funding_name,
      patreon: funding_name,
    },
  },
  mastodon_id: '109370961877277568',
}
