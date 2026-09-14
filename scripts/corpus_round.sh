#!/bin/sh
# 语料轮薄包装(#241 行1):申报批跑标志 + 转发;edu_agent/ 零改动(P2-2)。
# 必须 uv run:裸 python3 -m 缺项目 venv 直接 ImportError(v2 设计稿规格 bug 修正)。
flag="/tmp/edu-agent-batch/corpus-round.$$"
mkdir -p /tmp/edu-agent-batch || exit 1
touch "$flag" || exit 1   # fail-closed:申报不了就不开工,门不会静默让路
trap 'rm -f "$flag"' EXIT  # kill -9 场景:pid 死 → benchmark live() 顺手清死标志
uv run python -m edu_agent.evals.corpus_round "$@"
