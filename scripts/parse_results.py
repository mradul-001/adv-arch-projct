#!/usr/bin/env python3
"""Parse ChampSim logs into CSV files.

Usage: .venv/bin/python scripts/parse_results.py [results/w50M_s200M]

Writes, inside the results directory:
  summary.csv        one row per (config, trace): IPC, speedup, L1D accuracy,
                     coverage, late fraction, MPKI, DRAM traffic
  gap_summary.csv    one row per trace from the berti_gap runs
  gap_ip/<trace>.csv per-IP rows from the berti_gap runs

Metric definitions follow the Berti authors' scripts (Berti-Artifact/Python):
  accuracy  = (timely + late) / (timely + late + useless)
  coverage  = (timely + late) / (timely + late + L1D load misses + L1D RFO misses)
  late_frac = late / (timely + late)
"""
import csv
import math
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RES = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results/w50M_s200M"
CONFIGS = ["nopf", "ipstride", "bop", "berti", "bertigap"]

TRACE_INFO = {
    "603.bwaves_s-3699B": ("bwaves", "regular"),
    "619.lbm_s-4268B": ("lbm", "regular"),
    "649.fotonik3d_s-1176B": ("fotonik3d", "regular"),
    "605.mcf_s-665B": ("mcf", "irregular"),
    "620.omnetpp_s-874B": ("omnetpp", "irregular"),
    "623.xalancbmk_s-700B": ("xalancbmk", "irregular"),
    "bfs-3": ("bfs", "graph"),
    "pr-3": ("pr", "graph"),
    "cc-5": ("cc", "graph"),
}


