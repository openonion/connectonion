# install-connectonion

Install ConnectOnion and configure everything — package, project, keys, integrations — verified end to end.

## Install

```bash
co copy install-connectonion
# → .co/skills/install-connectonion/SKILL.md
```

(Chicken-and-egg note: this skill is for agents that set up ConnectOnion on
*other* machines/projects — a coding agent that already has `co` can copy it,
then walk a fresh environment through the whole setup.)

## Usage

```
/install-connectonion
```

The skill walks 6 steps, each verified before the next:

1. **Install** — `pip install connectonion`, verify with `co --version` + `co doctor`
2. **Project** — `co create --yes` (minimal/coder/browser/web-research/...) or `co init --yes`
3. **Model access** — managed keys via `co auth` (co/* models) OR own provider keys in `.env`
4. **Integrations** — optional `co auth google` / `co auth microsoft`
5. **Smoke test** — run a real 2-line agent and read the reply
6. **Report** — tell the user exactly what is configured

## See Also

- [Quickstart](../quickstart.md) — the human-facing version of the same flow
- [co auth](../cli/auth.md) — managed keys and OAuth integrations
- [co create](../cli/create.md) — templates and first-time global setup
- [Built-in Skills](README.md) — all copyable skills
