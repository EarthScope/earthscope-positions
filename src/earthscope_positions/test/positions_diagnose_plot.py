"""
positions_diagnose_plot — visualize results from a positions_diagnose JSONL file.

Reads one or more JSONL files produced by positions_diagnose and generates:

  overview.png      Error rate, throughput, p50/p95 latency vs. worker count
                    for both endpoints on shared axes
  breakdown.png     Stacked bar chart of status-code mix by worker count,
                    one panel per endpoint
  timeline.png      Time series of error rate and throughput over the run,
                    with worker-count phase transitions shaded

Also prints a text summary of the most common error response bodies so you can
distinguish "server busy" from "actual server error."

Usage:
    positions_diagnose_plot data/positions_diagnose/diagnose_20260630T220000Z.jsonl
    positions_diagnose_plot diagnose_*.jsonl --output-dir plots/
    positions_diagnose_plot diagnose_*.jsonl --show          # display interactively
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import pathlib
import sys

import orjson

try:
    import pandas as pd
except ImportError:
    sys.exit("pandas is required:  pip install pandas")

try:
    import matplotlib
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.ticker import MaxNLocator
except ImportError:
    sys.exit("matplotlib is required:  pip install matplotlib")

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

_STATUS_COLOR = {
    200: "#27ae60",   # green  — data returned
    404: "#95a5a6",   # gray   — no data for this date/station
    500: "#e74c3c",   # red    — internal server error
    503: "#e67e22",   # orange — service unavailable
    429: "#f39c12",   # amber  — rate limited
    0:   "#8e44ad",   # purple — network exception / timeout
}
_STATUS_LABEL = {
    200: "200 ok",
    404: "404 no-data",
    500: "500 server error",
    503: "503 unavailable",
    429: "429 rate limited",
    0:   "exception",
}
_EP_COLOR = {"auth": "#2980b9", "open": "#e67e22"}
_EP_NAME = {
    "auth": "api.earthscope.org (auth)",
    "open": "gnss-observations-api.prod (open)",
}


def _load(paths: list[pathlib.Path]) -> tuple[dict, pd.DataFrame]:
    """Load one or more JSONL files, return (meta, dataframe)."""
    meta: dict = {}
    records: list[dict] = []

    for path in paths:
        with path.open("rb") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = orjson.loads(line)
                except Exception:
                    continue
                if rec.get("_meta"):
                    meta = rec  # last meta wins (newest file)
                else:
                    records.append(rec)

    if not records:
        sys.exit("No request records found in the provided file(s).")

    df = pd.DataFrame(records)
    df["ts"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
    df["is_error"] = df["result"].str.startswith("error") | (df["result"] == "exception")
    df["worker_count"] = df["worker_count"].astype(int)
    df["latency_ms"] = pd.to_numeric(df["latency_ms"], errors="coerce")
    df["row_count"] = pd.to_numeric(df["row_count"], errors="coerce")

    return meta, df


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _aggregate_latency_by_result(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mean latency per (endpoint, worker_count, result_category).

    Categories:
      ok          200 with row_count > 0
      no-data     404 or 200 with row_count == 0
      error-NNN   any other status (grouped by code)
    """
    df = df.copy()

    def _cat(row) -> str:
        if row["status"] == 200 and pd.notna(row["row_count"]) and row["row_count"] > 0:
            return "ok (has data)"
        if row["status"] in (200, 404):
            return "no-data"
        if row["status"] == 0:
            return "exception"
        return f"error-{int(row['status'])}"

    df["result_cat"] = df.apply(_cat, axis=1)

    rows = []
    for (ep, w, cat), grp in df.groupby(["endpoint", "worker_count", "result_cat"]):
        lats = grp["latency_ms"].dropna()
        rows.append({
            "endpoint": ep,
            "worker_count": int(w),
            "result_cat": cat,
            "mean_ms": lats.mean() if len(lats) > 0 else float("nan"),
            "count": len(grp),
        })

    return pd.DataFrame(rows).sort_values(["endpoint", "worker_count", "result_cat"])


