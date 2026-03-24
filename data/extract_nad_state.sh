#!/usr/bin/env bash
# Extract rows for a single state from NAD_r21_TXT.zip
# Usage: ./extract_nad_state.sh GA
# Output: NAD_r21_GA.txt (with header)

set -euo pipefail

STATE="${1:?Usage: $0 <STATE_ABBREV>  (e.g. GA)}"
STATE_UPPER=$(echo "$STATE" | tr '[:lower:]' '[:upper:]')
ZIP="NAD_r21_TXT.zip"
OUT="NAD_r21_${STATE_UPPER}.txt"

if [ ! -f "$ZIP" ]; then
    echo "Error: $ZIP not found in current directory" >&2
    exit 1
fi

echo "Extracting ${STATE_UPPER} rows from ${ZIP} → ${OUT}..."

# State is field 34 (comma-delimited). Extract header + matching rows.
# Using FPAT to handle quoted CSV fields correctly.
unzip -p "$ZIP" "TXT/NAD_r21.txt" | awk -v state="$STATE_UPPER" '
    BEGIN { FPAT = "([^,]*)|(\"[^\"]*\")"; OFS = "," }
    NR == 1 { print; next }
    { gsub(/^[ \t]+|[ \t]+$/, "", $34); if (toupper($34) == state) print }
' > "$OUT"

ROWS=$(( $(wc -l < "$OUT") - 1 ))
echo "Done — ${ROWS} rows written to ${OUT}"
