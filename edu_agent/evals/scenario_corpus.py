"""确定性场景 corpus:薄加载 + 用例级 check 复算(带来源归属的失败清单)。

为什么不是复用现成 loader:EvalRunner 不读数据集(`run()` 只收预加载 cases,
runner.py 无 dataset 读取路径);唯一的既有 loader(image_teaching.load_scenarios)
锁死图文 v1 schema——必填 `id/title/grade/bucket/misconception_seed`、
`reference_answer.value/answer_type`、`visual_dependency`、`expected.outcome`、
`source.question_id/provider/lesson_name`、`student_turns`、图路径/sha256 全套
图文字段,会拒掉本 corpus——故此处是**薄 loader**(同 scripts/tuning_round.py
的 json.loads + ["scenarios"] 读取口径),不复制它的校验规则。

词表归属:datasets/ 目录里 v1/v3 老场景的 `expect.final_states` /
`assistant_contains` / `ready_to_record` 目前无任何代码消费(惰性数据);
**回归网只认本 schema 的 `expect.checks`**,消费端唯一,别往老词表上加新语义。

失败清单每条带 source 归属(issue + question_id,question_id 写全 24 位可直接
join 回题库 inventory):网的价值在「红要红得可追溯」。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .checks import REGISTRY, _numbers, run_check

SHORTBOARD_DATASET = "small_lecturer_regression_shortboard_v1.json"
SHORTBOARD_SCHEMA_VERSION = "small_lecturer_regression_shortboard/v1"
_STATUSES = ("known_red", "guarded")
# 题库 ObjectId 口径:question_id 写全 24 位十六进制才可 join 回 inventory
# (8 位截断正是上轮修掉的溯源错位,形态校验拦住它复发)。
_QID_RE = re.compile(r"[0-9a-f]{24}")


def datasets_dir() -> Path:
    """evals 数据集目录(老数据集零迁移证据与用例加载共用此定位)。"""
    return Path(__file__).resolve().parent / "datasets"


def load_shortboard_corpus(path: str | Path | None = None) -> list[dict]:
    """读回归网 corpus 并做最小校验;任一错误抛 ValueError(不静默跳过)。

    校验面:envelope(schema_version/scenarios)+ 形状必填 + check 名可解析且
    不重名 + answer 可提取(关掉恒真通道)+ source 归属齐全。既有数据集字段
    (ready_to_record 等)不受影响——本 loader 只看自己的键。"""
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
    """单条场景校验入口:形状(_shape_errors)+ 期望(_expect_errors)两半。"""
    if not isinstance(scenario, dict):
        return ["(非对象):场景必须是 dict"]
    return _shape_errors(scenario) + _expect_errors(scenario)


def _shape_errors(scenario: dict) -> list[str]:
    """必填键与类型(加用例只写数据,写错在这里立刻红,不用改任何 .py)。"""
    scenario_id = str(scenario.get("id") or "(缺 id)")
    errors: list[str] = []
    if not scenario.get("id"):
        errors.append(f"{scenario_id}:id 必填")
    if scenario.get("status") not in _STATUSES:
        errors.append(f"{scenario_id}:status 必须是 {'/'.join(_STATUSES)}")
    question = scenario.get("question")
    if not isinstance(question, dict) or not str(question.get("text") or "").strip():
        errors.append(f"{scenario_id}:question.text 必填")
    turns = scenario.get("student_turns")
    if not isinstance(turns, list) or not turns:
        errors.append(f"{scenario_id}:student_turns 必须是非空列表")
    else:
        errors.extend(f"{scenario_id}:student_turns[{i}] 必须是字符串(内核按文本回放)"
                      for i, turn in enumerate(turns) if not isinstance(turn, str))
    canned = scenario.get("fake_model")
    if not isinstance(canned, list) or not canned:
        errors.append(f"{scenario_id}:fake_model 必须是非空列表(本 corpus 只收确定性口径)")
    else:
        errors.extend(f"{scenario_id}:fake_model[{i}] 必须是 {{\"json\": {{...}}}} 形态"
                      for i, entry in enumerate(canned)
                      if not isinstance(entry, dict) or not isinstance(entry.get("json"), dict))
    return errors


def _expect_errors(scenario: dict) -> list[str]:
    """expect.checks 与 source:名字可解析不重名、answer 可提取、来源可追溯。"""
    scenario_id = str(scenario.get("id") or "(缺 id)")
    errors: list[str] = []
    checks = (scenario.get("expect") or {}).get("checks")
    if not isinstance(checks, list) or not checks:
        errors.append(f"{scenario_id}:expect.checks 必须是非空列表")
        return errors
    names = [str(entry.get("name") or "") for entry in checks if isinstance(entry, dict)]
    errors.extend(f"{scenario_id}:check 未注册:{entry.get('name')!r}(已注册:{sorted(REGISTRY)})"
                  for entry in checks
                  if not isinstance(entry, dict) or entry.get("name") not in REGISTRY)
    duplicated = sorted({name for name in names if names.count(name) > 1})
    if duplicated:
        errors.append(f"{scenario_id}:check 重名 {duplicated}(同一 check 声明两遍是写错)")
    if "text_excludes_answer_values" in names:
        answer = (scenario.get("question") or {}).get("answer") \
            if isinstance(scenario.get("question"), dict) else None
        if not _numbers(answer):
            errors.append(
                f"{scenario_id}:声明 text_excludes_answer_values 但 question.answer"
                " 取不到 ASCII 数字(中文数字/文字答案)——check 会恒真空转,请改写"
                " answer 为数字形态或换 check")
    source = scenario.get("source")
    if not isinstance(source, dict) or not source.get("issue"):
        errors.append(f"{scenario_id}:source.issue 必填(红要红得可追溯)")
        return errors
    question_id = source.get("question_id")
    if question_id is not None and not _QID_RE.fullmatch(str(question_id)):
        errors.append(f"{scenario_id}:source.question_id 必须是 24 位小写十六进制"
                      "(题库 ObjectId 口径,写全才可 join 回 inventory;截断/乱码"
                      f"会让溯源静默失效),实际 {question_id!r}")
    if scenario.get("status") == "known_red" and not question_id:
        errors.append(f"{scenario_id}:known_red 必须带 source.question_id(24 位,"
                      "可直接 join 回题库 inventory)")
    return errors


def deterministic_scenarios(scenarios: list[dict]) -> list[dict]:
    """确定性子集(带 fake_model 罐头剧本)。现状:v1 corpus 只收确定性口径
    (fake_model 必填由 loader 强制),本函数恒等于全集;真模型口径(第二批,
    #179/#187 拦截面等)进来时需先放宽 loader 的必填规则,再在此按口径分流。"""
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
    """失败清单 → 可读行(issue + question_id + lesson_name + 详情)。

    question_id 是可 join 的那半张牌(机器),lesson_name 是人读的那半张(CI 里
    24 位 id 不可读);详情自带具体数字/状态。"""
    return "\n".join(
        f"[{item.get('scenario')}]"
        f" source.issue={(item.get('source') or {}).get('issue', '-')}"
        f" source.question_id={(item.get('source') or {}).get('question_id', '-')}"
        f" source.lesson_name={(item.get('source') or {}).get('lesson_name', '-')}"
        f" check={item.get('check')}: {item.get('detail')}"
        for item in failures)