_RESULT_CAT_STYLE: dict[str, dict] = {
    "ok (has data)": {"color": "#27ae60", "marker": "o", "ls": "-"},
    "no-data":       {"color": "#95a5a6", "marker": "s", "ls": "--"},
    "exception":     {"color": "#8e44ad", "marker": "x", "ls": ":"},
}


def _result_cat_style(cat: str) -> dict:
    if cat in _RESULT_CAT_STYLE:
        return _RESULT_CAT_STYLE[cat]
    # error-NNN gets a red shade
    return {"color": "#e74c3c", "marker": "^", "ls": "-."}


def _aggregate(df: pd.DataFrame, phase_duration_s: float | None) -> pd.DataFrame:
    """
    Aggregate per (endpoint, worker_count):
      error_rate, rps, p50_ms, p95_ms, total, status counts
    """
    rows = []
    for (ep, w), grp in df.groupby(["endpoint", "worker_count"]):
        total = len(grp)
        errors = grp["is_error"].sum()
        lats = grp["latency_ms"].dropna()

        # Throughput: use known phase duration if available; else estimate from timestamps
        if phase_duration_s and phase_duration_s > 0:
            rps = total / phase_duration_s
        else:
            elapsed = (grp["ts"].max() - grp["ts"].min()).total_seconds()
            rps = total / elapsed if elapsed > 2 else float("nan")

        rows.append({
            "endpoint": ep,
            "worker_count": int(w),
            "total": total,
            "errors": int(errors),
            "error_rate": errors / total if total > 0 else 0.0,
            "rps": rps,
            "p50_ms": lats.quantile(0.50) if len(lats) > 0 else float("nan"),
            "p95_ms": lats.quantile(0.95) if len(lats) > 0 else float("nan"),
        })

    agg = pd.DataFrame(rows).sort_values(["endpoint", "worker_count"])
    return agg


# ---------------------------------------------------------------------------
# Figure 1 — Overview: error rate, throughput, latency vs. worker count
# ---------------------------------------------------------------------------


def _plot_overview(
    agg: pd.DataFrame,
    df: pd.DataFrame,
    output_path: pathlib.Path | None,
    title: str,
    show: bool,
) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle(title, fontsize=13, y=0.99)

    # ── Top row: error rate and throughput (both endpoints on shared axes) ──

    for ax, col, ylabel, subtitle, transform in [
        (axes[0, 0], "error_rate", "Error rate (%)", "Error Rate vs. Worker Count",
         lambda v: v * 100),
        (axes[0, 1], "rps", "Requests / second", "Throughput vs. Worker Count",
         lambda v: v),
    ]:
        for ep in ["auth", "open"]:
            sub = agg[agg["endpoint"] == ep].sort_values("worker_count")
            if sub.empty:
                continue
            marker = "o" if ep == "auth" else "s"
            ls = "-" if ep == "auth" else "--"
            ax.plot(sub["worker_count"], transform(sub[col]),
                    color=_EP_COLOR[ep], marker=marker, linestyle=ls,
                    linewidth=1.8, markersize=5, label=_EP_NAME[ep])

        ax.set_title(subtitle, fontsize=10)
        ax.set_xlabel("Worker count")
        ax.set_ylabel(ylabel)
        ax.set_ylim(bottom=0)
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8)

    # Annotate the constant auth error rate.
    # Compute mean error rate for auth; if it looks flat (low CV), annotate.
    auth_agg = agg[agg["endpoint"] == "auth"]
    if not auth_agg.empty:
        auth_err_pcts = auth_agg["error_rate"] * 100
        mean_pct = auth_err_pcts.mean()
        cv = auth_err_pcts.std() / mean_pct if mean_pct > 0 else 1.0
        if cv < 0.4 and mean_pct > 1:        # flat and non-trivial
            ax0 = axes[0, 0]
            ax0.axhline(mean_pct, color=_EP_COLOR["auth"],
                        linewidth=1.2, linestyle=":", alpha=0.75)
            # Place label near the right edge
            x_label = auth_agg["worker_count"].max() * 0.6
            ax0.text(x_label, mean_pct + 0.5,
                     f"auth mean {mean_pct:.0f}% — flat → CloudFront?",
                     color=_EP_COLOR["auth"], fontsize=7.5, va="bottom", alpha=0.9)

    # ── Bottom row: mean latency by result category, one panel per endpoint ──

    lat_by_result = _aggregate_latency_by_result(df)

    for ax, ep in [(axes[1, 0], "auth"), (axes[1, 1], "open")]:
        sub = lat_by_result[lat_by_result["endpoint"] == ep]
        if sub.empty:
            ax.set_visible(False)
            continue

        cats = sorted(sub["result_cat"].unique())
        for cat in cats:
            cat_sub = sub[sub["result_cat"] == cat].sort_values("worker_count")
            sty = _result_cat_style(cat)
            ax.plot(cat_sub["worker_count"], cat_sub["mean_ms"],
                    color=sty["color"], marker=sty["marker"], linestyle=sty["ls"],
                    linewidth=1.6, markersize=5, label=cat)

        ep_short = _EP_NAME.get(ep, ep)
        ax.set_title(f"Mean Latency by Result — {ep_short}", fontsize=9)
        ax.set_xlabel("Worker count")
        ax.set_ylabel("Mean latency (ms)")
        ax.set_ylim(bottom=0)
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8, title="result type", title_fontsize=7)

    plt.tight_layout()
    _save_or_show(fig, output_path, show)


