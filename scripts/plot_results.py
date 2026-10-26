#!/usr/bin/env python3
"""Make slide-ready plots from summary.csv and gap_summary.csv.

Usage: .venv/bin/python scripts/plot_results.py [results/w50M_s200M]
Output: <results dir>/plots/*.png
"""
import csv
import math
import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
RES = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results/w50M_s200M"
OUT = RES / "plots"
OUT.mkdir(exist_ok=True)

# Validated categorical slots 1-3 (light mode), fixed order: one colour per prefetcher.
SERIES = [("ipstride", "IP-stride", "#2a78d6"),
          ("bop", "BOP", "#eb6834"),
          ("berti", "Berti", "#1baf7a")]
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
GRID = "#e4e3df"
NEUTRAL = "#c3c2b7"
SURFACE = "#ffffff"

ORDER = ["bwaves", "lbm", "fotonik3d", "mcf", "omnetpp", "xalancbmk", "bfs", "pr", "cc"]
GROUP_OF = {"bwaves": "Regular", "lbm": "Regular", "fotonik3d": "Regular",
            "mcf": "Irregular", "omnetpp": "Irregular", "xalancbmk": "Irregular",
            "bfs": "Graph (GAP)", "pr": "Graph (GAP)", "cc": "Graph (GAP)"}

plt.rcParams.update({
    "font.size": 11,
    "axes.edgecolor": TEXT_2,
    "axes.labelcolor": TEXT,
    "xtick.color": TEXT_2,
    "ytick.color": TEXT_2,
    "text.color": TEXT,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "legend.frameon": False,
})


def read_csv(path):
    if not path.exists():
        return []
    with open(path) as fh:
        return list(csv.DictReader(fh))


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def geomean(xs):
    xs = [x for x in xs if x and x > 0]
    return math.exp(sum(math.log(x) for x in xs) / len(xs)) if xs else None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


summary = read_csv(RES / "summary.csv")
gap = read_csv(RES / "gap_summary.csv")
by = {(r["config"], r["name"]): r for r in summary}
names = [n for n in ORDER if any((c, n) in by for c, _, _ in SERIES)]


def style_axes(ax, ylabel):
    ax.set_ylabel(ylabel)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def group_labels(ax, items, extra_last=False):
    """Light separators and group names under the trace labels."""
    runs = []  # (group, first index, last index)
    for i, n in enumerate(items):
        g = GROUP_OF.get(n, "")
        if runs and runs[-1][0] == g:
            runs[-1][2] = i
        else:
            runs.append([g, i, i])
    for g, lo, hi in runs[1:]:
        ax.axvline(lo - 0.5, color=GRID, linewidth=1, zorder=0)
    if extra_last:
        ax.axvline(len(items) - 0.5, color=TEXT_2, linewidth=1, zorder=0)
    for g, lo, hi in runs:
        ax.text((lo + hi) / 2, -0.12 if not ax.get_xticklabels() or ax.get_xticklabels()[0].get_rotation() == 0 else -0.26, g, ha="center", va="top",
                transform=ax.get_xaxis_transform(), color=TEXT_2, fontsize=10)


def grouped_bars(metric, ylabel, fname, title, agg="mean", pct=True, ref=None,
                 configs=SERIES, label_fmt="{:.0%}"):
    if not names:
        return
    xs = list(range(len(names))) + [len(names)]
    labels = names + ["GEOMEAN" if agg == "geomean" else "MEAN"]
    width = 0.8 / len(configs)
    fig, ax = plt.subplots(figsize=(11, 4.6))
    for k, (cfg, label, color) in enumerate(configs):
        vals = [f(by.get((cfg, n), {}).get(metric)) for n in names]
        summ = geomean(vals) if agg == "geomean" else mean(vals)
        heights = [v if v is not None else 0 for v in vals] + [summ or 0]
        pos = [x + (k - (len(configs) - 1) / 2) * width for x in xs]
        base = ref if ref is not None else 0
        tag = f"{label} ({'geomean' if agg == 'geomean' else 'mean'} {label_fmt.format(summ)})" if summ is not None else label
        ax.bar(pos, [h - base if h else 0 for h in heights], width=width, bottom=base,
               color=color, edgecolor=SURFACE, linewidth=1.5, label=tag, zorder=2)
    if ref is not None:
        ax.axhline(ref, color=TEXT_2, linewidth=1, linestyle="--", zorder=1)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    ax.get_xticklabels()[-1].set_fontweight("bold")
    if pct:
        ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    style_axes(ax, ylabel)
    group_labels(ax, names, extra_last=True)
    ax.set_title(title, loc="left", fontsize=13, color=TEXT)
    ax.legend(ncol=len(configs), loc="upper left", bbox_to_anchor=(0, -0.2), fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / fname, dpi=200)
    plt.close(fig)
    print("wrote", OUT / fname)


# 1. Speedup over no prefetching
grouped_bars("speedup", "Speedup over no prefetching", "1_speedup.png",
             "IPC speedup over no prefetching (L1D prefetcher, single core)",
             agg="geomean", pct=False, ref=1.0, label_fmt="{:.3f}")

# 2-3. Accuracy and coverage
grouped_bars("accuracy", "L1D prefetch accuracy", "2_accuracy.png",
             "L1D prefetch accuracy: useful / (useful + useless)")
grouped_bars("coverage", "L1D miss coverage", "3_coverage.png",
             "L1D coverage: share of would-be misses removed by prefetching")

