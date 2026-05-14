# Test Organization Principles

*Keep simple things simple, make complicated things possible*

## Test Strategy

Two layers — **unit** and **e2e**. No separate "integration" layer.

- A test either exercises one source file in isolation (mocked deps) → `tests/unit/`
- Or it exercises a real flow end-to-end (real protocol, real I/O, possibly real APIs) → `tests/e2e/`

CLI and real-API tests are subtypes of e2e and live under `tests/e2e/cli/` and `tests/e2e/real_api/`. They keep their own markers (`cli`, `real_api`) for filtering.

## Folder Structure

```
tests/
├── unit/                       # fast, deps mocked
├── e2e/
│   ├── real_api/               # real LLM/API calls — requires keys, costs money
│   ├── cli/                    # real `co` CLI invocations
│   ├── manual/                 # demo scripts (not collected by pytest)
│   └── test_*.py               # offline workflows (relay, deploy, example agent)
├── fixtures/                   # shared test data
└── utils/                      # MockLLM, ProjectHelper, etc.
```

## Markers

Auto-applied by folder in `tests/conftest.py`:

| Folder | Markers added |
|---|---|
| `tests/unit/` | `unit` |
| `tests/e2e/` | `e2e` |
| `tests/e2e/cli/` | `e2e`, `cli` |
| `tests/e2e/real_api/` | `e2e`, `real_api` |

Additional opt-in markers: `slow`, `network`, `deploy`, `e2e_online`.

Default `pytest` invocation excludes `real_api` and `network` (see `pytest.ini` `addopts`).

## Decision Tree

```
Does the test exercise ONE source file with all deps mocked?
  ├─ YES → tests/unit/test_<file>.py
  └─ NO (multi-module / real I/O / full workflow)
      ├─ Real LLM API call?  → tests/e2e/real_api/test_*.py
      ├─ Real `co` CLI?      → tests/e2e/cli/test_cli_*.py
      └─ Offline workflow?   → tests/e2e/test_*.py
```

## Running

```bash
pytest                              # default: unit + e2e (no real_api, no network)
pytest -m unit                      # only unit
pytest -m e2e                       # all e2e (cli + real_api + offline)
pytest -m cli                       # only e2e/cli
pytest -m real_api                  # only e2e/real_api (needs API keys)
pytest tests/unit/test_agent.py     # single file
```

## Naming Conventions

- `tests/unit/test_*.py` — one file per source file when possible
- `tests/e2e/test_*.py` — offline end-to-end
- `tests/e2e/cli/test_cli_*.py` — CLI commands
- `tests/e2e/real_api/test_real_*.py` — real API integration

## Notes

- Prefer unit tests over e2e — they catch most bugs at <1s each
- Real API tests cost money — only add when you can't unit-test the failure mode
- Test functional behavior, not implementation details (no `_event_type ==` / `len(plugin) == N` style assertions)