# ---------------------------------------------------------------------------
# Figure 2 — Status-code breakdown: stacked bars per endpoint
# ---------------------------------------------------------------------------


def _bar_category(row) -> str:
    """Fine-grained category for stacked bar breakdown, splitting 200 by data presence."""
    if row["status"] == 200:
        if pd.notna(row["row_count"]) and row["row_count"] > 0:
            return "200 ok — has data"
        return "200 ok — no data"
    if row["status"] == 404:
        return "404 no-data"
    if row["status"] == 0:
        return "exception"
    return f"{int(row['status'])} error"


# Ordered bottom-to-top for stacking; unlisted codes appended alphabetically.
_BAR_CAT_ORDER = [
    "200 ok — has data",
    "200 ok — no data",
    "404 no-data",
    "429 error",
    "503 error",
    "500 error",
    "exception",
]
_BAR_CAT_COLOR = {
    "200 ok — has data": "#27ae60",   # green
    "200 ok — no data": "#a9cce3",    # light blue
    "404 no-data":       "#95a5a6",   # gray
    "500 error":         "#e74c3c",   # red
    "503 error":         "#e67e22",   # orange
    "429 error":         "#f39c12",   # amber
    "exception":         "#8e44ad",   # purple
}


def _plot_breakdown(
    df: pd.DataFrame,
    output_path: pathlib.Path | None,
    title: str,
    show: bool,
) -> None:
    df = df.copy()
    df["bar_cat"] = df.apply(_bar_category, axis=1)

    endpoints = sorted(df["endpoint"].unique())
    n_ep = len(endpoints)
    fig, axes = plt.subplots(1, n_ep, figsize=(8 * n_ep, 6), squeeze=False)
    fig.suptitle(title, fontsize=13)

    for ax, ep in zip(axes[0], endpoints):
        sub = df[df["endpoint"] == ep]
        workers = sorted(sub["worker_count"].unique())

        # Build ordered category list: known order first, then any extras
        present = set(sub["bar_cat"].unique())
        cats = [c for c in _BAR_CAT_ORDER if c in present]
        cats += sorted(present - set(cats))

        bottoms = [0.0] * len(workers)
        for cat in cats:
            pcts = []
            for w in workers:
                grp = sub[sub["worker_count"] == w]
                total = len(grp)
                n = int((grp["bar_cat"] == cat).sum())
                pcts.append(100.0 * n / total if total > 0 else 0.0)

            color = _BAR_CAT_COLOR.get(cat, "#3498db")
            ax.bar(workers, pcts, bottom=bottoms, color=color,
                   label=cat, width=0.65, alpha=0.87)
            bottoms = [b + p for b, p in zip(bottoms, pcts)]

        ax.set_title(_EP_NAME.get(ep, ep), fontsize=10)
        ax.set_xlabel("Worker count")
        ax.set_ylabel("% of requests")
        ax.set_ylim(0, 100)
        ax.set_xticks(workers)
        ax.grid(True, axis="y", alpha=0.25)
        ax.legend(loc="upper left", fontsize=8, framealpha=0.8)

    plt.tight_layout()
    _save_or_show(fig, output_path, show)


