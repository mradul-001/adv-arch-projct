#!/bin/bash
# Run every (config, trace) pair in parallel.
#
# Usage: scripts/run_batch.sh <warmup> <sim> <jobs> <config> [config ...]
#   e.g. scripts/run_batch.sh 25000000 100000000 6 nopf ipstride berti
#
# Binaries:  bin/champsim_<config>
# Traces:    names listed in traces.txt, files in traces/
# Output:    results/w<warmup>_s<sim>/<config>/<trace>.txt
# A run whose output already contains the final IPC line is skipped,
# so the script is safe to re-run after a crash.

set -u
cd "$(dirname "$0")/.."

if [ $# -lt 4 ]; then
    echo "usage: $0 <warmup> <sim> <jobs> <config> [config ...]" >&2
    exit 1
fi

WARMUP=$1; SIM=$2; JOBS=$3; shift 3
OUT=results/w$((WARMUP / 1000000))M_s$((SIM / 1000000))M

jobs_file=$(mktemp)
for cfg in "$@"; do
    bin=bin/champsim_$cfg
    [ -x "$bin" ] || { echo "missing binary: $bin" >&2; exit 1; }
    mkdir -p "$OUT/$cfg"
    while read -r trace; do
        [ -z "$trace" ] && continue
        [ -f "traces/$trace" ] || { echo "missing trace: traces/$trace" >&2; exit 1; }
        log="$OUT/$cfg/$trace.txt"
        if grep -q "CPU 0 cumulative IPC" "$log" 2>/dev/null; then
            continue
        fi
        echo "$bin -warmup_instructions $WARMUP -simulation_instructions $SIM -traces traces/$trace > $log 2>&1; echo \"done $cfg $trace exit=\$?\""
    done < traces.txt
done > "$jobs_file"

n=$(wc -l < "$jobs_file")
echo "$(date '+%F %T') starting $n runs, $JOBS at a time -> $OUT"
xargs -P "$JOBS" -I{} bash -c '{}' < "$jobs_file"
rm -f "$jobs_file"
echo "$(date '+%F %T') all runs finished"
