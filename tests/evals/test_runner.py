"""runner 骨架合同(00 §8.2):checkpoint 续跑、失败分类台账、并发限速与指数退避、
产物 manifest 与晨间摘要。全部用假被测对象与假数据集,不碰 gateway/老系统/真实模型。
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import fields
from pathlib import Path

import pytest
from evalkit import read_jsonl, results_of, write_jsonl

from edu_agent.evals import (
    EnvironmentFailure,
    EvalRunner,
    ResumeMismatch,
    RunnerConfig,
    morning_summary,
    safe_case_id,
    write_summary,
)

TOTAL = 20


class FakeSubject:
    """可编程假被测对象:按 case id 脚本出牌(ok / "env" / 异常实例),支持可编程延迟。

    intervals 记录每次 run_case 的 (开始, 结束) 单调钟区间——并发不变量
    (区间最大重叠数)的直接证据,供 test_concurrency_caps_parallelism。
    """

    name = "fake-subject"

    def __init__(self, script: dict | None = None, delay_s: float = 0.0):
        self.script = script or {}
        self.delay_s = delay_s
        self.calls: list[str] = []
        self.intervals: list[tuple[float, float]] = []

    def run_case(self, case: dict) -> dict:
        case_id = case["id"]
        self.calls.append(case_id)
        queue = self.script.get(case_id)
        outcome = queue.pop(0) if queue else "ok"
        started = time.monotonic()
        try:
            time.sleep(self.delay_s)
            if outcome == "env":
                raise EnvironmentFailure("环境抖动:服务暂不可用")
            if isinstance(outcome, BaseException):
                raise outcome
            return {"case_id": case_id, "messages": [{"role": "assistant", "content": f"答案-{case_id}"}]}
        finally:
            self.intervals.append((started, time.monotonic()))


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    return write_jsonl(tmp_path / "fake20.jsonl",
                       [{"id": f"c{i:02d}", "question": f"3+{i}=?"} for i in range(TOTAL)])


def make_runner(tmp_path: Path, subject, **config) -> EvalRunner:
    return EvalRunner(subject, RunnerConfig(**config), tmp_path / "runs")


def test_all_ok_writes_checkpoint_and_manifest(tmp_path, dataset):
    subject = FakeSubject()
    run_dir = make_runner(tmp_path, subject).run(dataset, read_jsonl(dataset))
    results = results_of(run_dir)
    assert len(results) == TOTAL and all(r["status"] == "ok" for r in results.values())
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["subject"] == "fake-subject"
    assert manifest["total_cases"] == TOTAL
    assert manifest["dataset"]["sha256"] == hashlib.sha256(dataset.read_bytes()).hexdigest()
    assert manifest["config"]["sha256"]
    assert results["c00"]["transcript"]["messages"][0]["content"] == "答案-c00"


def test_resume_only_reruns_missing_and_environment(tmp_path, dataset):
    # 首轮:c00-c14 成功,c15-c17 环境失败(Gateway 穷尽类,不整案重跑),c18-c19 内容失败
    cases = read_jsonl(dataset)
    script = {**{f"c{i:02d}": ["env"] for i in range(15, 18)},
              **{f"c{i:02d}": [ValueError("输出缺字段")] for i in range(18, 20)}}
    first = make_runner(tmp_path, FakeSubject(script))
    run_dir = first.run(dataset, cases)
    assert {r["status"] for r in results_of(run_dir).values()} == {"ok", "environment", "content"}
    # 续跑:环境失败与缺失重跑,内容失败与成功不碰
    resumed = FakeSubject()
    make_runner(tmp_path, resumed).run(dataset, cases, run_dir=run_dir)
    assert sorted(resumed.calls) == ["c15", "c16", "c17"]  # 只补缺与环境失败
    final = results_of(run_dir)
    assert final["c15"]["status"] == "ok" and final["c17"]["status"] == "ok"  # 补跑成功
    assert final["c18"]["status"] == "content" and final["c19"]["status"] == "content"  # 不补跑
    assert final["c00"]["attempts"] == 1 and len(resumed.calls) == 3


def test_environment_failure_runs_once_no_case_retry(tmp_path, dataset):
    """新语义(#254 P1):EnvironmentFailure → 整案仅执行一次,不进程内重跑。

    Gateway 已在其内部穷尽 retry+fallback,Runner 整案重跑只会叠加可靠性语义;
    脚本里留一个后续 "ok" 证明不会重入;恢复手段 = 续跑补跑(resume 测试覆盖)。
    """
    cases = read_jsonl(dataset)[:1]
    dataset_one = write_jsonl(tmp_path / "one.jsonl", cases)
    subject = FakeSubject({"c00": ["env", "ok"]})
    run_dir = make_runner(tmp_path, subject).run(dataset_one, cases)
    result = results_of(run_dir)["c00"]
    assert subject.calls == ["c00"]  # 仅执行一次:脚本第二张牌 "ok" 未被消费
    assert result["status"] == "environment" and result["attempts"] == 1
    ledger = [json.loads(line) for line in (run_dir / "failures.jsonl").read_text().splitlines()]
    assert [e["kind"] for e in ledger] == ["environment"]


def test_content_failure_not_retried(tmp_path, dataset):
    cases = read_jsonl(dataset)[:1]
    dataset_one = write_jsonl(tmp_path / "one.jsonl", cases)
    script = {"c00": [ValueError("内容缺陷:缺总结")]}
    run_dir = make_runner(tmp_path, FakeSubject(script)).run(dataset_one, cases)
    result = results_of(run_dir)["c00"]
    assert result["status"] == "content" and result["attempts"] == 1  # 不重试
    assert "ValueError" in result["error"]


def _max_in_flight(intervals: list[tuple[float, float]]) -> int:
    """同一时刻在跑的最大数(事件点扫描线;同刻先处理结束再处理开始,交接不算并行)。"""
    events = [(t, delta) for start, end in intervals for t, delta in ((start, 1), (end, -1))]
    current = peak = 0
    for _, delta in sorted(events):
        current += delta
        peak = max(peak, current)
    return peak


def test_concurrency_caps_parallelism(tmp_path, dataset):
    """并发 2 的不变量:任一时刻 ≤2 条在跑,且确实出现 2 条同时在跑。

    用执行区间重叠判定,不用总时长阈值——self-hosted runner 的进程环境会拉伸
    定时器/调度(2026-09-09 晚 main CI 连续两红 #127:elapsed 0.87/0.90s 顶到
    0.8s 上限;同机同 commit SSH 直跑全绿,证代码无罪、墙钟阈值对机器状态过敏)。
    区间重叠只看相对时序,对绝对时长漂移免疫。
    """
    cases = read_jsonl(dataset)[:6]
    dataset_six = tmp_path / "six.jsonl"
    write_jsonl(dataset_six, cases)
    subject = FakeSubject(delay_s=0.15)
    make_runner(tmp_path, subject, concurrency=2).run(dataset_six, cases)
    assert len(subject.intervals) == 6
    assert _max_in_flight(subject.intervals) == 2  # 既真的并发了(≥2),也没超限(≤2)


def test_resume_mismatch_refused(tmp_path, dataset):
    cases = read_jsonl(dataset)
    runner = make_runner(tmp_path, FakeSubject())
    run_dir = runner.run(dataset, cases)
    other = tmp_path / "other.jsonl"
    write_jsonl(other, [{"id": f"x{i}", "q": i} for i in range(3)])
    with pytest.raises(ResumeMismatch, match="数据集版本"):
        runner.run(other, cases, run_dir=run_dir)
    different_config = make_runner(tmp_path, FakeSubject(), concurrency=4)
    with pytest.raises(ResumeMismatch, match="配置哈希"):
        different_config.run(dataset, cases, run_dir=run_dir)


def test_morning_summary_counts_and_actions(tmp_path, dataset):
    cases = read_jsonl(dataset)
    script = {**{f"c{i:02d}": ["env"] for i in (3, 7)},
              **{f"c{i:02d}": [ValueError("内容缺陷")] for i in (11, 13, 15)},
              "c17": [KeyboardInterrupt()]}
    # 单并发 + c17 中断:c17-c19 三条未跑,即过夜中断后的目录状态
    with pytest.raises(KeyboardInterrupt):
        make_runner(tmp_path, FakeSubject(script), concurrency=1).run(dataset, cases)
    run_dir = next((tmp_path / "runs").iterdir())
    summary = morning_summary(run_dir)
    assert "ok 12/20(60%)" in summary
    assert "未跑 3 · 环境失败 2 · 内容失败 3" in summary
    assert "environment 2 · content 3" in summary
    assert "续跑:还有 3 条" in summary
    assert "补跑环境失败 2 条" in summary
    assert "内容失败 3 条转 judge" in summary
    assert "p50" in summary and "p95" in summary
    write_summary(run_dir)
    assert (run_dir / "summary.md").read_text(encoding="utf-8") == summary
    # 全绿路径
    ok_dir = make_runner(tmp_path, FakeSubject()).run(dataset, cases)
    assert "全部 20 条完成:进入 judge 评分与报告" in morning_summary(ok_dir)


def test_run_with_identity_writes_manifest_block(tmp_path, dataset):
    """#238 件 A:identity 原样进 manifest;不传 = 键缺席(其他调用方不受影响)。"""
    run_dir = make_runner(tmp_path, FakeSubject()).run(
        dataset, read_jsonl(dataset),
        identity={"git_sha": "abc123", "prompts_sha256": "p" * 64, "models_sha256": "m" * 64})
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["identity"] == {"git_sha": "abc123", "prompts_sha256": "p" * 64,
                                    "models_sha256": "m" * 64}
    run_dir2 = make_runner(tmp_path, FakeSubject()).run(dataset, read_jsonl(dataset))
    manifest2 = json.loads((run_dir2 / "manifest.json").read_text(encoding="utf-8"))
    assert "identity" not in manifest2


# 消费者真实字段名(git/rubric/prompt/cases/battery/models/addendum 七 hash);
# Runner 对字段名 schema-agnostic——哑字段亦可,只证完整全等
IDENT = {"git_sha": "g" * 40,
         "rubric_freeze_sha": "r" * 64,
         "prompt_asset_sha": "p" * 64,
         "cases_sha": "c" * 64,
         "battery_sha": "b" * 64,
         "models_yaml_sha": "m" * 64,
         "addendum_sha256": "a" * 64}


def test_strict_identity_resume_identical_passes(tmp_path, dataset):
    """#490 M1:strict 模式下 stored/current 全等 → 可续跑,环境失败案照常补跑。"""
    cases = read_jsonl(dataset)
    script = {"c00": ["env"]}
    run_dir = make_runner(tmp_path, FakeSubject(script)).run(dataset, cases, identity=IDENT)
    resumed = FakeSubject()
    make_runner(tmp_path, resumed).run(dataset, cases, run_dir=run_dir,
                                       identity=IDENT, strict_identity=True)
    assert resumed.calls == ["c00"]  # 全等放行:只补环境失败案,其余 checkpoint 不碰


@pytest.mark.parametrize("key", sorted(IDENT))
def test_strict_identity_resume_refuses_any_field_change(tmp_path, dataset, key):
    """M1 必测(#490 §四):git/rubric/prompt/cases/battery/models/addendum
    任一 hash 字段变化即拒,错误指名变化字段。"""
    cases = read_jsonl(dataset)
    run_dir = make_runner(tmp_path, FakeSubject()).run(dataset, cases, identity=IDENT)
    changed = {**IDENT, key: "x" * 64}
    with pytest.raises(ResumeMismatch, match=f"字段 {key} 值变"):
        make_runner(tmp_path, FakeSubject()).run(dataset, cases, run_dir=run_dir,
                                                 identity=changed, strict_identity=True)


def test_strict_identity_resume_refuses_added_and_removed_fields(tmp_path, dataset):
    """增字段(current-only)与删字段(stored-only)均拒,错误指名字段与类别。"""
    cases = read_jsonl(dataset)
    run_dir = make_runner(tmp_path, FakeSubject()).run(dataset, cases, identity=IDENT)
    with pytest.raises(ResumeMismatch, match="新增字段 extra_sha"):
        make_runner(tmp_path, FakeSubject()).run(
            dataset, cases, run_dir=run_dir,
            identity={**IDENT, "battery_sha": "b" * 64, "extra_sha": "e" * 64},
            strict_identity=True)
    removed = {k: v for k, v in IDENT.items() if k != "models_yaml_sha"}
    with pytest.raises(ResumeMismatch, match="缺失字段 models_yaml_sha"):
        make_runner(tmp_path, FakeSubject()).run(dataset, cases, run_dir=run_dir,
                                                 identity=removed, strict_identity=True)


def test_strict_identity_resume_refuses_missing_stored_and_current(tmp_path, dataset):
    """fail closed 两角:stored 缺失(旧 run 无 identity)与 current 缺失(未传)。"""
    cases = read_jsonl(dataset)
    plain_dir = make_runner(tmp_path, FakeSubject()).run(dataset, cases)  # 无 identity 旧 run
    with pytest.raises(ResumeMismatch, match="stored identity 缺失"):
        make_runner(tmp_path, FakeSubject()).run(dataset, cases, run_dir=plain_dir,
                                                 identity=IDENT, strict_identity=True)
    ident_dir = make_runner(tmp_path, FakeSubject()).run(dataset, cases, identity=IDENT)
    with pytest.raises(ResumeMismatch, match="未传 identity"):
        make_runner(tmp_path, FakeSubject()).run(dataset, cases, run_dir=ident_dir,
                                                 strict_identity=True)


def test_strict_identity_resume_refuses_pathological_stored(tmp_path, dataset):
    """stored 非对象(病态 manifest)→ 干净拒绝,不 AttributeError 崩溃。"""
    cases = read_jsonl(dataset)
    run_dir = make_runner(tmp_path, FakeSubject()).run(dataset, cases, identity=IDENT)
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["identity"] = "not-a-mapping"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ResumeMismatch, match="非对象"):
        make_runner(tmp_path, FakeSubject()).run(dataset, cases, run_dir=run_dir,
                                                 identity=IDENT, strict_identity=True)


