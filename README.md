# LoGO: Local Deltas + Global Offsets for L1D prefetching

## Problem

Data prefetchers guess which cache lines a program needs next and fetch them
early, hiding the 300+ cycles a DRAM access costs. Two families:

- **Local, e.g. Berti:** learns a delta for each load.
  Very accurate, but it stays **silent** when
  it has no confident delta and that load then misses.
- **Global, e.g. BOP:** always guesses, but the
  shared offset is wrong for many loads.


**The problem I am trying to solve:** can a global offset fill Berti's silent misses without losing accuracy?

## Checkpoint 1

**Simulation Setup:**  
Single core, 9 traces (regular, irregular, graph algos), Berti vs BOP vs IP-stride at L1D.

**What we are trying to measure:**  
A measurement-only copy of Berti counts *silent misses* (L1D misses while Berti has no confident delta for that load) and runs a watch-only BOP algo to see which of them a global offset would have caught.

**Project Directory:**
| Path | What |
|---|---|
| `Berti-Artifact/ChampSim/Berti/` | Simulator: the Berti authors' ChampSim (MICRO'22 artifact, [agusnt/Berti-Artifact](https://github.com/agusnt/Berti-Artifact) @ `5db2457`), *trimmed to what I build |
| `…/prefetcher/bop.l1d_pref` | BOP, written from Michaud, HPCA'16 |
| `…/prefetcher/ip_stride.l1d_pref` | IP-stride (authors' file) |
| `traces.txt` | The 9 traces used |
| `results/w50M_s200M/` | Raw simulator logs, CSVs, charts |


## Notes

1. There were many other prefetchers that came bundled with the simulator code. I have removed them from the git tracking since they were making the repo more verbose and cluttered.

2. The helper scripts I used to build the simulators, run the experiments and plot the results are not included here, to keep the repo small. I can share them on request.

In case you want to see any of these, please ping (at 23b0980@iitb.ac.in) me, I will add them to the tracking.