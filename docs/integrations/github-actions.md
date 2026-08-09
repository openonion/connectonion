# GitHub Actions PR review

ConnectOnion ships a composite action that runs the bundled `review-pr` skill,
consumes `co ai --json`, and creates or updates one pull-request comment.

## Safe default: maintainer-triggered review

Add the model credential as an Actions secret, then trigger the included
**ConnectOnion PR review** workflow from the default branch and provide a pull
request number. The workflow grants only:

```yaml
permissions:
  contents: read
  pull-requests: read
  checks: read
  statuses: read
  issues: write
```

The workflow never checks out the pull-request branch. It checks out the
default branch and runs `uses: ./`, so the action implementation comes from
trusted code. Rerunning it updates the existing bot comment instead of adding a
new comment.

## Use from another repository

```yaml
name: ConnectOnion PR review

on:
  workflow_dispatch:
    inputs:
      pr_number:
        required: true
        type: number

permissions:
  contents: read
  pull-requests: read
  checks: read
  statuses: read
  issues: write

concurrency:
  group: co-ai-review-${{ inputs.pr_number }}
  cancel-in-progress: false

jobs:
  review:
    if: github.ref == format('refs/heads/{0}', github.event.repository.default_branch)
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: openonion/connectonion@RELEASE_COMMIT_SHA
        with:
          pr-number: ${{ inputs.pr_number }}
        env:
          OPENONION_API_KEY: ${{ secrets.OPENONION_API_KEY }}
```

Pin the action to the full commit SHA for the ConnectOnion release you audited.
You may also pass `model` or `python-version`; the defaults are suitable for the
managed model.

## Security boundary

The pull-request diff is untrusted input. The Action therefore does not expose
the normal `co ai` shell, file, browser, or GitHub-write tools to the model. Its
only tool performs fixed GET requests for the selected PR's metadata,
discussion (including inline review comments), checks, commit statuses, and
diff. Comment creation happens afterward in ordinary Python code; the model
cannot choose its endpoint or HTTP method.

The review reads GitHub data and existing check results. It does not check out
or execute pull-request code. This is intentional: a model credential and an
untrusted branch must not share an unrestricted runner. GitHub's own API limits
still apply to very large diffs.

Do not change the workflow to `pull_request_target` and then check out the pull
request branch. That event has access to base-repository secrets. Ordinary fork
`pull_request` workflows do not receive model secrets and get a read-only
`GITHUB_TOKEN`. This Action's restricted reader avoids needing a secret-bearing
checkout of the fork.

Credentials are inherited as environment variables. The action never places a
model key in its command line, outputs, or PR comment.

Keep the per-PR `concurrency` group shown above. GitHub's issue-comment API has
no atomic upsert operation; serializing reruns prevents two first runs from
creating duplicate marker comments.
