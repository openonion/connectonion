# Release Visual Evidence

Screenshots proving a release's user-visible changes are part of the release,
not an expiring CI artifact (#1124). A user opening a GitHub Release or a
Design Journal entry must be able to see what visibly changed without
starting O Chat or downloading an Actions artifact that died two weeks ago.

## The manifest

Every release **with user-visible changes** commits a reviewed set under:

```text
docs/releases/assets/vX.Y.Z/
  manifest.yml
  control-center-desktop.webp
  work-room-approval-mobile.webp
  cli-template-to-deploy.webp
```

A backend-only patch commits a manifest with an explicit exemption instead —
absence of the directory is a failed release check, never a shrug.

### manifest.yml shape

```yaml
version: v1.6.12
# EITHER an explicit reviewed exemption:
no_visual_change: "backend-only patch: LLM network bounds and Outlook CLI fixes"
# OR the image set:
images:
  - file: control-center-desktop.webp
    alt: "Control Center showing three permission profiles"
    caption: "The Control Center now names the active permission profile."
    scenario: "operator opens dashboard after co deploy --to prod"
    viewport: "1440x900, light"
    commit: 25fefdf8
    source_run: "https://github.com/openonion/oo-chat/actions/runs/<id>"
```

Required per image: `file`, `alt`, `caption`, `scenario`, `viewport`,
`commit`, `source_run`. The file must exist beside the manifest, be
non-empty, and stay under 2 MB — optimize without making text unreadable.

### What the set contains

1. **Hero** — the main outcome.
2. **Narrow/mobile** (375–390 px) where applicable.
3. **Critical interaction** — approval, reconnect, running state — when one changed.
4. **Before / After** — required when an existing surface changes materially.
5. **CLI/terminal capture** — only when the release's primary change is a CLI workflow.

Never publish raw prompts, credentials, invite codes, private local paths,
reasoning traces, or customer data. The reviewer of the release PR reviews
the captions and the images, not just the code.

## Validation

```bash
python scripts/check_release_visuals.py vX.Y.Z
```

Run it before tagging (it is part of the release checklist in
VERSIONING.md). It fails when the directory is missing, when a listed file
is absent/empty/oversized, when required metadata is missing, and when a
manifest claims both `no_visual_change` and `images`.

## Immutability

A published version's evidence is append-only: retrying a release run may
repair a missing asset, but replacing reviewed images with unrelated output
is a review failure, the same as force-pushing a tag. CI artifacts remain
the full QA record; this directory is the small, reviewed, permanent subset.
