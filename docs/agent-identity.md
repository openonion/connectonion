# Agent identity and the account that pays

The signing key determines an agent's address. The managed-model token determines
the account billed for a call. An `AGENT_ADDRESS` env value records an address; it
does not replace the signing key. Read these sources separately when diagnosing
a mismatch.

## Global configuration in the 1.8.4 candidate

`co init` initializes the designated global directory, normally `~/.co/`.
`AGENT_CONFIG_PATH`, explicitly inherited from the process, selects another global
directory. Its `keys/agent.key` holds the global signing identity and `keys.env`
holds settings. Changing working directory does not select a different identity
or load a project's `.env`.

Use `co --env-file /path/to/app.env …` to select another env file explicitly.
Inherited process values take precedence; Google/Microsoft credentials resolve as
whole records, so missing fields never borrow another account's tokens. With explicit env selection, CLI identity readers use an existing key in the
selected file's adjacent `.co/` directory, falling back to the designated global
identity if no key exists there. A deployed service sets its own
`AGENT_CONFIG_PATH` and therefore uses the key on that server.

Explicit project creation remains available with `co create` or `co init ./`.
It does not make project `.env` loading automatic. Old instructions that said
`co create` copied all personal credentials and every deploy forwarded them
wholesale describe the previous behavior.

## Read the live address

Query the actual configured Host endpoint:

```bash
curl --fail --silent --show-error http://localhost:8000/info \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["address"])'
```

Use the real port on a remote service. Hostnames, `servers.yaml`, and env address
notes can be stale. `address.load(co_dir)` requires an explicit directory and
computes the address from its key. `AGENT_EMAIL` and `IS_EMAIL_ACTIVE` affect email
metadata; they do not choose that key.

## Inspect the token's account

Run this in the same environment as the process being diagnosed. It only prints
account identifiers and balance, never the JWT or recovery material. The decoded
claim is diagnostic, not signature verification; the authenticated GET verifies
the account at the configured backend.

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

`co status` authenticates the selected signing identity and shows that
identity's account. It is not proof that a separately supplied model token bills
the same account. `POST /api/v1/auth` can create an account, so use the read-only
GET above when checking an existing token. Do not hardcode a production backend
when diagnosing a development or self-hosted installation.

## Deployment and recovery

`co deploy --to` derives a candidate key from the operator's recovery phrase and
normalized agent name using SLIP-0013 `agent://<name>`. An existing server key is
preserved. `--own-identity` creates the key on the server when no key exists; it
does not rotate an existing identity.

After setup, deploy authenticates **the key actually held by the server**, including
legacy or independently created keys. That account supplies the managed-model
token and email metadata. The key never returns to the workstation. When remote
authentication fails, deploy removes operator identity metadata and explains that
managed models still need authentication; it does not fall back to billing the
operator.

Default deployment reads selected global app configuration and filters personal
provider credentials and operator identity. An explicit `--env-file` opts into
deploying that file's provider credentials. Operator identity fields are still
replaced by the server account. Keep intentional credentials in the selected
source; editing only the generated server EnvironmentFile is undone on redeploy.

The same normalized name and recovery phrase derive the same candidate key.
Two live hosts can therefore share an address while keeping separate delivery
ledgers and business state. Verify both endpoints and their deployment history;
the shared address alone neither proves a compromise nor proves the hosts should
both run. Establish which service should remain active with the owner before
stopping either one.

A live address differing from a newly derived candidate may simply mean deploy
preserved an older key. Do not delete a working key to make the addresses agree.
Back up recovery material securely; an independently generated or legacy key may
not be recoverable from the current derivation scheme. Never print a recovery
phrase, private key, or token into a diagnostic report.

## See also

- [Key derivation](key-derivation.md)
- [Deployment](network/deploy.md)
- [Agent identity skill](useful_skills/agent-identity.md)
