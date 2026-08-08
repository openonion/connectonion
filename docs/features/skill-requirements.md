# Skill Runtime Requirements

A skill can declare what must already exist on the machine before it runs. The
manifest lives in `SKILL.md` frontmatter and is optional, so existing skills do
not need to change.

```yaml
---
name: send-report
description: Build and email the weekly report
requirements:
  version: 1
  required:
    python:
      - name: pandas
        version: ">=2.2,<3"
        setup: "Install with: pip install 'pandas>=2.2,<3'"
    executables:
      - name: wkhtmltopdf
        version: ">=0.12"
        setup: "Install wkhtmltopdf with your system package manager"
    environment:
      - name: REPORT_FROM_ADDRESS
        setup: "Set REPORT_FROM_ADDRESS in .env"
    oauth:
      - provider: google
        scopes: [gmail.send]
        setup: "Connect Google in co auth"
    capabilities:
      - name: outbound-network
        setup: "Allow HTTPS access to the mail provider"
  optional:
    python:
      - name: pyarrow
        version: ">=16"
        setup: "Install pyarrow for faster exports"
---

Build the report and send it.
```

`required` entries prevent safe execution when they are unavailable. `optional`
entries enable enhancements and never prevent the skill from running. Both
sections support these categories:

| Category | Identity field | Other fields |
| --- | --- | --- |
| `python` | `name` | `version`, `setup` |
| `executables` | `name` | `version`, `setup` |
| `environment` | `name` | `setup` |
| `oauth` | `provider` | `scopes`, `setup` |
| `capabilities` | `name` | `version`, `setup` |

`version` is a non-empty [PEP 440](https://packaging.python.org/en/latest/specifications/version-specifiers/)
constraint interpreted by the validator for that category. `setup` is an
actionable message shown to a human when the requirement is missing. OAuth
`scopes` is a list of non-empty scope names.

The manifest is strict. Unknown fields, wrong types, and unsupported schema
versions fail with the skill name and exact field, for example:

```text
Skill 'send-report': requirements.required.python[0].version: must be a non-empty string
```

Schema version `1` describes requirements only. It never installs packages,
starts an OAuth flow, probes the network, or changes the machine.

Platform runtimes advertise capabilities locally through the comma-separated
`CONNECTONION_CAPABILITIES` environment variable. When a capability has a
version constraint, its version is read from
`CONNECTONION_CAPABILITY_VERSIONS` as comma-separated `name=version` pairs.

The same local preflight runs after `co skills copy`, in `co doctor`, and when
`co ai` starts. Missing required entries stop that skill before its instructions
or temporary permissions are loaded. Missing optional entries are shown as
informational setup hints and do not stop the skill.

During deploy, required Python constraints from every project or explicitly
bundled skill are packaged into `.co/skill-python-requirements.txt` and installed
before the service starts. A successful installation records `pip freeze --all`
as the realized state; the request digest is advanced only afterwards, so a
failed installation is retried by the next deploy. Required executables and
platform capabilities are not installed automatically and stop deploy with the
skill's setup hint. Optional dependencies remain informational.
