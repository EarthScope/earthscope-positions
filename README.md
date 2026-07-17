# earthscope-positions

Download, store, process, visualize, and export GNSS PPP position data from the EarthScope API.

---

## What this is

`earthscope-positions` is a Python toolkit for working with GNSS Precise Point Positioning (PPP) position data from the EarthScope GNSS network. It provides:

- A **CLI** (`es-pos`) that downloads and manages position data locally as [Apache Arrow](https://arrow.apache.org/) IPC files.
- A **web UI** (`es-pos webserver`) — a Quasar/Vue 3 SPA backed by FastAPI — for interactive visualization, completeness monitoring, station-list building, and replay control.
- **Export** to MiniSEED 3, GeoJSON (compact NDJSON and full FeatureCollection), and PPSD PNG plots.
- **Kafka replay** (`es-pos replay`) — replay position data to a Kafka topic at original ingest timing, with time-scale control and web UI progress monitoring.

---

## Quick start

```bash
# 1. Authenticate with EarthScope
es user login

# 2. Build a station list (ShakeAlert network as example)
es-pos stations get datasource --network-name SHAKE:ShakeAlert -o ShakeAlert

# 3. Download data
es-pos fetch get -i ShakeAlert --start 2026-01-01 --end 2026-01-08

# 4. Pre-compute completeness summaries (speeds up the web UI)
es-pos process completeness

# 5. Launch the web UI
es-pos webserver
# → open http://localhost:8000
```

---

## Installation

Requires **Python ≥ 3.13**.

```bash
python3.13 -m venv venv
source venv/bin/activate
pip install -e .          # from project root (editable install)
```

When returning to the project later, re-activate the virtual environment:

```bash
source venv/bin/activate
```

The `es`, `es-pos`, and `inspect` CLIs are now available in your virtual environment.

### The SPA

The SPA (Single Page Application) is pre-built in `spa/spaBuild/` and served by the web server. Only Earthscope developers should edit the SPA source in `spa/spaGenerator/`, which requires access to the private npm registry for the `@earthscope/spa-lib` package.
---

## Data flow

```
es-pos stations get  ──►  data/station-lists/<name>.json
                              │
                              ▼
es-pos fetch get     ──►  data/arrow/<GEOSNCL>/YYYYMM/<GEOSNCL>_<start>_<end>.arrow
                              │
                    ┌─────────┴────────────────────────┐
                    ▼                                  ▼
es-pos process      ──►  data/arrow/<GEOSNCL>/...     es-pos webserver
completeness              .completeness.arrow          http://localhost:8000
                              │
                    ┌─────────┴──────────────────────────────┐
                    ▼                        ▼               ▼
es-pos export    ──►  data/miniseed/…   data/geojson/…   data/plots/ppsd/…
miniseed/geojson/ppsd                                     (visible in File Plots tab)
                              │
                              ▼
es-pos replay    ──►  Kafka topic (compact GeoJSON NDJSON, keyed by GEOSNCL)
                       (also controllable via web UI Replay tab)
```

---

## GEOSNCL format

Arrow files are organized by **GEOSNCL** — a compound identifier encoding all stream metadata:

```
<STATION_FCID>.<PROCESSING_CENTER>.LY_.<PPP_SOLUTION><SOLUTION_TYPE>
```

| Field               | Values                                                |
|---------------------|-------------------------------------------------------|
| `STATION_FCID`      | 4-character station ID, e.g. `P143`                   |
| `PROCESSING_CENTER` | `PB` EarthScope · `PW` CWU · `NC` USGS Menlo Park · `BK` UCB · `CI` USGS Pasadena |
| `LY_`               | SEED channel base (always `LY_`)                      |
| `PPP_SOLUTION`      | `0` CWU Fastlane · `1` Trimble PIVOT/RTX · `2` RTNet · `3` Septentrio · `4` Trimble RTX on-board · `5` Network · `6` JPL PPP |
| `SOLUTION_TYPE`     | `0` PPP/AR FAST · `1` DIF/RTK · `2` PPP/AR COMPLETE · `3` PPP/AR FAST+COMPLETE |

Example: `P143.CI.LY_.20` = station P143, USGS Pasadena, RTNet PPP/AR FAST.

---

## Arrow data schema

Each `.arrow` file is an **Arrow IPC stream** (use `pyarrow.ipc.open_stream()`, not `open_file()`).

| Column              | Type      | Unit          | Description                          |
|---------------------|-----------|---------------|--------------------------------------|
| `time`              | int64     | ms since epoch| UTC sample timestamp                 |
| `east`              | float64   | metres        | East displacement                    |
| `north`             | float64   | metres        | North displacement                   |
| `up`                | float64   | metres        | Up displacement                      |
| `sigEE`             | float64   | metres        | East uncertainty (1σ)                |
| `sigNN`             | float64   | metres        | North uncertainty (1σ)               |
| `sigUU`             | float64   | metres        | Up uncertainty (1σ)                  |
| `qChannel`          | int64     |               | Quality flag                         |
| `ingestLatency`     | int64     | ms            | Time from epoch to ingest            |
| `processingDelay`   | int64     | ms            | Time from ingest to processing       |

Sample rate is nominally 1 Hz (one row per second).

---

## CLI reference

### `es-pos stations`

Discover and manage station lists from the EarthScope API. Lists are written to `./data/station-lists/<name>.json`.

```bash
# Discover all ShakeAlert streams
es-pos stations get datasource --network-name SHAKE:ShakeAlert -o ShakeAlert

# Discover stations within 100 km of a point
es-pos stations get radial --latitude 37.5 --longitude -122.0 --distance 100 -o bay_area

# Filter an existing list (e.g. keep only JPL-processed)
es-pos stations filter -i ShakeAlert -o ShakeAlert.jpl --facility JPL
```

> **Tip:** Station lists can also be built interactively in the **Station Builder** tab of the web UI,
> which displays all stations on an interactive map and lets you select by clicking, dragging
> rectangles, or filtering by processing center and solution type.

### `es-pos fetch`

Download GNSS PPP position data from `api.earthscope.org` and store as Arrow IPC files.
Requires EarthScope credentials (`es user login`) and VPN access for authenticated endpoints.

```bash
# Download data for a station list, date range
es-pos fetch get -i ShakeAlert --start 2026-01-01 --end 2026-04-01

# Multiple lists at once
es-pos fetch get -i ShakeAlert -i bay_area --start 2026-03-01

# Re-download everything (ignore caches)
es-pos fetch get -i ShakeAlert --start 2026-01-01 --redownload

# Concatenate Arrow files into one merged file
es-pos fetch concat data/arrow/P548.CI.LY_.20/202601/*.arrow -o merged.arrow
```

Downloaded data appears immediately in the **Positions** and **Completeness & Latency** tabs
of the web UI. The web server also supports on-demand fetching via the Fetch button.

Output layout:
```
data/arrow/<GEOSNCL>/YYYYMM/<GEOSNCL>_<START>_<END>.arrow
data/arrow/<GEOSNCL>/no_data.json   ← days with no API data
```

### `es-pos process completeness`

Pre-compute 15-minute completeness and latency summaries. The web UI generates these on demand,
but pre-computing them speeds up the **Completeness & Latency** tab significantly.

```bash
es-pos process completeness
es-pos process completeness --overwrite                    # regenerate even if files exist
es-pos process completeness --data-directory /archive      # custom base data directory
es-pos process completeness --arrow-data-directory /a/arrow # override just the Arrow root
```

Each Arrow file gets a sibling `.completeness.arrow` with 96 rows (one per 15-min bin):

| Column                     | Description                                  |
|----------------------------|----------------------------------------------|
| `bucket_start_ms`          | Bin start timestamp (ms since epoch)         |
| `row_count`                | Observed samples in this bin                 |
| `expected_count`           | Expected samples at nominal sample rate (900 at 1 Hz) |
| `completeness`             | `row_count / expected_count` (capped at 1.0) |
| `mean_ingest_latency_s`    | Mean ingest latency in seconds               |
| `mean_processing_delay_s`  | Mean processing delay in seconds             |

Results power the **Completeness & Latency** tab heat map in the web UI.

### `es-pos webserver`

Launch the web UI and data API.

```bash
es-pos webserver                            # http://localhost:8000
es-pos webserver --port 9000
es-pos webserver --data-directory /archive  # serve data from a custom base directory

# Run on a remote machine (bind all interfaces + advertise a public hostname
# so the Replay curl callbacks point at the right host):
es-pos webserver --host 0.0.0.0 --hostname gnss.example.org --port 8000
```

| Option | Default | Description |
| ------ | ------- | ----------- |
| `--host` | `127.0.0.1` | Bind address. Use `0.0.0.0` to accept remote connections. |
| `--port` | `8000` | Bind port. |
| `--hostname` | `localhost` | Externally-reachable hostname used for callback URLs shown in the UI (e.g. the Replay curl commands). Set to the server's public name/IP when running remotely. |
| `--data-directory` | `./data` | Base data directory (see [Data directory](#data-directory)). |

The SPA must be built first (`cd spa/spaGenerator && npm run build`).
The web UI has these tabs:

| Tab | Description |
|-----|-------------|
| **Station Builder** | Interactive map of all stations in `reference/coordinates/coordinates.csv`. Click or rectangle-drag to select stations; filter by processing center and solution type; **Prune** deselects stations with no matching stream; **All Streams → List** saves every `gnss_ppp` stream; **Load Network** loads all streams for a chosen `RTDB:*`/`SHAKE:*` network; save selections as station lists. |
| **Fetch Data** | Guided three-step walkthrough (choose lists → date range & filters → fetch) that downloads only the missing `(geosncl, day)` pairs with a live progress bar and log. Only one fetch runs at a time; the job keeps running when you switch tabs. |
| **Completeness & Latency** | Heat-map of data completeness and ingest latency per station per day. Completeness is generated on-demand if not pre-computed. Includes a Fetch button that runs `es-pos fetch get` for the selected list/range. |
| **Positions** | Interactive ENU time-series plots with power spectra (linear-frequency axis, down to 5-minute noise). Select stations from a saved list, set a date range, overlay multiple stations. |
| **File Plots** | File browser for `./data/plots/` — navigate directories and display PNG/JPEG plots generated by `es-pos export ppsd`. |
| **Replay** | Configure and run a Kafka replay from the browser. Shows preload summary, a live status log, and a **delivery check** (a consumer reads the topic back from the latest offset, reporting messages written vs. read, one-for-one matches, mean added round-trip latency, and a warning/error if echoes lag ≥ 2 s / 5 s). State persists server-side — closing and reopening the browser reconnects to the same replay. |

### `es-pos export miniseed`

Export Arrow position files to **MiniSEED 3** (8 channels per station-day file).

Specify stations with `-i <list>` or `--all`, and a date range using exactly two of
`--start-time`, `--stop-time`, `--duration` (duration format: `7d`, `24h`, `90m`, `3600s`, or
a bare integer for days).

```bash
es-pos export miniseed -i ShakeAlert --start-time 2026-01-01 --stop-time 2026-01-31
es-pos export miniseed -i ShakeAlert --start-time 2026-01-01 --duration 30d
es-pos export miniseed --all --stop-time 2026-01-31 --duration 7d
es-pos export miniseed -i ShakeAlert --start-time 2026-01-01 --duration 7d --root /archive/miniseed
```

Channel mapping (SEED band=L, source=Y):

| Channel | Arrow column      | Type    | Unit         |
|---------|-------------------|---------|--------------|
| `LYE`   | `east`            | float64 | metres       |
| `LYN`   | `north`           | float64 | metres       |
| `LYZ`   | `up`              | float64 | metres       |
| `LY1`   | `sigEE`           | float64 | metres       |
| `LY2`   | `sigNN`           | float64 | metres       |
| `LY3`   | `sigUU`           | float64 | metres       |
| `LYQ`   | `qChannel`        | int32   |              |
| `LYL`   | `ingestLatency`   | int32   | milliseconds |

FDSN Source Identifier: `FDSN:{NET}_{STA}_{LOC}_{BAND}_{SOURCE}_{SUBSOURCE}`
e.g. `FDSN:PW_DEEJ_00_L_Y_E`

Output paths are controlled by `miniseed_path_spec.toml` (auto-created on first run).
Default layout: `data/miniseed/{year}/{network}/{station}/{channel}.D/{network}.{station}.{location}.{channel}.D.{year}.{julday}.mseed`

### `es-pos export geojson`

Export Arrow position files to **GeoJSON** (ENU coordinate order: East, North, Up).

Specify stations with `-i <list>` or `--all`, and a date range using exactly two of
`--start-time`, `--stop-time`, `--duration` (duration format: `7d`, `24h`, `90m`, `3600s`, or
a bare integer for days).

```bash
es-pos export geojson -i ShakeAlert --start-time 2026-01-01 --stop-time 2026-01-31
es-pos export geojson -i ShakeAlert --start-time 2026-01-01 --duration 30d --format compact
es-pos export geojson --all --stop-time 2026-01-31 --duration 7d
```

Two formats, both written as JSONL (one JSON object per line):

**compact** — `*.compact.geojson.jsonl`, one compact record per sample:
```json
{"time":1735689600000,"Q":3,"type":"ENU","SNCL":"DEEJ.PW.LY_.00","coor":[0.001,0.002,-0.001],"err":[0.0005,0.0005,0.001],"rate":1}
```

**full** — `*.full.geojson.jsonl`, one GeoJSON Feature per sample (SNCL and sampleRate embedded per feature):
```json
{"type":"Feature","geometry":{"type":"Point","coordinates":[E,N,U]},"properties":{"coordinateType":"ENU","SNCL":"...","time":...,"EError":...,"NError":...,"UError":...,"quality":...,"sampleRate":1}}
```

The `--format` flag selects the output format: `compact`, `full`, or `both` (default). Output paths
are controlled by `geojson_path_spec.toml` (auto-created from built-in defaults on first run).

### `es-pos export ppsd`

Compute **Probabilistic Power Spectral Density** plots (3-panel PNG: East | North | Up).

```bash
es-pos export ppsd --all
es-pos export ppsd --all --start 2026-01-01 --end 2026-01-31
es-pos export ppsd data/arrow/P143.CI.LY_.20/202601/*.arrow
es-pos export ppsd --all --combined    # all stations in one plot
```

Algorithm parameters (matching MonitorApplication.java):

| Parameter  | Value   |
|------------|---------|
| Window     | 1024 samples |
| Step       | 512 samples (50% overlap) |
| NFFT       | 32768 |
| Period range | 1 s – 10 000 s (log scale) |
| Period bins | 67 |
| Power bins | 100 |
| Power range | −80 to +20 dB (m²/Hz) |

Output: `data/plots/ppsd/<start>_<end>/ppsd-<geosncl>.png`

Plots are visible in the **File Plots** tab of the web UI immediately after generation.

### `es-pos replay`

Replay Arrow position data to a **Kafka topic** as compact GeoJSON NDJSON records, timed to match
the original ingest arrival of each message.

#### Timing model

Each row is sent at the wall-clock time that corresponds to when it originally arrived at the
ingest system:

```
send_time = start_replay_wall + (data_arrival − start_data) / time_scale
```

where `data_arrival = data_time + ingest_latency` (if `--apply-latency`, the default). The offset
`start_replay_wall − start_data` is computed once at replay start and held constant throughout.

At `time_scale=1.0` the replay proceeds at real time (1-second GPS data = 1 second wall-clock gap
between messages). At `time_scale=2.0` the replay runs twice as fast.

#### Message format

Every message is a compact GeoJSON NDJSON record (the same format written by
`es-pos export geojson --format compact`):

```json
{"time":1735689600000,"Q":3,"type":"ENU","SNCL":"DEEJ.PW.LY_.00","coor":[0.001,0.002,-0.001],"err":[0.0005,0.0005,0.001],"rate":1}
```

The Kafka **message key** is the GEOSNCL string (UTF-8 bytes). The connection uses plain-text
(no TLS). The producer is configured with `batch.num.messages=500` and `linger.ms=10`.

#### Station and date selection

Same pattern as `es-pos export`: use `-i/--input` (station list name, repeatable) or `--all`, and
supply exactly two of `--start-time`, `--stop-time`, `--duration`.

#### CLI examples

```bash
# Replay ShakeAlert stations for one week at real speed
es-pos replay -i ShakeAlert --start-time 2026-01-01 --stop-time 2026-01-07

# Replay at 4× speed without latency compensation
es-pos replay -i ShakeAlert --start-time 2026-01-01 --duration 7d \
    --time-scale 4.0 --no-apply-latency

# Custom Kafka target, filter to CWU and RTNet streams only
es-pos replay -i ShakeAlert --start-time 2026-01-01 --duration 1d \
    --bootstrap-server kafka.internal:9092 \
    --topic my.positions.topic \
    --filter-center PW --filter-center NC

# Filter to a single PPP solution / solution type
es-pos replay -i ShakeAlert --start-time 2026-01-01 --duration 1d \
    --filter-solution 2 --filter-type 0
```

#### Options

| Option | Default | Description |
| ------ | ------- | ----------- |
| `-i/--input LIST` | — | Station list name (repeatable). Mutually exclusive with `--all`. |
| `--all` | — | Replay all stations in the data directory. |
| `--start-time`, `--stop-time`, `--duration` | — | Exactly two required. Duration: `7d`, `24h`, `90m`, `3600s`, or bare int (days). |
| `--time-scale X` | `1.0` | Replay speed multiplier (2.0 = 2× faster). |
| `--apply-latency` / `--no-apply-latency` | on | Whether to add original `ingestLatency` to the data timestamp when computing send time. |
| `--bootstrap-server HOST:PORT` | `localhost:9092` | Kafka bootstrap server. |
| `--topic TOPIC` | `protected.gnss.positions.shakealert.geojson.compact` | Kafka topic. |
| `--filter-center CENTER` | all | Keep only streams from this processing center (repeatable). |
| `--filter-solution DIGIT` | all | Keep only streams with this PPP solution digit 0–6 (repeatable). |
| `--filter-type DIGIT` | all | Keep only streams with this solution-type digit 0–3 (repeatable). |
| `--data-directory PATH` | `./data` | Base data directory (see [Data directory](#data-directory)). |
| `--arrow-data-directory PATH` | `<base>/arrow` | Override just the Arrow data root; supersedes `--data-directory`. |

#### Web UI Replay tab

The **Replay** tab in the web UI provides the same functionality with a richer workflow:

1. **Configure** — select station list(s), date range, stream filters, time scale, apply-latency toggle, Kafka bootstrap server, and topic. All disabled while a replay is active.
2. **Preload** — scans Arrow files, counts total messages, and identifies any stations with no data in the requested range (with a one-click Fetch Missing button to download them). Generates a random **job ID**.
3. **Go** — starts the replay. The page shows:
   - Messages sent / total, elapsed time, current send rate
   - Live cumulative progress bar and line chart (updated every second)
   - A copyable **curl command** to trigger Go from external scripts:

     ```bash
     curl -X POST http://localhost:8000/api/replay/<job_id>/go
     ```

4. **Cancel** — stops the replay immediately. A copyable curl command is also shown:

   ```bash
   curl -X POST http://localhost:8000/api/replay/<job_id>/cancel
   ```

The replay runs entirely server-side. Closing the browser or switching to another tab does **not**
stop it — reconnecting to the Replay tab restores the live view from the server's current state.
Only one replay can be in progress at a time (a new Preload while one is running returns an error).

### `es-pos test`

Diagnostic tools for the EarthScope positions API. Requires EarthScope VPN for the authenticated endpoint.

```bash
# Concurrency sweep against both API endpoints
es-pos test fetch -i ShakeAlert.clean --start 2026-01-01 --total-duration 25200

# Plot results from a previous test run
es-pos test plot data/positions_diagnose/diagnose_20260701T000000Z.jsonl
```

### `inspect`

Standalone tool to inspect Arrow IPC files (print schema, sample rows, statistics).

```bash
inspect data/arrow/P143.CI.LY_.20/202601/P143.CI.LY_.20_20260101T000000Z_20260102T000000Z.arrow
```

---

## Web API

The web server exposes a REST API at `/api/`:

| Endpoint | Description |
|----------|-------------|
| `GET /api/status` | Server status (stations indexed, file counts) |
| `GET /api/data-range` | Earliest and latest dates in the data |
| `GET /api/station-lists` | Names of all saved station lists |
| `GET /api/station-lists/{name}` | Geosncl strings in a named list |
| `POST /api/station-lists/{name}` | Save a station list `{"geosncls": [...]}` |
| `GET /api/stations?list=&search=` | Geosncl inventory with filter/search |
| `GET /api/completeness?list=&start=&end=` | Heat-map completeness data |
| `GET /api/positions?geosncls=&start=&end=` | Position time series |
| `GET /api/station-builder/data` | All stations with coordinates and stream list |
| `GET /api/plots/list?path=` | Directory listing under `data/plots/` |
| `GET /api/plots/img?path=` | Serve an image from `data/plots/` |
| `GET /api/fetch-missing` | SSE stream: run `es-pos fetch` in background |
| `POST /api/replay/preload` | Start a replay preload (scans files, counts rows, finds missing stations) |
| `GET /api/replay/status` | Current replay state (status, progress, config, job ID) |
| `POST /api/replay/{job_id}/go` | Start a preloaded replay (callable from curl for job sync) |
| `POST /api/replay/{job_id}/cancel` | Cancel a running replay (callable from curl) |
| `POST /api/replay/reset` | Reset replay to idle state |
| `GET /api/docs` | Interactive API documentation (Swagger UI) |

---

## Station lists

Station lists are JSON files in `./data/station-lists/`:

```json
[
  {"geosncl": "P143.CI.LY_.20"},
  {"geosncl": "DEEJ.PW.LY_.00"},
  ...
]
```

Built three ways:
1. **CLI** — `es-pos stations get datasource/radial` then optionally `es-pos stations filter`
2. **Web UI Station Builder tab** — interactive map with click/drag selection and stream-type filters
3. **Manually** — any JSON editor placed in `./data/station-lists/`

Used by `es-pos fetch get -i <name>` and loaded in the web UI via the list selector.

---

## Station coordinates

`reference/coordinates/coordinates.csv` is a merged coordinate table with priority:

1. GAGE GPS IGS14 solutions (`reference/coordinates/gage_gps.igs14.txt`)
2. ShakeAlert extended coordinates (`reference/coordinates/station_coords_extended.dat`)
3. RealTimeDB (`reference/coordinates/rtdb.csv`)

Regenerate with:
```bash
python scripts/build_coordinates_csv.py
```

The coordinates file powers the **Station Builder** map tab and the
`earthscope_positions.coordinates.Coordinates` class.

```python
from earthscope_positions.coordinates import Coordinates

coords = Coordinates()
c = coords.get("P143")
print(c.latitude, c.longitude, c.height, c.source)
```

---

## Configuration

### Data directory

All data lives under a single **base data directory**, resolved with this precedence:

1. the `--data-directory PATH` CLI flag (available on every data-touching command);
2. the `ES_POS_DATA_DIRECTORY` environment variable;
3. `./data` (the default).

The layout is derived from the base:

```
<base>/arrow/                 # downloaded position Arrow files
<base>/station-lists/         # station-list JSONL files
<base>/plots/                 # generated plot images (e.g. ppsd/)
<base>/positions_diagnose/    # es-pos test fetch output
<base>/positions_errors.jsonl # fetch API error log
```

Examples:

```bash
# Point the whole tree at a custom location
es-pos --help                                   # (flag lives on each subcommand)
es-pos fetch get -i ShakeAlert --start 2026-01-01 --data-directory /mnt/es
ES_POS_DATA_DIRECTORY=/mnt/es es-pos webserver   # same, via environment
```

The Arrow root can be pointed somewhere else independently with
`--arrow-data-directory PATH`, which **supersedes** `--data-directory` for Arrow
data only (station lists and plots still come from the base). This is handy for
`es-pos replay`, `process`, and `export` when the Arrow archive lives on a
separate volume:

```bash
es-pos replay -i ShakeAlert --start-time 2026-01-01 --duration 1d \
    --data-directory /mnt/es --arrow-data-directory /fast-nvme/arrow
```

### MiniSEED path spec (`miniseed_path_spec.toml`)

Controls output naming for `es-pos export miniseed`. Auto-created from the bundled default on first run.

### GeoJSON path spec (`geojson_path_spec.toml`)

Controls output naming for `es-pos export geojson` (separate sections for compact and full formats).

---

## Project structure

```
earthscope-positions/
├── src/earthscope_positions/
│   ├── es_pos.py              # Unified CLI entry point (es-pos)
│   ├── arrow_inspect.py       # inspect CLI tool
│   ├── coordinates.py         # Station coordinate lookup class
│   ├── stations/
│   │   └── station_list.py    # es-pos stations subcommands
│   ├── fetch/
│   │   └── positions_fetch.py # es-pos fetch subcommands
│   ├── process/
│   │   └── completeness.py    # es-pos process completeness
│   ├── export/
│   │   ├── miniseed_writer.py # MiniSEED 3 export
│   │   ├── geojson_writer.py  # GeoJSON export
│   │   └── ppsd_writer.py     # PPSD plot generation
│   ├── replay/
│   │   └── replay.py          # Kafka replay engine (singleton state, CLI entry point)
│   ├── test/
│   │   ├── positions_diagnose.py       # es-pos test fetch
│   │   └── positions_diagnose_plot.py  # es-pos test plot
│   └── webserver/
│       └── webserver.py       # FastAPI app + static SPA serving
├── spa/
│   ├── spaGenerator/          # Vue 3 + Quasar source (npm project)
│   │   └── src/pages/
│   │       ├── CompletenessPage.vue
│   │       ├── PositionsPage.vue
│   │       ├── StationBuilderPage.vue
│   │       ├── PlotsPage.vue
│   │       └── ReplayPage.vue
│   └── spaBuild/              # Compiled SPA (git-ignored; run npm run build)
├── data/
│   ├── arrow/                 # Downloaded position data
│   ├── station-lists/         # Saved station list JSON files
│   └── plots/                 # Generated plots (power spectral density, etc.)
├── reference/
│   └── coordinates/           # Station coordinate source files + merged CSV
├── scripts/
│   └── build_coordinates_csv.py
├── miniseed_path_spec.toml
├── geojson_path_spec.toml
└── pyproject.toml
```

---

## Requirements

- Python ≥ 3.13
- EarthScope SDK + CLI (`earthscope-sdk`, `earthscope-cli`)
- PyArrow ≥ 12
- FastAPI + uvicorn (web server)
- matplotlib ≥ 3.7 (PPSD plots)
- confluent-kafka (required only for `es-pos replay`; install with `pip install confluent-kafka`)
- Node.js / npm (to build the SPA)

See `pyproject.toml` for the full dependency list.

---

## Authentication

The EarthScope positions API requires authentication. Log in once with:

```bash
es user login
```

Tokens are cached at `~/.earthscope/default/tokens.json` and refreshed automatically.
The `es-pos test fetch` command also requires EarthScope VPN connectivity.


---

## Point of contact

**Charlie Sievers** — charlie.sievers@earthscope.org
