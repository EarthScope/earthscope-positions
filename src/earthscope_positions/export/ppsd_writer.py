"""
PPSD (Probabilistic Power Spectral Density) writer for GNSS position Arrow files.

Algorithm:
  Direct DFT at N_PERIOD_BINS logarithmically-spaced target periods, evaluated
  on 50%-overlapping Hanning-windowed segments.  The DFT is computed via a
  precomputed (N_PERIOD_BINS × WINDOW) complex basis matrix, giving exact power
  estimates at each target period without the bin-mapping approximation of the
  FFT approach.

  WINDOW = 16384 samples (4.55 h at 1 Hz) covers the full period axis up to
  10 000 s (2.78 h).  NaN gaps are handled by substituting zero and rescaling
  the window normalisation, so time-axis integrity is preserved.

X-axis:  log10(period) from 1 s to 10 000 s
Y-axis:  power in dB (m²/Hz)
Output:  3-panel PNG  (East | North | Up)  per station or per station-group

Cache:
  Each source arrow file gets a sidecar *_ppsd.arrow* file storing a sparse
  representation of the three (E, N, U) histograms.  Subsequent runs skip the
  DFT step entirely and just merge the cached counts.

CLI:
  es-pos export ppsd --all
  es-pos export ppsd data/arrow/P143.CI.LY_.20/202601/*.arrow
  es-pos export ppsd --all --start 2026-01-02 --end 2026-01-10
"""
from __future__ import annotations

import datetime as dt
import pathlib
import re
import sys
from typing import Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import pyarrow as pa
import pyarrow.ipc as ipc

# ── PPSD parameters ────────────────────────────────────────────────────────────
WINDOW         = 16384   # samples per analysis window (16384 s at 1 Hz = 4.55 h)
STEP           = 8192    # 50% overlap
POWER_MIN      = -80.0
POWER_MAX      =  20.0
LOG_PERIOD_MIN = 0.0     # log10(1 s)
LOG_PERIOD_MAX = 4.0     # log10(10 000 s)
N_PERIOD_BINS  = 67
N_POWER_BINS   = 100
MIN_VALID_FRAC = 0.80    # skip windows with more than 20% NaN
# ──────────────────────────────────────────────────────────────────────────────

# Target periods (seconds): 67 exact log-spaced values, 1 s → 10 000 s
_TARGET_PERIODS = 10.0 ** np.linspace(LOG_PERIOD_MIN, LOG_PERIOD_MAX, N_PERIOD_BINS)

# Nyquist mask: for 1 Hz data the minimum resolvable period is 2 samples.
# Bins at T < 2 s are aliased (T=1 s is the DC alias) and must be excluded.
_NYQUIST_MASK = _TARGET_PERIODS >= 2.0  # shape (N_PERIOD_BINS,)

# Hanning window of length WINDOW
_HANNING     = 0.5 * (1.0 - np.cos(2.0 * np.pi * np.arange(WINDOW) / (WINDOW - 1)))
_HANNING_WSS = float(np.sum(_HANNING ** 2))   # full-window normalisation

# DFT basis matrix: (N_PERIOD_BINS, WINDOW), complex128, pre-multiplied by the
# Hanning weights so  _DFT_BASES @ signal  gives the windowed DFT at every
# target period in a single BLAS matrix-vector call (~17 MB, loaded once).
_DFT_BASES = (
    np.exp(-1j * 2.0 * np.pi * np.arange(WINDOW)[None, :] / _TARGET_PERIODS[:, None])
    * _HANNING[None, :]
)

# Right-axis sigma labels (white-noise standard deviation)
_SIGMA_M      = [0.0001, 0.0003, 0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1.0]
_SIGMA_LABELS = ["0.1mm", "0.3mm", "1mm", "3mm", "1cm", "3cm", "10cm", "30cm", "1m"]
_SIGMA_DB     = [10.0 * np.log10(2.0 * s**2) for s in _SIGMA_M]

_PERIOD_TICKS_S = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000]
_PERIOD_TICK_LABELS = ["1s", "2s", "5s", "10s", "20s", "50s",
                       "100s", "200s", "500s", "1ks", "2ks", "5ks", "10ks"]