# ---------------------------------------------------------------------------
# Figure 3 — Timeline: error rate and throughput over the full run
# ---------------------------------------------------------------------------


def _plot_timeline(
    df: pd.DataFrame,
    output_path: pathlib.Path | None,
    title: str,
    show: bool,
) -> None:
    if df["ts"].isna().all():
        return

    df_s = df.sort_values("ts").copy()

    # Bin into 2-minute windows
    df_s["window"] = df_s["ts"].dt.floor("2min")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    fig.suptitle(title, fontsize=13)

    for ep in ["auth", "open"]:
        sub = df_s[df_s["endpoint"] == ep]
        if sub.empty:
            continue

        binned = (
            sub.groupby("window")
            .agg(
                error_rate=("is_error", "mean"),
                rps=("is_error", "count"),      # count → divide by window size
                worker_count=("worker_count", "last"),
            )
            .reset_index()
        )
        binned["rps"] = binned["rps"] / 120.0  # 2-min window = 120 s

        color = _EP_COLOR[ep]
        ls = "-" if ep == "auth" else "--"
        ax1.plot(binned["window"], binned["error_rate"] * 100,
                 color=color, linestyle=ls, linewidth=1.5, label=_EP_NAME[ep])
        ax2.plot(binned["window"], binned["rps"],
                 color=color, linestyle=ls, linewidth=1.5, label=_EP_NAME[ep])

    # Shade phase transitions using worker-count steps from the combined df
    phase_changes = (
        df_s.groupby(["worker_count", "endpoint"])["ts"]
        .min()
        .reset_index()
        .groupby("worker_count")["ts"]
        .min()
        .reset_index()
        .sort_values("ts")
    )
    if len(phase_changes) > 1:
        for i, row in phase_changes.iterrows():
            for ax in (ax1, ax2):
                ax.axvline(row["ts"], color="gray", linewidth=0.6,
                           linestyle=":", alpha=0.6)

    # Worker count on right axis of top panel
    wc_series = df_s.groupby("window")["worker_count"].last().reset_index()
    ax1r = ax1.twinx()
    ax1r.step(wc_series["window"], wc_series["worker_count"],
              color="gray", alpha=0.35, linewidth=1, where="post")
    ax1r.set_ylabel("Worker count", color="gray", fontsize=8)
    ax1r.tick_params(axis="y", labelcolor="gray", labelsize=7)
    ax1r.set_ylim(bottom=0)

    ax1.set_title("Error rate over time (dotted lines = phase transitions)", fontsize=10)
    ax1.set_ylabel("Error rate (%)")
    ax1.set_ylim(bottom=0)
    ax1.legend(fontsize=8, loc="upper left")
    ax1.grid(True, alpha=0.22)

    ax2.set_title("Throughput over time", fontsize=10)
    ax2.set_ylabel("Requests / second (2-min bins)")
    ax2.set_ylim(bottom=0)
    ax2.legend(fontsize=8, loc="upper left")
    ax2.grid(True, alpha=0.22)
    ax2.set_xlabel("Time (UTC)")

    fig.autofmt_xdate()
    plt.tight_layout()
    _save_or_show(fig, output_path, show)


# ---------------------------------------------------------------------------
# Text summary — error body analysis
# ---------------------------------------------------------------------------


