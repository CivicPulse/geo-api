#!/bin/bash
# Download TIGER/Line shapefiles from Census Bureau for PostGIS Tiger geocoder.
#
# Downloads all county-level and state-level files needed by setup-tiger.
# Run this OUTSIDE Docker on a machine with good bandwidth, then upload
# the output directory to R2/S3/etc.
#
# Usage:
#   ./scripts/download-tiger-data.sh GA          # single state
#   ./scripts/download-tiger-data.sh GA FL AL     # multiple states
#   ./scripts/download-tiger-data.sh --all        # all 50 states + DC
#
# Output structure (mirrors Census FTP layout expected by PostGIS loader):
#   tiger-data/
#     ADDR/tl_2024_13001_addr.zip
#     EDGES/tl_2024_13001_edges.zip
#     FACES/tl_2024_13001_faces.zip
#     FEATNAMES/tl_2024_13001_featnames.zip
#     PLACE/tl_2024_13_place.zip
#     COUSUB/tl_2024_13_cousub.zip
#     TRACT/tl_2024_13_tract.zip
#     TABBLOCK20/tl_2024_13_tabblock20.zip
#     STATE/tl_2024_us_state.zip
#     COUNTY/tl_2024_us_county.zip

set -euo pipefail

TIGER_YEAR="${TIGER_YEAR:-2024}"
BASE_URL="https://www2.census.gov/geo/tiger/TIGER${TIGER_YEAR}"
OUTPUT_DIR="${OUTPUT_DIR:-tiger-data}"
WAIT="${WAIT:-30}"
INITIAL_WAIT="${INITIAL_WAIT:-15}"

# State-level tables (one file per state)
STATE_TABLES=(PLACE COUSUB TRACT TABBLOCK20)

# County-level tables (one file per county)
COUNTY_TABLES=(ADDR EDGES FACES FEATNAMES)

# National tables (one file total, needed once)
NATIONAL_TABLES=(STATE COUNTY)

# FIPS code lookup
declare -A FIPS=(
  [AL]=01 [AK]=02 [AZ]=04 [AR]=05 [CA]=06 [CO]=08 [CT]=09 [DE]=10
  [DC]=11 [FL]=12 [GA]=13 [HI]=15 [ID]=16 [IL]=17 [IN]=18 [IA]=19
  [KS]=20 [KY]=21 [LA]=22 [ME]=23 [MD]=24 [MA]=25 [MI]=26 [MN]=27
  [MS]=28 [MO]=29 [MT]=30 [NE]=31 [NV]=32 [NH]=33 [NJ]=34 [NM]=35
  [NY]=36 [NC]=37 [ND]=38 [OH]=39 [OK]=40 [OR]=41 [PA]=42 [RI]=44
  [SC]=45 [SD]=46 [TN]=47 [TX]=48 [UT]=49 [VT]=50 [VA]=51 [WA]=53
  [WV]=54 [WI]=55 [WY]=56 [AS]=60 [GU]=66 [MP]=69 [PR]=72 [VI]=78
)

# --- Argument parsing ---

STATES=()
if [[ "${1:-}" == "--all" ]]; then
  STATES=("${!FIPS[@]}")
