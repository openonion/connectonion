# Synology tool

`Synology()` uses the selected global NAS profile created by verified
`co syno login`. `Synology(nas="office")` selects another profile. It does not
silently import old `SYNOLOGY_*` env fields. Explicit SDK URL/account/password
arguments form an ephemeral connection and never inherit a saved SID.

```python
from connectonion import Synology

nas = Synology(nas="home", timeout=60)
page = nas.list_page("/home/docs", limit=20)
record = nas.info("/home/docs/report.pdf")
result = nas.download("/home/docs/report.pdf", "./Downloads/")
```

Public operations receive one waiting budget per call, shared by their nested
requests. Synchronous SNMP inspection in an async application must run in a
worker thread. The CLI uses one fixed budget per invocation.

| Method | Result |
| --- | --- |
| `connectivity()` | Verified File Station hostname/access and client request timing |
| `status()` | Aggregate checks with explicit partial coverage |
| `network_status()` | Client connectivity and source-labeled NAS interfaces |
| `storage_status()` / `storage_disks()` | Available SNMPv3 capacity/status/disk indicators |
| `service_list(running=False)` | Actual SSH service enumeration |
| `list_page(path="/", limit=20, cursor=None, sort="name", order="asc")` | Live page, cursor and frozen listing ID |
| `list_files(path=None, last=20)` | First live page as a list |
| `info(path)` | One complete NAS path |
| `search_page(query, path, glob=False, kind="all", limit=20, cursor=None)` | Completed and cleaned search snapshot |
| `search_files(query, path, last=20)` | First search page as a list |
| `download(path, dest=".", recursive=False, overwrite=False, skip_existing=False, dry_run=False)` | Transfer plan and completed/skipped/failed evidence |
| `upload(local_path, path, overwrite=False, recursive=False, skip_existing=False, dry_run=False)` | Transfer into an existing NAS directory |
| `mkdir(path, parents=False, dry_run=False)` | Ordinary directory plan/completions |
| `copy(source, destination, recursive=False, overwrite=False, dry_run=False)` | Durable copy workflow |
| `move(source, destination, overwrite=False, dry_run=False)` | Durable move/rename workflow |
| `operation_status(identifier, wait=False)` | Observe the same task; never submit new writes |
| `share_create(path, expires=None, no_expiry=False, password=None, dry_run=False)` | Explicitly restricted link creation |
| `share_list(limit=20, cursor=None, show_url=False)` | Link inventory; URLs opt in |
| `share_revoke(identifier, dry_run=False)` | Revoke only the selected link |
| `logout()` | Clear local auth, retain settings and report remote invalidation |

The Python API assumes the caller already authorized a write; human confirmation
is a CLI concern. SDK `share(path, expires=..., no_expiry=...)` remains a URL-returning
convenience but now requires an explicit expiry choice. `list_sharing_links`
defaults to masking URLs. Transfer methods now return structured evidence rather
than confirmation strings.

See the [CLI guide](../cli/synology.md) for profiles, adapter onboarding,
path/race boundaries, migration changes, pending operations and the live
acceptance limitation.