_PERIOD_TICK_X = [np.log10(p) for p in _PERIOD_TICKS_S]

# ── Sparse cache schema ────────────────────────────────────────────────────────
PPSD_CACHE_SUFFIX = "_ppsd.arrow"

_CACHE_SCHEMA = pa.schema([
    pa.field("component", pa.uint8()),   # 0=E, 1=N, 2=U
    pa.field("p_bin",     pa.uint16()),
    pa.field("q_bin",     pa.uint16()),
    pa.field("count",     pa.uint32()),
])


# ---------------------------------------------------------------------------
# Colormap
# ---------------------------------------------------------------------------

def ppsd_colormap() -> mcolors.LinearSegmentedColormap:
    return mcolors.LinearSegmentedColormap.from_list(
        "ppsd",
        [
            (0.00, 0.00, 0.40),
            (0.00, 0.60, 0.80),
            (0.00, 1.00, 0.00),
            (1.00, 1.00, 0.00),
            (1.00, 0.00, 0.00),
        ],
    )


# ---------------------------------------------------------------------------
# Core computation (DFT-based)
# ---------------------------------------------------------------------------

def accumulate_ppsd(signal: np.ndarray, histogram: np.ndarray) -> int:
    """Add Hanning-windowed DFT frames into *histogram* (in-place).

    Computes the one-sided power spectral density at each of the
    N_PERIOD_BINS target periods via direct DFT, giving exact frequency
    control and reliable estimates for all periods up to WINDOW samples.

    NaN samples are replaced with zero and the window normalisation is
    rescaled to the valid-sample fraction, preserving time-axis integrity.

    Returns the number of frames added.
    """
    n = len(signal)
    if n < WINDOW:
        return 0

    frames = 0
    for start in range(0, n - WINDOW + 1, STEP):
        seg = signal[start : start + WINDOW]
        valid = np.isfinite(seg)
        n_valid = int(valid.sum())
        if n_valid < int(WINDOW * MIN_VALID_FRAC):
            continue

        # Substitute NaN with 0, subtract mean of valid samples to remove DC
        mean_val = seg[valid].mean()
        seg_clean = np.where(valid, seg - mean_val, 0.0)

        # Effective window sum-of-squares (accounts for NaN → 0 substitution)
        wss_eff = float(np.dot(_HANNING ** 2, valid.astype(np.float64)))
        if wss_eff < 1e-30:
            continue

        # One-sided DFT power at all target periods (single BLAS call)
        X     = _DFT_BASES @ seg_clean       # (N_PERIOD_BINS,) complex
        power = np.abs(X) ** 2 / wss_eff * 2.0  # ×2 for one-sided PSD

        with np.errstate(divide="ignore"):
            db = np.where(power > 0.0, 10.0 * np.log10(power), -1e9)

        q     = ((db - POWER_MIN) / (POWER_MAX - POWER_MIN) * N_POWER_BINS).astype(int)
        good  = (q >= 0) & (q < N_POWER_BINS) & _NYQUIST_MASK
        np.add.at(histogram, (np.where(good)[0], q[good]), 1)
        frames += 1

    return frames


# ---------------------------------------------------------------------------
# Arrow loading
# ---------------------------------------------------------------------------

