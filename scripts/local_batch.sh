#!/usr/bin/env bash
# Evaluate models served on this machine (Ollama by default) on both environments, then re-score
# every solution with V1-V4, using the same local server as the LLM judge. Made for a fixed lab
# window: no run is started after DEADLINE (local time, HH:MM).
#
#   MODELS="local/gpt-oss-20b local/qwen3-14b" REPEATS=3 DEADLINE=12:15 bash scripts/local_batch.sh
#
# Run directories are listed in .tmp/local/runs.txt, so a later batch re-scores earlier runs too.
# Results: results/audit/local_{solutions.jsonl,verdicts.csv}, results/evals/ tables and traces.
set -u
cd "$(dirname "$0")/.."
MODELS=${MODELS:-"local/gpt-oss-20b local/qwen3-14b"}
REPEATS=${REPEATS:-3}
DEADLINE=${DEADLINE:-23:59}
JUDGE=${JUDGE:-local/gpt-oss-20b}
SERVER=${SERVER:-http://localhost:11434}
OUT=.tmp/local
RUNS=$OUT/runs.txt
LOG=$OUT/log.txt
mkdir -p "$OUT"
touch "$RUNS"
export PYTHONUTF8=1 LOCAL_API_KEY=local
# Containers reach the host's model server through host.docker.internal.
export LOCAL_LLM=${SERVER/localhost/host.docker.internal}/v1
log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

curl -sf "$SERVER/v1/models" >/dev/null || { log "no model server at $SERVER; start Ollama first"; exit 1; }
docker info >/dev/null 2>&1 || { log "Docker is not running; start Docker first"; exit 1; }

for model in $MODELS; do
    for env in workflows patches; do
        if [[ "$(date +%H:%M)" > "$DEADLINE" ]]; then log "deadline $DEADLINE reached; no new runs"; break 2; fi
        before=$(ls -d .tmp/evals/*/ 2>/dev/null | sort)
        log "start $env $model (x$REPEATS)"
        sh scripts/run_eval.sh "$env" "$model" -r "$REPEATS" >> "$LOG" 2>&1
        after=$(ls -d .tmp/evals/*/ 2>/dev/null | sort)
        dir=$(comm -13 <(echo "$before") <(echo "$after") | head -1)
        dir=${dir%/}
        if [ -n "$dir" ]; then echo "$env $model $dir" >> "$RUNS"; log "done $env $model -> $dir"; fi
    done
done

DIRS=$(awk '{ print $3 }' "$RUNS")
[ -n "$DIRS" ] || { log "no runs to score"; exit 0; }
log "re-scoring every collected solution with V1-V4 (judge: $JUDGE)"
# shellcheck disable=SC2086
uv run python -m audit.collect $DIRS --out results/audit/local_solutions.jsonl >> "$LOG" 2>&1
uv run python -m audit.verify results/audit/local_solutions.jsonl --out results/audit/local_verdicts.csv \
    --judge-model "$JUDGE" --judge-base-url "$SERVER/v1" --judge-key-var LOCAL_API_KEY >> "$LOG" 2>&1
uv run python runtime/workflows.py cleanup >> "$LOG" 2>&1
for dir in $DIRS; do
    [ -f "$dir/traces.jsonl" ] || continue
    uv run python scripts/summarize_evals.py "$dir" > /dev/null 2>> "$LOG"
    cp "$dir/traces.jsonl" "results/evals/traces/$(basename "$dir").jsonl"
done
log "batch finished"
