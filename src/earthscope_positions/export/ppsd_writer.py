"""
PPSD (Probabilistic Power Spectral Density) writer for GNSS position Arrow files.

Algorithm matches ~/python/src/csievers/positions/plot_ppsd.py / MonitorApplication.java:
  WINDOW = 1024  (Hanning window)
  STEP   = 512   (50 % overlap)
  NFFT   = 32768 (zero-padded for frequency resolution)

X-axis:  log10(period) from 1 s to 10 000 s
Y-axis:  power in dB (m²/Hz)
Output:  3-panel PNG  (East | North | Up)  per station or per station-group

Cache:
  Each source arrow file gets a sidecar *_ppsd.arrow* file storing a sparse
  representation of the three (E, N, U) histograms.  Subsequent runs skip the
  FFT step entirely and just merge the cached counts.

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

# ── PPSD parameters (matching MonitorApplication.java) ────────────────────────
WINDOW       = 1024
STEP         = 512
NFFT         = 32768
POWER_MIN    = -80.0
POWER_MAX    =  20.0
LOG_PERIOD_MIN = 0.0    # log10(1 s)
LOG_PERIOD_MAX = 4.0    # log10(10 000 s)
N_PERIOD_BINS  = 67
N_POWER_BINS   = 100
# ──────────────────────────────────────────────────────────────────────────────

_HANNING     = 0.5 * (1.0 - np.cos(2.0 * np.pi * np.arange(WINDOW) / (WINDOW - 1)))
_HANNING_WSS = float(np.sum(_HANNING ** 2))

_KS          = np.arange(1, NFFT // 2 + 1)
_LOG_PERIODS = np.log10(NFFT / _KS.astype(float))
_IN_RANGE    = (_LOG_PERIODS >= LOG_PERIOD_MIN) & (_LOG_PERIODS <= LOG_PERIOD_MAX)
_KS          = _KS[_IN_RANGE]
_LOG_PERIODS = _LOG_PERIODS[_IN_RANGE]
_P_BINS      = np.clip(
    ((_LOG_PERIODS - LOG_PERIOD_MIN) / (LOG_PERIOD_MAX - LOG_PERIOD_MIN) * N_PERIOD_BINS).astype(int),
    0, N_PERIOD_BINS - 1,
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
# Core computation (vectorized)
# ---------------------------------------------------------------------------

def accumulate_ppsd(signal: np.ndarray, histogram: np.ndarray) -> int:
    """Add Hanning-windowed, 50%-overlap FFT segments into *histogram* (in-place).

    Linear power is averaged per log-period bin via np.bincount (vectorized),
    then the bin's dB value is histogrammed.  Returns the number of frames added.
    """
    n = len(signal)
    if n < WINDOW:
        return 0
    frames = 0
    bin_counts = np.bincount(_P_BINS, minlength=N_PERIOD_BINS).astype(float)
    valid_period = bin_counts > 0  # period bins that have at least one FFT bin

    for start in range(0, n - WINDOW + 1, STEP):
        segment = signal[start : start + WINDOW] * _HANNING
        padded = np.zeros(NFFT)
        padded[:WINDOW] = segment
        fft_vals = np.fft.rfft(padded)

        power = (np.abs(fft_vals) ** 2) / _HANNING_WSS
        power[1:-1] *= 2.0
        power_ks = power[_KS]

        # Average linear power within each period bin (vectorized)
        bin_sum = np.bincount(_P_BINS, weights=power_ks, minlength=N_PERIOD_BINS)
        avg_lin = np.where(valid_period, bin_sum / np.where(valid_period, bin_counts, 1.0), 0.0)

        with np.errstate(divide="ignore", invalid="ignore"):
            avg_db = np.where(avg_lin > 0, 10.0 * np.log10(avg_lin), -1e9)

        q_bins = ((avg_db - POWER_MIN) / (POWER_MAX - POWER_MIN) * N_POWER_BINS).astype(int)
        in_range = valid_period & (q_bins >= 0) & (q_bins < N_POWER_BINS)

        np.add.at(histogram, (np.where(in_range)[0], q_bins[in_range]), 1)
        frames += 1

    return frames


# ---------------------------------------------------------------------------
# Arrow loading
# ---------------------------------------------------------------------------

def load_arrow_enu(path: pathlib.Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load an Arrow IPC stream file and return (east, north, up) as float64 arrays."""
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
        b"geosncl":      geosncl.encode(),
        b"date":         date_str.encode(),
        b"frames_e":     str(frames_e).encode(),
        b"frames_n":     str(frames_n).encode(),
        b"frames_u":     str(frames_u).encode(),
        b"window":       str(WINDOW).encode(),
        b"nfft":         str(NFFT).encode(),
        b"power_min":    str(POWER_MIN).encode(),
        b"power_max":    str(POWER_MAX).encode(),
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

    mask = np.isfinite(east) & np.isfinite(north) & np.isfinite(up)
    e, n, u = east[mask], north[mask], up[mask]

    hist_e = np.zeros((N_PERIOD_BINS, N_POWER_BINS), dtype=np.int64)
    hist_n = np.zeros((N_PERIOD_BINS, N_POWER_BINS), dtype=np.int64)
    hist_u = np.zeros((N_PERIOD_BINS, N_POWER_BINS), dtype=np.int64)

    frames_e = accumulate_ppsd(e, hist_e)
    frames_n = accumulate_ppsd(n, hist_n)
    frames_u = accumulate_ppsd(u, hist_u)

    if frames_e == 0 and frames_n == 0 and frames_u == 0:
        return None

    geosncl = _geosncl_from_path(arrow_path) or ""
    m = re.search(r"(\d{4})(\d{2})(\d{2})T", arrow_path.stem)
    date_str = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""

    table = _histograms_to_sparse(hist_e, hist_n, hist_u, frames_e, frames_n, frames_u, geosncl, date_str)
    if table is None:
        return None

    cp = cache_path_for(arrow_path)
    with open(cp, "wb") as f:
        writer = ipc.new_stream(f, table.schema)
        writer.write_table(table)
        writer.close()

    return cp


