# co trust

Manage who can call one agent. With no flags, commands use the project's `.co`
(found from the current directory, including project subdirectories).
`co trust` alone lists that agent's trust lists.

Every subcommand accepts the same target options after its name:

| Option | Target |
| --- | --- |
| `--co-dir <directory>` | The directory containing the Host's trust lists; use the exact directory printed by the Host |
| `--global`, `-g` | Your global identity: `~/.co`, used by `co ai` and `co handoff` |

`--global` is shorthand for `--co-dir ~/.co`. If `AGENT_CONFIG_PATH` selects
another global identity directory, `--global` follows it. Choose one target
option; combining `--global` with `--co-dir` is a usage error. Relative paths
and `~` are supported. Quote paths containing spaces.

## Commands

Replace `<address>` with the full `0x` address shown by `list`.

| Command | Effect | Example targeting the global identity |
| --- | --- | --- |
| `list` | Show admins, whitelist, handoffs, contacts and blocked addresses | `co trust list --global` |
| `level <address>` | Show current trust and file paths | `co trust level <address> --global` |
| `add <address>` | Add a contact | `co trust add <address> --global` |
| `add <address> -w` | Add to the whitelist | `co trust add <address> -w --global` |
| `remove <address>` | Remove contact and whitelist membership | `co trust remove <address> --global` |
| `block <address>` | Deny access, with optional `--reason` | `co trust block <address> --reason spam --global` |
| `unblock <address>` | Remove the block; other memberships and Host policy decide access | `co trust unblock <address> --global` |
| `admin add <address>` | Grant admin access | `co trust admin add <address> --global` |
| `admin remove <address>` | Remove an added admin (the identity's own address remains admin) | `co trust admin remove <address> --global` |

For a Host with its own identity directory, use that same target throughout:

```sh
co trust list --co-dir /srv/agent/.co
co trust block <address> --co-dir /srv/agent/.co
co trust level <address> --co-dir /srv/agent/.co
co trust unblock <address> --co-dir /srv/agent/.co
```

The next-action tips from `level` retain your selected directory. `remove`
leaves blocks and admins unchanged. Removing a contact or whitelist entry does
not deny strangers under an open policy; use `block` to deny access.
Live revocation takes effect on the requester's next frame, when the Host
rejects the request and asks running work to stop cooperatively. A requester
who has disconnected sends no frame, so the Host also re-checks trust before
every tool or model step of their turn and stops it there. A step already
running finishes first. Every edit (`add`, `remove`, `block`, `unblock`,
`admin add/remove`) prints `Updated: <file>` for each list it wrote, and
`level` prints the files it read.
