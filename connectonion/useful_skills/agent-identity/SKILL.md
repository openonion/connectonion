---
name: agent-identity
description: Verify an agent's live address and billing account before sharing a chat link, diagnosing a deploy mismatch, or deciding why two hosts share an identity.
---

# Agent identity

Read the signing identity, model payer, and env metadata from their own sources.
Never print tokens, private keys, or recovery phrases in diagnostics.

## 1. Verify the live agent

Query the configured Host `/info` endpoint and read `address`. Use the actual
service port, not an assumed hostname or a copied `AGENT_ADDRESS` value.

```bash
curl --fail --silent --show-error http://localhost:8000/info \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["address"])'
```

The key determines the address. `AGENT_EMAIL` and `IS_EMAIL_ACTIVE` are email
metadata. Env address notes, server inventories, and DNS names can be stale.

## 2. Check the selected account

All env settings default to `$AGENT_CONFIG_PATH/keys.env`, normally `~/.co/keys.env`.
Entering a project never loads its `.env`. `co --env-file /path/to/app.env …`
explicitly selects a different file; inherited process settings win. With explicit selection, CLI identity readers use an existing key in the file's
adjacent `.co/`, falling back to the global key when it has none. `co init` initializes global configuration;
project creation requires `co create` or an explicit `co init ./`.

Run this diagnostic in the target process's environment. Decoding alone does not
verify a JWT. The GET checks the same backend used by auth and models, refuses
redirects, and prints only the account and balance.

```python
import base64
import json
import os
from pathlib import Path
import requests
from connectonion.backend import backend_url
from connectonion.environment import load_environment, select_env_file

# Optional explicit selection, equivalent to co --env-file /path/to/app.env:
# select_env_file(Path("/path/to/app.env"))
load_environment()
token = os.environ.get("OPENONION_API_KEY")
if not token:
    raise SystemExit("No managed-model token in the selected environment")
try:
    payload = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    print("Token account (unverified claim):", claims["public_key"])
except (IndexError, KeyError, ValueError, UnicodeError):
    raise SystemExit("Token is not a decodable account JWT; do not print it") from None

# Resolve the same backend as auth/models. Never put a token in shell arguments.
response = requests.get(
    f"{backend_url()}/api/v1/auth/me",
    headers={"Authorization": f"Bearer {token}"},
    timeout=15,
    allow_redirects=False,
)
if response.status_code != 200:
    raise SystemExit(f"Account lookup failed (HTTP {response.status_code})")
account = response.json()
print("Verified account:", account.get("public_key"))
print("Balance:", account.get("balance_usd"))
```

`co status` authenticates the selected signing identity, which may differ from a
separately supplied model token. `POST /api/v1/auth` may create a new account;
do not use it just to inspect an existing token.

## 3. Explain a deploy mismatch

Deployment derives a candidate from the normalized name and operator phrase, but
preserves an existing server key. `--own-identity` creates a server-owned key only
when none exists. The deployment authenticates the live server key and uses its
account token/email; a different derived candidate is not a reason to delete it.

Default deployment filters global personal provider credentials and operator
identity. An explicit env file opts into that file's provider credentials; operator
identity still comes from the live server account. If authentication fails, deploy
does not substitute the operator's account. Check its failure output and repair
the intended account through the normal auth workflow after obtaining approval.

## 4. Investigate duplicate hosts

The same name and phrase can produce one key on two machines. Compare live `/info`
addresses, deployment records, and business-state timestamps. Separate hosts can
repeat work because their delivery ledgers are separate. Agree which instance
should run before stopping either one; never infer that one is disposable from
the address alone.

Report the live address, selected env source, token account, configured backend,
and evidence for any mismatch. Omit all secret values. Keep corrections in the
selected deployment source so a later deploy does not undo them.

## References

- `docs/agent-identity.md`
- `docs/key-derivation.md`
- `docs/network/deploy.md`
