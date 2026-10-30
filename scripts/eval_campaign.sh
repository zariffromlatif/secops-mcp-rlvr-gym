#!/usr/bin/env bash
# One day of the multi-day evaluation campaign on Groq's free tier.
#
#   bash scripts/eval_campaign.sh            # run today's share, then re-score and summarize
#   bash scripts/eval_campaign.sh --status   # only print progress
#
# Every model gets ~200K tokens per rolling 24 h, and a patch episode costs 25-35K, so all tasks
# for both models take several days. Each day resumes the same run directories (vf-eval
# --resume re-runs missing and errored episodes), recorded in .tmp/campaign/state.txt. When every
# task has a successful episode, or after 4 days, the status line says COMPLETE or STOPPED.
#
# Needs GROQ_API_KEY in .env. Runs on Linux and macOS (start Docker first) and on Windows in Git
# Bash, where it also keeps the PC awake and starts Docker Desktop if needed.
set -u
cd "$(dirname "$0")/.."
CAMPAIGN=.tmp/campaign
STATE=$CAMPAIGN/state.txt
DAYS=$CAMPAIGN/days.txt
LOG=$CAMPAIGN/log.txt
mkdir -p "$CAMPAIGN"
touch "$STATE" "$DAYS"
export PYTHONUTF8=1
ON_WINDOWS=
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
        ON_WINDOWS=1
        # The campaign PC keeps uv's cache on E:; set UV_CACHE_DIR to use another place.
        [ -n "${UV_CACHE_DIR:-}" ] || export UV_CACHE_DIR='E:\.cache\uv' ;;
esac
log() { echo "[$(date -u '+%F %T') UTC] $*" | tee -a "$LOG"; }
status() { uv run python scripts/campaign_status.py "$STATE" --days-run "$(wc -l < "$DAYS")" | tee "$CAMPAIGN/status.txt"; }

if [ "${1:-}" = "--status" ]; then status; exit 0; fi
if grep -qE "^(COMPLETE|STOPPED)" "$CAMPAIGN/status.txt" 2>/dev/null; then
    log "campaign already finished; nothing to do"; status; exit 0
fi

if [ -n "$ON_WINDOWS" ]; then
    # Keep the PC from idle-sleeping while this script runs (a per-process request; no settings change).
    powershell -NoProfile -Command "Add-Type -Name P -Namespace W -MemberDefinition '[DllImport(\"kernel32.dll\")] public static extern uint SetThreadExecutionState(uint f);'; [void][W.P]::SetThreadExecutionState([uint32]2147483649); while (\$true) { Start-Sleep 60 }" &
    AWAKE=$!
    trap 'kill $AWAKE 2>/dev/null' EXIT
fi

if [ -n "$ON_WINDOWS" ] && ! docker info >/dev/null 2>&1; then
    log "starting Docker Desktop"
    powershell -NoProfile -Command "Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe'"
    for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 5; done
fi
docker info >/dev/null 2>&1 || { log "Docker did not start; giving up for today"; exit 1; }
docker compose -f runtime/docker-compose.yml up -d --wait >/dev/null 2>&1

date -u '+%F' >> "$DAYS"
log "day $(wc -l < "$DAYS") of the campaign"

run_one() {  # <env> <model>: resume this pair's run directory, or start it
    local env=$1 model=$2 dir before after
    dir=$(awk -v e="$env" -v m="$model" '$1 == e && $2 == m { print $3 }' "$STATE")
    if [ -n "$dir" ]; then
        log "resume $env $model ($dir)"
        sh scripts/run_eval.sh resume "$dir" >> "$LOG" 2>&1
    else
        before=$(ls -d .tmp/evals/*/ 2>/dev/null | sort)
        log "start $env $model"
        sh scripts/run_eval.sh "$env" "$model" -r 1 >> "$LOG" 2>&1
        after=$(ls -d .tmp/evals/*/ 2>/dev/null | sort)
        dir=$(comm -13 <(echo "$before") <(echo "$after") | head -1)
        dir=${dir%/}
        if [ -n "$dir" ]; then echo "$env $model $dir" >> "$STATE"; else log "no run directory created for $env $model"; fi
    fi
}

# Cheap workflows first, then patches; each model has its own quota.
run_one workflows qwen/qwen3.8-27b
run_one workflows openai/gpt-oss-120b
run_one patches qwen/qwen3.8-27b
run_one patches openai/gpt-oss-120b

log "re-scoring every collected solution with V1-V4"
RUNS=$(awk '{ print $3 }' "$STATE")
# shellcheck disable=SC2086
uv run python -m audit.collect $RUNS --out results/audit/solutions.jsonl >> "$LOG" 2>&1
( set -a; . ./.env; set +a
  uv run python -m audit.verify results/audit/solutions.jsonl --out results/audit/verdicts.csv \
      --judge-model openai/gpt-oss-20b >> "$LOG" 2>&1 )
uv run python runtime/workflows.py cleanup >> "$LOG" 2>&1

for dir in $RUNS; do
    [ -f "$dir/traces.jsonl" ] || continue
    uv run python scripts/summarize_evals.py "$dir" > /dev/null 2>> "$LOG"
    cp "$dir/traces.jsonl" "results/evals/traces/$(basename "$dir").jsonl"
done
log "done for today"
status
