# Security policy

## Reporting a vulnerability

Please do not report security vulnerabilities in public GitHub issues,
discussions, pull requests or Discord channels.

Report them privately through GitHub security advisories:

1. Open the repository's
   [Security tab](https://github.com/openonion/connectonion/security).
2. Choose **Report a vulnerability** and fill in the form.

Only the maintainers can see the report, and the conversation, the fix and the
eventual advisory all stay in that private thread until we publish.

If the **Report a vulnerability** button is not shown, open a public issue
titled "Security contact request", with no details of the problem. A
maintainer will open a private draft advisory and invite you to it, and you
can describe the issue there.

## What to include

- the ConnectOnion version (`co --version`) and your operating system;
- the command, code or configuration that triggers the problem;
- what an attacker gains: for example reading credentials from
  `~/.co/keys.env`, running commands without approval, or calling a hosted
  agent they should not reach;
- whether you have seen it exploited.

## What happens next

A maintainer acknowledges the report in the advisory thread, confirms whether
it reproduces, and agrees a disclosure date with you. Fixes ship in a stable
patch release; the advisory is published with the release, and reporters are
credited unless they ask not to be.

## Supported versions

Security fixes go to the current stable line (1.8.x, see
[docs/releases.md](docs/releases.md)) and to the next preview release. If you
run an older version, upgrade to the latest stable release first and check
whether the problem still reproduces.
