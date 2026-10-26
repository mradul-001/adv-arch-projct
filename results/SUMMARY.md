# Summary

## Simulation Setup

**Simulator:**
ChampSim (Berti authors' version), 1 out-of-order core.
L1D 48 KB -> L2 512 KB -> LLC 2 MB -> DRAM. All prefetchers sit at L1D.

**Run length:**
50M warm-up + 200M measured instructions (same as the Berti paper).

**Traces (9):**

| Group | Traces |
|---|---|
| Regular | bwaves, lbm, fotonik3d |
| Irregular | mcf, omnetpp, xalancbmk |
| Graph | BFS, PageRank, Connected Components |

**Compared:** no prefetching, IP-stride, BOP (I wrote it from the HPCA'16
paper), Berti.

## Measuring Berti's silence

A measurement-only copy of Berti (`berti_gap`). It gives exactly the same
cycles as Berti on all 9 traces, so it does not change what it measures.

1. On every L1D load, we ask Berti: do you have a confident delta for this load?
2. If not and the load misses -> **silent miss**, counted per load. (Q1 from the ppt, how many misses?)
3. A watch-only BOP algo guesses `X + D` for that miss and stores it in a *would-prefetch list* (L1D-sized, 768 lines). It never issues a prefetch.
4. A later miss on a listed line would have been a hit -> **caught**. (Q2, how many misses global offset catch)
5. Caught ÷ guesses = **accuracy**. (Q3, how accurate are our guesses)


## Baselines

**Speedup over no prefetching (geomean):**

| IP-stride | BOP | Berti |
|---|---|---|
| 1.14× | 1.11× | **1.16×** |

- Berti is the strongest baseline.
- Most gains come from regular code (fotonik3d +74%) and BFS (+43%).
- On irregular code (mcf, omnetpp, xalancbmk), no prefetcher helps much.
- BOP slows PageRank down by 8%.

## Q1: How big is the gap?

Share of Berti's L1D misses that happen while Berti is silent:

| lbm | fotonik3d | mcf | omnetpp | xalancbmk | BFS | PageRank | Conn. Comp. |
|---|---|---|---|---|---|---|---|
| 15% | 6% | 93% | 99% | 96% | 68% | 94% | 96% |

**On irregular and graph code, 68–99% of Berti's misses are silent.**
On regular code the gap is small.

## Q2 + Q3: Can a global offset fill it?

| Trace | Silent misses caught (Q2) | Guesses used (Q3) |
|---|---|---|
| lbm | 23% | 91% |
| fotonik3d | 12% | 73% |
| mcf | 9% | 11% |
| omnetpp | 18% | 21% |
| xalancbmk | 30% | 37% |
| BFS | 14% | 19% |
| PageRank | 2.5% | 2.7% |
| Conn. Comp. | 2.9% | 3.3% |

**Mostly no.** On irregular and graph code it catches only 2–30% of the silent
misses and only 3–37% of its guesses are used. On regular code the guesses are
good, but there is little left to catch.

## Who causes the gap?

Load instructions causing 80% of the silent misses:

| lbm | fotonik3d | mcf | omnetpp | xalancbmk | BFS | PageRank | Conn. Comp. |
|---|---|---|---|---|---|---|---|
| 14 of 58 | 19 of 47 | 4 of 125 | 53 of 522 | 3 of 868 | 2 of 138 | 1 of 52 | 1 of 3 |

- **On most programs, 1 - 4 hot loads cause the gap.** omnetpp is the exception (53).
- **Not cold loads:** loads with fewer than 1,000 accesses cause ≤0.2% of silent
  misses on irregular and graph code.

## Key takeaways

- **93%** of Berti's prefetches are right, because it stays silent when unsure.
- **68–99%** of its misses happen while it is silent (irregular and graph code).
- A global offset fixes only **≤30%** of these silent misses.
- But **1 - 4 loads** cause 80% of them.

**We should fix silent misses per load, not globally.**


## Files

- Charts: `results/w50M_s200M/plots/`, slide charts: `presentation/checkpoint-one/figs/`
- Data: `results/w50M_s200M/summary.csv`, `gap_summary.csv`, `ip_analysis.csv`, `gap_ip/<trace>.csv`
- Raw simulator logs: `results/w50M_s200M/<config>/<trace>.txt`