# 3b. Expensive misses removed: LLC load misses (loads that go to DRAM)
grouped_bars("llc_miss_reduction", "LLC load misses removed", "3b_llc_miss_reduction.png",
             "Load misses that reach DRAM: share removed vs no prefetching")

# 4. Late prefetches
grouped_bars("late_frac", "Late / useful prefetches", "4_late.png",
             "Late prefetches: correct, but arrived after the demand")

# 5. DRAM traffic
grouped_bars("dram_vs_nopf", "DRAM reads vs no prefetching", "5_dram_traffic.png",
             "DRAM read traffic, normalised to no prefetching", agg="geomean", pct=False,
             ref=1.0, label_fmt="{:.2f}x")

# 6. Key experiment: where Berti's remaining misses come from
gap_by = {g["name"]: g for g in gap}
gnames = [n for n in ORDER if n in gap_by]
if gnames:
    covered, uncovered, confident = [], [], []
    for n in gnames:
        g = gap_by[n]
        m = f(g["misses"])
        s = f(g["silent_misses"])
        c = f(g["fb_covered_silent"])
        covered.append(c / m)
        uncovered.append((s - c) / m)
        confident.append((m - s) / m)

    fig, ax = plt.subplots(figsize=(11, 4.6))
    x = list(range(len(gnames)))
    w = 0.6
    ax.bar(x, covered, w, color="#2a78d6", edgecolor=SURFACE, linewidth=2,
           label="Silent miss, global offset would cover", zorder=2)
    ax.bar(x, uncovered, w, bottom=covered, color="#eb6834", edgecolor=SURFACE, linewidth=2,
           label="Silent miss, not covered", zorder=2)
    ax.bar(x, confident, w, bottom=[a + b for a, b in zip(covered, uncovered)], color=NEUTRAL,
           edgecolor=SURFACE, linewidth=2, label="Berti had a confident delta", zorder=2)
    for i, n in enumerate(gnames):
        silent = covered[i] + uncovered[i]
        ax.text(i, silent - 0.015, f"{silent:.0%} silent", ha="center", va="top", fontsize=9,
                color=TEXT)
    ax.set_xticks(x)
    ax.set_xticklabels(gnames)
    ax.set_ylim(0, 1.0)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    style_axes(ax, "Share of Berti's L1D load misses")
    group_labels(ax, gnames)
    ax.set_title("Berti's remaining L1D misses: how many happen while Berti is silent for that IP",
                 loc="left", fontsize=13)
    ax.legend(ncol=3, loc="upper left", bbox_to_anchor=(0, -0.2), fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "6_gap_breakdown.png", dpi=200)
    plt.close(fig)
    print("wrote", OUT / "6_gap_breakdown.png")

    # 7. Fallback quality: coverage of the gap vs accuracy (two panels, one axis each)
    fb_cov = [f(gap_by[n]["fb_cover_of_silent"]) or 0 for n in gnames]
    fb_acc = [f(gap_by[n]["fb_accuracy"]) or 0 for n in gnames]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4), sharey=True)
    for ax, vals, title in ((axes[0], fb_cov, "Coverage: silent misses it would remove"),
                            (axes[1], fb_acc, "Accuracy: useful / issued fallback prefetches")):
        ax.bar(x, vals, 0.6, color="#2a78d6", edgecolor=SURFACE, linewidth=2, zorder=2)
        for i, v in enumerate(vals):
            ax.text(i, v, f"{v:.0%}", ha="center", va="bottom", fontsize=9)
        ax.set_xticks(x)
        ax.set_xticklabels(gnames, rotation=30, ha="right", fontsize=9)
        ax.set_ylim(0, 1.0)
        ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
        ax.yaxis.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.set_title(title, loc="left", fontsize=12)
        group_labels(ax, gnames)
    fig.suptitle("Ungated global-offset fallback on Berti's silent misses (shadow BOP estimate)",
                 x=0.01, ha="left", fontsize=13)
    fig.tight_layout()
    fig.savefig(OUT / "7_fallback_potential.png", dpi=200)
    plt.close(fig)
    print("wrote", OUT / "7_fallback_potential.png")

    # 8. Where the silent misses come from: never-confident IPs vs IPs that lose confidence
    never = []
    flicker = []
    for n in gnames:
        g = gap_by[n]
        s = f(g["silent_misses"]) or 1
        nc = min(f(g["never_conf_misses"]) or 0, s)
        never.append(nc / s)
        flicker.append(1 - nc / s)
    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.bar(x, never, 0.6, color="#2a78d6", edgecolor=SURFACE, linewidth=2,
           label="IP never had a confident delta", zorder=2)
    ax.bar(x, flicker, 0.6, bottom=never, color="#eb6834", edgecolor=SURFACE, linewidth=2,
           label="IP was confident at other times", zorder=2)
    for i, v in enumerate(never):
        ax.text(i, v, f"{v:.0%}", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(gnames)
    ax.set_ylim(0, 1.0)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    style_axes(ax, "Share of silent misses")
    group_labels(ax, gnames)
    ax.set_title("Silent misses by IP type", loc="left", fontsize=13)
    ax.legend(ncol=2, loc="upper left", bbox_to_anchor=(0, -0.2), fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "8_silent_by_ip_type.png", dpi=200)
    plt.close(fig)
    print("wrote", OUT / "8_silent_by_ip_type.png")
