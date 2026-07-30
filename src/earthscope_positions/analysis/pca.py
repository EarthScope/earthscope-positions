"""
Classical Principal Component Analysis (PCA) network decomposition — the
sibling method to Karhunen-Loeve (kle.py) described in Dong et al. (2006).

Where KLE builds its covariance matrix pairwise-complete (using whichever
timestamps each *pair* of streams shares, so every stream can contribute even
with gaps that don't align across the network), classical PCA instead
requires a genuinely complete data matrix: only timestamps where *every*
selected stream has valid data simultaneously are used. That makes PCA's
decomposition exact — a real eigendecomposition of one consistent dataset,
and each mode's time series is computed by direct projection, not KLE's
loading-weighted least-squares reconstruction — but it can only speak to the
epochs where all streams overlap; elsewhere it offers no comment (this is
exactly the gap KLE exists to fill, per Dong et al.).

Practical implication for common-mode removal: pca_common_mode_removed
cleanly strips the common mode wherever the whole network shares data: any
epoch missing even one stream's data is left as raw, unmodified data there.
"""
from __future__ import annotations

import numpy as np


def _demean_over(v: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, float]:
    mean = float(np.mean(v[mask])) if mask.any() else 0.0
    return v - mean, mean


def principal_component_analysis(dense: dict[str, np.ndarray], *, n_modes: int = 5) -> dict:
    """PCA over the epochs where every stream has simultaneous valid data.

    *dense* maps geosncl -> 1 Hz dense array (NaN for gaps), all the same
    length (see coherence.densify_1hz).

    Returns a dict:
        geosncls:               sorted stream order (also the loading order)
        means:                  {geosncl: mean over the complete epochs used}
        n_modes:                number of modes actually returned
        eigenvalues:            length n_modes, descending
        variance_explained_pct: length n_modes, sums to <= 100
        loadings:               n_modes x len(geosncls) — same convention as kle
        n_complete_epochs:      how many timestamps had every stream present
                                (a low fraction of the requested span means
                                PCA is only speaking for a small slice of it —
                                the epochs never all missing/incomplete for
                                every stream at once are what's left)
        mode_series:            n_modes x len(any dense array), np.ndarray —
                                exact per-epoch projection, NaN outside the
                                complete epochs
    """
    geosncls = sorted(dense.keys())
    n = len(geosncls)
    n_t = len(dense[geosncls[0]]) if geosncls else 0
    if n == 0:
        return {
            "geosncls": [], "means": {}, "n_modes": 0, "eigenvalues": [],
            "variance_explained_pct": [], "loadings": [], "n_complete_epochs": 0,
            "mode_series": [],
        }

    complete = np.ones(n_t, dtype=bool)
    for g in geosncls:
        complete &= ~np.isnan(dense[g])
    n_complete = int(np.count_nonzero(complete))

    if n_complete < 2:
        return {
            "geosncls": geosncls, "means": {g: 0.0 for g in geosncls}, "n_modes": 0,
            "eigenvalues": [], "variance_explained_pct": [], "loadings": [],
            "n_complete_epochs": n_complete, "mode_series": [],
        }

    means: dict[str, float] = {}
    Y = np.zeros((n, n_complete))
    for i, g in enumerate(geosncls):
        demeaned, means[g] = _demean_over(dense[g], complete)
        Y[i] = demeaned[complete]

    cov = (Y @ Y.T) / n_complete
    eigvals, eigvecs = np.linalg.eigh(cov)  # ascending; cov is symmetric
    order = np.argsort(eigvals)[::-1]
    eigvals = eigvals[order]
    eigvecs = eigvecs[:, order]

    k = min(n_modes, n)
    total_var = float(np.sum(np.clip(eigvals, 0.0, None)))
    var_pct = (
        (np.clip(eigvals[:k], 0.0, None) / total_var * 100.0).tolist()
        if total_var > 0 else [0.0] * k
    )

    mode_series: list[np.ndarray] = []
    for mode_idx in range(k):
        v = eigvecs[:, mode_idx]
        scores_complete = v @ Y  # (n_complete,) — exact projection, no fitting needed
        full = np.full(n_t, np.nan)
        full[complete] = scores_complete
        mode_series.append(full)

    return {
        "geosncls": geosncls,
        "means": means,
        "n_modes": k,
        "eigenvalues": eigvals[:k].tolist(),
        "variance_explained_pct": var_pct,
        "loadings": eigvecs[:, :k].T.tolist(),
        "n_complete_epochs": n_complete,
        "mode_series": mode_series,
    }


def pca_common_mode_removed(
    dense: dict[str, np.ndarray], *, n_modes_removed: int = 1
) -> dict[str, np.ndarray]:
    """Each stream's original series with the leading PCA mode(s) subtracted,
    only at epochs where every stream had simultaneous data — elsewhere the
    original value is returned unchanged (no common-mode estimate exists
    there without full overlap; see module docstring).
    """
    geosncls = sorted(dense.keys())
    if len(geosncls) < 2:
        return {g: dense[g].copy() for g in geosncls}

    result = principal_component_analysis(dense, n_modes=max(n_modes_removed, 1))
    residual = {g: dense[g].copy() for g in geosncls}
    if result["n_modes"] == 0:
        return residual

    for k in range(min(n_modes_removed, result["n_modes"])):
        loadings = result["loadings"][k]
        pc = result["mode_series"][k]  # NaN outside the complete epochs
        for i, g in enumerate(geosncls):
            contribution = loadings[i] * pc
            residual[g] = residual[g] - np.where(np.isnan(contribution), 0.0, contribution)

    return residual
