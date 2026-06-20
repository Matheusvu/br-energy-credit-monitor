#!/usr/bin/env bash
#
# build_data.sh — Download ONS constrained-off (curtailment) CSVs for wind & solar,
# aggregate the half-hourly rows, and emit ../data.js for the dashboard.
#
# Uses only tools that ship with macOS: bash, curl, awk, sort, date.
# No Homebrew / Node / Python required.
#
# Config (override via env):
#   END=YYYY-MM     last month to include   (default: 2026-03, latest wind month)
#   MONTHS=N        how many months back     (default: 12)
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/data.js"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

END="${END:-2026-03}"
MONTHS="${MONTHS:-12}"

WIND_BASE="https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/restricao_coff_eolica_tm/RESTRICAO_COFF_EOLICA"
SOLAR_BASE="https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/restricao_coff_fotovoltaica_tm/RESTRICAO_COFF_FOTOVOLTAICA"

echo ">> Building dataset: last $MONTHS months ending $END"

# ---- 1. Download monthly CSVs (skip any that 404) -------------------------
months=()
i=0
while [ "$i" -lt "$MONTHS" ]; do
  ym=$(date -j -v-"${i}"m -f "%Y-%m-%d" "$END-01" "+%Y_%m")
  months+=("$ym")
  i=$((i+1))
done

fetch() { # src label, base url
  local src="$1" base="$2"
  for ym in "${months[@]}"; do
    local dash="${ym/_/-}"
    local url="${base}_${ym}.csv"
    local dest="$TMP/${src}-${dash}.csv"
    if curl -fsSL "$url" -o "$dest" 2>/dev/null; then
      printf '   ok  %s %s (%s)\n' "$src" "$dash" "$(du -h "$dest" | cut -f1)"
    else
      printf '   --  %s %s (not published)\n' "$src" "$dash"
      rm -f "$dest"
    fi
  done
}

echo ">> Downloading wind..."
fetch wind  "$WIND_BASE"
echo ">> Downloading solar..."
fetch solar "$SOLAR_BASE"