def trace_key(fname):
    name = fname.name
    for suffix in (".champsimtrace.xz.txt", ".trace.gz.txt"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return None


def num(pattern, text, cast=int, default=None):
    m = re.search(pattern, text)
    return cast(m.group(1)) if m else default


def parse_log(path):
    t = path.read_text(errors="replace")
    if "CPU 0 cumulative IPC" not in t:
        return None
    d = {}
    d["ipc"] = num(r"CPU 0 cumulative IPC: ([\d.]+)", t, float)
    d["instructions"] = num(r"CPU 0 cumulative IPC: [\d.]+ instructions: (\d+)", t)
    d["l1d_load_miss"] = num(r"L1D LOAD\s+ACCESS:\s+\d+\s+HIT:\s+\d+\s+MISS:\s+(\d+)", t)
    d["l1d_rfo_miss"] = num(r"L1D RFO\s+ACCESS:\s+\d+\s+HIT:\s+\d+\s+MISS:\s+(\d+)", t)
    d["pf_issued"] = num(r"L1D PREFETCH  REQUESTED:\s+\d+\s+ISSUED:\s+(\d+)", t)
    d["pf_useless"] = num(r"L1D PREFETCH  REQUESTED:.*USELESS:\s+(\d+)", t)
    d["pf_timely"] = num(r"L1D TIMELY PREFETCHES:\s+(\d+)", t)
    d["pf_late"] = num(r"L1D TIMELY PREFETCHES:\s+\d+ LATE PREFETCHES: (\d+)", t)
    d["l2c_load_miss"] = num(r"L2C LOAD\s+ACCESS:\s+\d+\s+HIT:\s+\d+\s+MISS:\s+(\d+)", t)
    d["llc_load_miss"] = num(r"LLC LOAD\s+ACCESS:\s+\d+\s+HIT:\s+\d+\s+MISS:\s+(\d+)", t)
    rq = re.search(r"RQ ROW_BUFFER_HIT:\s+(\d+)\s+ROW_BUFFER_MISS:\s+(\d+)", t)
    wq = re.search(r"WQ ROW_BUFFER_HIT:\s+(\d+)\s+ROW_BUFFER_MISS:\s+(\d+)", t)
    d["dram_reads"] = int(rq.group(1)) + int(rq.group(2)) if rq else None
    d["dram_writes"] = int(wq.group(1)) + int(wq.group(2)) if wq else None

    kilo = d["instructions"] / 1000.0
    used = d["pf_timely"] + d["pf_late"]
    d["l1d_mpki"] = d["l1d_load_miss"] / kilo
    d["l1d_rfo_mpki"] = d["l1d_rfo_miss"] / kilo
    d["l2c_load_mpki"] = d["l2c_load_miss"] / kilo
    d["llc_load_mpki"] = d["llc_load_miss"] / kilo
    d["accuracy"] = used / (used + d["pf_useless"]) if used + d["pf_useless"] else None
    misses = d["l1d_load_miss"] + d["l1d_rfo_miss"]
    d["coverage"] = used / (used + misses) if used + misses else None
    d["late_frac"] = d["pf_late"] / used if used else None
    d["dram_rpki"] = d["dram_reads"] / kilo if d["dram_reads"] is not None else None

    if "GAP loads:" in t:
        g = {}
        g["loads"] = num(r"GAP loads: (\d+)", t)
        g["misses"] = num(r"GAP loads: \d+ misses: (\d+)", t)
        g["silent_misses"] = num(r"silent_misses: (\d+)", t)
        g["never_conf_misses"] = num(r"never_confident_ip_misses: (\d+)", t)
        g["ips"] = num(r"GAP ips: (\d+)", t)
        g["ips_with_miss"] = num(r"ips_with_miss: (\d+)", t)
        g["ips_ever_conf"] = num(r"ips_ever_confident: (\d+)", t)
        g["fb_issued"] = num(r"GAP fallback issued: (\d+)", t)
        g["fb_useful"] = num(r"GAP fallback issued: \d+ useful: (\d+)", t)
        g["fb_redundant"] = num(r"redundant: (\d+)", t)
        g["fb_covered_silent"] = num(r"covered_silent: (\d+)", t)
        g["fb_covered_other"] = num(r"covered_other: (\d+)", t)
        g["fb_skipped_cached"] = num(r"skipped_cached: (\d+)", t)
        g["fb_skipped_off"] = num(r"skipped_off: (\d+)", t)
        g["bop_phases"] = num(r"GAP shadow_bop phases: (\d+)", t)
        g["bop_phases_off"] = num(r"GAP shadow_bop phases: \d+ off: (\d+)", t)
        g["bop_offsets"] = num(r"GAP shadow_bop phases: \d+ off: \d+ offsets:(.*)", t, str, "").strip()

        m, sm = g["misses"], g["silent_misses"]
        g["silent_frac"] = sm / m if m else None
        g["never_conf_frac"] = g["never_conf_misses"] / m if m else None
        g["fb_cover_of_silent"] = g["fb_covered_silent"] / sm if sm else None
        g["fb_accuracy"] = g["fb_useful"] / g["fb_issued"] if g["fb_issued"] else None
        d["gap"] = g

        block = re.search(r"GAP_IP_BEGIN\n(.*?)\nGAP_IP_END", t, re.S)
        d["gap_ip"] = block.group(1) if block else ""
    return d


def geomean(xs):
    xs = [x for x in xs if x and x > 0]
    return math.exp(sum(math.log(x) for x in xs) / len(xs)) if xs else None


def main():
    data = {}
    for cfg in CONFIGS:
        for f in sorted((RES / cfg).glob("*.txt")) if (RES / cfg).is_dir() else []:
            key = trace_key(f)
            if key is None:
                continue
            d = parse_log(f)
            if d is None:
                print(f"skip (unfinished): {f}", file=sys.stderr)
                continue
            data[(cfg, key)] = d

    cols = ["config", "trace", "name", "group", "ipc", "speedup", "accuracy", "coverage",
            "late_frac", "l1d_mpki", "miss_reduction", "l1d_rfo_mpki", "l2c_load_mpki",
            "llc_load_mpki", "llc_miss_reduction", "dram_rpki", "dram_vs_nopf",
            "pf_issued", "pf_timely", "pf_late", "pf_useless", "l1d_load_miss"]
    rows = []
    for (cfg, key), d in sorted(data.items(), key=lambda kv: (CONFIGS.index(kv[0][0]), list(TRACE_INFO).index(kv[0][1]) if kv[0][1] in TRACE_INFO else 99)):
        name, group = TRACE_INFO.get(key, (key, "?"))
        base = data.get(("nopf", key))
        r = {"config": cfg, "trace": key, "name": name, "group": group}
        for c in cols[4:]:
            r[c] = d.get(c)
        r["speedup"] = d["ipc"] / base["ipc"] if base else None
        r["miss_reduction"] = 1 - d["l1d_load_miss"] / base["l1d_load_miss"] if base and base["l1d_load_miss"] else None
        r["dram_vs_nopf"] = d["dram_reads"] / base["dram_reads"] if base and base["dram_reads"] else None
        r["llc_miss_reduction"] = 1 - d["llc_load_miss"] / base["llc_load_miss"] if base and base["llc_load_miss"] else None
        rows.append(r)

    with open(RES / "summary.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    # Gap study
    gcols = ["trace", "name", "group", "misses", "silent_misses", "silent_frac",
             "never_conf_misses", "never_conf_frac", "ips", "ips_with_miss", "ips_ever_conf",
             "fb_issued", "fb_useful", "fb_accuracy", "fb_covered_silent", "fb_cover_of_silent",
             "fb_covered_other", "fb_redundant", "fb_skipped_cached", "fb_skipped_off",
             "bop_phases", "bop_phases_off", "bop_offsets"]
    grows = []
    (RES / "gap_ip").mkdir(exist_ok=True)
    for key in TRACE_INFO:
        d = data.get(("bertigap", key))
        if not d or "gap" not in d:
            continue
        name, group = TRACE_INFO[key]
        r = {"trace": key, "name": name, "group": group}
        r.update({c: d["gap"].get(c) for c in gcols[3:]})
        grows.append(r)
        (RES / "gap_ip" / f"{name}.csv").write_text(d["gap_ip"] + "\n")
    if grows:
        with open(RES / "gap_summary.csv", "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=gcols)
            w.writeheader()
            w.writerows(grows)

    # Console summary
    print(f"parsed {len(data)} runs from {RES}")
    for cfg in CONFIGS[1:4]:
        sp = [r["speedup"] for r in rows if r["config"] == cfg and r["speedup"]]
        acc = [r["accuracy"] for r in rows if r["config"] == cfg and r["accuracy"] is not None]
        cov = [r["coverage"] for r in rows if r["config"] == cfg and r["coverage"] is not None]
        if sp:
            print(f"  {cfg:9s} n={len(sp)} geomean speedup {geomean(sp):.3f}  "
                  f"mean accuracy {sum(acc)/len(acc):.1%}  mean coverage {sum(cov)/len(cov):.1%}")
    for g in grows:
        print(f"  gap {g['name']:10s} silent {g['silent_frac']:.1%}  never-conf {g['never_conf_frac']:.1%}  "
              f"fallback covers {g['fb_cover_of_silent']:.1%} of silent at {g['fb_accuracy']:.1%} accuracy")


if __name__ == "__main__":
    main()