def test_identity_mismatch_without_strict_still_resumes(tmp_path, dataset):
    """零变化锚(镜像 rescore_judge 用法):非 strict 下 identity 不一致照常续跑。"""
    cases = read_jsonl(dataset)
    run_dir = make_runner(tmp_path, FakeSubject()).run(dataset, cases, identity=IDENT)
    again = make_runner(tmp_path, FakeSubject()).run(
        dataset, cases, run_dir=run_dir, identity={**IDENT, "git_sha": "z" * 40})
    assert again == run_dir


def test_new_run_strict_manifest_has_no_extra_keys(tmp_path, dataset):
    """新 run + strict:manifest 与非 strict 同构——strict 不落 manifest、无新键、
    不进 config sha(started_at 是两次 run 间唯一合法差异,剔除后逐键全等)。"""
    cases = read_jsonl(dataset)
    strict_dir = make_runner(tmp_path, FakeSubject()).run(
        dataset, cases, identity=IDENT, strict_identity=True)
    plain_dir = make_runner(tmp_path, FakeSubject()).run(dataset, cases, identity=IDENT)

    def manifest_without_ts(run_dir):
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        del manifest["started_at"]
        return manifest

    assert manifest_without_ts(strict_dir) == manifest_without_ts(plain_dir)
    assert set(manifest_without_ts(strict_dir)) == {
        "dataset", "config", "subject", "total_cases", "identity"}
    # identity 字段无丢失(#490 M3 迁移证明):七字段整映射逐字落盘,无键增删
    assert manifest_without_ts(strict_dir)["identity"] == IDENT


