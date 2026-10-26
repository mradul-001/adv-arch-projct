# Checkpoint 1 — results summary

All 45 runs finished with 0 failures (26 Oct, 00:29).

## Setup (methodology slide)

- **Simulator:** the Berti authors' ChampSim fork (MICRO'22 artifact), single core, built with GCC 7.5.
- **Run length:** 50M warmup + 200M simulated instructions, the same as the Berti paper.
- **Traces (9):**
  - Regular: `bwaves_s-3699B`, `lbm_s-4268B`, `fotonik3d_s-1176B`
  - Irregular: `mcf_s-665B`, `omnetpp_s-874B`, `xalancbmk_s-700B`
  - Graph (GAP): `bfs-3`, `pr-3`, `cc-5`
- **Prefetchers, all at L1D:**
  - none
  - IP-stride
  - BOP, written from Michaud's HPCA'16 paper: 26 offsets ≤ 60, 256-entry RR table, SCOREMAX 31, ROUNDMAX 100, BADSCORE 1, degree 1
  - Berti, the authors' code
- **Metrics (the Berti authors' definitions):**
  - accuracy = (timely + late) / (timely + late + useless)
  - coverage = (timely + late) / (timely + late + remaining L1D misses)
- **Gap study:** `berti_gap` = Berti plus counters and a shadow BOP. It gives cycle-for-cycle identical results to Berti on all 9 traces.

## Baselines

| | Geomean speedup | Mean accuracy | Mean coverage | DRAM reads vs none |
|---|---|---|---|---|
| IP-stride | 1.143 | 82% | 21% | 1.03× |
| BOP | 1.106 | 48% | 24% | **1.51×** |
| Berti | **1.162** | **93%** | 19% | 1.07× |

- Berti beats both on speedup and accuracy, matching the Berti paper's trend.
- BOP has the highest coverage, but low accuracy on irregular and graph traces: 8–28% on mcf, omnetpp, xalancbmk, pr and cc.
- On `pr`, BOP **slows the program down (0.92×)** and reads **2.7× more from DRAM**.
- omnetpp and xalancbmk gain ~0% from every prefetcher.
- bwaves has almost no L1D misses (MPKI 0.02), so it says little.

## Key experiment: the gap Berti leaves

**Silent miss** = an L1D miss at a moment when Berti has no confident delta for that IP.

| Trace | Silent share of Berti's misses | Silent misses from never-confident IPs | Ungated fallback: covers (of silent) | Ungated fallback: accuracy |
|---|---|---|---|---|
| lbm | 15% | 7% | 23% | 91% |
| fotonik3d | 6% | 45% | 12% | 73% |
| mcf | 93% | 5% | 9% | 11% |
| omnetpp | 99% | 25% | 18% | 21% |
| xalancbmk | 96% | 6% | 30% | 37% |
| bfs | 68% | 0% | 14% | 19% |
| pr | 94% | 0% | 2.5% | 2.7% |
| cc | 96% | 0% | 2.9% | 3.3% |

(bwaves left out: Berti leaves only 904 misses in total.)

## Findings

1. **The gap is real and large where it matters.** On irregular and graph traces, 68–99% of Berti's remaining L1D misses happen while Berti is silent for that IP. On regular traces it's only 6–21%.
2. **The gap isn't cold IPs.** Except on omnetpp, at most 6% of silent misses on irregular and graph traces come from IPs that were never confident. But those IPs are only **rarely** confident (on <10% of their loads; see the analysis below), so they aren't "flickering" IPs. *This refines the proposal's hypothesis*, which assumed cold or low-access IPs.
3. **A single global offset recovers little of that gap.** Ungated, it covers 2.5–30% of silent misses on irregular and graph traces, at **3–37% accuracy**. Where it's accurate (73–91% on regular traces), the gap is small.
4. **The accuracy gate is necessary.** Real BOP costs 1.51× DRAM reads overall and up to 2.7× on graphs. An ungated fallback would add this kind of traffic.

## What this means for LoGO (decision for you)

The proposal's insight #1 holds: the gap exists. Insight #2 holds only weakly: a global offset predicts *part* of the silent misses, but mostly inaccurately. With an accuracy gate, the fallback would mostly stay off on irregular and graph traces and switch on where the gap is small. So the expected gain from LoGO *as proposed* is **small**.

Options for checkpoint 2:
- **A. Keep LoGO but gate per IP, not globally.** xalancbmk (30% coverage at 37% overall accuracy) may contain individual IPs where the offset is accurate. The per-IP logs (`gap_ip/*.csv`) can test this, but would need per-IP fallback accuracy added (~1 hr plus one rerun).
- **B. Switch to the backup idea** (bandwidth-aware degree control for Berti), as the proposal says to if the gap turns out not to be worth it. The gap *is* large; it just isn't recoverable with a global offset.
- **C. Keep the gap, change the fallback.** Keep each IP's last confident delta for a while (hysteresis). *Day-2 analysis weakens this:* on mcf, xalancbmk, pr and cc the silent IPs are confident on <10% of their loads, so a remembered delta is rarely the right one. It fits bfs and lbm better.

## Day-2 analysis (26 Oct, no new runs)

### Sanity checks: are the results real or setup artifacts?

New charts: `3b_llc_miss_reduction.png` (DRAM-bound load misses removed).

| Trace (no prefetch) | L1D load MPKI | L1D store MPKI | L2 load MPKI | LLC load MPKI |
|---|---|---|---|---|
| bwaves | 0.0 | 0.1 | 0.0 | 0.0 |
| lbm | 12.0 | **67.2** | 12.0 | 12.0 |
| fotonik3d | 13.2 | 0.0 | 10.5 | 8.8 |
| mcf | 31.1 | 3.8 | 18.8 | 9.6 |
| omnetpp | 15.8 | 2.5 | 10.7 | 8.3 |
| xalancbmk | **47.3** | 1.5 | 1.6 | **0.2** |
| bfs | 29.8 | 1.4 | 23.0 | 15.9 |
| pr | 172.2 | 0.3 | 120.1 | 48.4 |
| cc | 73.1 | 0.0 | 47.6 | 16.2 |

| LLC load misses removed | IP-stride | BOP | Berti |
|---|---|---|---|
| lbm | 56% | 37% | **83%** |
| fotonik3d | 98% | 81% | 98% |
| mcf | 60% | 50% | **70%** |
| omnetpp | 2% | **19%** | 1% |
| xalancbmk | 16% | 6% | 2% |
| bfs | 59% | 62% | 67% |
| pr | 26% | 7% | 27% |
| cc | 28% | 5% | 28% |

What these show:
- **L1D coverage undersells Berti.** Berti sends most of its prefetches to L2. On lbm, L1D load misses drop only 17%, but L2 load misses drop 80% and LLC load misses 83%. That is where its 15% speedup comes from. On mcf it removes 70% of DRAM-bound load misses. **For the slides, show LLC misses removed (chart 3b) next to L1D coverage.**
- **lbm is store-dominated** (67 store misses vs 12 load misses per 1000 instructions). No L1D prefetcher touches store misses, which caps every prefetcher's gain.
- **xalancbmk's misses are cheap.** 97% of its L1D misses hit in L2 (average miss latency 20 cycles), so prefetching has little to gain, and its "96% silent" misses barely cost anything.
- **omnetpp is the hard irregular case.** Its misses reach DRAM, Berti issues almost nothing, and **BOP removes 19% of DRAM-bound load misses where Berti removes 1%.** This is the one trace where a global offset reaches misses Berti can't (at 21% accuracy, for a 0.8% speedup).
- **bwaves** has essentially no misses. Keep it as a "not memory-intensive" control, or drop it from the slides.

### Gap deep-dive: which IPs cause the silent misses?

New charts: `9_ip_concentration.png`, `10_ip_confidence_rate.png`. Data: `ip_analysis.csv`.

| Trace | IPs with silent misses | IPs causing 80% | Top IP's share | Silent misses from IPs confident on <10% of loads |
|---|---|---|---|---|
| lbm | 58 | 14 | 8% | 46% |
| fotonik3d | 47 | 19 | 16% | 45% |
| mcf | 125 | **4** | 27% | 99% |
| omnetpp | 522 | 53 | 9% | 95% |
| xalancbmk | 868 | **3** | 39% | 98% |
| bfs | 138 | **2** | 63% | 29% |
| pr | 52 | **1** | **100%** | 100% |
| cc | 3 | **1** | **95%** | 100% |

1. **Very concentrated.** On mcf, xalancbmk, bfs, pr and cc, **1–4 load instructions cause 80% of the silent misses.** Any per-IP fix only needs to track a handful of IPs, so a tiny table is enough hardware. omnetpp is the exception (53 IPs).
2. **Rarely confident, not flickering.** On mcf, xalancbmk, pr and cc, 98–100% of silent misses come from IPs that are confident on less than 10% of their loads. They are essentially unpredictable by deltas; Berti only occasionally finds one. bfs is different: 63% come from IPs confident 10–50% of the time.
3. **pr and cc: the gap is an indirect load (likely `A[index[i]]`).** One IP causes ~all silent misses (94–96% miss rate), and the IP right next to it is 100% confident with ~0% misses. The likely reading: Berti handles the streamed index array, but the dependent access to `A[...]` is random. **No delta or offset prefetcher can cover this; it needs an indirect prefetcher** (e.g. IMP, MICRO'15). Treat it as out of scope for LoGO.
4. **xalancbmk: one IP suits a global offset.** For `0x638ed1`, the shadow fallback covers 83% of its silent misses, while it covers far less for the other IPs. A per-IP gate (option A) would find IPs like this, but xalancbmk's misses are cheap (L2 hits), so the speedup would be small.

### Measurement gap to fix if the project continues

The gap study weighs every L1D miss equally, but an L2 hit costs ~20 cycles while a DRAM miss costs hundreds. Next step: record the fill level (L2 / LLC / DRAM) of each silent miss in `berti_gap`, so the gap is measured in **DRAM-bound silent misses**. That's ~30 minutes of code plus one ~1-hour rerun.

## Caveats

- The fallback numbers are an **estimate**. A would-be prefetch counts as useful if its line is missed within roughly one L1D's worth of fills. Timing, MSHR limits and cache pollution are ignored, so treat them as optimistic.
- BOP is our own implementation from the paper. It does well on streaming traces (fotonik3d +57%, lbm +6%), which suggests it's sound.
- Single core, 9 traces, one SimPoint per benchmark.

## Files

- Charts: `results/w50M_s200M/plots/1_speedup.png` … `10_ip_confidence_rate.png` (11 charts, including `3b`)
- Data: `results/w50M_s200M/summary.csv`, `gap_summary.csv`, `ip_analysis.csv`, `gap_ip/<trace>.csv`
- Raw logs: `results/w50M_s200M/<config>/<trace>.txt`
- Regenerate: `.venv/bin/python scripts/parse_results.py && .venv/bin/python scripts/plot_results.py && .venv/bin/python scripts/analyze_ips.py`
