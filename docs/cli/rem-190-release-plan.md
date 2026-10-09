# co rem 1.9.0 release plan

This is the historical plan for the **1.9.0** co rem release
([#1443](https://github.com/openonion/connectonion/issues/1443)). The
[1.9.0 release record](../releases/1.9.0.md) states what the 90-day public-wheel
trial, installed candidate, source review and browser checks actually proved.
The plan does not turn a sampled page or a source check into an all-page quality
claim. Follow-up work has a [1.9.1 milestone](https://github.com/openonion/connectonion/milestone/41).

## Release gate

Before proposing 1.9.0 stable, verify the complete user path with the built package: initialize an empty notebook; show source coverage and an accurate map; investigate one project, person, and Skill from retained evidence; check citations and unsupported claims; accept a correction and update the page without losing its structure; then view and export the results. Include cases where a mailbox is unavailable or a model run fails. Record model usage and quality findings as well as command exit status. Review sharing and source visibility before calling a page safe to hand to another person or AI.

The live failure in [#1628](https://github.com/openonion/connectonion/issues/1628) originally blocked acceptance: all three attempted real person pages failed to write. [#1634](https://github.com/openonion/connectonion/pull/1634) repaired the default model, post-init mail availability, and candidate/evidence validation. The same real-notebook flow then accepted 11 of 11 selected people pages, with retained candidates, material, and reviews. That is evidence for the repaired sample, not a guarantee about every page. The broader harness audit in [#1629](https://github.com/openonion/connectonion/issues/1629) remains a dependency review. Resolve its co rem-critical findings before declaring the harness path accepted; unrelated harness enhancements can ship separately.

## Scope and tracking

| Issue | Role in 1.9.0 |
| --- | --- |
| [#1443](https://github.com/openonion/connectonion/issues/1443) | Feature umbrella and release decision. |
| [#1523](https://github.com/openonion/connectonion/issues/1523), [#1616](https://github.com/openonion/connectonion/issues/1616) | Lifecycle and current init contract. The map phase uses no model; init then investigates the owner and every eligible mapped person, project, organisation and installed Skill in terminals, scripts and JSON runs. The foreground first run has no REM page or weekly quota stop; provider limits and model access still apply. See [the updated init contract](rem-init-contract.md). |
| [#1580](https://github.com/openonion/connectonion/issues/1580) | Product scenarios and experience criteria; not proof that every proposed interface is implemented. |
| [#1610](https://github.com/openonion/connectonion/issues/1610) | Question-driven investigation and model routing; validate actual result quality and cost. |
| [#1611](https://github.com/openonion/connectonion/issues/1611) | Attributed reflections, corrections, and incremental updates. |
| [#1520](https://github.com/openonion/connectonion/issues/1520) | Session capture/retention proposal; assess privacy and lifecycle before making it a default. |
| [#1625](https://github.com/openonion/connectonion/issues/1625) | WhatsApp source proposal, including opt-in group scope. Track separately from the minimum Codex/mail acceptance path. |
| [#1609](https://github.com/openonion/connectonion/issues/1609) | Friction and surprise design exploration; not a stable-release blocker unless an approved 1.9.0 requirement explicitly depends on it. |
| [#1628](https://github.com/openonion/connectonion/issues/1628) | Blocking real-person investigation failure. |
| [#1629](https://github.com/openonion/connectonion/issues/1629) | Harness dependency audit; resolve co rem-critical findings. |

The preview issues and old feature branch are historical evidence. The stable
release record names its own acceptance and remaining limits; it supersedes
this plan's assumptions about what a preview established.