elif [[ $# -gt 0 ]]; then
  for arg in "$@"; do
    upper=$(echo "$arg" | tr '[:lower:]' '[:upper:]')
    if [[ -z "${FIPS[$upper]+x}" ]]; then
      echo "Error: unknown state '$arg'" >&2
      echo "Usage: $0 GA [FL AL ...]  or  $0 --all" >&2
      exit 1
    fi
    STATES+=("$upper")
  done
else
  echo "Usage: $0 STATE [STATE ...]  or  $0 --all" >&2
  echo "Examples:" >&2
  echo "  $0 GA              # Georgia only" >&2
  echo "  $0 GA FL AL        # multiple states" >&2
  echo "  $0 --all           # all states" >&2
  exit 1
fi

echo "Tiger year: ${TIGER_YEAR}"
echo "Output dir: ${OUTPUT_DIR}"
echo "States:     ${STATES[*]}"
echo ""

if [[ "$INITIAL_WAIT" -gt 0 ]]; then
  echo "Waiting ${INITIAL_WAIT}s before starting downloads..."
  sleep "$INITIAL_WAIT"
  echo "Starting downloads."
  echo ""
fi

mkdir -p "${OUTPUT_DIR}"

# --- Helper: download with retry on 429 ---

download() {
  local url="$1"
  local dest="$2"

  # Skip if already downloaded (non-empty file)
  if [[ -f "$dest" && -s "$dest" ]]; then
    return 0
  fi

  local max_retries=5
  for attempt in $(seq 1 $max_retries); do
    # Capture stderr for HTTP status detection; || true prevents set -e abort
    local stderr_file
    stderr_file=$(mktemp)
    local rc=0
    wget --no-verbose -O "$dest" "$url" 2>"$stderr_file" || rc=$?
    local stderr_out
    stderr_out=$(cat "$stderr_file")
    rm -f "$stderr_file"

    # Success: non-zero exit code 0 and file has content
    if [[ $rc -eq 0 && -s "$dest" ]]; then
      return 0
    fi

    # Detect 429 from wget output (exit code 8 = server error)
    if echo "$stderr_out" | grep -q "429"; then
      rm -f "$dest"
      local wait_secs=$((30 * attempt))
      echo "    Rate limited (429). Waiting ${wait_secs}s (attempt ${attempt}/${max_retries})..." >&2
      sleep "$wait_secs"
      continue
    fi

    # Other failure
    echo "    Failed: $(basename "$dest") (exit $rc)" >&2
    [[ -n "$stderr_out" ]] && echo "    $stderr_out" >&2
    rm -f "$dest"
    return 1
  done
  echo "    Giving up on $(basename "$dest") after ${max_retries} retries" >&2
  rm -f "$dest"
  return 1
}

# --- Helper: fetch directory listing with retry-after support ---

fetch_listing() {
  local url="$1"
  local max_retries=5
  local base_wait=60

  for attempt in $(seq 1 $max_retries); do
    local header_file
    header_file=$(mktemp)
    local body http_code
    body=$(curl -s -D "$header_file" -w '\n%{http_code}' "$url" || true)
    http_code=$(echo "$body" | tail -1)
    body=$(echo "$body" | sed '$d')

    if [[ "$http_code" == "200" && -n "$body" ]]; then
      rm -f "$header_file"
      echo "$body"
      return 0
    fi

    if [[ "$http_code" == "429" ]]; then
      # Parse retry-after header (case-insensitive)
      local retry_after
      retry_after=$(grep -i '^retry-after:' "$header_file" | head -1 | tr -d '\r' | awk '{print $2}')
      rm -f "$header_file"

      # Use server's retry-after if numeric, otherwise exponential backoff
      local wait_secs
      if [[ -n "$retry_after" && "$retry_after" =~ ^[0-9]+$ ]]; then
        wait_secs=$((retry_after + 10))
      else
        wait_secs=$((base_wait * attempt))
      fi

      echo "  [listing] Rate limited (429). Waiting ${wait_secs}s (attempt ${attempt}/${max_retries})..." >&2
      sleep "$wait_secs"
      continue
    fi

    # Other HTTP error
    rm -f "$header_file"
    local wait_secs=$((base_wait * attempt))
    echo "  [listing] HTTP ${http_code} fetching ${url}. Retrying in ${wait_secs}s (attempt ${attempt}/${max_retries})..." >&2
    sleep "$wait_secs"
  done

  echo "  [listing] FAILED to fetch ${url} after ${max_retries} retries" >&2
  return 1
}

# --- National tables (download once) ---

for table in "${NATIONAL_TABLES[@]}"; do
  dir="${OUTPUT_DIR}/${table}"
  mkdir -p "$dir"
  fname="tl_${TIGER_YEAR}_us_$(echo "$table" | tr '[:upper:]' '[:lower:]').zip"
  url="${BASE_URL}/${table}/${fname}"
  if [[ -f "${dir}/${fname}" && -s "${dir}/${fname}" ]]; then
    echo "[national] ${fname} (cached)"
  else
    echo "[national] Downloading ${fname}..."
    download "$url" "${dir}/${fname}"
  fi
done

# --- Pre-fetch county table directory listings (4 requests, not 4×N) ---
# Cached as plain text files (one zip filename per line) in .listings/

LISTINGS_DIR="${OUTPUT_DIR}/.listings"
mkdir -p "$LISTINGS_DIR"

echo ""
echo "=== Pre-fetching county table listings ==="
declare -A COUNTY_LISTINGS
for table in "${COUNTY_TABLES[@]}"; do
  table_lower=$(echo "$table" | tr '[:upper:]' '[:lower:]')
  cache_file="${LISTINGS_DIR}/${table}.txt"

  # Use cached listing if it exists and is less than 30 days old
  cache_max_age=$((30 * 24 * 60 * 60))
  if [[ -f "$cache_file" && -s "$cache_file" ]] && \
     [[ $(($(date +%s) - $(date -r "$cache_file" +%s))) -lt $cache_max_age ]]; then
    COUNTY_LISTINGS[$table]=$(cat "$cache_file")
    count=$(wc -l < "$cache_file")
    echo "  ${table}: cached (${count} files)"
  else
    echo "  Fetching ${table} listing..."
    if html=$(fetch_listing "${BASE_URL}/${table}/"); then
      filenames=$(echo "$html" | grep -oP "tl_${TIGER_YEAR}_\\d+_${table_lower}\\.zip" | sort -u)
      echo "$filenames" > "$cache_file"
      COUNTY_LISTINGS[$table]="$filenames"
      count=$(echo "$filenames" | grep -c . || true)
      echo "  ${table}: OK (${count} files)"
    else
      echo "  WARNING: Could not fetch ${table} listing. County downloads for ${table} will be skipped." >&2
      COUNTY_LISTINGS[$table]=""
    fi
    sleep "$WAIT"
  fi
done

# --- Per-state processing ---

for state in "${STATES[@]}"; do
  fips="${FIPS[$state]}"
  echo ""
  echo "=== ${state} (FIPS ${fips}) ==="

  # State-level tables
  for table in "${STATE_TABLES[@]}"; do
    dir="${OUTPUT_DIR}/${table}"
    mkdir -p "$dir"
    fname="tl_${TIGER_YEAR}_${fips}_$(echo "$table" | tr '[:upper:]' '[:lower:]').zip"
    url="${BASE_URL}/${table}/${fname}"
    if [[ -f "${dir}/${fname}" && -s "${dir}/${fname}" ]]; then
      echo "  [${table}] ${fname} (cached)"
    else
      echo "  [${table}] Downloading ${fname}..."
      download "$url" "${dir}/${fname}"
      sleep "$WAIT"
    fi
  done

  # County-level tables — filter from pre-fetched directory listing
  for table in "${COUNTY_TABLES[@]}"; do
    dir="${OUTPUT_DIR}/${table}"
    mkdir -p "$dir"
    table_lower=$(echo "$table" | tr '[:upper:]' '[:lower:]')

    listing="${COUNTY_LISTINGS[$table]}"
    files=$(echo "$listing" | grep -oP "tl_${TIGER_YEAR}_${fips}\\d+_${table_lower}\\.zip" | sort -u)
    count=$(echo "$files" | grep -c . || true)

    if [[ "$count" -eq 0 ]]; then
      echo "  [${table}] Warning: no files found for ${state}!"
      continue
    fi

    echo "  [${table}] Found ${count} files. Downloading..."
    downloaded=0
    skipped=0
    idx=0
    for fname in $files; do
      idx=$((idx + 1))
      if [[ -f "${dir}/${fname}" && -s "${dir}/${fname}" ]]; then
        skipped=$((skipped + 1))
        continue
      fi
      echo "  [${table}] (${idx}/${count}) Downloading ${fname}..."
      url="${BASE_URL}/${table}/${fname}"
      if download "$url" "${dir}/${fname}"; then
        downloaded=$((downloaded + 1))
      fi
      sleep "$WAIT"
    done
    echo "  [${table}] Done: ${downloaded} downloaded, ${skipped} cached (${count} total)"
  done
done

echo ""
echo "=== Download complete ==="
total=$(find "${OUTPUT_DIR}" -name "*.zip" | wc -l)
size=$(du -sh "${OUTPUT_DIR}" | cut -f1)
echo "Total files: ${total}"
echo "Total size:  ${size}"
echo ""
echo "To upload to R2:"
echo "  rclone sync ${OUTPUT_DIR}/ r2:your-bucket/tiger-data/"
echo ""
echo "To use with setup-tiger, copy into the container:"
echo "  docker cp ${OUTPUT_DIR}/. geo-api-api-1:/gisdata/www2.census.gov/geo/tiger/TIGER${TIGER_YEAR}/"
echo "  docker compose exec api geo-import setup-tiger ${STATES[*]}"
