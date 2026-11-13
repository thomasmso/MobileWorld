#!/usr/bin/env bash
# Usage: bash scripts/run_bid_baseline.sh [agent_type] [log_root]
# Defaults reproduce the baseline: planner_executor -> traj_logs/baseline
set -u

AGENT_TYPE="${1:-planner_executor}"
LOG_ROOT="${2:-traj_logs/baseline}"
EXECUTOR_URL="https://6af63d1b6be47a5101200a0a.endpoints.huggingface.cloud/v1"
MODELS=(openai/gpt-5 anthropic/claude-sonnet-4.5 google/gemini-3.1-pro-preview)

for m in "${MODELS[@]}"; do
  echo "=== $AGENT_TYPE / $m ==="
  uv run mw eval --agent-type "$AGENT_TYPE" --task BidFileRenameTask \
    --model-name "$m" --llm-base-url https://openrouter.ai/api/v1 \
    --executor-agent-class uiins --executor-model-name UI-Ins-7B \
    --executor-llm-base-url "$EXECUTOR_URL" \
    --aw-host http://127.0.0.1:6800 --device emulator-5554 \
    --max-round 50 --auto-retry 0 --pass-k 3 \
    --log-file-root "$LOG_ROOT/${m//\//_}"
done