def test_strict_identity_gate_precedes_three_faces(tmp_path, dataset):
    """拒绝强度不降(顺序保持):identity 与三面同时不一致时,identity 门先报、
    错误指名 identity 字段——迁移前 s2/d6d7 脚本门先于 runner 三面的报错优先级
    在公共层内保持。"""
    cases = read_jsonl(dataset)
    run_dir = make_runner(tmp_path, FakeSubject()).run(dataset, cases, identity=IDENT)
    other = tmp_path / "other.jsonl"
    write_jsonl(other, [{"id": f"x{i}", "q": i} for i in range(3)])
    with pytest.raises(ResumeMismatch, match="字段 git_sha 值变") as exc_info:
        make_runner(tmp_path, FakeSubject()).run(
            other, cases, run_dir=run_dir,
            identity={**IDENT, "git_sha": "z" * 40}, strict_identity=True)
    assert "数据集版本" not in str(exc_info.value)  # 三面未先行吞掉 identity 错


def test_runner_config_surface_has_no_domain_gates():
    """专项门未进 Runner(#490 §七「不把专项 preflight 收进 Runner」):RunnerConfig
    公开面只有并发——无 30 案/exposed/模型身份等任何领域字段。"""
    assert [f.name for f in fields(RunnerConfig)] == ["concurrency"]


