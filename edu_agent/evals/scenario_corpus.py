"""确定性场景 corpus:薄加载 + 用例级 check 复算(带来源归属的失败清单)。

为什么不是复用现成 loader:EvalRunner 不读数据集(`run()` 只收预加载 cases,
runner.py 无 dataset 读取路径);唯一的既有 loader(image_teaching.load_scenarios)
锁死图文 v1 schema(source.question_id/provider/lesson_name 必填),会拒掉本
corpus——故此处是**薄 loader**(同 scripts/tuning_round.py 的 json.loads +
["scenarios"] 读取口径),不复制它的校验规则。

失败清单每条带 source 归属(issue/session):网的价值在「红要红得可追溯」。
"""

from __future__ import annotations

import json
from pathlib import Path

from .checks import REGISTRY, run_check

SHORTBOARD_DATASET = "small_lecturer_regression_shortboard_v1.json"
SHORTBOARD_SCHEMA_VERSION = "small_lecturer_regression_shortboard/v1"
_STATUSES = ("known_red", "guarded")


def datasets_dir() -> Path:
    """evals 数据集目录(老数据集零迁移证据与用例加载共用此定位)。"""
    return Path(__file__).resolve().parent / "datasets"


def load_shortboard_corpus(path: str | Path | None = None) -> list[dict]:
    """读回归网 corpus 并做最小校验;任一错误抛 ValueError(不静默跳过)。

    校验面:envelope(schema_version/scenarios)+ 必填键 + check 名可解析。
    既有数据集字段(ready_to_record 等)不受影响——本 loader 只看自己的键。"""
    dataset = Path(path) if path is not None else datasets_dir() / SHORTBOARD_DATASET
    payload = json.loads(dataset.read_text(encoding="utf-8"))
    version = payload.get("schema_version")
    if version != SHORTBOARD_SCHEMA_VERSION:
        raise ValueError(
            f"schema_version 不符:期望 {SHORTBOARD_SCHEMA_VERSION},实际 {version!r}")
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("scenarios 必须是非空列表")
    errors = [error for scenario in scenarios for error in _scenario_errors(scenario)]
    if errors:
        raise ValueError("corpus 校验失败:\n" + "\n".join(errors))
    return scenarios


def _scenario_errors(scenario: object) -> list[str]:
    """单条场景的最小校验(加用例只写数据,写错在这里立刻红,不用改任何 .py)。"""
    if not isinstance(scenario, dict):
        return ["(非对象):场景必须是 dict"]
    scenario_id = str(scenario.get("id") or "(缺 id)")
    errors = []
    if not scenario.get("id"):
        errors.append(f"{scenario_id}:id 必填")
    if scenario.get("status") not in _STATUSES:
        errors.append(f"{scenario_id}:status 必须是 {'/'.join(_STATUSES)}")
    question = scenario.get("question")
    if not isinstance(question, dict) or not str(question.get("text") or "").strip():
        errors.append(f"{scenario_id}:question.text 必填")
    if not isinstance(scenario.get("student_turns"), list) or not scenario.get("student_turns"):
        errors.append(f"{scenario_id}:student_turns 必须是非空列表")
    if not isinstance(scenario.get("fake_model"), list) or not scenario.get("fake_model"):
        errors.append(f"{scenario_id}:fake_model 必须是非空列表(本 corpus 只收确定性口径)")
    checks = (scenario.get("expect") or {}).get("checks")
    if not isinstance(checks, list) or not checks:
        errors.append(f"{scenario_id}:expect.checks 必须是非空列表")
    else:
        errors.extend(
            f"{scenario_id}:check 未注册:{entry.get('name')!r}(已注册:{sorted(REGISTRY)})"
            for entry in checks
            if not isinstance(entry, dict) or entry.get("name") not in REGISTRY)
    if scenario.get("status") == "known_red" and not (scenario.get("source") or {}).get("issue"):
        errors.append(f"{scenario_id}:known_red 必须带 source.issue(红要红得可追溯)")
    return errors


def deterministic_scenarios(scenarios: list[dict]) -> list[dict]:
    """确定性子集(带 fake_model 罐头剧本);将来混合真模型口径时在此分流。"""
    return [scenario for scenario in scenarios if scenario.get("fake_model")]


def to_kernel_case(scenario: dict) -> dict:
    """场景 → KernelSubject.run_case 入参(gateway 由调用方注入,分层要求:
    edu_agent.evals 不 import tests/,FakeGateway 的构造在测试侧)。"""
    return {
        "id": scenario["id"],
        "question": scenario["question"],
        "grade": scenario.get("grade", ""),
        "answer_status": scenario.get("answer_status", ""),
        "student_turns": scenario["student_turns"],
    }


def run_scenario_checks(scenario: dict, result: dict) -> list[dict]:
    """跑场景声明的全部 expect.checks,返回失败清单(每条带 source 归属)。"""
    failures = []
    for entry in (scenario.get("expect") or {}).get("checks", []):
        ok, detail = run_check(entry, scenario, result)
        if not ok:
            failures.append({
                "scenario": str(scenario.get("id") or ""),
                "source": scenario.get("source") or {},
                "check": str(entry.get("name") or ""),
                "detail": detail,
            })
    return failures


def format_failures(failures: list[dict]) -> str:
    """失败清单 → 可读行(含 source.issue / source.session;详情自带具体数字/状态)。"""
    return "\n".join(
        f"[{item.get('scenario')}]"
        f" source.issue={(item.get('source') or {}).get('issue', '-')}"
        f" source.session={(item.get('source') or {}).get('session', '-')}"
        f" check={item.get('check')}: {item.get('detail')}"
        for item in failures)
