"""
Karhunen-Loeve (network PCA) decomposition of GNSS position streams.

Where pairwise coherence answers "how much do these two streams share,"
KLE answers "what is the network's dominant shared signal, and how strongly
does each stream participate in it" — the standard geodesy tool for isolating
regional common-mode error (Dong et al. 2006; Wdowinski et al. 1997's simple
network-average filter is the special case where every loading is equal).

Algorithm
---------
1. Each stream is demeaned over its own valid samples.
2. The spatial covariance matrix is built pairwise-complete: cov[i,j] uses
   only timestamps where *both* i and j have valid data.  This (rather than
   requiring one dense complete matrix) is what lets KLE work on a gappy,
   irregularly-available network — the same practical approximation
   :mod:`coherence` uses.
3. Eigendecomposition of that covariance matrix gives, per mode: the fraction
   of network variance it explains (eigenvalue / total) and its spatial
   loading (eigenvector — how strongly, and in what direction, each stream
   participates).
4. A mode's time series is reconstructed by, at each timestamp, a
   loading-weighted least-squares combination of whichever streams have valid
   data right then (so gaps in any one stream don't break the reconstruction).
5. "Common-mode removed" = each stream's original series minus its own
   loading times the reconstructed mode series, for the leading mode(s).
"""
from __future__ import annotations

import numpy as np


def _demean(v: np.ndarray) -> tuple[np.ndarray, float]:
    valid = ~np.isnan(v)
    mean = float(np.mean(v[valid])) if valid.any() else 0.0
    return v - mean, mean


def karhunen_loeve(dense: dict[str, np.ndarray], *, n_modes: int = 5) -> dict:
    """Decompose the network's shared variance into KLE modes.

    *dense* maps geosncl -> 1 Hz dense array (NaN for gaps), all the same
    length (see :func:`coherence.densify_1hz`).

    Returns a dict:
        geosncls:              sorted stream order (also the loading order)
        means:                 {geosncl: mean of its valid samples}
        n_modes:                number of modes actually returned (<= n_modes, <= len(geosncls))
        eigenvalues:            length n_modes, descending
        variance_explained_pct: length n_modes, sums to <= 100
        loadings:               n_modes x len(geosncls) — loadings[k][i] is
                                stream i's participation in mode k
        min_pair_overlap:       smallest pairwise-complete sample count used
                                to build the covariance matrix (a low value
                                means some pair barely overlapped — the
                                corresponding covariance entry is noisy)
    """
    geosncls = sorted(dense.keys())
    n = len(geosncls)
    if n == 0:
        return {
            "geosncls": [], "means": {}, "n_modes": 0,
            "eigenvalues": [], "variance_explained_pct": [], "loadings": [],
            "min_pair_overlap": 0,
        }

    demeaned: dict[str, np.ndarray] = {}
    means: dict[str, float] = {}
    for g in geosncls:
        demeaned[g], means[g] = _demean(dense[g])

    cov = np.zeros((n, n))
    min_overlap = None
    for i in range(n):
        for j in range(i, n):
            xi, xj = demeaned[geosncls[i]], demeaned[geosncls[j]]
            mask = ~np.isnan(xi) & ~np.isnan(xj)
            cnt = int(np.count_nonzero(mask))
            if i != j:
                min_overlap = cnt if min_overlap is None else min(min_overlap, cnt)
            if cnt < 2:
                continue
            c = float(np.mean(xi[mask] * xj[mask]))
            cov[i, j] = cov[j, i] = c

    eigvals, eigvecs = np.linalg.eigh(cov)  # ascending; cov is symmetric
    order = np.argsort(eigvals)[::-1]
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]

    k = min(n_modes, n)
    total_var = float(np.sum(np.clip(eigvals, 0.0, None)))
    if total_var > 0:
        var_pct = (np.clip(eigvals[:k], 0.0, None) / total_var * 100.0).tolist()
    else:
        var_pct = [0.0] * k

    return {
        "geosncls": geosncls,
        "means": means,
        "n_modes": k,
        "eigenvalues": eigvals[:k].tolist(),
        "variance_explained_pct": var_pct,
        "loadings": eigvecs[:, :k].T.tolist(),
        "min_pair_overlap": int(min_overlap) if min_overlap is not None else 0,
    }


def reconstruct_mode(
    dense: dict[str, np.ndarray], geosncls: list[str], loadings: list[float]
) -> np.ndarray:
    """Reconstruct one mode's time series: at each timestamp, the
    loading-weighted least-squares combination of whichever streams have
    valid data there.  NaN where no stream had valid data at all."""
    n_t = len(dense[geosncls[0]]) if geosncls else 0
    num = np.zeros(n_t)
    den = np.zeros(n_t)
    for i, g in enumerate(geosncls):
        d, _mean = _demean(dense[g])
        valid = ~np.isnan(d)
        num[valid] += loadings[i] * d[valid]
        den[valid] += loadings[i] ** 2
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 1e-12, num / den, np.nan)


def common_mode_removed(
    dense: dict[str, np.ndarray], *, n_modes_removed: int = 1
) -> dict[str, np.ndarray]:
    """Each stream's original series with the leading *n_modes_removed* KLE
    mode(s) subtracted — in the stream's own original units and mean level,
    so it drops in as a direct replacement for the raw series.
    """
    geosncls = sorted(dense.keys())
    if len(geosncls) < 2:
        return {g: dense[g].copy() for g in geosncls}

    kle = karhunen_loeve(dense, n_modes=max(n_modes_removed, 1))
    residual = {g: dense[g].copy() for g in geosncls}

    for k in range(min(n_modes_removed, kle["n_modes"])):
        loadings = kle["loadings"][k]
        pc = reconstruct_mode(dense, geosncls, loadings)
        for i, g in enumerate(geosncls):
            contribution = loadings[i] * pc
            residual[g] = residual[g] - np.where(np.isnan(contribution), 0.0, contribution)

    return residual
