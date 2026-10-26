#!/usr/bin/env python3
"""Generate prefetcher/berti_gap.l1d_pref from Berti's vberti.l1d_pref.

berti_gap = unmodified Berti + measurement code for the checkpoint-1 gap study:
  - per-IP counts of loads, misses and "silent" misses (misses where Berti had
    no confident delta for that IP at that moment)
  - a shadow BOP learner that never issues prefetches; it estimates how many
    silent misses a global-offset fallback could have covered, and how
    accurate that fallback would be

The measurement code only reads Berti's state, so IPC must match plain Berti.
"""
import pathlib
import sys

PF_DIR = pathlib.Path(__file__).resolve().parent.parent / "Berti-Artifact/ChampSim/Berti/prefetcher"
src = (PF_DIR / "vberti.l1d_pref").read_text()


def patch(text, old, new):
    if text.count(old) != 1:
        sys.exit(f"patch point not found exactly once: {old!r}")
    return text.replace(old, new)


GAP_CODE = r'''
// ===================== checkpoint-1 gap measurement =====================
#include <algorithm>
#include <unordered_map>
#include <vector>

namespace gap {

// ---- shadow BOP learner (same parameters as bop.l1d_pref) ----
const int OFFSETS[] = {1,  2,  3,  4,  5,  6,  8,  9,  10, 12, 15, 16, 18,
                       20, 24, 25, 27, 30, 32, 36, 40, 45, 48, 50, 54, 60};
const int NUM_OFFSETS = sizeof(OFFSETS) / sizeof(OFFSETS[0]);
const int SCORE_MAX = 31;
const int ROUND_MAX = 100;
const int BAD_SCORE = 1;
const int RR_SIZE = 256;

// Lines the fallback "would have prefetched". FIFO sized to the L1D
// (64 sets x 12 ways) as a rough stand-in for how long a prefetched
// line would stay in the cache.
const size_t WOULD_SIZE = L1D_SET * L1D_WAY;

struct IPStat {
    uint64_t loads = 0;
    uint64_t misses = 0;
    uint64_t silent_misses = 0;
    uint64_t confident_loads = 0;
    uint64_t fb_covered = 0;    // silent misses the fallback would have covered
    bool ever_confident = false; // confident at any point, warmup included
};

struct State {
    // learner
    uint64_t rr[RR_SIZE] = {};
    int scores[NUM_OFFSETS] = {};
    int test_idx = 0;
    int round = 0;
    int best_offset = 1;
    bool on = true;
    uint64_t phases = 0, phases_off = 0;
    uint64_t offset_hist[NUM_OFFSETS] = {};

    // fallback estimate
    std::vector<std::pair<uint64_t, uint64_t> > would_ring; // (line, seq)
    size_t would_head = 0;
    uint64_t seq = 0;
    std::unordered_map<uint64_t, uint64_t> would; // line -> seq

    // counters (after warmup only)
    uint64_t loads = 0, misses = 0, silent_misses = 0;
    uint64_t fb_issued = 0, fb_useful = 0, fb_redundant = 0;
    uint64_t fb_covered_silent = 0, fb_covered_other = 0;
    uint64_t fb_skipped_cached = 0, fb_skipped_off = 0;

    std::unordered_map<uint64_t, IPStat> ips;
};

State st[NUM_CPUS];

inline uint32_t rr_index(uint64_t line) { return (line ^ (line >> 8)) & (RR_SIZE - 1); }

void end_phase(State& s)
{
    int best = 0;
    for (int i = 1; i < NUM_OFFSETS; i++)
        if (s.scores[i] > s.scores[best])
            best = i;
    s.best_offset = OFFSETS[best];
    s.on = s.scores[best] > BAD_SCORE;
    s.phases++;
    if (!s.on)
        s.phases_off++;
    s.offset_hist[best]++;
    for (int i = 0; i < NUM_OFFSETS; i++)
        s.scores[i] = 0;
    s.test_idx = 0;
    s.round = 0;
}

// One BOP learning step for trigger line X (an L1D demand miss).
void learn(State& s, uint64_t line)
{
    int idx = s.test_idx;
    uint64_t base = line - OFFSETS[idx];
    if (s.rr[rr_index(base)] == base) {
        if (++s.scores[idx] >= SCORE_MAX) {
            end_phase(s);
            return;
        }
    }
    if (++s.test_idx == NUM_OFFSETS) {
        s.test_idx = 0;
        if (++s.round >= ROUND_MAX)
            end_phase(s);
    }
}

// Shadow BOP never prefetches, so it uses BOP's "prefetch off" RR rule:
// insert every demand fill.
void on_demand_fill(uint32_t cpu, uint64_t line)
{
    st[cpu].rr[rr_index(line)] = line;
}

bool in_l1d(uint32_t cpu, uint64_t line)
{
    uint32_t set = line % L1D_SET;
    for (uint32_t w = 0; w < L1D_WAY; w++)
        if (scache[cpu][set][w].addr == line)
            return true;
    return false;
}

void would_add(State& s, uint64_t line)
{
    if (s.would_ring.empty())
        s.would_ring.assign(WOULD_SIZE, std::make_pair(0ULL, 0ULL));
    std::pair<uint64_t, uint64_t>& slot = s.would_ring[s.would_head];
    if (slot.second != 0) {
        std::unordered_map<uint64_t, uint64_t>::iterator it = s.would.find(slot.first);
        if (it != s.would.end() && it->second == slot.second)
            s.would.erase(it);
    }
    s.seq++;
    slot = std::make_pair(line, s.seq);
    s.would[line] = s.seq;
    s.would_head = (s.would_head + 1) % WOULD_SIZE;
}

// Called for every L1D demand load, before Berti changes any state.
void record(uint32_t cpu, uint64_t raw_ip, uint64_t line, bool hit, bool confident)
{
    State& s = st[cpu];
    IPStat& ip = s.ips[raw_ip];
    if (confident)
        ip.ever_confident = true;

    bool counting = warmup_complete[cpu];
    bool silent_miss = !hit && !confident;

    // 1) Would an earlier fallback prefetch have covered this access?
    std::unordered_map<uint64_t, uint64_t>::iterator it = s.would.find(line);
    if (it != s.would.end()) {
        s.would.erase(it);
        if (counting) {
            if (!hit) {
                s.fb_useful++;
                if (silent_miss) {
                    s.fb_covered_silent++;
                    ip.fb_covered++;
                } else {
                    s.fb_covered_other++;
                }
            } else {
                s.fb_redundant++; // something else already brought it in
            }
        }
    }

    // 2) Count.
    if (counting) {
        s.loads++;
        ip.loads++;
        if (confident)
            ip.confident_loads++;
        if (!hit) {
            s.misses++;
            ip.misses++;
            if (silent_miss) {
                s.silent_misses++;
                ip.silent_misses++;
            }
        }
    }

    // 3) Train the shadow learner on misses (what is left after Berti).
    if (!hit)
        learn(s, line);

    // 4) Fallback fires on silent misses only.
    if (silent_miss) {
        if (!s.on) {
            if (counting)
                s.fb_skipped_off++;
        } else {
            uint64_t target = line + s.best_offset;
            if (in_l1d(cpu, target) || s.would.count(target)) {
                if (counting)
                    s.fb_skipped_cached++;
            } else {
                would_add(s, target);
                if (counting)
                    s.fb_issued++;
            }
        }
    }
}

bool by_misses(const std::pair<uint64_t, IPStat>& a, const std::pair<uint64_t, IPStat>& b)
{
    return a.second.misses > b.second.misses;
}

void print(uint32_t cpu)
{
    State& s = st[cpu];
    uint64_t ips_conf = 0, never_conf_misses = 0, ips_with_miss = 0;
    std::vector<std::pair<uint64_t, IPStat> > rows(s.ips.begin(), s.ips.end());
    for (size_t i = 0; i < rows.size(); i++) {
        if (rows[i].second.ever_confident)
            ips_conf++;
        else
            never_conf_misses += rows[i].second.misses;
        if (rows[i].second.misses)
            ips_with_miss++;
    }
    std::sort(rows.begin(), rows.end(), by_misses);

    std::cout << "GAP loads: " << s.loads << " misses: " << s.misses
              << " silent_misses: " << s.silent_misses
              << " never_confident_ip_misses: " << never_conf_misses << std::endl;
    std::cout << "GAP ips: " << rows.size() << " ips_with_miss: " << ips_with_miss
              << " ips_ever_confident: " << ips_conf << std::endl;
    std::cout << "GAP fallback issued: " << s.fb_issued << " useful: " << s.fb_useful
              << " redundant: " << s.fb_redundant
              << " covered_silent: " << s.fb_covered_silent
              << " covered_other: " << s.fb_covered_other
              << " skipped_cached: " << s.fb_skipped_cached
              << " skipped_off: " << s.fb_skipped_off << std::endl;
    std::cout << "GAP shadow_bop phases: " << s.phases << " off: " << s.phases_off
              << " offsets:";
    for (int i = 0; i < NUM_OFFSETS; i++)
        if (s.offset_hist[i])
            std::cout << " " << OFFSETS[i] << ":" << s.offset_hist[i];
    std::cout << std::endl;

    std::cout << "GAP_IP_BEGIN" << std::endl;
    std::cout << "ip,loads,misses,silent_misses,confident_loads,ever_confident,fb_covered" << std::endl;
    for (size_t i = 0; i < rows.size(); i++) {
        const IPStat& r = rows[i].second;
        if (r.loads == 0)
            continue;
        std::cout << std::hex << "0x" << rows[i].first << std::dec << "," << r.loads << ","
                  << r.misses << "," << r.silent_misses << "," << r.confident_loads << ","
                  << (r.ever_confident ? 1 : 0) << "," << r.fb_covered << std::endl;
    }
    std::cout << "GAP_IP_END" << std::endl;
}

} // namespace gap
// =========================================================================

void CACHE::l1d_prefetcher_initialize() '''