def test_runner_imposes_no_specialty_preflight(tmp_path):
    """专项 preflight 未进 Runner(行为面):d6d7 的恰 30/唯一/exposed 恰 5、S2 的
    battery 面数门在各自脚本;Runner 对携带这些字段且不满足这些门的批量照常执行。"""
    rows = [{"id": f"p{i}", "answer_exposed": True} for i in range(3)]  # ≠30 且 exposed=3
    mini = write_jsonl(tmp_path / "mini.jsonl", rows)
    run_dir = make_runner(tmp_path, FakeSubject()).run(mini, rows)
    results = results_of(run_dir)
    assert len(results) == 3 and all(r["status"] == "ok" for r in results.values())


def test_safe_case_id_keeps_long_ids_and_uniqueness():
    """#450 regression(Phase A 2026-09-25 infra incident):97 字符案整串保真——
    结果行 case_id 与 scenarios 键(原始 id)一致,check_rows/judge_rows 查键不再
    断;超文件名字节预算(240B)的病理长 ID 以内容哈希后缀保唯一,同前缀不撞档。"""
    long_id = "a64_target_v3_northwest_clarification_not_leakage" + "z" * 48
    assert len(long_id) == 97
    assert safe_case_id(long_id, 0) == long_id           # 不截断:join 键保真
    # 既有契约回归面:短 id 原样、非法字符替换、None/空 → 序号兜底
    assert safe_case_id("c00", 0) == "c00"
    assert safe_case_id("a/b c", 3) == "a_b_c"
    assert safe_case_id(None, 7) == "case-0007"
    assert safe_case_id("", 7) == "case-0007"
    # 超预算:同 240B 前缀的两个不同 id → 不同 safe id;输出恒 ≤240B;同 id 幂等
    huge_a = "甲" * 200 + "A"                              # 601B,前 600B 同
    huge_b = "甲" * 200 + "B"
    assert safe_case_id(huge_a, 0) != safe_case_id(huge_b, 0)
    assert all(len(safe_case_id(h, 0).encode("utf-8")) <= 240 for h in (huge_a, huge_b))
    assert safe_case_id(huge_a, 0) == safe_case_id(huge_a, 1)
