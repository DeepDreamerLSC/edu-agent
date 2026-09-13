"""回归网 corpus(#197 第二批起含确定性/真模型两口径):薄加载 + 用例级 check 复算
(带来源归属的失败清单)。

EvalRunner.run() 只收预加载 cases(不读数据集路径),image_teaching.load_scenarios
锁死图文 v1 schema 会拒本 corpus——故用 scripts/tuning_round.py 同款薄读取口径。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .checks import REGISTRY, _numbers, run_check

SHORTBOARD_DATASET = "small_lecturer_regression_shortboard_v1.json"
SHORTBOARD_SCHEMA_VERSION = "small_lecturer_regression_shortboard/v1"
# #197 第二批(真模型口径):shadow pilot 两数据集迁入 corpus 形态——question 字典
# 带 bank 对回的 answer + source.issue + 可选 expect.checks;无 fake_model 罐头。
PILOT_CORPUS_SCHEMA_VERSION = "small_lecturer_shadow_pilot_corpus/v1"
# #178 gold 候选(dialogue_scenarios/v2):分支剧本——学生消息由跟随器按导师
# 上一句选分支(select_branch),不是线性 student_turns;校验规则见
# _gold_dialogue_errors(只拦「跟随器跑不动」的写法)。
GOLD_DIALOGUE_SCHEMA_VERSION = "small_lecturer_dialogue_scenarios/v2"
CORPUS_SCHEMA_VERSIONS = (SHORTBOARD_SCHEMA_VERSION, PILOT_CORPUS_SCHEMA_VERSION,
                          GOLD_DIALOGUE_SCHEMA_VERSION)
_STATUSES = ("known_red", "guarded")
# 题库 ObjectId 口径:question_id 写全 24 位十六进制才可 join 回 inventory
# (8 位截断正是上轮修掉的溯源错位,形态校验拦住它复发)。
_QID_RE = re.compile(r"[0-9a-f]{24}")
# evals 数据集目录(老数据集零迁移证据与 corpus 加载共用)。
DATASETS_DIR = Path(__file__).resolve().parent / "datasets"


def load_shortboard_corpus(path: str | Path | None = None) -> list[dict]:
    """读回归网 corpus 并做最小校验;任一错误抛 ValueError(不静默跳过)。

    校验面:envelope + 形状必填 + check 名可解析不重名 + answer 可提取(关恒真
    通道)+ unauthorized 纯引用形态(拦挂错轮次)+ source 归属齐全。既有数据集
    字段(ready_to_record 等)不受影响——本 loader 只看自己的键。"""
    dataset = Path(path) if path is not None else DATASETS_DIR / SHORTBOARD_DATASET
    payload = json.loads(dataset.read_text(encoding="utf-8"))
    version = payload.get("schema_version")
    if version not in CORPUS_SCHEMA_VERSIONS:
        raise ValueError(
            f"schema_version 不符:期望 {'/'.join(CORPUS_SCHEMA_VERSIONS)},实际 {version!r}")
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("scenarios 必须是非空列表")
    errors: list[str] = []
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            errors.append("(非对象):场景必须是 dict")
            continue
        if version == GOLD_DIALOGUE_SCHEMA_VERSION:
            errors.extend(_gold_dialogue_errors(scenario))
            continue
        errors.extend(_shape_errors(scenario))
        errors.extend(_expect_errors(scenario))
    if errors:
        raise ValueError("corpus 校验失败:\n" + "\n".join(errors))
    return scenarios


def _shape_errors(scenario: dict) -> list[str]:
    """必填键与类型(加用例只写数据,写错在这里立刻红,不用改任何 .py)。

    口径分流(#197 第二批):有 fake_model = 确定性口径,必填规则一条不减;
    无 fake_model = 真模型口径——免罐头,但 question.answer 必填(泄漏/判停
    判据与 judge 的共同锚点),student_turns 可缺(adaptive 模拟器线无剧本)。"""
    scenario_id = str(scenario.get("id") or "(缺 id)")
    errors: list[str] = []
    if not scenario.get("id"):
        errors.append(f"{scenario_id}:id 必填")
    deterministic = scenario.get("fake_model") is not None
    if deterministic and scenario.get("status") not in _STATUSES:
        errors.append(f"{scenario_id}:status 必须是 {'/'.join(_STATUSES)}")
    question = scenario.get("question")
    if not isinstance(question, dict) or not str(question.get("text") or "").strip():
        errors.append(f"{scenario_id}:question.text 必填")
    if not deterministic and (not isinstance(question, dict)
                              or not str(question.get("answer") or "").strip()):
        errors.append(f"{scenario_id}:question.answer 必填(真模型口径:无罐头,answer"
                      " 是 check/judge 共同锚点,从 bank 对回或明标来源,不许缺)")
    turns = scenario.get("student_turns")
    if turns is not None or deterministic:
        if not isinstance(turns, list) or not turns:
            errors.append(f"{scenario_id}:student_turns 必须是非空列表")
        else:
            errors.extend(f"{scenario_id}:student_turns[{i}] 必须是字符串(内核按文本回放)"
                          for i, turn in enumerate(turns) if not isinstance(turn, str))
    canned = scenario.get("fake_model")
    if deterministic:
        if not isinstance(canned, list) or not canned:
            errors.append(f"{scenario_id}:fake_model 必须是非空列表(确定性口径)")
        else:
            errors.extend(f"{scenario_id}:fake_model[{i}] 必须是 {{\"json\": {{...}}}} 形态"
                          for i, entry in enumerate(canned)
                          if not isinstance(entry, dict) or not isinstance(entry.get("json"), dict))
    return errors


def _expect_errors(scenario: dict) -> list[str]:
    """expect.checks 与 source:名字可解析不重名、answer 可提取、来源可追溯。

    真模型口径(#197 第二批)checks 可缺(无确定性运行面,如 adaptive 模拟器线);
    一旦声明,校验与确定性口径完全一致(可解析、不重名、answer 可提取)。"""
    scenario_id = str(scenario.get("id") or "(缺 id)")
    errors: list[str] = []
    deterministic = scenario.get("fake_model") is not None
    checks = (scenario.get("expect") or {}).get("checks")
    names: list[str] = []
    if deterministic or checks is not None:
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
    if "text_excludes_unauthorized_numbers" in names:
        errors.extend(_unauthorized_check_errors(scenario_id, scenario))
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


def _unauthorized_check_errors(scenario_id: str, scenario: dict) -> list[str]:
    """挂 text_excludes_unauthorized_numbers 的用例必须是纯引用形态(第 4 条)。

    机器口径:罐头剧本里 tutor 可见文本(reply/step)的数字必须 ⊆ 题面 ∪ 学生
    剧本数字——否则本 check 会对合法导出数字(如 28/10)假阳性红。
    # ponytail: 天花板 = 只拦剧本数据;内核生成文本(bottom-out 揭晓终答、首问
    模板)是运行期现实,挂到那些轮次会运行期红,由红暴露,不在加载期拦。
    """
    allowed = _numbers((scenario.get("question") or {}).get("text"))
    allowed |= _numbers(" ".join(scenario.get("student_turns") or []))
    introduced: set[float] = set()
    for entry in scenario.get("fake_model") or []:
        payload = entry.get("json") if isinstance(entry, dict) else {}
        if not isinstance(payload, dict):
            continue
        texts = [str(payload.get("reply") or "")]
        texts += [str(step.get("step") or "")
                  for step in payload.get("steps") or [] if isinstance(step, dict)]
        introduced |= _numbers(" ".join(texts)) - allowed
    if introduced:
        return [f"{scenario_id}:声明 text_excludes_unauthorized_numbers,但罐头剧本"
                f"(reply/step)引入题面 ∪ 学生允许集之外的数字 "
                f"{','.join(f'{value:g}' for value in sorted(introduced))}——本 check "
                "只适用于纯引用题面数字的轮次,挂到判断/计算轮会假阳性;请换 check 或改写剧本"]
    return []


def deterministic_scenarios(scenarios: list[dict]) -> list[dict]:
    """确定性子集(带 fake_model 罐头剧本)——口径分流口(#197 第二批已启用:
    真模型场景(无 fake_model,如 shadow pilot 两数据集)不进确定性回放,由
    夜评/真模型运行面消费;loader 对两口径分别校验,必填规则互不放松)。"""
    return [scenario for scenario in scenarios if scenario.get("fake_model")]


def _gold_dialogue_errors(scenario: dict) -> list[str]:
    """gold 候选(v2 分支剧本)加载校验:只拦「跟随器跑不动」的写法。

    question 是裸字符串(答案在剧本/期望里,不另设 question.answer 锚);
    expect 只声明 ready_to_record(checks 未声明 → corpus_round 记「无声明」);
    转正/驳回状态(gold.status)走 review.csv 人工流(#178 审核包),不在
    加载期约束词表。"""
    scenario_id = str(scenario.get("id") or "(缺 id)")
    errors: list[str] = []
    if not scenario.get("id"):
        errors.append(f"{scenario_id}:id 必填")
    if not isinstance(scenario.get("question"), str) or not scenario["question"].strip():
        errors.append(f"{scenario_id}:question 必须是非空字符串(v2 口径)")
    steps = scenario.get("steps")
    if not isinstance(steps, list) or not steps:
        return errors + [f"{scenario_id}:steps 必须是非空列表(分支剧本)"]
    gold = scenario.get("gold")
    if not isinstance(gold, dict) or not str(gold.get("status") or "").strip():
        errors.append(f"{scenario_id}:gold.status 必填(候选/转正走 review.csv 人工流)")
    for i, step in enumerate(steps):
        branches = step.get("branches") if isinstance(step, dict) else None
        if not isinstance(branches, list) or not branches:
            errors.append(f"{scenario_id}:steps[{i}].branches 必须是非空列表")
            continue
        fallbacks = 0
        for branch in branches:
            when = branch.get("when") or {}
            if when.get("fallback"):
                fallbacks += 1
            elif not (when.get("assistant_contains_any") or when.get("assistant_contains_all")):
                errors.append(f"{scenario_id}:steps[{i}] 分支 {branch.get('id')!r} 非兜底"
                              "但无 contains 触发条件(跟随器永远选不到 = 不可达)")
            if not str(branch.get("student_response") or "").strip():
                errors.append(f"{scenario_id}:steps[{i}] 分支 {branch.get('id')!r}"
                              " student_response 必填")
        if fallbacks != 1:
            errors.append(f"{scenario_id}:steps[{i}] 必须恰一个 fallback 分支,实际 {fallbacks}")
    return errors


def select_branch(branches: list[dict], tutor_text: str) -> dict:
    """分支跟随器(dialogue_scenarios/v2):按导师上一句选学生分支。

    规则:非兜底分支按声明顺序取**首个命中**——`assistant_contains_any` 任一
    子串在导师句中,或 `assistant_contains_all` 全部子串在;全不命中走该步
    唯一的 fallback。纯文本路由,确定性可复算(同句重选同支)。
    # ponytail: interaction_states 非空时视为不命中(内核交互态路由未接线;
    # 本批 60 条全空;真要用时在此接状态源,数据面不动)。"""
    fallback = None
    for branch in branches:
        when = branch.get("when") or {}
        if when.get("fallback"):
            fallback = branch
            continue
        if when.get("interaction_states"):
            continue
        keys_any = when.get("assistant_contains_any") or []
        keys_all = when.get("assistant_contains_all") or []
        if keys_any and any(key in tutor_text for key in keys_any):
            return branch
        if keys_all and all(key in tutor_text for key in keys_all):
            return branch
    if fallback is None:
        raise ValueError("分支剧本缺 fallback 分支(每步必须恰一个兜底)")
    return fallback


def to_kernel_case(scenario: dict) -> dict:
    """场景 → KernelSubject.run_case 入参(gateway 由调用方注入,分层要求:
    edu_agent.evals 不 import tests/,FakeGateway 的构造在测试侧)。

    v2 分支剧本传 steps(学生消息由跟随器逐轮选);其余口径传线性
    student_turns。"""
    case = {
        "id": scenario["id"],
        "question": scenario["question"],
        "grade": scenario.get("grade", ""),
        "answer_status": scenario.get("answer_status", ""),
    }
    if scenario.get("steps"):
        case["steps"] = scenario["steps"]
    else:
        case["student_turns"] = scenario["student_turns"]
    return case


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
