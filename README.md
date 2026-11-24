# LoGO: Local Deltas + Global Offsets for L1D prefetching

## Problem

Data prefetchers guess which cache lines a program needs next and fetch them
early, hiding the 300+ cycles a DRAM access costs. Two families:

- **Local, e.g. Berti:** learns a delta for each load.
  Very accurate, but it stays **silent** when
  it has no confident delta and that load then misses.
- **Global, e.g. BOP:** always guesses, but the
  shared offset is wrong for many loads.

**The question:** can a global offset fill Berti's silent misses without losing accuracy?

## LoGO

Berti runs unchanged. On a silent miss (an L1D miss while Berti has no
confident delta for that load), LoGO prefetches `X + D`, where `D` is one
global offset learned BOP-style from all L1D misses. A 16-entry gate table
decides which loads may use it: every guess is checked for one L1D lifetime,
and after each window of 256 guesses a load turns ON at 25% used and stays
ON while 20% are used. While OFF, its guesses are only checked, never issued.

## Results (12 traces, 50M warm-up + 200M measured)

| Prefetcher | Speedup over no prefetching (geomean) |
|---|---|
| BOP | 1.110x |
| IP-stride | 1.138x |
| Berti | 1.152x |
| **LoGO** | **1.155x** (+0.20% over Berti, worst trace -0.21%) |

Without the gate, the same offset is 1.0% slower than Berti on average and
8.1% slower on PageRank.

## Build and run

The simulator is the Berti authors' ChampSim. To build a prefetcher (for
example `logo`):

```
cd Berti-Artifact/ChampSim/Berti
./build_champsim.sh hashed_perceptron no logo no no no no no lru lru lru srrip drrip lru lru lru 1 no
bin/hashed_perceptron-no-logo-no-no-no-no-no-lru-lru-lru-srrip-drrip-lru-lru-lru-1core-no \
    -warmup_instructions 50000000 -simulation_instructions 200000000 -traces <trace>
```

Replace `logo` with `no`, `ip_stride`, `bop`, `vberti` (Berti) or
`berti_gap` for the other configurations. The trace list is in `traces.txt`;
the 3 DPC4 traces come from the DPC4 infrastructure page.

## Project directory

| Path | What |
|---|---|
| `Berti-Artifact/ChampSim/Berti/` | Simulator: the Berti authors' ChampSim (MICRO'22 artifact, [agusnt/Berti-Artifact](https://github.com/agusnt/Berti-Artifact) @ `5db2457`), trimmed to what I build |
| `…/prefetcher/logo.l1d_pref` | LoGO: Berti + gated global offset |
| `…/prefetcher/berti_gap.l1d_pref` | Measurement-only Berti: silent misses, why Berti is silent, shadow offset learners, an offset oracle and per-load accuracy windows |
| `…/prefetcher/bop.l1d_pref` | BOP, written from Michaud, HPCA'16 |
| `…/prefetcher/ip_stride.l1d_pref` | IP-stride (authors' file) |
| `traces.txt` | The 12 traces used |
| `results/w50M_s200M/` | Raw simulator logs for every configuration above, `summary.csv` (IPC, accuracy, coverage and MPKI per prefetcher and trace) and `speedup.csv` (cycles and speedups for every LoGO version) |
| `presentation/`, `proposal/` | Checkpoint 1 slides and the proposal |

## Notes

The helper scripts I used to build the simulators, run the experiments and
analyse the results are not included, to keep the repo small. In case you want
to see them, please ping me at 23b0980@iitb.ac.in and I will add them.
