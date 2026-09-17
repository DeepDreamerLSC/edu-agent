#!/usr/bin/env python3
"""GEPA nets-in-loop main-03(2026-09-18 用户信封:2 代 / 300 calls 帽 / 停等审)。

泄露网即 loop 内约束(既有机制,零新判据):gepa.evaluate_batch 每案转录后立即
过 Net A(checks.text_excludes_answer_values,终答值不得出现在任何 tutor 轮),
命中 = 候选级硬否决 + 停批 + 分数不注册(永不可为父代/最优)。

本脚本只做运维壳(上次 smoke 教训制度化):
  1. --self-check 开跑前三查(checkpoint / 预算硬限 / held-out 隔离),零模型调用;
  2. 硬帽网关:每次 invoke 前查 facts 计数 ≥ 300 即抛 BudgetCapReached——第 301
     只调用不会发生,超顶 = 0(checkpoint 每代已落盘,截断代留证在 round 报告);
  3. 心跳 state.json:每次 invoke 原子更新(看门狗盯新鲜度,挂了只记录不重跑);
  4. 停跑条件:2 代完成 | 硬帽触发 | 种子泄露否决(gepa_loop 内建)。

跑法(仓根):
  .venv/bin/python edu_agent/evals/artifacts/gepa-nets-main-03/run_nets.py --self-check
  nohup .venv/bin/python edu_agent/evals/artifacts/gepa-nets-main-03/run_nets.py \
    >> edu_agent/evals/artifacts/gepa-nets-main-03/driver.log 2>&1 &

判读预注册(跑前冻结):
- 接受判定 = HNU 接受函数(#332:H/N/U 不增且 Δ≥0.125,或 HNU 减且 Δ≥0);
- 泄露网拦截读数(进 loop 前后)= seed 批 stats.leak_net_violations vs 各代
  round 报告 leak_net_veto/stats(零违例时记 0,与 main-02 epoch-2 口径同款);
- 初始模板 = main-02 best(单一最优 lineage 延续,双旋钮组合原样);
  editor_focus=mean(main-02 已穷尽 nr 靶向方向)、editor_role=judge
  (r24 起本地跑口径,夜间无人值守不依赖远程 API)。
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))  # 工件驱动仓根注入(run_probe.py 同款)

OUT_DIR = Path(__file__).resolve().parent
HARD_CAP_CALLS = 300  # 用户信封(2026-09-18):全程硬帽,含 seed/编辑/配对闸
GENERATIONS = 2
CORPUS_V2 = REPO / "edu_agent/evals/artifacts/corpus-round-v2/cases.jsonl"
HELDOUT = REPO / "edu_agent/evals/datasets/small_lecturer_math_gold_b2_heldout.json"
INITIAL_TEMPLATE = (
    "请复讲：先说核心思路，再写出第一步的具体算式或操作，最后给出明确结论。"
    "请用完整句子描述步骤与结果，以便确认掌握。"
)  # main-02 best(checkpoint 原文逐字)
LOCAL_PORTS = (8301, 8303)  # judge(mlx_27b) / tutor(vision_8b)


class BudgetCapReached(RuntimeError):
    """硬帽触发:facts 实计 ≥ HARD_CAP_CALLS,下一次 invoke 前熔断。"""


def _heartbeat(phase: str, calls: int) -> None:
    """心跳原子落盘(看门狗盯 mtime;os.replace 保证不读半截)。"""
    payload = {"pid": os.getpid(), "phase": phase, "calls": calls,
               "ts": time.time(), "iso": time.strftime("%Y-%m-%dT%H:%M:%S")}
    tmp = OUT_DIR / "state.json.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(OUT_DIR / "state.json")


class CappedGateway:
    """硬帽 + 心跳网关(组合而非继承:只包 invoke 一个面)。

    facts 计数用 Gateway 自带进程内 writer.count(fresh facts 目录 → 从 0 起);
    每次调用前检查,≥ 帽即熔断;每次调用后心跳。委托其余属性给内层网关。
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self._phase = "run"

    def set_phase(self, phase: str) -> None:
        self._phase = phase

    def invoke(self, request):
        if self._inner.writer.count >= HARD_CAP_CALLS:
            raise BudgetCapReached(f"facts={self._inner.writer.count} ≥ {HARD_CAP_CALLS}")
        response = self._inner.invoke(request)
        _heartbeat(self._phase, self._inner.writer.count)
        return response

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _tcp_alive(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(2.0)
        try:
            sock.connect(("127.0.0.1", port))
        except OSError:
            return False
        return True


def _ids_from_heldout() -> set[str]:
    payload = json.loads(HELDOUT.read_text(encoding="utf-8"))
    scenarios = payload.get("scenarios", payload if isinstance(payload, list) else [])
    return {s.get("id", "") for s in scenarios}


def self_check() -> int:
    """开跑前三查 + 运维预检,零模型调用;任一不过即非零退出。"""
    failures = []
    # 查一 checkpoint:全新信封要求干净目录(有断点 = 误重入旧 run)
    stale = OUT_DIR / "checkpoint.json"
    if stale.exists():
        failures.append(f"checkpoint 查:目录已有 checkpoint.json(重入旧 run?)")
    # 查二 预算硬限:facts 台账干净 + 帽线三处一致(driver 常量 == 信封 == 循环配置)
    facts_files = list((OUT_DIR / "facts").glob("model_calls-*.jsonl"))
    if facts_files:
        lines = sum(1 for _ in facts_files[0].open(encoding="utf-8"))
        failures.append(f"预算查:facts 台账非空({facts_files[0].name} {lines} 行)")
    if HARD_CAP_CALLS != 300 or GENERATIONS != 2:
        failures.append("预算查:帽线/代数与用户信封(300/2)不符")
    # 查三 held-out 隔离:三个案集两两不相交,且 93 面齐全
    from edu_agent.evals.gepa import load_enriched12
    corpus_ids = {json.loads(line)["id"] for line
                  in CORPUS_V2.read_text(encoding="utf-8").splitlines() if line.strip()}
    heldout_ids = _ids_from_heldout()
    enriched_ids = {c.get("id", "") for c in load_enriched12()}
    if len(corpus_ids) != 93:
        failures.append(f"held-out 查:corpus v2 应 93 案,实际 {len(corpus_ids)}")
    overlaps = {"corpus∩heldout": corpus_ids & heldout_ids,
                "enriched∩heldout": enriched_ids & heldout_ids}
    for name, overlap in overlaps.items():
        if overlap:
            failures.append(f"held-out 查:{name} 非空:{sorted(overlap)}")
    # 运维预检(非三查,零调用):本地双服务活性 + registry 可载
    for port in LOCAL_PORTS:
        if not _tcp_alive(port):
            failures.append(f"运维预检:127.0.0.1:{port} 不通")
    if failures:
        for item in failures:
            print(f"SELF-CHECK-FAIL {item}")
        return 1
    print(f"SELF-CHECK-OK checkpoint=干净 facts=空 硬帽={HARD_CAP_CALLS} "
          f"代数={GENERATIONS} heldout隔离=∅ (corpus 93 / enriched 12 / heldout "
          f"{len(heldout_ids)}) 本地端口 {LOCAL_PORTS} 全通")
    return 0


def main() -> int:
    if "--self-check" in sys.argv:
        return self_check()
    # 开跑前必过三查(夜间无人值守,预检失败即退,不烧任何调用)
    if self_check() != 0:
        return 2
    from edu_agent.evals import GepaConfig, gepa_loop
    from edu_agent.gateway import Gateway, load_registry

    train_cases = [json.loads(line) for line
                   in CORPUS_V2.read_text(encoding="utf-8").splitlines() if line.strip()]
    inner = Gateway(load_registry(REPO / "configs/models.yaml"),
                    facts_dir=OUT_DIR / "facts")
    gateway = CappedGateway(inner)
    config = GepaConfig(
        rounds=GENERATIONS,
        batch_size=16,  # 仅入身份指纹;实际批 = 分层采样 3u+3s+3c+7bg(#332)
        max_calls=HARD_CAP_CALLS,
        judge_role="judge",  # 本地 27B 主选(#305 裁决①)
        two_knobs=True,  # main-02 best 是双旋钮组合,lineage 延续须双臂同置
        editor_focus="mean",  # main-02 已穷尽 nr 靶向;mean 为未试方向
        editor_role="judge",  # r24 起本地跑口径;夜间无人值守不依赖远程 API
    )
    stop_reason = "generations_done"
    _heartbeat("start", 0)
    try:
        gateway.set_phase("run")
        _, _, reports = gepa_loop(
            train_cases=train_cases,
            initial_template=INITIAL_TEMPLATE,
            config=config,
            gateway=gateway,
            output_dir=OUT_DIR,
            resume=False,  # 全新信封;重入由三查挡在门外
        )
        if not reports:
            stop_reason = "seed_vetoed_or_immediate_stop"
    except BudgetCapReached as exc:
        stop_reason = f"budget_cap: {exc}"
    finally:
        # 熔断若被转录层宽捕获吞掉,循环会「正常」返回——按 facts 终值复核:
        # writer.count 是硬事实,任何路径下 ≥ 帽都改判 budget_cap
        if inner.writer.count >= HARD_CAP_CALLS:
            stop_reason = "budget_cap(轮内熔断或轮首截断)"
        gateway.set_phase("wrap")
        ledger = _budget_ledger(OUT_DIR / "facts", inner)
        payload = {"stop_reason": stop_reason, "hard_cap": HARD_CAP_CALLS,
                   "generations": GENERATIONS, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "budget_ledger": ledger}
        (OUT_DIR / "run-exit.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        _heartbeat("done", inner.writer.count)
        inner.close()
    print(f"RUN-DONE stop={stop_reason} ledger={json.dumps(ledger, ensure_ascii=False)}")
    return 0


def _budget_ledger(facts_dir: Path, gateway) -> dict:
    """预算台账:facts 逐条拆 role×provider(计数/tokens/降级)。"""
    breakdown: dict[str, dict] = {}
    for path in sorted(facts_dir.glob("model_calls-*.jsonl")):
        for line in path.open(encoding="utf-8"):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = f"{rec.get('edu.role', '?')}@{rec.get('gen_ai.provider.name', '?')}"
            slot = breakdown.setdefault(
                key, {"calls": 0, "tokens_in": 0, "tokens_out": 0, "fallbacks": 0})
            slot["calls"] += 1
            slot["tokens_in"] += rec.get("gen_ai.usage.input_tokens") or 0
            slot["tokens_out"] += rec.get("gen_ai.usage.output_tokens") or 0
            if rec.get("edu.fallback_from"):
                slot["fallbacks"] += 1
    return {"total_calls": gateway.writer.count,
            "tokens_in": gateway.writer.tokens_in,
            "tokens_out": gateway.writer.tokens_out,
            "breakdown": breakdown}


if __name__ == "__main__":
    raise SystemExit(main())
