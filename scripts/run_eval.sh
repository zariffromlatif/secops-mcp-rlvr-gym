#!/bin/sh
# Evaluate a model on one environment through the free-tier proxy (retries rate limits).
#
#   sh scripts/run_eval.sh patches   qwen/qwen3.8-27b [extra vf-eval args...]
#   sh scripts/run_eval.sh workflows openai/gpt-oss-20b -r 2
#
# Needs GROQ_API_KEY in .env (or set UPSTREAM_BASE_URL / UPSTREAM_API_KEY_VAR for another
# OpenAI-compatible provider). Results land in .tmp/evals/.
set -e
cd "$(dirname "$0")/.."
#   sh scripts/run_eval.sh resume .tmp/evals/<run-dir>     # re-run missing/errored episodes
ENV="$1"; MODEL="$2"; shift 2
KEY_VAR="${UPSTREAM_API_KEY_VAR:-GROQ_API_KEY}"
case "$ENV" in
    patches)   EVAL="vf-eval secops_gym_patches --env.agent.runtime.type docker --model $MODEL \
                    --client.base-url http://127.0.0.1:8099/v1 --client.api-key-var $KEY_VAR -c 1 -o /work/.tmp/evals" ;;
    workflows) EVAL="vf-eval secops_gym_workflows --env.agent.runtime.type subprocess --model $MODEL \
                    --client.base-url http://127.0.0.1:8099/v1 --client.api-key-var $KEY_VAR -c 1 -o /work/.tmp/evals" ;;
    resume)    EVAL="vf-eval @ /work/$MODEL/configs/resolved/eval.json --resume" ;;
    *) echo "usage: $0 patches|workflows <model> [vf-eval args]  |  $0 resume <run-dir>"; exit 2 ;;
esac
docker compose -f runtime/docker-compose.yml up -d --wait >/dev/null 2>&1
sh scripts/devbox.sh sh -c "
    UPSTREAM_BASE_URL='${UPSTREAM_BASE_URL:-https://api.groq.com/openai/v1}' UPSTREAM_API_KEY_VAR=$KEY_VAR \
        uv run --no-sync python scripts/llm_proxy.py >> /work/.tmp/llm_proxy.log 2>&1 &
    sleep 3
    uv run --no-sync $EVAL $* 2>&1 | grep -vE 'deprecated|prime-rl|Trace push|PRIME_API_KEY|mode=.disabled|live into a dashboard'
"
# Interrupted workflow rollouts can leave their episode databases behind.
if [ "$ENV" = "workflows" ] || [ "$ENV" = "resume" ]; then
    uv run python runtime/workflows.py cleanup >/dev/null 2>&1 || true
fi
