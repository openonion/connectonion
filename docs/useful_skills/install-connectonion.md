# install-connectonion

Install ConnectOnion and configure everything — Python check, package, project, keys —
verified end to end, then hand the user a plain-language account summary. Built to be run
**for a non-technical person**: it auto-corrects failures instead of dumping errors.

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

The skill walks 6 steps, each verified before the next, and self-corrects on failure:

1. **Check Python** — requires 3.10+; sets up a virtualenv when it helps
2. **Install** — `pip install connectonion`, verify with `co --version` + `co doctor`
3. **Project** — `co create --yes` (minimal/coder/browser/web-research/...) or `co init --yes`
4. **Model access** — managed keys via `co auth` (co/* models, comes with free credit) OR own provider keys in `.env`
5. **Verify** — run a real 2-line agent and read the reply
6. **Summary** — a friendly, plain-language account report: free credit, balance, agent email, what's installed

## Built for non-technical users

Two things make this skill different from a plain command list:

- **Auto-correction.** Every step has a *Recovery* block. When something fails — `co` not
  on PATH, a hung interactive prompt, a wrong virtualenv, an out-of-credit account — the
  agent diagnoses it, applies the known fix, and retries (up to 2 attempts) instead of
  stopping and pasting a stack trace. It only asks the human for things only a human can
  do (browser login, adding credit).

- **A real end-of-run UI.** Step 6 turns `co status` into a warm summary the person
  actually understands:

  ```
  ✅ You're all set up! Here's your ConnectOnion account:

    🎁  Free credit ConnectOnion gave you:  $X.XX
    💰  Money available to use now:          $X.XX
    📧  Your agent's email address:          you@mail.openonion.ai
    🤖  Model access:                        managed (co/* models)
    📦  Installed:                           connectonion vX.Y.Z
    📁  Your project:                        ./my-agent  (minimal template)
  ```

  Low or `$0` balance is stated gently with the top-up link — never as an alarm.

## See Also

- [Quickstart](../quickstart.md) — the human-facing version of the same flow
- [co auth](../cli/auth.md) — managed keys and OAuth integrations
- [co create](../cli/create.md) — templates and first-time global setup
- [co status](../cli/status.md) — the account fields the summary is built from
- [Built-in Skills](README.md) — all copyable skills
