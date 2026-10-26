#!/bin/bash
# Download the 9 traces listed in traces.txt into traces/ (~4.7 GB).
#
# Usage: scripts/download_traces.sh
# SPEC CPU2017 traces: DPC-3 server (Stony Brook).
# GAP traces: UT Austin ML-DPC Box folder (ChampSimTraces/gap).
# Files already present and intact are skipped.

set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/traces"
cd "$ROOT/traces"

SPEC=https://dpc3.compas.cs.stonybrook.edu/champsim-traces/speccpu
BOX="https://utexas.app.box.com/index.php?rm=box_download_shared_file&shared_name=2k54kp8zvrqdfaa8cdhfquvcxwh7yn85&file_id=f_"

url_for() {
    case "$1" in
        bfs-3.trace.gz) echo "${BOX}782969530379" ;;
        pr-3.trace.gz)  echo "${BOX}782970353678" ;;
        cc-5.trace.gz)  echo "${BOX}782971699530" ;;
        *)              echo "$SPEC/$1" ;;
    esac
}

intact() {
    case "$1" in
        *.xz) xz -t "$1" 2>/dev/null ;;
        *.gz) gzip -t "$1" 2>/dev/null ;;
    esac
}

fail=0
while read -r t; do
    [ -z "$t" ] && continue
    if [ -f "$t" ] && intact "$t"; then
        echo "ok (already here) $t"
        continue
    fi
    echo "downloading $t"
    if curl -sSL --fail --retry 3 -o "$t.part" "$(url_for "$t")" && mv "$t.part" "$t" && intact "$t"; then
        echo "ok $t"
    else
        echo "FAILED $t"
        rm -f "$t.part"
        fail=1
    fi
done < "$ROOT/traces.txt"
exit $fail