count=$(ls "$TMP"/*.csv 2>/dev/null | wc -l | tr -d ' ')
if [ "$count" -eq 0 ]; then
  echo "!! No data downloaded — check your connection." >&2
  exit 1
fi
echo ">> Aggregating $count files..."

# ---- 2. Aggregate with awk -------------------------------------------------
# Curtailment (constrained-off), MWmed = max(0, ref_final - geracao),
#   falling back to ref when ref_final is blank.
# Counted ONLY when a restriction reason (cod_razaorestricao) is recorded.
# Energy MWh = MWmed * 0.5  (half-hourly samples).
AGG="$TMP/agg.tsv"
awk -F';' -v OFS='\t' '
  FNR==1 {
    n=split(FILENAME,a,"/"); base=a[n]; sub(/\.csv$/,"",base);
    split(base,b,"-"); src=b[1]; month=b[2]"-"b[3];
    next                                  # skip header row
  }
  {
    reason=$14; if (reason=="") next       # only flagged constrained-off
    g=$9+0; rf=($13!=""?$13+0:$12+0);
    c=rf-g; if (c<0) c=0; mwh=c*0.5;
    if (mwh<=0) next
    K[src]            += mwh
    M[src SUBSEP month]  += mwh
    B[src SUBSEP $2]     += mwh
    E[src SUBSEP $3 SUBSEP $4] += mwh
    R[src SUBSEP reason] += mwh
  }
  END {
    for (k in K){ print "K","", "", k, K[k] }
    for (k in M){ split(k,p,SUBSEP); print "M",p[2],"",p[1],M[k] }
    for (k in B){ split(k,p,SUBSEP); print "B",p[2],"",p[1],B[k] }
    for (k in E){ split(k,p,SUBSEP); print "E",p[2],p[3],p[1],E[k] }
    for (k in R){ split(k,p,SUBSEP); print "R",p[2],"",p[1],R[k] }
  }
' "$TMP"/*.csv > "$AGG"

# ---- 3. Emit data.js -------------------------------------------------------
gen="$(date "+%Y-%m-%d %H:%M")"
start_m="$(awk -F'\t' '$1=="M"{print $2}' "$AGG" | sort | head -1)"
end_m="$(awk -F'\t' '$1=="M"{print $2}' "$AGG" | sort | tail -1)"

# helper: emit "month wind solar" merged JSON rows
monthly_json() {
  awk -F'\t' '$1=="M"{ if($4=="wind")w[$2]=$5; else s[$2]=$5; seen[$2]=1 }
    END{ for(m in seen) print m, (w[m]+0), (s[m]+0) }' "$AGG" \
  | sort | awk '{ printf "%s{\"month\":\"%s\",\"wind\":%.1f,\"solar\":%.1f}", (NR>1?",":""), $1, $2/1000, $3/1000 }'
}
subsystem_json() {
  awk -F'\t' '$1=="B"{ if($4=="wind")w[$2]=$5; else s[$2]=$5; seen[$2]=1 }
    END{ for(k in seen) print k, (w[k]+0), (s[k]+0), (w[k]+s[k]) }' "$AGG" \
  | sort -k4 -nr | awk '{ printf "%s{\"name\":\"%s\",\"wind\":%.1f,\"solar\":%.1f}", (NR>1?",":""), $1, $2/1000, $3/1000 }'
}
reasons_json() {
  awk -F'\t' '$1=="R"{ if($4=="wind")w[$2]=$5; else s[$2]=$5; seen[$2]=1 }
    END{ for(k in seen) print k, (w[k]+0), (s[k]+0), (w[k]+s[k]) }' "$AGG" \
  | sort -k4 -nr | awk '{ printf "%s{\"code\":\"%s\",\"wind\":%.1f,\"solar\":%.1f}", (NR>1?",":""), $1, $2/1000, $3/1000 }'
}
states_json() {
  # Keep tab-delimited throughout so multi-word state names (e.g. "RIO GRANDE DO NORTE") survive.
  awk -F'\t' '$1=="E"{ key=$2"\t"$3; if($4=="wind")w[key]=$5; else s[key]=$5; seen[key]=1 }
    END{ for(k in seen) printf "%s\t%.3f\n", k, (w[k]+s[k]) }' "$AGG" \
  | sort -t"$(printf '\t')" -k3 -nr | head -10 \
  | awk -F'\t' '{ printf "%s{\"uf\":\"%s\",\"name\":\"%s\",\"total\":%.1f}", (NR>1?",":""), $1, $2, $3/1000 }'
}
kpi_field() { awk -F'\t' -v s="$1" '$1=="K" && $4==s{ printf "%.1f", $5/1000 }' "$AGG"; }

wind_gwh="$(kpi_field wind)";  solar_gwh="$(kpi_field solar)"
wind_gwh="${wind_gwh:-0}"; solar_gwh="${solar_gwh:-0}"
total_gwh="$(awk -v a="$wind_gwh" -v b="$solar_gwh" 'BEGIN{printf "%.1f", a+b}')"

{
  echo "// Generated by scripts/build_data.sh — do not edit by hand."
  echo "// Source: ONS Dados Abertos (constrained-off eólica & fotovoltaica)."
  echo "window.ONS_DATA = {"
  echo "  \"generated\": \"$gen\","
  echo "  \"range\": {\"start\": \"$start_m\", \"end\": \"$end_m\"},"
  echo "  \"unit\": \"GWh\","
  echo "  \"kpi\": {\"wind\": $wind_gwh, \"solar\": $solar_gwh, \"total\": $total_gwh},"
  echo "  \"monthly\": [$(monthly_json)],"
  echo "  \"subsystem\": [$(subsystem_json)],"
  echo "  \"reasons\": [$(reasons_json)],"
  echo "  \"states\": [$(states_json)]"
  echo "};"
} > "$OUT"

echo ">> Wrote $OUT"
echo ">> Range $start_m..$end_m | wind ${wind_gwh} GWh | solar ${solar_gwh} GWh | total ${total_gwh} GWh"