def _print_error_summary(df: pd.DataFrame) -> None:
    errors = df[df["is_error"] & df["body"].notna() & (df["body"] != "")]

    if errors.empty:
        print("\nNo error responses with bodies found.")
        return

    print(f"\n{'='*64}")
    print("Error body analysis")
    print(f"{'='*64}")
    print(f"Total error records: {len(errors)}")

    for ep in ["auth", "open"]:
        sub = errors[errors["endpoint"] == ep]
        if sub.empty:
            continue

        print(f"\n  {_EP_NAME.get(ep, ep)}  ({len(sub)} errors)")

        # Count by stringified body
        counts = collections.Counter(
            str(b)[:200] for b in sub["body"] if b is not None
        )
        for body_str, n in counts.most_common(8):
            print(f"    [{n:>4}×]  {body_str[:120]}")

        # Count by status
        status_dist = sub["status"].value_counts()
        print(f"  Status breakdown: " +
              "  ".join(f"{int(c)}:{n}" for c, n in status_dist.items()))

    print(f"{'='*64}\n")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _save_or_show(fig: "plt.Figure", path: pathlib.Path | None, show: bool) -> None:
    if show:
        plt.show()
    elif path:
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=150, bbox_inches="tight")
        print(f"  Saved → {path}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _build_parser(prog=None) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog=prog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Plot results from an 'es-pos test fetch' JSONL file.

Generates three figures:
  overview.png    Error rate, throughput, p50/p95 latency vs. worker count
  breakdown.png   Status-code mix by worker count (stacked bars)
  timeline.png    Error rate and throughput as a time series

Also prints a text summary of the most common error response bodies.

Examples:
  es-pos test plot data/positions_diagnose/diagnose_20260630T220000Z.jsonl
  es-pos test plot diagnose_*.jsonl --output-dir plots/
  es-pos test plot diagnose_*.jsonl --show
""",
    )
    ap.add_argument("files", nargs="+", metavar="JSONL",
                    help="test-fetch output file(s).")
    ap.add_argument("--output-dir", metavar="DIR",
                    help="Directory for PNG output (default: same dir as first input file).")
    ap.add_argument("--show", action="store_true",
                    help="Display plots interactively instead of saving.")
    ap.add_argument("--no-timeline", action="store_true",
                    help="Skip the timeline plot (faster for large files).")
    return ap


def _dispatch(args: argparse.Namespace) -> None:
    paths = [pathlib.Path(f) for f in args.files]
    for p in paths:
        if not p.exists():
            sys.exit(f"File not found: {p}")

    print(f"Loading {len(paths)} file(s)…")
    meta, df = _load(paths)

    n_req = len(df)
    n_ep = df["endpoint"].nunique()
    worker_range = f"{df['worker_count'].min()}–{df['worker_count'].max()}"
    run_ts = meta.get("run_ts", "unknown")
    phase_s = meta.get("phase_duration_s")

    print(f"  {n_req:,} requests  |  {n_ep} endpoints  |  workers {worker_range}  |  run: {run_ts}")

    agg = _aggregate(df, phase_s)

    title = (
        f"EarthScope Positions API Diagnostic  —  "
        f"{n_req:,} requests  workers {worker_range}  {run_ts}"
    )

    if args.show:
        out_dir = None
    elif args.output_dir:
        out_dir = pathlib.Path(args.output_dir)
    else:
        out_dir = paths[0].parent

    def out(name: str) -> pathlib.Path | None:
        return (out_dir / name) if out_dir else None

    print("\nGenerating plots…")

    _plot_overview(agg, df, out("overview.png"), title, args.show)
    _plot_breakdown(df, out("breakdown.png"), title, args.show)

    if not args.no_timeline:
        _plot_timeline(df, out("timeline.png"), title, args.show)

    _print_error_summary(df)

    if out_dir:
        print(f"\nAll plots saved to {out_dir}/")


def main() -> None:
    ap = _build_parser()
    args = ap.parse_args()
    _dispatch(args)


if __name__ == "__main__":
    main()
