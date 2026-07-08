# Tests

Pytest suite for `earthscope-positions`. Every test runs **offline** — no
network, no EarthScope VPN, no reading of `~/.earthscope/tokens.json`. The two
API surfaces are spoofed at their natural boundaries.

## Running

```bash
# from the repo root, using the project venv
venv/bin/python -m pytest

# or install the test extras into any environment
pip install -e ".[test]"
pytest
```

## How the API is spoofed

There are two different clients in this codebase, so there are two spoofing
mechanisms (all fixtures live in [`conftest.py`](conftest.py)):

### 1. Position download — `requests` → `responses`

`earthscope_positions.fetch.positions_fetch` calls the REST endpoint directly
with `requests.get(_API_BASE, ...)`. Tests intercept it at the HTTP layer with
the [`responses`](https://github.com/getsentry/responses) library via the
`mock_positions_api` fixture:

```python
def test_something(project_tree, mock_positions_api):
    mock_positions_api.get(
        positions_fetch._API_BASE,
        body=make_positions_arrow(50),          # synthetic Arrow payload
        status=200,
        content_type="application/vnd.apache.arrow.stream",
    )
    status = positions_fetch._fetch_one_day(...)
```

Any request to a URL you didn't register **raises**, so a test can never
silently hit the real API. Use `mock_positions_api.calls` to assert on the
outgoing request (URL params, auth header).

### 2. Station discovery — SDK → fake `DiscoverApi`

`earthscope_positions.stations.station_list` goes through the generated
`earthscope_client` SDK (urllib3 under the hood). Rather than hand-craft nested
SDK response models, the `fake_discover_api` fixture swaps the API-client
factory (`_make_api`) for a configurable `FakeDiscoverApi`:

```python
def test_something(fake_token, fake_discover_api):
    fake_discover_api.datasource_pages = [
        ([{"edid": "E1", "geosncl": "P100.CI.LY_.20",
           "facility": "caltech", "software": "jpl_ppp"}], False),
    ]
    records = station_list._get_datasource(args)
```

Records are plain dicts (`edid`, `geosncl`, `facility`, `software`);
`facility`/`software` values must be valid `Facility`/`StreamSoftware` enum
members. Inspect `fake_discover_api.datasource_calls` / `.radial_calls` to
assert the SDK was called with the right arguments.

### Auth and filesystem

- `fake_token` — makes `_ensure_token()` return a dummy token in both modules,
  so nothing shells out to `es user login` or reads real credentials.
- `project_tree` — `chdir`s into an isolated tmp project root (with a
  `pyproject.toml` and `data/` tree). The fetch code resolves its data
  directory by walking up to the nearest `pyproject.toml`, so this keeps all
  writes inside tmp and lets tests assert on the files produced.

## Fixtures / helpers reference

| Name                    | Purpose                                                        |
|-------------------------|----------------------------------------------------------------|
| `mock_positions_api`    | `responses` mock scoped to the positions REST endpoint         |
| `fake_discover_api`     | Configurable stand-in for the SDK `DiscoverApi`                 |
| `fake_token`            | Stub `_ensure_token()` in both API modules                     |
| `project_tree`          | Isolated tmp project root (cwd + `data/`)                       |
| `positions_arrow_bytes` | Ready-made 10-row Arrow payload                                 |
| `make_positions_arrow(...)` | Build Arrow IPC bytes matching the real positions schema   |

## Note on the moved repo

The venv's editable-install pointer
(`venv/lib/python3.13/site-packages/__editable__.earthscope_positions-*.pth`)
contains an absolute path to `src/`. If you move the repo again, update that
file (or `pip install -e .` afresh) or imports will fail — `test_smoke.py`
catches this early.
