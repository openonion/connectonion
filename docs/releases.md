# Release channels

ConnectOnion has two release channels:

- **Stable** is the default `pip install connectonion` channel. It is the version
  recommended for production agents.
- **Preview** contains alpha, beta, and release-candidate builds for features
  that are still being exercised end to end. Install one explicitly, for
  example: `pip install connectonion==1.7.0a1`.

Preview releases never replace the stable recommendation on the documentation
site, and GitHub marks them as pre-releases rather than latest releases.

## Design Journal

Release notes record what changed. A Design Journal post records the problem,
alternatives, decision, tradeoffs, evidence, and what would make us revisit it.
Meaningful feature-train launches, the first beta and RC, stable releases, and
material architecture or workflow decisions receive a new or substantially
updated post.

Maintenance-only patches stay in release history unless they contain a reusable
design lesson. Drafts can be prepared with the candidate, but the public post
must not claim that a version is available until PyPI and its GitHub Release are
visible.

The current release-train decision is documented in
[Why Alpha, Beta, and RC Come Before ConnectOnion 1.7 LTS](https://docs.connectonion.com/blog/alpha-beta-rc-before-lts).