def load_arrow_enu(path: pathlib.Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load an Arrow IPC stream file and return (east, north, up) as float64 arrays.

    Missing values are preserved as NaN (not removed) so that time-axis
    integrity is maintained for the DFT computation.
    """
    with open(path, "rb") as f:
        table = ipc.open_stream(f).read_all()
    east  = table.column("east").to_pylist()
    north = table.column("north").to_pylist()
    up    = table.column("up").to_pylist()
    e = np.array([v if v is not None else np.nan for v in east],  dtype=float)
    n = np.array([v if v is not None else np.nan for v in north], dtype=float)
    u = np.array([v if v is not None else np.nan for v in up],    dtype=float)
    return e, n, u


# ---------------------------------------------------------------------------
# Sparse PPSD cache
# ---------------------------------------------------------------------------

def cache_path_for(arrow_path: pathlib.Path) -> pathlib.Path:
    return arrow_path.with_name(arrow_path.stem + PPSD_CACHE_SUFFIX)


def _histograms_to_sparse(
    hist_e: np.ndarray, hist_n: np.ndarray, hist_u: np.ndarray,
    frames_e: int, frames_n: int, frames_u: int,
    geosncl: str, date_str: str,
) -> pa.Table | None:
    """Convert three dense histograms to a single sparse Arrow table."""
    rows_comp: list[int] = []
    rows_p:    list[int] = []
    rows_q:    list[int] = []
    rows_cnt:  list[int] = []

    for comp_idx, hist in enumerate([hist_e, hist_n, hist_u]):
        ps, qs = np.nonzero(hist)
        for p, q in zip(ps.tolist(), qs.tolist()):
            rows_comp.append(comp_idx)
            rows_p.append(int(p))
            rows_q.append(int(q))
            rows_cnt.append(int(hist[p, q]))

    if not rows_comp:
        return None

    metadata = {
        b"geosncl":       geosncl.encode(),
        b"date":          date_str.encode(),
        b"frames_e":      str(frames_e).encode(),
        b"frames_n":      str(frames_n).encode(),
        b"frames_u":      str(frames_u).encode(),
        b"window":        str(WINDOW).encode(),
        b"algorithm":     b"dft",
        b"power_min":     str(POWER_MIN).encode(),
        b"power_max":     str(POWER_MAX).encode(),
        b"n_period_bins": str(N_PERIOD_BINS).encode(),
        b"n_power_bins":  str(N_POWER_BINS).encode(),
    }
    schema = _CACHE_SCHEMA.with_metadata(metadata)
    return pa.table(
        {
            "component": np.array(rows_comp, dtype=np.uint8),
            "p_bin":     np.array(rows_p,    dtype=np.uint16),
            "q_bin":     np.array(rows_q,    dtype=np.uint16),
            "count":     np.array(rows_cnt,  dtype=np.uint32),
        },
        schema=schema,
    )


def compute_ppsd_cache(arrow_path: pathlib.Path) -> pathlib.Path | None:
    """Compute PPSD for one arrow file and write a sparse sidecar cache.

    Returns the cache path on success, None if the file has no valid data.
    Safe to call from a thread pool — all numpy operations release the GIL.
    """
    try:
        east, north, up = load_arrow_enu(arrow_path)
    except Exception:
        return None

    hist_e = np.zeros((N_PERIOD_BINS, N_POWER_BINS), dtype=np.int64)
    hist_n = np.zeros((N_PERIOD_BINS, N_POWER_BINS), dtype=np.int64)
    hist_u = np.zeros((N_PERIOD_BINS, N_POWER_BINS), dtype=np.int64)

    frames_e = accumulate_ppsd(east,  hist_e)
    frames_n = accumulate_ppsd(north, hist_n)
    frames_u = accumulate_ppsd(up,    hist_u)

    if frames_e == 0 and frames_n == 0 and frames_u == 0:
        return None

    geosncl = _geosncl_from_path(arrow_path) or ""
    m = re.search(r"(\d{4})(\d{2})(\d{2})T", arrow_path.stem)
    date_str = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""

    table = _histograms_to_sparse(
        hist_e, hist_n, hist_u,
        frames_e, frames_n, frames_u,
        geosncl, date_str,
    )
    if table is None:
        return None

    cp = cache_path_for(arrow_path)
    with open(cp, "wb") as f:
        writer = ipc.new_stream(f, table.schema)
        writer.write_table(table)
        writer.close()

    return cp


def load_ppsd_cache(arrow_path: pathlib.Path) -> pa.Table | None:
    """Load the sidecar cache for *arrow_path* if it is valid and current.

    Returns None if the file is missing, structurally broken, or was produced
    by an older algorithm version (triggering recomputation).
    """
    cp = cache_path_for(arrow_path)
    if not cp.exists():
        return None
    try:
        with open(cp, "rb") as f:
            table = ipc.open_stream(f).read_all()
        required = {"component", "p_bin", "q_bin", "count"}
        if not required.issubset(set(table.column_names)):
            return None
        meta = table.schema.metadata or {}
        # Reject caches built with a different window size or algorithm
        if meta.get(b"window") != str(WINDOW).encode():
            return None
        if meta.get(b"algorithm") != b"dft":
            return None
        return table
    except Exception:
        return None


def ensure_ppsd_cache(arrow_path: pathlib.Path) -> pathlib.Path | None:
    """Return path to a valid cache, computing it first if missing or stale.

    Called from the thread pool — returns None if the file yields no valid data.
    """
    if load_ppsd_cache(arrow_path) is not None:
        return cache_path_for(arrow_path)
    return compute_ppsd_cache(arrow_path)


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def merge_sparse_tables(
    tables: list[pa.Table],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Merge a list of sparse PPSD cache tables into three dense histograms.

    Returns (hist_e, hist_n, hist_u, total_frames_e).
    """
    empty = (
        np.zeros((N_PERIOD_BINS, N_POWER_BINS), dtype=np.int64),
        np.zeros((N_PERIOD_BINS, N_POWER_BINS), dtype=np.int64),
        np.zeros((N_PERIOD_BINS, N_POWER_BINS), dtype=np.int64),
        0,
    )
    if not tables:
        return empty

    all_comp = np.concatenate([t.column("component").to_numpy() for t in tables])
    all_p    = np.concatenate([t.column("p_bin").to_numpy()     for t in tables])
    all_q    = np.concatenate([t.column("q_bin").to_numpy()     for t in tables])
    all_c    = np.concatenate([t.column("count").to_numpy()     for t in tables])

    hist = np.zeros((3, N_PERIOD_BINS, N_POWER_BINS), dtype=np.int64)
    np.add.at(hist, (all_comp, all_p, all_q), all_c)

    total_frames = 0
    for t in tables:
        meta = t.schema.metadata or {}
        try:
            total_frames += int(meta.get(b"frames_e", b"0"))
        except (ValueError, TypeError):
            pass

    return hist[0], hist[1], hist[2], total_frames


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_ppsd_panel(ax: plt.Axes, histogram: np.ndarray, title: str, cmap) -> None:  # type: ignore[type-arg]
    col_totals = histogram.sum(axis=1, keepdims=True)
    col_totals = np.where(col_totals == 0, 1, col_totals)
    prob = histogram / col_totals.astype(float)

    x_edges = np.linspace(LOG_PERIOD_MIN, LOG_PERIOD_MAX, N_PERIOD_BINS + 1)
    y_edges = np.linspace(POWER_MIN, POWER_MAX, N_POWER_BINS + 1)

    vmax = float(prob.max()) if prob.max() > 0 else 1.0
    ax.pcolormesh(x_edges, y_edges, prob.T, cmap=cmap, vmin=0.0, vmax=vmax, shading="flat")

    ax.set_facecolor((0.0, 0.0, 0.196))
    ax.set_xlim(LOG_PERIOD_MIN, LOG_PERIOD_MAX)
    ax.set_ylim(POWER_MIN, POWER_MAX)
    ax.set_xticks(_PERIOD_TICK_X)
    ax.set_xticklabels(_PERIOD_TICK_LABELS, fontsize=7, rotation=45, ha="right")
    ax.set_xlabel("Period", fontsize=8)
    ax.set_ylabel("dB (m²/Hz)", fontsize=8)
    ax.tick_params(axis="y", labelsize=7)
    ax.set_title(title, fontsize=9)
    ax.grid(True, color=(0.24, 0.24, 0.31), linewidth=0.5)

    ax2 = ax.twinx()
    ax2.set_ylim(POWER_MIN, POWER_MAX)
    sigma_ticks = [(db, lbl) for db, lbl in zip(_SIGMA_DB, _SIGMA_LABELS)
                   if POWER_MIN <= db <= POWER_MAX]
    if sigma_ticks:
        ax2.set_yticks([db for db, _ in sigma_ticks])
        ax2.set_yticklabels([lbl for _, lbl in sigma_ticks], fontsize=7)
    ax2.set_ylabel("σ (white noise)", fontsize=8)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _geosncl_from_path(arrow_path: pathlib.Path) -> str | None:
    candidate = arrow_path.parent.parent.name
    if "." in candidate:
        return candidate
    m = re.match(r"^(.+?)_\d{8}T", arrow_path.stem)
    return m.group(1) if m else None


def _safe_stem(geosncl: str) -> str:
    return geosncl


def _date_range_label(arrow_files: Sequence[pathlib.Path]) -> str:
    dates: list[dt.date] = []
    for p in arrow_files:
        m = re.search(r"(\d{8})T", p.stem)
        if m:
            try:
                dates.append(dt.date(int(m.group(1)[:4]), int(m.group(1)[4:6]), int(m.group(1)[6:8])))
            except ValueError:
                pass
    if not dates:
        return dt.date.today().isoformat()
    return f"{min(dates).isoformat()}_{max(dates).isoformat()}"


# ---------------------------------------------------------------------------
# Cache-based render (fast path used by the web API)
# ---------------------------------------------------------------------------

def write_ppsd_from_caches(
    files: list[pathlib.Path],
    output_root: pathlib.Path,
    *,
    label: str,
    mode: str,
    date_range: str,
    slug: str | None = None,
    title_prefix: str = "",
    verbose: bool = False,
) -> pathlib.Path | None:
    """Merge cached PPSD data for *files* and render a PNG under *output_root*.

    Output path: ``<output_root>/<mode>/ppsd-<slug>/ppsd-<slug>_<date_range>.png``
    — grouping by PPSD type (*mode*) first, then by plot identity, so repeated
    runs for the same station/group accumulate side-by-side instead of
    scattering across per-run date folders.

    Any file whose cache is missing or stale is computed on-the-fly (fallback).
    Returns the written PNG path, or None if no valid data was found.
    """
    tables: list[pa.Table] = []
    for path in files:
        t = load_ppsd_cache(path)
        if t is None:
            compute_ppsd_cache(path)
            t = load_ppsd_cache(path)
        if t is not None:
            tables.append(t)

    if not tables:
        return None

    hist_e, hist_n, hist_u, total_frames = merge_sparse_tables(tables)
    if total_frames == 0:
        return None

    cmap = ppsd_colormap()
    n_files = len(files)
    pfx = f"{title_prefix} " if title_prefix else ""

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.patch.set_facecolor("white")
    for ax, hist, comp in zip(axes, [hist_e, hist_n, hist_u], ["East", "North", "Up"]):
        plot_ppsd_panel(
            ax, hist,
            f"{pfx}{comp}  ({total_frames} frames, {n_files} file{'s' if n_files != 1 else ''})",
            cmap,
        )
    fig.suptitle(f"PPSD — {label}", fontsize=11, fontweight="bold")
    plt.tight_layout()

    safe = slug if slug else re.sub(r"[^\w.+()-]", "_", label)
    group_dir = output_root / mode / f"ppsd-{safe}"
    group_dir.mkdir(parents=True, exist_ok=True)
    out = group_dir / f"ppsd-{safe}_{date_range}.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)

    if verbose:
        print(f"  [ppsd] {label}: {total_frames} frames, {n_files} files → {out}", file=sys.stderr)

    return out


# ---------------------------------------------------------------------------
# Legacy: write PPSDs directly (used by CLI)
# ---------------------------------------------------------------------------

def write_ppsd(
    arrow_files: Sequence[pathlib.Path],
    output_root: pathlib.Path,
    *,
    start: dt.date | None = None,
    end: dt.date | None = None,
    separate: bool = True,
    verbose: bool = True,
    group_label: str | None = None,
    mode: str | None = None,
) -> list[pathlib.Path]:
    """Compute and write PPSD plots (legacy direct path, used by CLI).

    separate=True (default): one 3-panel PNG per geosncl.
    separate=False: accumulate all files into one combined plot.

    Output path: ``<output_root>/<mode>/ppsd-<name>/ppsd-<name>_<date-range>.png``
    — *mode* defaults to ``"by-stream"`` (separate), ``"by-center"`` (when
    *group_label* is given), or ``"all"`` (combined, no group_label).
    """
    cmap = ppsd_colormap()

    if start is not None or end is not None:
        filtered: list[pathlib.Path] = []
        for p in arrow_files:
            m = re.search(r"(\d{4})(\d{2})(\d{2})T", p.stem)
            if m:
                try:
                    d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                except ValueError:
                    continue
                if start is not None and d < start:
                    continue
                if end is not None and d > end:
                    continue
            filtered.append(p)
        arrow_files = filtered

    if not arrow_files:
        print("[ppsd] No Arrow files to process after date filtering.", file=sys.stderr)
        return []

    date_label = _date_range_label(arrow_files)

    written: list[pathlib.Path] = []

    if separate:
        effective_mode = mode or "by-stream"
        groups: dict[str, list[pathlib.Path]] = {}
        for p in arrow_files:
            g = _geosncl_from_path(p)
            if g is None:
                continue
            groups.setdefault(g, []).append(p)

        for geosncl, files in sorted(groups.items()):
            out = _write_one_ppsd(geosncl, files, output_root, cmap,
                                  mode=effective_mode, date_range=date_label, verbose=verbose)
            if out:
                written.append(out)
    else:
        effective_mode = mode or ("by-center" if group_label else "all")
        if group_label:
            label = group_label
        else:
            geosncls = sorted({g for p in arrow_files if (g := _geosncl_from_path(p)) is not None})
            label = "+".join(geosncls[:3]) + (f"+…({len(geosncls)})" if len(geosncls) > 3 else "")
        out = _write_one_ppsd(label, list(arrow_files), output_root, cmap,
                              mode=effective_mode, date_range=date_label, verbose=verbose,
                              title_prefix="Combined")
        if out:
            written.append(out)

    return written


def _write_one_ppsd(
    label: str,
    files: list[pathlib.Path],
    output_root: pathlib.Path,
    cmap,  # type: ignore[type-arg]
    *,
    mode: str,
    date_range: str,
    verbose: bool,
    title_prefix: str = "",
) -> pathlib.Path | None:
    hist_e = np.zeros((N_PERIOD_BINS, N_POWER_BINS), dtype=np.int64)
    hist_n = np.zeros((N_PERIOD_BINS, N_POWER_BINS), dtype=np.int64)
    hist_u = np.zeros((N_PERIOD_BINS, N_POWER_BINS), dtype=np.int64)
    total_frames = 0
    n_files = 0

    for path in sorted(files):
        try:
            east, north, up = load_arrow_enu(path)
        except Exception as exc:
            if verbose:
                print(f"  [ppsd] skip {path.name}: {exc}", file=sys.stderr)
            continue
        total_frames += accumulate_ppsd(east,  hist_e)
        accumulate_ppsd(north, hist_n)
        accumulate_ppsd(up,    hist_u)
        n_files += 1

    if total_frames == 0:
        if verbose:
            print(f"  [ppsd] {label}: no valid frames — skipping", file=sys.stderr)
        return None

    pfx = f"{title_prefix} " if title_prefix else ""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.patch.set_facecolor("white")
    for ax, hist, comp in zip(axes, [hist_e, hist_n, hist_u], ["East", "North", "Up"]):
        plot_ppsd_panel(
            ax, hist,
            f"{pfx}{comp}  ({total_frames} frames, {n_files} file{'s' if n_files != 1 else ''})",
            cmap,
        )
    title = f"PPSD — {label}"
    fig.suptitle(title, fontsize=11, fontweight="bold")
    plt.tight_layout()

    safe = re.sub(r'[^\w.+()-]', '_', label)
    group_dir = output_root / mode / f"ppsd-{safe}"
    group_dir.mkdir(parents=True, exist_ok=True)
    out = group_dir / f"ppsd-{safe}_{date_range}.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)

    if verbose:
        try:
            display = out.relative_to(pathlib.Path.cwd())
        except ValueError:
            display = out
        print(f"  [ppsd] {label}: {total_frames} frames  → {display}", file=sys.stderr)

    return out