out = src
out = patch(out, "\nvoid CACHE::l1d_prefetcher_initialize() ", GAP_CODE)

# Keep the unhashed IP for per-IP stats.
out = patch(out,
    "    uint64_t line_addr = (addr >> LOG2_BLOCK_SIZE); // Line addr\n    \n    ip = ((ip >> 1) ^ (ip >> 4));",
    "    uint64_t line_addr = (addr >> LOG2_BLOCK_SIZE); // Line addr\n    uint64_t raw_ip = ip; // gap\n    \n    ip = ((ip >> 1) ^ (ip >> 4));")

# Decide "confident" from Berti's table BEFORE Berti updates anything on this
# access, then record. Uses a scratch copy so Berti's own lookup is unchanged.
out = patch(out,
    "    if (!cache_hit)\n    {\n        // This is a miss",
    """    if (type == LOAD)
    {
        stride_t probe[MAX_PF];
        for (int i = 0; i < MAX_PF; i++)
        {
            probe[i].conf = 0;
            probe[i].stride = 0;
            probe[i].rpl = R;
            probe[i].per = 0;
        }
        bool confident = false;
        if (vberti_table_get(ip, cpu, probe))
            for (int i = 0; i < MAX_PF; i++)
                if (probe[i].stride != 0 &&
                    (probe[i].rpl == L1 || probe[i].rpl == L2 || probe[i].rpl == L2R))
                    confident = true;
        gap::record(cpu, raw_ip, line_addr, cache_hit, confident);
    }

    if (!cache_hit)
    {
        // This is a miss""")

# RR feed for the shadow learner: demand fills.
out = patch(out,
    "    shadow_cache_add(cpu, set, way, line_addr, prefetch, latency);",
    "    shadow_cache_add(cpu, set, way, line_addr, prefetch, latency);\n    if (!prefetch) gap::on_demand_fill(cpu, line_addr);")

out = patch(out,
    "void CACHE::l1d_prefetcher_final_stats()\n{\n}",
    "void CACHE::l1d_prefetcher_final_stats()\n{\n    gap::print(cpu);\n}")

(PF_DIR / "berti_gap.l1d_pref").write_text(out)
print("wrote", PF_DIR / "berti_gap.l1d_pref")
