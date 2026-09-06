"""runner 骨架合同(00 §8.2):checkpoint 续跑、失败分类台账、并发限速与指数退避、
产物 manifest 与晨间摘要。全部用假被测对象与假数据集,不碰 gateway/老系统/真实模型。
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest

from edu_agent.evals import (
    EnvironmentFailure,
    EvalRunner,
    ResumeMismatch,
    RunnerConfig,
    morning_summary,
    write_summary,
)

TOTAL = 20


class FakeSubject:
    """可编程假被测对象:按 case id 脚本出牌(ok / "env" / 异常实例),支持可编程延迟。"""

    name = "fake-subject"

    def __init__(self, script: dict | None = None, delay_s: float = 0.0):
        self.script = script or {}
        self.delay_s = delay_s
        self.calls: list[str] = []

    def run_case(self, case: dict) -> dict:
        case_id = case["id"]
        self.calls.append(case_id)
        queue = self.script.get(case_id)
        outcome = queue.pop(0) if queue else "ok"
        time.sleep(self.delay_s)
        if outcome == "env":
            raise EnvironmentFailure("环境抖动:服务暂不可用")
        if isinstance(outcome, BaseException):
            raise outcome
        return {"case_id": case_id, "messages": [{"role": "assistant", "content": f"答案-{case_id}"}]}


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    path = tmp_path / "fake20.jsonl"
    lines = [json.dumps({"id": f"c{i:02d}", "question": f"3+{i}=?"}) for i in range(TOTAL)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def load_cases(dataset: Path) -> list[dict]:
    return [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip()]


def make_runner(tmp_path: Path, subject, **config) -> EvalRunner:
    defaults = {"backoff_base_s": 0.01, "backoff_cap_s": 0.05}
    return EvalRunner(subject, RunnerConfig(**{**defaults, **config}), tmp_path / "runs")


def results_of(run_dir: Path) -> dict[str, dict]:
    return {path.stem: json.loads(path.read_text(encoding="utf-8"))
            for path in (run_dir / "results").glob("*.json")}


def test_all_ok_writes_checkpoint_and_manifest(tmp_path, dataset):
    subject = FakeSubject()
    run_dir = make_runner(tmp_path, subject).run(dataset, load_cases(dataset))
    results = results_of(run_dir)
    assert len(results) == TOTAL and all(r["status"] == "ok" for r in results.values())
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["subject"] == "fake-subject"
    assert manifest["total_cases"] == TOTAL
    assert manifest["dataset"]["sha256"] == hashlib.sha256(dataset.read_bytes()).hexdigest()
    assert manifest["config"]["sha256"]
    assert results["c00"]["transcript"]["messages"][0]["content"] == "答案-c00"


def test_resume_only_reruns_missing_and_environment(tmp_path, dataset):
    # 首轮:c00-c14 成功,c15-c17 环境失败(重试耗尽),c18-c19 内容失败
    cases = load_cases(dataset)
    script = {**{f"c{i:02d}": ["env", "env", "env", "env"] for i in range(15, 18)},
              **{f"c{i:02d}": [ValueError("输出缺字段")] for i in range(18, 20)}}
    first = make_runner(tmp_path, FakeSubject(script), env_retry_attempts=2)
    run_dir = first.run(dataset, cases)
    assert {r["status"] for r in results_of(run_dir).values()} == {"ok", "environment", "content"}
    # 续跑:环境失败与缺失重跑,内容失败与成功不碰
    resumed = FakeSubject()
    make_runner(tmp_path, resumed, env_retry_attempts=2).run(dataset, cases, run_dir=run_dir)
    assert sorted(resumed.calls) == ["c15", "c16", "c17"]  # 只补缺与环境失败
    final = results_of(run_dir)
    assert final["c15"]["status"] == "ok" and final["c17"]["status"] == "ok"  # 补跑成功
    assert final["c18"]["status"] == "content" and final["c19"]["status"] == "content"  # 不补跑
    assert final["c00"]["attempts"] == 1 and len(resumed.calls) == 3


def test_environment_failure_retries_with_backoff(tmp_path, dataset):
    cases = load_cases(dataset)
    cases = [cases[0]]
    dataset_one = tmp_path / "one.jsonl"
    dataset_one.write_text(json.dumps(cases[0]) + "\n", encoding="utf-8")
    script = {"c00": ["env", "env", "ok"]}
    runner = make_runner(tmp_path, FakeSubject(script), env_retry_attempts=3,
                          backoff_base_s=0.05, backoff_cap_s=1.0)
    started = time.monotonic()
    run_dir = runner.run(dataset_one, cases)
    elapsed = time.monotonic() - started
    result = results_of(run_dir)["c00"]
    assert result["status"] == "ok" and result["attempts"] == 3
    assert elapsed >= 0.15  # 指数退避 0.05 + 0.10 真睡了
    # 台账记了两次环境失败事件(重试过程可见),最终结果 ok
    ledger = [json.loads(line) for line in (run_dir / "failures.jsonl").read_text().splitlines()]
    assert [e["kind"] for e in ledger] == ["environment", "environment"]


def test_content_failure_not_retried(tmp_path, dataset):
    cases = load_cases(dataset)[:1]
    dataset_one = tmp_path / "one.jsonl"
    dataset_one.write_text(json.dumps(cases[0]) + "\n", encoding="utf-8")
    script = {"c00": [ValueError("内容缺陷:缺总结")]}
    run_dir = make_runner(tmp_path, FakeSubject(script)).run(dataset_one, cases)
    result = results_of(run_dir)["c00"]
    assert result["status"] == "content" and result["attempts"] == 1  # 不重试
    assert "ValueError" in result["error"]


def test_concurrency_caps_parallelism(tmp_path, dataset):
    cases = load_cases(dataset)[:6]
    dataset_six = tmp_path / "six.jsonl"
    dataset_six.write_text("\n".join(json.dumps(c) for c in cases) + "\n", encoding="utf-8")
    subject = FakeSubject(delay_s=0.15)
    started = time.monotonic()
    make_runner(tmp_path, subject, concurrency=2).run(dataset_six, cases)
    elapsed = time.monotonic() - started
    # 6 条 × 0.15s:串行 ≥0.9s;并发 2 ≈ 3 波 0.45s,上下都留余量
    assert 0.35 <= elapsed < 0.8, elapsed


def test_resume_mismatch_refused(tmp_path, dataset):
    cases = load_cases(dataset)
    runner = make_runner(tmp_path, FakeSubject())
    run_dir = runner.run(dataset, cases)
    other = tmp_path / "other.jsonl"
    other.write_text("\n".join(json.dumps({"id": f"x{i}", "q": i}) for i in range(3)) + "\n",
                     encoding="utf-8")
    with pytest.raises(ResumeMismatch, match="数据集版本"):
        runner.run(other, cases, run_dir=run_dir)
    different_config = make_runner(tmp_path, FakeSubject(), concurrency=4)
    with pytest.raises(ResumeMismatch, match="配置哈希"):
        different_config.run(dataset, cases, run_dir=run_dir)


def test_morning_summary_counts_and_actions(tmp_path, dataset):
    cases = load_cases(dataset)
    script = {**{f"c{i:02d}": ["env", "env", "env", "env"] for i in (3, 7)},
              **{f"c{i:02d}": [ValueError("内容缺陷")] for i in (11, 13, 15)},
              "c17": [KeyboardInterrupt()]}
    # 单并发 + c17 中断:c17-c19 三条未跑,即过夜中断后的目录状态
    with pytest.raises(KeyboardInterrupt):
        make_runner(tmp_path, FakeSubject(script), env_retry_attempts=2, concurrency=1).run(dataset, cases)
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
