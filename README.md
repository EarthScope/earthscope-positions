# earthscope-positions

Download, store, process, visualize, and export GNSS PPP position data from the EarthScope API.

---

## What this is

`earthscope-positions` is a Python toolkit for working with GNSS Precise Point Positioning (PPP) position data from the EarthScope GNSS network. It provides:

- A **CLI** (`es-pos`) that downloads and manages position data locally as [Apache Arrow](https://arrow.apache.org/) IPC files.
- A **web UI** (`es-pos webserver`) — a Quasar/Vue 3 SPA backed by FastAPI — for interactive visualization, completeness monitoring, station-list building, and replay control.
- **Export** to MiniSEED (version 3 by default, version 2 optional), GeoJSON
  (compact NDJSON and full FeatureCollection), and PPSD PNG plots.
- **Kafka replay** (`es-pos replay`) — replay position data to a Kafka topic at original ingest timing, with time-scale control and web UI progress monitoring.

---

## Installation

Requires **Python ≥ 3.11**. (3.11 is the floor because the export path-spec
readers use the stdlib `tomllib`, which landed in 3.11.)

```bash
python3 -m venv venv
source venv/bin/activate
pip install .          # from project root
```

When returning to the project later, re-activate the virtual environment:

```bash
source venv/bin/activate
```

The `es` and `es-pos` CLIs are now available in your virtual environment.

---

## Quick start

Please follow the installation instructions and active the environment, then run the following commands to start the web server:

```bash
es user login       # authenticate with EarthScope
es-pos webserver    # → open http://localhost:8000
```

That is the whole setup. On first run the server picks a
[data directory](#where-your-data-lives), seeds the default stream and station lists, and
everything else — building lists, downloading data, processing, plotting, exporting,
replaying — is available from the tabs in the browser.

The CLI does the same jobs if you would rather script them; see the
[CLI reference](#cli-reference).

---

## Docker quick start

```bash
./es-pos-docker.sh build
./es-pos-docker.sh run --detach
docker logs -f earthscope-positions
```

Please note that this application scans the entire data directory for many requests.  On a Mac, the bind mounds make this request significantly slower than running the application outside of docker.  This is much less of an issue on Linux.

### The SPA

The SPA (Single Page Application) is pre-built in `spa/spaBuild/` and served by the web server. Only Earthscope developers should edit the SPA source in `spa/spaGenerator/`, which requires access to the private npm registry for the `@earthscope/spa-lib` package.

---

## Where your data lives

Everything this tool writes — downloaded position data, your lists, exports, plots —
goes under a single **data directory**.

**The default is `~/earthscope-positions`.** On the first interactive run you are asked
where you want it and the answer is saved; a non-interactive first run takes the default
and prints where it went. Nothing is written next to the repository, and nothing depends
on which directory you happen to be standing in.

The choice is remembered in **`~/.earthscope-positions.json`**:

```json
{
  "data_directory": "/Volumes/BigDisk/positions",
  "known_data_directories": [
    "/Users/you/earthscope-positions",
    "/Volumes/BigDisk/positions"
  ]
}
```

That file is created at runtime in your home directory — **not** inside the installed
package — so it survives `pip install --upgrade`, reinstalls, and uninstalls. You should
never need to edit it by hand; `es-pos config` writes it.

```bash
es-pos config show                            # where is my data, and what set it?
es-pos config list-data-dirs                  # every directory used before, numbered
es-pos config use-data-dir 2                  # switch by number (no data is moved)
es-pos config set-data-dir /mnt/gnss          # record a new location
es-pos config move-data-dir /Volumes/BigDisk  # move the tree there, then record it
```

Each data directory is also tied to one EarthScope deployment — production or stage. See
[Production and stage](#production-and-stage).

The Overview tab of the web UI shows the same information read-only. Switching is a
command-line operation: the server resolves its data directory once at startup, so change
it with `es-pos config` and restart `es-pos webserver`.

Inside the base directory:

```
<data-dir>/arrow/                 # downloaded position Arrow files
<data-dir>/stream-lists/          # stream-list JSONL files
<data-dir>/station-lists/         # station-list JSONL files
<data-dir>/plots/                 # generated plot images
<data-dir>/miniseed/              # `es-pos export miniseed` output (per the path spec)
<data-dir>/geojson/               # `es-pos export geojson` output (per the path spec)
<data-dir>/resources/             # editable coordinates.csv + export path-spec TOMLs
<data-dir>/positions_errors.jsonl # fetch API error log
<data-dir>/.config/               # which deployment this tree pulls from (not data)
```

For CI, cron, and Docker, `ES_POS_DATA_DIRECTORY` overrides the configured location for a
single invocation. Full precedence rules are under [Data directory](#data-directory).

---

## Production and stage

EarthScope runs two deployments, and **a data directory belongs to exactly one of them**:

| | Production (default) | Stage |
|---|---|---|
| API | `https://api.earthscope.org` | `https://api.dev.earthscope.org` |
| `es` profile | `default` | `stage` |
| Marked by | nothing — this is the default | `<data-dir>/.config/environment.json` |
| Web UI | no badge | amber **STAGE** badge beside the help button |

They are not interchangeable. **The same physical station has a different EDID in each**,
so a stream list built against one is meaningless against the other, and a tree holding
both would contain the same station twice under unrelated identifiers with no way to tell
them apart. That is why the environment is a property of the *directory* rather than a
flag on each command.

### Putting a directory on stage

One command can do it, and it is the only one:

```bash
es-pos config use-data-dir --stage ~/earthscope-positions-stage
```

That writes `<data-dir>/.config/environment.json` and makes the directory active. It is
**refused** for a directory that already holds data (anything under `arrow/`,
`stream-lists/` or `station-lists/`) — use a separate directory instead. `--force`
overrides the refusal if you genuinely need it.

`--prod` switches a directory back the same way. Plain `es-pos config use-data-dir` never
changes a directory's environment, so switching between a prod tree and a stage tree is
just switching directories:

```bash
es-pos config list-data-dirs     # stage entries are tagged [Stage]
es-pos config use-data-dir 2     # keeps whatever environment #2 already has
```

Every `es-pos config` subcommand reports which environment it is talking about.

### Credentials

Stage needs its own tokens, from an `es` profile pointed at the dev deployment. Add one to
`~/.earthscope/config.toml`:

```toml
[profile.stage]
resources.api_url = "https://api.dev.earthscope.org"
oauth2.audience   = "https://api.dev.earthscope.org"
oauth2.domain     = "https://login-dev.earthscope.org"
oauth2.client_id  = "<the dev client id>"
```

then log in once:

```bash
es user login --profile stage
```

If your dev credentials already live under a differently-named profile, point the
directory at that one instead of duplicating the entry:

```bash
es-pos config use-data-dir --stage --profile dev ~/earthscope-positions-stage
```

`es-pos config show` tells you if the profile a directory needs is not defined yet, and
names the profiles that are.

### What follows the directory

Everything: the API host for both the SDK calls and the direct REST radial search, the
token cache the fetch path reads, the profile `es-pos test fetch` probes with, the
subprocesses the web server spawns, and the badge in the web UI. There is no per-command
override — `ES_PROFILE` overrides just the profile if you need it, and
`ES_POS_ENVIRONMENT` exists for the web server to pin its children, not as a user-facing
switch.

Stage has no unauthenticated positions endpoint, so `es-pos test fetch` sweeps only the
authenticated one there (production probes both).

---

## Data flow

Two kinds of list feed everything else. **Station lists** are just station codes and are
used to scope *which stations you are looking at*; **stream lists** name the individual
streams and are what actually gets fetched.

```
es-pos lists get-stations        ──►  <data-dir>/station-lists/<name>.jsonl
es-pos lists get-radial-stations        {"station": "P143"}
        (Station Builder tab)                    │
                                                 │  used as include/exclude sets
                                                 ▼
es-pos lists get-streams         ──►  <data-dir>/stream-lists/<name>.jsonl
es-pos lists get-radial-streams         {"geosncl": "P143.PB.LY_.10", "edid": …}
es-pos lists filter-streams                      │
        (Stream List Builder tab)                │
                                                 ▼
es-pos fetch --list <name>       ──►  <data-dir>/arrow/<GEOSNCL>/YYYYMM/
        (Fetch Data tab)                           <GEOSNCL>_<start>_<end>.arrow
                                                 │
                          ┌──────────────────────┴──────────────────────┐
                          ▼                                             ▼
es-pos process completeness ──►  <data-dir>/arrow/<GEOSNCL>/       es-pos webserver
        (Completeness tab)         ….completeness.arrow            http://localhost:8000
                                                 │
              ┌──────────────────────────────────┼──────────────────────────────────┐
              ▼                                  ▼                                  ▼
es-pos export miniseed          es-pos export geojson             es-pos export ppsd
   <data-dir>/miniseed/…           <data-dir>/geojson/…              <data-dir>/plots/ppsd/…
        (Export tab)                   (Export tab)                  (PPSD Generation tab)
                                                 │
                                                 ▼
                                    browse any of it in the File Explorer tab
                                                 │
                                                 ▼
es-pos replay -i <name>          ──►  Kafka topic
        (Replay tab)                    compact GeoJSON NDJSON, keyed by GEOSNCL
```

Only stream lists are fetchable — a station list has no stream identifiers in it. The
usual path is to down-select stations on the map (saving a station list), then build a
stream list from those stations filtered by processing center and solution type.

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

### `es-pos lists`

Build and inspect the two kinds of list everything else runs on. The command names mirror the
two builder tabs in the web UI.

| Kind | Contents | Location | Used by |
| --- | --- | --- | --- |
| **stream list** | full geosncl records | `<data-dir>/stream-lists/` | fetch, completeness, positions, ppsd, export, replay |
| **station list** | station codes only | `<data-dir>/station-lists/` | include/exclude sets when building stream lists |

`stream_type=gnss_ppp` is always applied; the radial commands also set `tier=stream`.

**Inspecting what you have**

```bash
es-pos lists list                       # every list of both kinds, with entry counts
es-pos lists list --streams             # …only stream lists
es-pos lists list --stations            # …only station lists

es-pos lists show-streams ShakeAlert    # print a stream list
es-pos lists show-stations ShakeAlert   # print a station list
```

`list` gives the full path of every list and how many entries it holds:

```
Stream lists (4)
  SCGN             431 entries  /Users/you/earthscope-positions/stream-lists/SCGN.jsonl
  all-streams    7,107 entries  /Users/you/earthscope-positions/stream-lists/all-streams.jsonl
  shake-alert    5,502 entries  /Users/you/earthscope-positions/stream-lists/shake-alert.jsonl
  …

Station lists (3)
  SCGN              138 entries  /Users/you/earthscope-positions/station-lists/SCGN.jsonl
  all-stations    1,665 entries  /Users/you/earthscope-positions/station-lists/all-stations.jsonl
  …
```

**Editing a list by hand**

`--edit` opens the list in `$VISUAL` / `$EDITOR` and reports the entry count when you come
back, so a bad hand-edit shows up immediately:

```bash
es-pos lists show-streams ShakeAlert --edit
es-pos lists show-stations bay-area --edit
```

```
…/stream-lists/ShakeAlert.jsonl — 5,503 entries  (+1 from 5,502)
```

If the editor exits non-zero the list is reported as left alone. `$VISUAL` wins over
`$EDITOR`, either may carry arguments (`EDITOR="code -w"`), and with neither set it falls
back to `vi` (`notepad` on Windows) when that is actually installed — otherwise it tells you
to set the variable rather than failing obscurely.

`--path` prints the absolute path and nothing else, for composing with other tools:

```bash
es-pos lists show-streams ShakeAlert --path
wc -l "$(es-pos lists show-streams ShakeAlert --path)"
```

**Building lists from the API**

```bash
# All ShakeAlert streams → stream list
es-pos lists get-streams --network-name SHAKE:ShakeAlert -o ShakeAlert

# The same query, saved as a station list instead
es-pos lists get-stations --network-name SHAKE:ShakeAlert -o ShakeAlert

# Everything within 100 km of a point
es-pos lists get-radial-streams  --latitude 37.5 --longitude -122.0 --distance 100 -o bay_area
es-pos lists get-radial-stations --latitude 37.5 --longitude -122.0 --distance 100 -o bay_area

# Filter an existing stream list (e.g. keep only JPL-processed)
es-pos lists filter-streams -i ShakeAlert -o ShakeAlert.jpl --facility JPL
```

Omit `-o` on any `get-*` command to print to screen without saving.

> **A 404 `{"detail":"No streams found"}` from the radial commands means nothing matched**, not
> that something broke — check the centre point is on land and the radius actually reaches a
> station. The `tier=stream` / `stream_type=gnss_ppp` filters are always applied, so a point over
> land with no PPP streams in range returns 404 too.

> **Renamed:** this group used to be `es-pos stations`, with `get datasource` / `get radial` /
> `filter`. It managed only stream lists, with no way to produce a station list — which is what
> the Station Builder tab writes. Running the old name prints the mapping to the new one.

> **Tip:** Both kinds can also be built interactively in the web UI — the **Station Builder** tab
> displays all stations on a map for click/drag selection, and the **Stream List Builder** tab
> filters those stations' streams by processing center and solution type.

### `es-pos fetch`

Download GNSS PPP position data from `api.earthscope.org` and store as Arrow IPC files.
Requires EarthScope credentials (`es user login`) — this endpoint is public-facing and does
**not** require EarthScope VPN (unlike `es-pos test fetch`, see [Authentication](#authentication)).

```bash
# Download data for a station list, date range
es-pos fetch --list ShakeAlert --start 2026-01-01 --end 2026-04-01

# Multiple lists at once
es-pos fetch --list ShakeAlert --list bay_area --start 2026-03-01

# Re-download everything (ignore caches)
es-pos fetch --list ShakeAlert --start 2026-01-01 --redownload

# Retry every previously failed (error-NNN) request found anywhere in the data directory
es-pos fetch --retry
```

Downloaded data appears immediately in the **Positions** and **Completeness & Latency** tabs
of the web UI. The web server also supports on-demand fetching via the Fetch button.

Output layout:
```
data/arrow/<GEOSNCL>/YYYYMM/<GEOSNCL>_<START>_<END>.arrow
data/arrow/<GEOSNCL>/no_data.jsonl   ← days with no API data, or a request error
```

### `es-pos process completeness`

Pre-compute 15-minute completeness and latency summaries. The web UI generates these on demand,
but pre-computing them speeds up the **Completeness & Latency** tab significantly.

```bash
es-pos process completeness
es-pos process completeness --overwrite                    # regenerate even if files exist
es-pos process completeness --gap-seconds 10 --overwrite   # only longer outages count
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
| `restart_count`            | Gaps the stream resumed from inside this bin |
| `max_gap_s`                | Longest of those gaps, in seconds            |

Results power the **Completeness & Latency** tab's three heat maps in the web UI.

Completeness files written before restart tracking existed lack the last two columns.
They are regenerated automatically — by `es-pos process completeness` and by the web
server as it serves them — because reading them as-is would make the restart metric look
like a uniform zero, which is indistinguishable from a stream with no outages.

#### Gaps, restarts and continuous blocks

A **gap** is an interval between consecutive samples longer than `--gap-seconds`
(default **2 s**). A **restart** is the stream resuming after one, so restarts = gaps and
**continuous blocks = restarts + 1**.

The threshold is 2 s rather than "any missing sample" because at 1 Hz a single dropped
epoch produces a 2.000 s interval and is ordinary — about **0.4% of all intervals** in
real data, working out to a mean of ~274 per station-day. Counting those as outages would
swamp the signal and duplicate what `completeness` already reports. Intervals of two or
more consecutive missing epochs run ~19 per station-day, which is what the default
counts. Lower `--gap-seconds` to include single drops, raise it for sustained outages
only:

| gap longer than | median/station-day | mean/station-day |
|---|---|---|
| 1 s (any dropped epoch) | 9 | 274 |
| **2 s (default)** | **4.5** | **18.6** |
| 10 s | 1 | 5.5 |
| 60 s | 0 | 2.0 |

Each gap is attributed to the bin holding the sample that **resumed** the stream, not the
one where it stopped. A multi-bin outage is therefore counted once, in the bin where data
came back, and the bins it spans show as empty in `completeness` — which is what they
are. It also means restart counts stay correct when the heat map aggregates 15-minute
bins into coarser ones.

A completeness file only sees its own source file (one UTC day), so an outage spanning
midnight leaves no interior gap in either day: the first just ends early and the second
just starts late. A file that **starts late** relative to the window in its filename
therefore counts one restart at its first sample. That late start does not split the
samples it does have into an extra block, so restarts can be one more than blocks − 1.

The threshold each file was built with is stored inside it, so generating with a
non-default `--gap-seconds` is not silently undone by a later run (or by the web server)
using the default. The Restarts plot is labelled with the threshold the data carries, and
the File Explorer's per-file summary uses the same threshold the sibling completeness file
recorded, so the two views never disagree.

#### Precomputing

Completeness files are built on demand as pages are viewed. That is fine for a handful of
streams, but on a large tree each new page or date range pays to build whatever it
touches, which is what makes browsing feel slow. The Completeness tab's **Precompute**
button builds everything the current list, filters and date range need — across every
page, not just the one on screen — with a progress bar. Measured on a real tree, a page of
50 streams over 24 days went from **1.27 s to 0.05 s** once precomputed.

`es-pos process completeness` does the same thing for the whole data directory from the
command line.

Files that cannot be read at all (normally a truncated download) are reported rather than
failing the request: the Completeness tab shows a banner naming them, and the precache
dialog lists them. Re-fetch with `es-pos fetch --list <name> --redownload`.

### `es-pos webserver`

Launch the web UI and data API.

```bash
es-pos webserver                            # http://localhost:8000
es-pos webserver --port 9000

# Run on a remote machine (bind all interfaces + advertise a public hostname
# so the Replay curl callbacks point at the right host):
es-pos webserver --host 0.0.0.0 --hostname gnss.example.org --port 8000
```

| Option | Default | Description |
| ------ | ------- | ----------- |
| `--host` | `127.0.0.1` | Bind address. Use `0.0.0.0` to accept remote connections. |
| `--port` | `8000` | Bind port. |
| `--hostname` | `localhost` | Externally-reachable hostname used for callback URLs shown in the UI (e.g. the Replay curl commands). Set to the server's public name/IP when running remotely. |

The SPA must be built first (`cd spa/spaGenerator && npm run build`).
The web UI has these tabs:

| Tab | Description |
|-----|-------------|
| **Station Builder** | Interactive map of all stations in `<data-directory>/resources/coordinates.csv` (see [Data directory](#data-directory)). Click or rectangle-drag to select stations; filter by processing center and solution type; **Prune** deselects stations with no matching stream; **All Streams → List** saves every `gnss_ppp` stream; **Add Network Stations** adds every station in a chosen `RTDB:*`/`SHAKE:*` network to the selection **and saves them as a station list named after the network** — if that list already exists it is loaded from disk rather than re-queried, so hand-edits survive (**Re-query network** refetches and overwrites); save selections as station lists. |
| **Fetch Data** | Guided three-step walkthrough (choose lists → date range & filters → fetch) that downloads only the missing `(geosncl, day)` pairs with a live progress bar and log. Only one fetch runs at a time; the job keeps running when you switch tabs. |
| **Completeness & Latency** | Three heat-maps per station per time bin — completeness, ingest latency, and **restarts** (times the stream came back after a gap; see [Gaps, restarts and continuous blocks](#gaps-restarts-and-continuous-blocks)). Completeness is generated on-demand if not pre-computed; **Precompute** builds it for the whole list/filter/date selection up front so paging through is instant. Clicking a cell opens that stream-day's Arrow file in the File Explorer. Includes a Fetch button that runs `es-pos fetch` for the selected list/range. |
| **Positions** | Interactive ENU time-series plots with power spectra (linear-frequency axis, down to 5-minute noise). Select stations from a saved list, set a date range, overlay multiple stations. **Zoom:** drag on a time-series plot to zoom its value axis, Shift+drag to zoom the shared time axis, click to reset both; Shift+drag a box on a scatter panel to zoom it, click to reset. With PCA/KLE common-mode removal on, the scatter panels and histograms are drawn a second time for the residual, so you can see whether the cloud actually tightened. |
| **Export** | Convert downloaded Arrow position data into MiniSEED or GeoJSON. Pick the format, the **MiniSEED version** (3 by default, or 2), stream list(s) and a date range. The path-spec TOML controlling output directory structure and filenames is editable in-page (**Save spec**, then **Convert** with overwrite to regenerate under the new layout). |
| **File Explorer** | File browser rooted at the **data directory** — the Arrow tree, stream/station lists, exports and plots in one place. Selecting a file shows a type-aware summary: `.arrow` (a time-series plot of every numeric column, plus rows, columns, time span, schema, and **continuity** — continuous blocks, restarts, longest gap, total time in gaps, and a table of every block with its start, end, duration and sample count; see [Gaps, restarts and continuous blocks](#gaps-restarts-and-continuous-blocks). **Each continuous block is plotted in its own colour with a red marker at every restart**, so a break is visible even across a full-day axis. `.completeness` arrays plot per-bucket completeness, latency and restarts, and summarise the stored restart totals; `_ppsd` arrays render the three-panel PPSD. Files whose whole preview is one picture — stored images and `_ppsd` arrays — get a **checkbox** in the tree; tick several to see them stacked in one pane for comparison, and click any other file to untick them all), MiniSEED (a waveform plot, plus records, channels, format, encoding), GeoJSON (a time-series plot, features, stations, lat/lon bounds, first 25 lines), `.jsonl` (stream vs station list, entry counts, first lines); images render inline. Text files can be edited in place (JSONL validated line-by-line), and any file renamed or deleted. |
| **Replay** | Configure and run a Kafka replay from the browser. Shows preload summary, a live status log, and a **delivery check** (a consumer reads the topic back from the latest offset, reporting messages written vs. read, one-for-one matches, mean added round-trip latency, and a warning/error if echoes lag ≥ 2 s / 5 s). State persists server-side — closing and reopening the browser reconnects to the same replay. |

### `es-pos export miniseed`

Export Arrow position files to **MiniSEED** (8 channels per station-day file).

Records are encoded by [`pymseed`](https://github.com/EarthScope/pymseed), EarthScope's
binding for the C `libmseed` library. It installs as a prebuilt wheel on macOS, Linux, and
Windows, so there is no compiler or build step — a plain `pip install -e .` is enough.

Specify stations with `-i <list>` or `--all`, and a date range using exactly two of
`--start-time`, `--stop-time`, `--duration` (duration format: `7d`, `24h`, `90m`, `3600s`, or
a bare integer for days).

```bash
es-pos export miniseed -i ShakeAlert --start-time 2026-01-01 --stop-time 2026-01-31
es-pos export miniseed -i ShakeAlert --start-time 2026-01-01 --duration 30d
es-pos export miniseed --all --stop-time 2026-01-31 --duration 7d
es-pos export miniseed -i ShakeAlert --start-time 2026-01-01 --duration 7d --root /archive/miniseed
es-pos export miniseed -i ShakeAlert --start-time 2026-01-01 --duration 7d --format-version 2
```

#### Format version

Output is **MiniSEED 3** by default — the current FDSN standard. Pass `--format-version 2`
for classic SEED, for downstream tooling that cannot read version 3. The default lives in
the path spec's `[encoding] format_version`; the flag overrides it, and the web UI exposes
the same choice as a dropdown on the Export tab.

MiniSEED 2 records are fixed length, so version 2 requires `max_record_length` to be a
power of two (512, 1024, 2048, 4096, …) — this is checked before writing and reported as a
clear error. MiniSEED 3 records are variable length, so there the value is only an upper
bound.

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

Output paths are controlled by `<data-directory>/resources/miniseed_path_spec.toml`
(auto-created from the bundled default on first run).
Default layout: `data/miniseed/{year}/{network}/{station}/{channel}.D/{network}.{station}.{location}.{channel}.D.{year}.{julday}.mseed`

For MiniSEED 2, libmseed maps the source identifier back onto classic SEED
network/station/location/channel codes.

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
are controlled by `<data-directory>/resources/geojson_path_spec.toml`
(auto-created from built-in defaults on first run).

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

Output: `data/plots/ppsd/<mode>/ppsd-<geosncl>/ppsd-<geosncl>_<start>_<end>.png`
(`<mode>` is `by-stream`, `by-center`, or `all`) — grouped by PPSD type first,
then by plot identity, so repeated runs for the same station/group accumulate
side-by-side instead of scattering across per-run date folders.

Plots are visible in the **File Explorer** tab of the web UI immediately after generation.

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

Both endpoints follow the active data directory's environment. Stage publishes no
unauthenticated endpoint, so a stage run sweeps the authenticated one alone.

```bash
# Concurrency sweep against both API endpoints
es-pos test fetch -i ShakeAlert.clean --start 2026-01-01 --total-duration 25200

# Plot results from a previous test run
es-pos test plot data/positions_diagnose/diagnose_20260701T000000Z.jsonl
```

### `es-pos config`

Show or change the persisted data-directory setting, and which EarthScope deployment each
directory pulls from.

```bash
es-pos config show                                # where is my data, and what set it?
es-pos config list-data-dirs                      # every directory used before, numbered
es-pos config use-data-dir 2                      # switch active directory by number
es-pos config use-data-dir /mnt/gnss/positions    # …or by path
es-pos config set-data-dir /mnt/gnss/positions    # record a location (does not move data)
es-pos config move-data-dir /Volumes/BigDisk/pos  # move the tree there, then record it
es-pos config forget-data-dir 3                   # drop from the list; data untouched

# Point a directory at the stage deployment (api.dev.earthscope.org).
es-pos config use-data-dir --stage ~/earthscope-positions-stage
es-pos config use-data-dir --stage --profile dev ~/es-pos-stage   # use an existing profile
es-pos config use-data-dir --prod  ~/earthscope-positions         # …and back again
```

`show` reports the resolved directory, **which layer decided it**, how much is in it, the
environment (production or stage) with its API host and `es` profile, the config file
path, the remembered list, and a note if `ES_POS_DATA_DIRECTORY` disagrees with the
configured value.

`list-data-dirs` numbers every directory this install has used, marks the active one with
`*`, tags any non-production one with its environment (`[Stage]`), and shows each one's
size (or `(missing)` if it has been deleted or moved outside the tool). The numbers come from the config file's stored order and do **not** shuffle when
you switch, so a number you read stays valid.

`use-data-dir` switches the active directory, taking either a number from the listing or a
path. A path that has not been seen before is remembered too. No data is moved.

It is also the **only** command that can change a directory's environment, via `--stage`
or `--prod`; without one of those the directory keeps whatever it already has. Changing
the environment of a directory that already holds data is refused (prod and stage EDIDs
differ, so the two cannot share a tree) unless you pass `--force`. `--profile NAME`
records which `es` profile that directory's tokens come from, for when yours are not under
the default name. See [Production and stage](#production-and-stage).

`set-data-dir` records a location and creates the directory (pass `--no-create` to skip),
but never moves existing data. Use `move-data-dir` for that — it relocates the tree and
updates the config in one step, refusing to overwrite a non-empty destination or to move a
directory into itself, and confirming first unless given `--yes`. The vacated path is
dropped from the remembered list, since it no longer exists.

`forget-data-dir` removes an entry from the list without touching the directory or its
contents. The active directory cannot be forgotten — switch away from it first.

### `es-pos inspect`

Inspect Arrow IPC files (print schema, sample rows, statistics). Auto-detects IPC file
format (`.arrow`), IPC stream format (`.arrows`), and JSON error payloads written by
failed downloads.

```bash
es-pos inspect data/arrow/P143.CI.LY_.20/202601/P143.CI.LY_.20_20260101T000000Z_20260102T000000Z.arrow
es-pos inspect data/arrow/P143.CI.LY_.20/202601/*.arrow --rows 5
es-pos inspect /tmp/test.arrow --schema-only
es-pos inspect /tmp/test.arrow --stats
```

---

## Web API

The web server exposes a REST API at `/api/`:

| Endpoint | Description |
|----------|-------------|
| `GET /api/status` | Server status (stations indexed, file counts) |
| `GET /api/data-range` | Earliest and latest dates in the data |
| `GET /api/stream-lists` | Names of all saved stream lists |
| `GET /api/stream-lists/{name}` | Geosncl strings in a named list |
| `POST /api/stream-lists/{name}` | Save a stream list `{"geosncls": [...]}` |
| `GET /api/station-lists` | Names of all saved station (station-code) lists |
| `GET /api/station-lists/{name}` | Station codes in a named list |
| `POST /api/station-lists/{name}` | Save a station list `{"stations": [...]}` |
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

Station lists name **stations**, nothing more. They live in
`<data-dir>/station-lists/` as JSONL — one JSON object per line, not a JSON array:

```
{"station": "P143"}
{"station": "DEEJ"}
```

They are the down-selection step: which stations am I interested in? They are **not
fetchable** on their own, because a station code says nothing about which of that
station's streams to download. Their job is to act as the include/exclude sets the Stream
List Builder works from.

Built four ways:

1. **CLI** — `es-pos lists get-stations` / `es-pos lists get-radial-stations`
2. **Web UI Station Builder tab** — click or rectangle-drag on the map, radial search, or
   **Add Network Stations** (which also saves a list named after the network)
3. **Automatically** — loading a network saves one; `all-stations` and `shake-alert` are
   created on first server start
4. **By hand** — `es-pos lists show-stations <name> --edit`, or any editor

```bash
es-pos lists list --stations                    # what do I have, and how big?
es-pos lists show-stations bay-area             # print one
es-pos lists show-stations bay-area --edit      # open it in $EDITOR
es-pos lists show-stations bay-area --path      # just the path, for scripting
```

---

## Stream lists

Stream lists name **streams** — a station plus a specific processing solution — and are
what everything downstream actually consumes. They live in `<data-dir>/stream-lists/`,
also as JSONL:

```
{"geosncl": "P143.PB.LY_.10", "edid": "01H46MV4YA5Z3MFKJZ0NW4T39W", "facility": "earthscope", "software": "pivot_rtx"}
{"geosncl": "DEEJ.PW.LY_.00", "edid": "01H46MV4E16V5EKRJRKV4B9AT2", "facility": "cwu", "software": "fastlane"}
```

**All four fields are required.** `edid` is the datasource id the fetch API is actually
queried with — a record without one 422s on every request and reads as "no data" rather
than as an error — and `facility`/`software` are what the builders filter on. Every stream
must also appear in `all-streams`, the generated superset that every other list is
validated against.

Those rules are enforced where lists are written: the web UI's editor rejects an
incomplete line and names it, the Stream List Builder's Save writes complete records
(reporting anything it had to skip), and loading a list reports how many entries were
dropped as unusable.

`all-streams` itself is **read-only** — it is the reference the others are checked
against, so the UI offers no edit, rename, or delete for it. To rebuild it, delete the
file and restart the server.

To audit what you already have:

```bash
es-pos lists validate-streams            # check every list; exits non-zero on problems
es-pos lists validate-streams SCGN       # check one
es-pos lists validate-streams --fix      # repair from all-streams (keeps a .bak)
```

`--fix` repairs rather than discards: a record missing only `facility`/`software` is
completed from `all-streams`, and only entries that cannot be resolved at all are dropped.
Lists built before these rules existed — anything saved with just `geosncl`+`edid`, or a
radial search from before the `GEOSNCL:` prefix fix — are repaired in place.

One station typically has several streams (different processing centers and solution
types), which is why a station list cannot stand in for a stream list.

Built four ways:

1. **CLI** — `es-pos lists get-streams` / `get-radial-streams`, then optionally
   `es-pos lists filter-streams`
2. **Web UI Stream List Builder tab** — pick include/exclude station lists, then filter
   those stations' streams by processing center and solution type
3. **Automatically** — `all-streams` and `shake-alert` are created on first server start
4. **By hand** — `es-pos lists show-streams <name> --edit`, or any editor

```bash
es-pos lists list --streams                     # what do I have, and how big?
es-pos lists show-streams ShakeAlert --edit     # open it in $EDITOR
```

Consumed by `es-pos fetch --list <name>`, `es-pos process`, `es-pos export`,
`es-pos replay -i <name>`, and every list selector in the web UI.

---

## Station coordinates

`resources/coordinates.csv` (bundled with the package) is a merged coordinate table with priority:

1. GAGE GPS IGS14 solutions (`resources/coordinates_generation/gage_gps.igs14.txt`)
2. ShakeAlert extended coordinates (`resources/coordinates_generation/station_coords_extended.dat`)
3. RealTimeDB (`resources/coordinates_generation/rtdb.csv`)

Regenerate with:
```bash
python resources/build_coordinates_csv.py
```

On first use, this bundled file is copied to the **editable** working copy at
`<data-directory>/resources/coordinates.csv` (see [Data directory](#data-directory)) —
edits there (including via the Station Builder's Edit/Update Coordinates) never
touch the bundled copy. The coordinates file powers the **Station Builder** map
tab and the `earthscope_positions.coordinates.Coordinates` class.

```python
from earthscope_positions.coordinates import Coordinates

coords = Coordinates()
c = coords.get("P143")
print(c.latitude, c.longitude, c.height, c.source)
```

---

## Configuration

### Data directory

The default location and the config file are covered under
[Where your data lives](#where-your-data-lives); this section is the precedence
reference.

All data lives under a single **base data directory**, resolved with this precedence —
the first that applies wins:

1. the `ES_POS_DATA_DIRECTORY` environment variable;
2. `data_directory` in the config file (`~/.earthscope-positions.json`);
3. on a first run in a terminal, you are **asked**, and the answer is saved to (2);
4. otherwise the default, `~/earthscope-positions`.

Layer 1 is a per-invocation override for Docker, CI, and cron. Layer 2 is what makes a
choice persist across shells, which the environment variable does not — see
[`es-pos config`](#es-pos-config).

> **There is no `--data-directory` flag.** It was removed: a third way to say the same
> thing, repeated on every data-touching subcommand, caused more confusion than it
> resolved. `ES_POS_DATA_DIRECTORY` covers the same ground for automated callers, and the
> webserver propagates its resolved directory to child processes through the environment.

> **If layer 1 is in effect and disagrees with the configured value**, every command
> prints a one-time note showing both paths and how to reconcile them. A stale
> `ES_POS_DATA_DIRECTORY` in a shell profile otherwise wins silently, and you find out
> only after a long fetch lands somewhere unexpected.

Directories you have used before are remembered, so you can switch between them by
number rather than retyping a path — see `es-pos config list-data-dirs` / `use-data-dir`.

> **Changed:** earlier versions defaulted to `<nearest ancestor containing
> pyproject.toml>/data`. That is gone. Run from inside an unrelated Python project, it
> wrote a multi-GB tree into *that* project's directory. If you have an existing `./data`
> tree from before, the tool notices it and tells you the one command that adopts it:
> `es-pos config set-data-dir ./data`.

The layout is derived from the base:

```
<base>/arrow/                 # downloaded position Arrow files
<base>/stream-lists/          # stream-list JSONL files
<base>/station-lists/         # station-list JSONL files
<base>/plots/                 # generated plot images (e.g. ppsd/)
<base>/positions_diagnose/    # es-pos test fetch output
<base>/positions_errors.jsonl # fetch API error log
<base>/resources/             # editable coordinates.csv + export path-spec TOMLs
                               #   (seeded from the bundled ./resources/ on first use)
```

Examples:

```bash
# Point the whole tree at a custom location
es-pos --help                                   # (flag lives on each subcommand)
ES_POS_DATA_DIRECTORY=/mnt/es es-pos fetch --list ShakeAlert --start 2026-01-01
ES_POS_DATA_DIRECTORY=/mnt/es es-pos webserver   # same, via environment
```

The Arrow root is always `<data-directory>/arrow`; every sub-directory
(`arrow/`, `stream-lists/`, `station-lists/`, `plots/`, `resources/`, …) derives from
the single resolved base.

### Environment marker (`<data-directory>/.config/environment.json`)

Which EarthScope deployment the tree pulls from. Absent means production. Written only by
`es-pos config use-data-dir --stage` / `--prod` — see
[Production and stage](#production-and-stage) — and hidden from the File Explorer, since
hand-editing it would route around the guard that keeps prod and stage data apart.

```json
{
  "environment": "stage",
  "profile": "stage",
  "api_url": "https://api.dev.earthscope.org",
  "written_at": "2026-08-31T18:22:04Z",
  "written_by": "es-pos config use-data-dir"
}
```

It lives with the data rather than in `~/.earthscope-positions.json` because the two
deployments issue different EDIDs: it is a property of the tree, not of the install, and
it has to survive `move-data-dir` (it does — it rides along inside the moved directory).

Resolution order, first that applies:

1. the `ES_POS_ENVIRONMENT` environment variable — for the web server to pin its child
   processes, not a user-facing switch
2. `environment` in this file
3. `prod`

The `es` profile follows from the environment, unless `profile` here or the `ES_PROFILE`
environment variable names a different one.

### Config file (`~/.earthscope-positions.json`)

Holds settings that persist between runs — the active data directory and the ones used
before it:

```json
{
  "data_directory": "/Volumes/BigDisk/positions",
  "known_data_directories": [
    "/Users/you/earthscope-positions",
    "/mnt/gnss/positions",
    "/Volumes/BigDisk/positions"
  ]
}
```

`known_data_directories` keeps its first-seen order, so the numbers shown by
`es-pos config list-data-dirs` stay valid after you switch.

It is created at runtime in your home directory, **not** inside the installed package,
so it survives `pip install --upgrade`, reinstalls, and uninstalls. You should not need
to edit it by hand — `es-pos config` writes it — but it is plain JSON if you want to.
Set `ES_POS_CONFIG_FILE` to put it somewhere else.

### MiniSEED path spec (`<data-directory>/resources/miniseed_path_spec.toml`)

Controls output naming for `es-pos export miniseed`. Auto-created from the bundled default on first run.

The `[encoding]` section also holds `format_version` (3 or 2), `max_record_length`
(maximum record size in **bytes**), and `gap_factor`.

> **Note:** `max_record_length` replaced the older `max_samples_per_record` key, because
> libmseed packs to a byte budget rather than a sample count. Spec files written before
> that change still carry the old key; it is ignored with a warning, and the default
> 4096-byte record length applies. Delete the stale key to silence the warning.

### GeoJSON path spec (`<data-directory>/resources/geojson_path_spec.toml`)

`round_decimals` caps the precision of positions and uncertainties. Values are metres, so
**3 = millimetres**, which is the finest resolution meaningful for GNSS PPP output and the
maximum this writer emits — a larger value in the spec is clamped to 3 with a warning.
Writing raw float64 leaks binary-representation noise into the JSON
(`0.037` arriving as `0.037000000000000005`), which is not extra precision.

Controls output naming for `es-pos export geojson` (separate sections for compact and full formats).

---

## Project structure

```
earthscope-positions/
├── src/earthscope_positions/
│   ├── es_pos.py              # Unified CLI entry point (es-pos)
│   ├── arrow_inspect.py       # es-pos inspect subcommand
│   ├── paths.py               # Data-directory resolution + config file
│   ├── environment.py         # production vs stage, per data directory
│   ├── coordinates.py         # Station coordinate lookup class
│   ├── stations/
│   │   └── station_list.py    # es-pos lists subcommands
│   ├── fetch/
│   │   └── positions_fetch.py # es-pos fetch subcommands
│   ├── process/
│   │   └── completeness.py    # es-pos process completeness
│   ├── export/
│   │   ├── miniseed_writer.py # MiniSEED export (v3 default, v2 optional; via pymseed)
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
│   │       ├── StationListBuilderPage.vue
│   │       ├── StreamListBuilderPage.vue
│   │       ├── PlotsPage.vue
│   │       └── ReplayPage.vue
│   └── spaBuild/              # Compiled SPA (git-ignored; run npm run build)
├── data/
│   ├── arrow/                 # Downloaded position data
│   ├── stream-lists/          # Saved stream list JSON files
│   ├── station-lists/         # Saved station list JSON files
│   ├── plots/                 # Generated plots (power spectral density, etc.)
│   └── resources/             # Editable copies, seeded from ./resources/ on first use:
│       ├── coordinates.csv           #   station coordinates (Station Builder)
│       ├── geojson_path_spec.toml    #   `es-pos export geojson` output layout
│       └── miniseed_path_spec.toml   #   `es-pos export miniseed` output layout
├── resources/                  # Bundled templates for data/resources/ (see above)
│   ├── coordinates_generation/       # Station coordinate source files
│   ├── build_coordinates_csv.py      # Regenerates coordinates.csv from the sources above
│   ├── coordinates.csv
│   ├── geojson_path_spec.toml
│   └── miniseed_path_spec.toml
└── pyproject.toml
```

---

## Requirements

- Python ≥ 3.11
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

A data directory on **stage** uses a different `es` profile — `stage` by default — so its
tokens live at `~/.earthscope/stage/tokens.json` and are obtained with
`es user login --profile stage`. Every "not logged in" message names the right command for
whichever environment is active. See [Production and stage](#production-and-stage).


---

## Docker

Build and run the web server in Docker instead of a local venv, via the single
`es-pos-docker.sh` script (build, run, and the container's own entrypoint logic
all live in that one file):

```bash
./es-pos-docker.sh build              # build the image
./es-pos-docker.sh run                # run it (foreground, --rm -it)
```

`run` mounts a **data directory** at `/data` and your **`~/.earthscope`**
credentials at `/root/.earthscope`, so downloaded data and your EarthScope
login both persist on the host across container runs — log in with
`es user login` on the host first; the container never needs its own login.

**The container path is fixed at `/data`; only the host side varies.** With no
`--data-dir`, the script resolves the host directory the same way the CLI does —
`$ES_POS_DATA_DIRECTORY`, else `data_directory` from `~/.earthscope-positions.json`,
else `~/earthscope-positions` — so a container run lands on the same tree as
`es-pos` on the host without being told twice. The banner names which one it used:

```
Starting earthscope-positions:latest  ->  http://localhost:8000
  data:        /Users/you/earthscope-positions  ->  /data   (from /Users/you/.earthscope-positions.json)
  credentials: /Users/you/.earthscope  ->  /root/.earthscope
```

Point it somewhere else with `--data-dir /Volumes/BigDisk/positions`. `run` also sets
`ES_POS_HOST_DATA_DIRECTORY` inside the container — used only so the Overview tab can
show both ends of the mount, since `/data` on its own means nothing on the host.
Binds to `0.0.0.0` inside the container; on a Mac, Docker Desktop maps
`localhost:PORT` on the host straight through, so `http://localhost:8000`
(the default) just works.

### Logging in

`run` mounts `~/.earthscope` from the host, so if you've already run
`es user login` on the host, the container picks up those credentials with no
extra step. For a machine that's never logged in (or to add a second profile),
log in *inside Docker* instead:

```bash
./es-pos-docker.sh login
```

The container can't open a browser for you, but `es user login` already
handles that itself: it performs the Device Code flow (prints a URL + code to
open from any browser, on any device) whenever the profile isn't configured
for the redirect-based flow — so this works fine non-interactively. It runs
`es user login` and exits (always foreground `--rm -it`, since you need to see
the URL/code); it doesn't start the web server. Container name:
`earthscope-positions-login`.

`login` takes `--earthscope-dir PATH` (default `~/.earthscope` — point this at
an empty directory for a genuinely fresh login) and `--profile NAME` (default
`"default"`, the profile `es user login` uses with no `--profile` given).
`--stage` is shorthand for `--profile stage`.

You do **not** need to pass `--profile` to `run` or `cli` afterward: the profile
follows the mounted data directory's environment, so a directory marked with
`es-pos config use-data-dir --stage` resolves to the `stage` profile on its own.
Pass `--profile` only to override that — see
[Production and stage](#production-and-stage).

To run the container against stage, mark the host directory first and log into
the matching profile:

```bash
es-pos config use-data-dir --stage ~/earthscope-positions-stage
./es-pos-docker.sh login --stage
./es-pos-docker.sh run --data-dir ~/earthscope-positions-stage
```

The web UI then shows the amber **STAGE** badge in the nav bar.

### `run` options

| Flag | Default | Description |
| --- | --- | --- |
| `--data-dir PATH` | *(resolved — env var, then `~/.earthscope-positions.json`, then `~/earthscope-positions`)* | Host directory mounted at `/data` |
| `--earthscope-dir PATH` | `~/.earthscope` | Host directory mounted at `/root/.earthscope` |
| `--profile NAME` | *(from the data directory's environment: `default` for production, `stage` for a stage directory)* | Named profile to read credentials from. Pass it only to override the directory's own choice |
| `--port N` | `8000` | Port published on the host and inside the container |
| `--hostname NAME` | `localhost` | Hostname shown in UI callback URLs (e.g. the Replay curl commands) |
| `--image TAG` | `earthscope-positions:latest` | Image to run |
| `--name NAME` | `earthscope-positions` | Container name |
| `--detach` | off | Run detached with `--restart unless-stopped` (auto-starts on Docker/system restart, auto-restarts on crash) instead of the default foreground `--rm -it` |

### CLI access

For one-off commands (`es-pos fetch`, `es-pos lists`, `es-pos export`, …)
instead of the web server, use `cli`:

```bash
./es-pos-docker.sh cli
```

This mounts the same data directory and `~/.earthscope` credentials as `run`,
and runs the exact same startup pre-flight (auth check, seeding
coordinates.csv/path-spec resources, preloading default stream lists) — so
you land in a shell (venv already active) with the same state a `run`
container would have, just without a web server bound to a port. Takes the
same `--data-dir` / `--earthscope-dir` / `--profile` / `--image` / `--name` as
`run` (no `--port`/`--hostname`/`--detach` — there's no server here). Always
foreground `--rm -it`, named `earthscope-positions-cli`.

`build` takes `--tag IMAGE_TAG` (default `earthscope-positions:latest`).
`./es-pos-docker.sh help` (or no arguments) shows the full usage for all four.

Examples:

```bash
# Fresh login under a named profile, then run against that same profile
./es-pos-docker.sh login --earthscope-dir ./es-creds --profile dev
./es-pos-docker.sh run --earthscope-dir ./es-creds --profile dev

# Run against the stage deployment (the data directory carries the environment,
# so `run` needs no --profile)
es-pos config use-data-dir --stage ~/earthscope-positions-stage
./es-pos-docker.sh login --stage
./es-pos-docker.sh run --data-dir ~/earthscope-positions-stage

# Custom data location and port
./es-pos-docker.sh run --data-dir /mnt/es-data --port 9000

# Run as a long-lived background service
./es-pos-docker.sh run --detach

docker logs -f earthscope-positions   # follow logs
docker stop earthscope-positions      # stop it (won't auto-restart after an explicit stop)

# Run a one-off fetch against the same data directory `run` uses
./es-pos-docker.sh cli
# (inside the container)  es-pos fetch --list ShakeAlert --start 2026-01-01
```

The image (`Dockerfile`) copies the repo minus `data/` (see `.dockerignore`),
builds a venv with [`uv`](https://docs.astral.sh/uv/) (much faster than pip),
and installs the package into it — no data or credentials are ever baked in.

---

## Point of contact

**Charlie Sievers** — charlie.sievers@earthscope.org
