"""
Pairwise magnitude-squared coherence between GNSS position streams.

Quantifies "common-mode" noise shared across streams — signal correlated
across stations/processing-software at a given timescale, as opposed to each
stream's own independent noise.  Streams sharing the same clock/orbit
products, or observing the same satellites from nearby stations, tend to show
elevated coherence at the timescales where that shared error dominates.

Algorithm
---------
For each pair of streams:
  1. Both are projected onto a shared 1 Hz grid covering [start, end)
     (positions are nominally 1 Hz — see the top-level README).  Missing
     epochs become NaN.
  2. Only indices where BOTH streams have valid data are kept (the
     "intersection of validity").  This concatenates around gaps rather than
     modeling them explicitly — a standard practical approximation for
     lightly-gappy series.  Pairs without enough valid overlap are skipped.
  3. Welch's method (``scipy.signal.coherence``) estimates the full coherence
     spectrum for every pair, all sharing **one** segment length (picked once
     from the overall requested span) so every pair lands on the exact same
     frequency bins — required for the heatmap/multi-line display, where all
     pairs must share one frequency axis.
  4. Each pair's spectrum is resampled onto a fixed set of log-spaced
     frequency points for display, since a raw Welch spectrum can have many
     thousands of bins — one per stream pair would be an enormous response
     for no visual benefit (log-frequency binning is standard for spectra
     spanning several decades).
"""
from __future__ import annotations

import numpy as np
from scipy import signal

MIN_OVERLAP_FRAC = 0.5      # need >= 50% of the requested span valid for both streams
MIN_NPERSEG_S = 600.0       # never go below 10-min segments
MAX_NPERSEG_S = 8 * 3600.0  # cap segments at 8 h so shorter requests still average several
MIN_SEGMENTS = 4.0          # target at least this many (50%-overlap) Welch segments
N_DISPLAY_FREQS = 150       # log-spaced frequency points returned per pair


def densify_1hz(
    times_ms: np.ndarray, values: np.ndarray, start_ms: int, end_ms: int
) -> np.ndarray:
    """Project (times_ms, values) onto a dense 1 Hz grid covering [start_ms, end_ms).

    Each sample is snapped to the nearest whole second.  Returns a float64
    array of length ``(end_ms - start_ms) // 1000``, NaN wherever no sample
    fell in that second (or, if more than one did, the last one wins).
    """
    n = max(0, (end_ms - start_ms) // 1000)
    out = np.full(n, np.nan, dtype=np.float64)
    if n == 0 or len(times_ms) == 0:
        return out
    idx = np.round((np.asarray(times_ms) - start_ms) / 1000.0).astype(np.int64)
    valid = (idx >= 0) & (idx < n)
    out[idx[valid]] = np.asarray(values, dtype=np.float64)[valid]
    return out


def _adaptive_nperseg(n_samples: int, fs: float) -> int | None:
    """Pick a Welch segment length that resolves reasonably long periods while
    still averaging several segments.  Returns None if there isn't enough data
    to be useful at all."""
    target = n_samples / MIN_SEGMENTS
    nperseg = np.clip(target, MIN_NPERSEG_S * fs, MAX_NPERSEG_S * fs)
    nperseg = int(min(nperseg, n_samples))
    if nperseg < MIN_NPERSEG_S * fs:
        return None
    return nperseg


def _log_resample(f_src: np.ndarray, y_src: np.ndarray, f_grid: np.ndarray) -> np.ndarray:
    """Resample a spectrum onto *f_grid* (log-frequency linear interpolation)."""
    return np.interp(np.log(f_grid), np.log(f_src), y_src)


def pairwise_coherence_spectra(
    dense: dict[str, np.ndarray],
    *,
    fs: float = 1.0,
    min_overlap_frac: float = MIN_OVERLAP_FRAC,
    n_display_freqs: int = N_DISPLAY_FREQS,
) -> dict:
    """Compute the full pairwise magnitude-squared coherence spectrum for every
    pair of streams, all on one shared (log-spaced) frequency axis.

    *dense* maps geosncl -> 1 Hz dense array (NaN for gaps); all arrays must
    be the same length (the same [start, end) grid — see :func:`densify_1hz`).

    Returns a dict:
        geosncls:      sorted stream order
        frequencies:   shared log-spaced frequency axis (Hz), length n_display_freqs
        n_valid:       {geosncl: valid (non-NaN) sample count}
        n_total:       length of the requested grid (samples)
        pairs_skipped: [[geosncl_a, geosncl_b, reason], ...]
        pairs:         [{"a", "b", "coherence": [...]}, ...] — coherence is a
                       list the same length as `frequencies`, one entry per pair
                       that had enough overlapping data
    """
    geosncls = sorted(dense.keys())
    n_total = len(next(iter(dense.values()))) if dense else 0
    n_valid = {g: int(np.count_nonzero(~np.isnan(v))) for g, v in dense.items()}

    nperseg = _adaptive_nperseg(n_total, fs) if n_total else None

    pairs: list[dict] = []
    pairs_skipped: list[tuple[str, str, str]] = []
    freq_grid: np.ndarray | None = None

    if nperseg is None:
        for i in range(len(geosncls)):
            for j in range(i + 1, len(geosncls)):
                pairs_skipped.append((geosncls[i], geosncls[j], "too little data"))
        return {
            "geosncls": geosncls,
            "frequencies": [],
            "n_valid": n_valid,
            "n_total": n_total,
            "pairs_skipped": [list(p) for p in pairs_skipped],
            "pairs": [],
        }

    for i in range(len(geosncls)):
        for j in range(i + 1, len(geosncls)):
            gi, gj = geosncls[i], geosncls[j]
            xi, xj = dense[gi], dense[gj]
            mask = ~np.isnan(xi) & ~np.isnan(xj)
            n_overlap = int(np.count_nonzero(mask))
            if n_overlap < n_total * min_overlap_frac or n_overlap < nperseg:
                pairs_skipped.append((gi, gj, "insufficient overlap"))
                continue

            x, y = xi[mask], xj[mask]
            with np.errstate(invalid="ignore", divide="ignore"):
                f, cxy = signal.coherence(x, y, fs=fs, nperseg=nperseg, noverlap=nperseg // 2)
            # f[0] == 0 (DC) — coherence there is undefined/meaningless for a
            # demeaned-ish signal; drop it before the log-frequency grid.
            f, cxy = f[1:], cxy[1:]
            if freq_grid is None:
                freq_grid = np.geomspace(f[0], f[-1], n_display_freqs)
            # A bin with ~zero power in either signal makes Cxy = |Pxy|^2/Pxx/Pyy
            # a 0/0 division -> NaN (scipy warns "invalid value encountered in
            # divide"); log-resampling can then spread that NaN to nearby grid
            # points too.  JSON can't encode NaN at all (Starlette's encoder
            # rejects it outright), so treat "no measurable power to correlate"
            # as 0 coherence rather than leaving it undefined.
            cxy_grid = np.nan_to_num(_log_resample(f, cxy, freq_grid), nan=0.0, posinf=1.0, neginf=0.0)
            cxy_grid = np.clip(cxy_grid, 0.0, 1.0)
            pairs.append({"a": gi, "b": gj, "coherence": cxy_grid.tolist()})

    return {
        "geosncls": geosncls,
        "frequencies": freq_grid.tolist() if freq_grid is not None else [],
        "n_valid": n_valid,
        "n_total": n_total,
        "pairs_skipped": [list(p) for p in pairs_skipped],
        "pairs": pairs,
    }
