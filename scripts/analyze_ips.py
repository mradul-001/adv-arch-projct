#!/usr/bin/env python3
"""Per-IP analysis of Berti's silent misses (from berti_gap logs).

Usage: .venv/bin/python scripts/analyze_ips.py [results/w50M_s200M]

Answers two questions per trace:
  1. Concentration: how few IPs cause most of the silent misses?
  2. Flickering: for the IPs behind silent misses, how often were they
     confident? (confident loads / loads, weighted by silent misses)

Writes <results>/ip_analysis.csv and two charts in <results>/plots/.
"""
import csv
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

# bwaves is left out: Berti leaves it only ~900 misses.
ORDER = ["lbm", "fotonik3d", "mcf", "omnetpp", "xalancbmk", "bfs", "pr", "cc"]
GROUP_OF = {"lbm": "Regular", "fotonik3d": "Regular", "mcf": "Irregular",
            "omnetpp": "Irregular", "xalancbmk": "Irregular", "bfs": "Graph (GAP)",
            "pr": "Graph (GAP)", "cc": "Graph (GAP)"}

# Confidence-rate buckets for IPs behind silent misses (share of the IP's loads
# where Berti had a confident delta).
BUCKETS = [("Never confident (0%)", lambda r: r == 0.0),
           ("Rarely (<10%)", lambda r: 0 < r < 0.10),
           ("Sometimes (10-50%)", lambda r: 0.10 <= r < 0.50),
           ("Mostly (>=50%)", lambda r: r >= 0.50)]
# Sequential blue ramp, light -> dark = more often confident.
BUCKET_COLORS = ["#c9dcf4", "#86b3ea", "#3f88dc", "#1c5aa6"]

TEXT, TEXT_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#ffffff"
plt.rcParams.update({
    "font.size": 11, "axes.edgecolor": TEXT_2, "axes.labelcolor": TEXT,
    "xtick.color": TEXT_2, "ytick.color": TEXT_2, "text.color": TEXT,
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "legend.frameon": False,
})


def load(name):
    path = RES / "gap_ip" / f"{name}.csv"
    if not path.exists():
        return []
    with open(path) as fh:
        rows = []
        for r in csv.DictReader(fh):
            rows.append({k: (int(v) if k != "ip" else v) for k, v in r.items()})
        return rows


def ips_for_share(sorted_counts, total, share):
    acc = 0
    for i, c in enumerate(sorted_counts, 1):
        acc += c
        if acc >= share * total:
            return i
    return len(sorted_counts)


results = []
for name in ORDER:
    rows = load(name)
    if not rows:
        continue
    silent = sorted((r["silent_misses"] for r in rows), reverse=True)
    total_silent = sum(silent)
    if total_silent == 0:
        continue
    ips_with_silent = sum(1 for c in silent if c > 0)

    res = {"name": name, "group": GROUP_OF[name], "ips_with_silent": ips_with_silent,
           "silent_misses": total_silent}
    for share in (0.5, 0.8, 0.9):
        res[f"ips_for_{int(share * 100)}pct"] = ips_for_share(silent, total_silent, share)
    res["top1_share"] = silent[0] / total_silent
    res["top10_share"] = sum(silent[:10]) / total_silent

    # Flickering: weight each IP's confidence rate by its silent misses.
    for label, test in BUCKETS:
        res[label] = sum(r["silent_misses"] for r in rows
                         if r["silent_misses"] and test(r["confident_loads"] / r["loads"])) / total_silent
    # Fallback coverage concentration: share of fallback-covered misses from top-10 silent IPs.
    top10 = sorted(rows, key=lambda r: r["silent_misses"], reverse=True)[:10]
    fb_total = sum(r["fb_covered"] for r in rows)
    res["fb_covered_top10_share"] = sum(r["fb_covered"] for r in top10) / fb_total if fb_total else 0.0
    results.append(res)

cols = list(results[0].keys())
with open(RES / "ip_analysis.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols)
    w.writeheader()
    w.writerows(results)

names = [r["name"] for r in results]
x = list(range(len(names)))


def group_labels(ax):
    runs = []
    for i, n in enumerate(names):
        g = GROUP_OF[n]
        if runs and runs[-1][0] == g:
            runs[-1][2] = i
        else:
            runs.append([g, i, i])
    for g, lo, hi in runs[1:]:
        ax.axvline(lo - 0.5, color=GRID, linewidth=1, zorder=0)
    for g, lo, hi in runs:
        ax.text((lo + hi) / 2, -0.12, g, ha="center", va="top",
                transform=ax.get_xaxis_transform(), color=TEXT_2, fontsize=10)


# Chart 9: concentration - IPs needed for 80% of silent misses (single series).
fig, ax = plt.subplots(figsize=(11, 4.4))
vals = [r["ips_for_80pct"] for r in results]
ax.bar(x, vals, 0.6, color="#2a78d6", edgecolor=SURFACE, linewidth=2, zorder=2)
for i, r in enumerate(results):
    ax.text(i, vals[i], f'{vals[i]} of {r["ips_with_silent"]}', ha="center", va="bottom", fontsize=9)
ax.set_xticks(x)
ax.set_xticklabels(names)
ax.set_ylabel("IPs causing 80% of silent misses")
ax.yaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
ax.set_ylim(0, max(vals) * 1.18)
group_labels(ax)
ax.set_title("Silent misses are concentrated in few load IPs (labels: IPs needed / IPs with any silent miss)",
             loc="left", fontsize=12)
fig.tight_layout()
fig.savefig(OUT / "9_ip_concentration.png", dpi=200)
plt.close(fig)

# Chart 10: flickering - silent misses by how often their IP is confident.
fig, ax = plt.subplots(figsize=(11, 4.6))
bottom = [0.0] * len(results)
for (label, _), color in zip(BUCKETS, BUCKET_COLORS):
    vals = [r[label] for r in results]
    ax.bar(x, vals, 0.6, bottom=bottom, color=color, edgecolor=SURFACE, linewidth=2,
           label=label, zorder=2)
    bottom = [b + v for b, v in zip(bottom, vals)]
ax.set_xticks(x)
ax.set_xticklabels(names)
ax.set_ylim(0, 1.0)
ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
ax.set_ylabel("Share of silent misses")
ax.yaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
group_labels(ax)
ax.set_title("Silent misses by how often their IP has a confident Berti delta", loc="left", fontsize=13)
ax.legend(ncol=4, loc="upper left", bbox_to_anchor=(0, -0.2), fontsize=10,
          title="IP confident on this share of its loads:", title_fontsize=10)
fig.tight_layout()
fig.savefig(OUT / "10_ip_confidence_rate.png", dpi=200)
plt.close(fig)

# Console table
print(f'{"trace":10s} {"IPs":>5s} {"50%":>4s} {"80%":>4s} {"90%":>4s} {"top1":>5s} {"top10":>6s} | '
      + " ".join(f"{b[0].split(' (')[0][:9]:>9s}" for b in BUCKETS) + " | fb-top10")
for r in results:
    print(f'{r["name"]:10s} {r["ips_with_silent"]:5d} {r["ips_for_50pct"]:4d} {r["ips_for_80pct"]:4d} '
          f'{r["ips_for_90pct"]:4d} {r["top1_share"]:5.0%} {r["top10_share"]:6.0%} | '
          + " ".join(f"{r[b[0]]:9.0%}" for b in BUCKETS) + f' | {r["fb_covered_top10_share"]:6.0%}')
print("wrote", RES / "ip_analysis.csv", OUT / "9_ip_concentration.png", OUT / "10_ip_confidence_rate.png")