def load_ppsd_cache(arrow_path: pathlib.Path) -> pa.Table | None:
    """Load the sidecar cache for *arrow_path* if it exists and is structurally valid."""
    cp = cache_path_for(arrow_path)
    if not cp.exists():
        return None
    try:
        with open(cp, "rb") as f:
            table = ipc.open_stream(f).read_all()
        required = {"component", "p_bin", "q_bin", "count"}
        if required.issubset(set(table.column_names)):
            return table
    except Exception:
        pass
    return None


def ensure_ppsd_cache(arrow_path: pathlib.Path) -> pathlib.Path | None:
    """Return path to a valid cache, computing it first if missing.

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
    run_dir: pathlib.Path,
    *,
    label: str,
    title_prefix: str = "",
    verbose: bool = False,
) -> pathlib.Path | None:
    """Merge cached PPSD data for *files* and render a PNG into *run_dir*.

    Any file whose cache is missing is computed on-the-fly (fallback).
    Returns the written PNG path, or None if no valid data was found.
    """
    tables: list[pa.Table] = []
    for path in files:
        t = load_ppsd_cache(path)
        if t is None:
            # Cache was missing — try to compute it now (single-threaded fallback)
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

    run_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.+()-]", "_", label)
    out = run_dir / f"ppsd-{safe}.png"
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
) -> list[pathlib.Path]:
    """Compute and write PPSD plots (legacy direct path, used by CLI).

    separate=True (default): one 3-panel PNG per geosncl.
    separate=False: accumulate all files into one combined plot.
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
    run_dir = output_root / date_label
    run_dir.mkdir(parents=True, exist_ok=True)

    written: list[pathlib.Path] = []

    if separate:
        groups: dict[str, list[pathlib.Path]] = {}
        for p in arrow_files:
            g = _geosncl_from_path(p)
            if g is None:
                continue
            groups.setdefault(g, []).append(p)

        for geosncl, files in sorted(groups.items()):
            out = _write_one_ppsd(geosncl, files, run_dir, cmap, verbose=verbose)
            if out:
                written.append(out)
    else:
        if group_label:
            label = group_label
        else:
            geosncls = sorted({g for p in arrow_files if (g := _geosncl_from_path(p)) is not None})
            label = "+".join(geosncls[:3]) + (f"+…({len(geosncls)})" if len(geosncls) > 3 else "")
        out = _write_one_ppsd(label, list(arrow_files), run_dir, cmap, verbose=verbose,
                              title_prefix="Combined")
        if out:
            written.append(out)

    return written


def _write_one_ppsd(
    label: str,
    files: list[pathlib.Path],
    run_dir: pathlib.Path,
    cmap,  # type: ignore[type-arg]
    *,
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
        mask = np.isfinite(east) & np.isfinite(north) & np.isfinite(up)
        e, n, u = east[mask], north[mask], up[mask]
        total_frames += accumulate_ppsd(e, hist_e)
        accumulate_ppsd(n, hist_n)
        accumulate_ppsd(u, hist_u)
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
    out = run_dir / f"ppsd-{safe}.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)

    if verbose:
        try:
            display = out.relative_to(pathlib.Path.cwd())
        except ValueError:
            display = out
        print(f"  [ppsd] {label}: {total_frames} frames  → {display}", file=sys.stderr)

    return out
