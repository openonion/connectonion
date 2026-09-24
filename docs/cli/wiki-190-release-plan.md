# Personal Wiki 1.9.0 release plan

The Personal Wiki feature release targets **1.9.0** ([#1443](https://github.com/openonion/connectonion/issues/1443)). Published `1.8.8b1` remains immutable; `1.8.8b3` is a later preview candidate. Neither preview declares the Wiki ready for a stable release. `VERSIONING.md` names the version of the checked-out candidate, which becomes public only after review and tagging.

## Release gate

Before proposing 1.9.0 stable, verify the complete user path with the built package: initialize an empty notebook; show source coverage and an accurate map; investigate one project, person, and Skill from retained evidence; check citations and unsupported claims; accept a correction and update the page without losing its structure; then view and export the results. Include cases where a mailbox is unavailable or a model run fails. Record model usage and quality findings as well as command exit status. Review sharing and source visibility before calling a page safe to hand to another person or AI.

The live failure in [#1628](https://github.com/openonion/connectonion/issues/1628) originally blocked acceptance: all three attempted real person pages failed to write. [#1634](https://github.com/openonion/connectonion/pull/1634) repaired the default model, post-init mail availability, and candidate/evidence validation. The same real-notebook flow then accepted 11 of 11 selected people pages, with retained candidates, material, and reviews. That is evidence for the repaired sample, not a guarantee about every page. The broader harness audit in [#1629](https://github.com/openonion/connectonion/issues/1629) remains a dependency review. Resolve its Wiki-critical findings before declaring the harness path accepted; unrelated harness enhancements can ship separately.

## Scope and tracking

| Issue | Role in 1.9.0 |
| --- | --- |
| [#1443](https://github.com/openonion/connectonion/issues/1443) | Feature umbrella and release decision. |
| [#1523](https://github.com/openonion/connectonion/issues/1523), [#1616](https://github.com/openonion/connectonion/issues/1616) | Lifecycle and current init contract. Where the older lifecycle sketch conflicts with the later decision, init builds the map and stops before investigation. |
| [#1580](https://github.com/openonion/connectonion/issues/1580) | Product scenarios and experience criteria; not proof that every proposed interface is implemented. |
| [#1610](https://github.com/openonion/connectonion/issues/1610) | Question-driven investigation and model routing; validate actual result quality and cost. |
| [#1611](https://github.com/openonion/connectonion/issues/1611) | Attributed reflections, corrections, and incremental updates. |
| [#1520](https://github.com/openonion/connectonion/issues/1520) | Session capture/retention proposal; assess privacy and lifecycle before making it a default. |
| [#1625](https://github.com/openonion/connectonion/issues/1625) | WhatsApp source proposal, including opt-in group scope. Track separately from the minimum Codex/mail acceptance path. |
| [#1609](https://github.com/openonion/connectonion/issues/1609) | Friction and surprise design exploration; not a stable-release blocker unless an approved 1.9.0 requirement explicitly depends on it. |
| [#1628](https://github.com/openonion/connectonion/issues/1628) | Blocking real-person investigation failure. |
| [#1629](https://github.com/openonion/connectonion/issues/1629) | Harness dependency audit; resolve Wiki-critical findings. |

The feature branch and draft [PR #1454](https://github.com/openonion/connectonion/pull/1454) remain the integration point. Issues and preview releases are evidence of work in progress, not a claim that the full 1.9.0 behavior has passed acceptance.
