"""S2 专项 Judge 合同(#459 件二):提取等价门、battery 三面守护、schema 双分支、
泄露 sentinel、渲染与 Subject 失败分类、脚本门(P0-6/resume、P0-2/P0-4 模型身份、
GA/GB 判分)——全部走假上游,不调真实模型。

实现审口径:代码逐字执行已批准方案(v0.1.1,#459 评论 5855269212)。本文件同时
是方案机械条款的常驻守护:冻结件漂移/资产漂移/battery 漂移/期望泄露均测试红。
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest
from fake_openai import Reply, completion

import s2_judge_battery  # scripts/(conftest 挂载)
from edu_agent.evals import (
    S2_SCHEMA,
    S2JudgeSubject,
    ResumeMismatch,
    file_sha256,
    git_head_sha,
    head_sha256,
    s2_judge_transcript,
    s2_user_prompt,
)
from edu_agent.gateway import GatewayError
from gwkit import fake_gateway

_REPO = Path(__file__).resolve().parents[2]
_CASES = _REPO / "docs/evals/s2-step3-boundary-cases/CASES.md"
_RUBRIC = _REPO / "docs/evals/s2-judge-rubric-v0.1.md"
_BATTERY = _REPO / "docs/evals/s2-judge-battery-v0.1.jsonl"
_ASSET = _REPO / "edu_agent/evals/rubrics/s2_judge_v0_1.yaml"

FREEZE_SHA = "d415be391f4e5d4a2371f0f188b10f0c073cb0b236e6539069282de6107f04c7"  # rubric v0.3 草案(谱系修正后;冻结行补记后 sha 不变,head -n -1 口径)
GENERIC_TURNBACK = "我们先回到题目本身:你能说说题目给出的条件里,哪一条和这一步有关吗?"
SENTINEL = "__EXPECTED_LEAK_SENTINEL__"
ROLE = {"学生": "user", "Tutor": "assistant"}


def s2_env(tmp_path, replies: list):
    """单 judge 角色(json_strict true,路线 1)指向假上游的假环境(镜像 judge_env)。"""
    return fake_gateway(tmp_path, replies, role_name="judge", provider_json_strict=False,
                         concurrency=2, first_token_timeout_s=2.0, total_timeout_s=5.0)


def axis_payload(verdict="no", turns=(), markers=(), tags=("B-0",),
                 rationale="走查:B-0 仅 A0 基线形态,无 giving。"):
    return {"verdict": verdict, "supporting_turns": list(turns),
            "evidence_tags": list(tags), "boundary_markers": list(markers),
            "rationale": rationale}


def s2_output(s2a=None, s2b=None) -> str:
    payload = {"s2a": s2a or axis_payload(), "s2b": s2b or axis_payload()}
    return json.dumps(payload, ensure_ascii=False)


# ---------- 冻结件与提取等价门(方案 §1;仿 #254 渲染等价门) ----------


def test_frozen_rubric_unchanged():
    """identity 纪律的常驻守护:冻结件被改 → head -n -1 sha 变 → 测试红(v0.2=a17f5b6a…)。"""
    head = "".join(_RUBRIC.read_text(encoding="utf-8").splitlines(keepends=True)[:-1])
    assert hashlib.sha256(head.encode()).hexdigest() == FREEZE_SHA


def test_prompt_asset_extraction_gate():
    """资产 system_prompt 与冻结件 §2 ```text 块逐字节相等(单一事实源在冻结件)。"""
    import yaml

    doc = _RUBRIC.read_text(encoding="utf-8")
    prompt = re.search(r"## 2\. System Prompt 全文.*?\n```text\n(.*?)\n```",
                       doc, re.S).group(1)
    asset = yaml.safe_load(_ASSET.read_text(encoding="utf-8"))
    assert asset["version"] == "s2_judge_v0_3"  # v0.3 资产(+E1/E2 分界、验证问句窄授权)
    assert asset["system_prompt"] == prompt


# ---------- battery 三面守护(方案 §3:CASES.md ↔ jsonl ↔ 件一 §4) ----------


def _family_anchors(text: str) -> dict:
    families = {}
    for m in re.finditer(r"^## \d+\. 锚点 (C\d+)\(.*?\n(.*?)(?=^## |\Z)", text, re.M | re.S):
        quotes = {}
        for q in re.finditer(r"t(\d+) (学生|Tutor)「([^」]+)」", m.group(2)):
            quotes[("t" + q.group(1), q.group(2))] = q.group(3)
        families[m.group(1)] = quotes
    return families


def _resolve(rest: str, turn: str, role_zh: str, fam: str, families) -> str:
    rest = rest.strip()
    if rest.startswith("「"):  # R1 引语(rindex 剥尾注)
        return rest[1:rest.rindex("」")]
    if rest.startswith("(锚案支架逐字:"):  # R4 内联引语
        inner = rest[len("(锚案支架逐字:"):].rstrip()
        assert inner.startswith("「") and inner.endswith("」)"), rest
        return inner[1:-2]
    if rest == "(锚案回应逐字)":  # R3 家族锚案同轮
        return families[fam][(turn, role_zh)]
    if rest in ("(泛化反问句)", "(泛化反问句,逐字)"):  # R2 同句(判据 A-3b)
        return GENERIC_TURNBACK
    raise ValueError(f"R5 不可解引用: {rest}")  # R5:禁编造


def _convert_cases() -> list[dict]:
    """从 #460 冻结 CASES.md 重导 24 案 messages(与落盘 jsonl 的生成同款逻辑)。"""
    text = _CASES.read_text(encoding="utf-8")
    families = _family_anchors(text)
    blocks = re.findall(
        r"^(#{2,4} (C\d+-T\d))[^\n]*\n(.*?)(?=^#{2,4} C\d+-T\d|^## \d+\. |\Z)",
        text, re.M | re.S)
    assert len(blocks) == 24
    rows = []
    for _, cid, body in blocks:
        fam = cid.split("-")[0]
        messages = []
        for t in re.finditer(r"^- t(\d+) (学生|Tutor):(.+)$", body, re.M):
            turn, role_zh = "t" + t.group(1), t.group(2)
            messages.append({"turn": turn, "role": ROLE[role_zh],
                             "content": _resolve(t.group(3), turn, role_zh, fam, families)})
        rows.append({"case_id": cid, "messages": messages})
    return rows


def _parse_axis(cell: str):
    cell = cell.strip()
    if cell == "—":
        return None
    m = re.match(r"^(YES|NO|UNSURE)(?:\s*\+\s*边界([①②④⑤⑥⑦]))?", cell)
    verdict, boundary = m.group(1).lower(), m.group(2)
    rest = cell[m.end():]
    turns, note = [], None
    pm = re.match(r"^\(([^)]*)\)", rest)
    if pm:
        turns = re.findall(r"t\d+", pm.group(1))
        note = rest[pm.end():].strip(" ;") or None
    if verdict == "unsure" and boundary is None and "U-0" in cell:
        boundary = "U-0"
    return {"verdict": verdict, "boundary": boundary, "turns": turns, "note": note}


def test_battery_payload_matches_cases_md():
    """jsonl 的 messages 与 #460 冻结件重导结果逐案相等(R1–R5 全量守护)。"""
    rows = [json.loads(line) for line in
            _BATTERY.read_text(encoding="utf-8").strip().splitlines()]
    derived = _convert_cases()
    assert [r["case_id"] for r in rows] == [r["case_id"] for r in derived]
    assert [{k: r[k] for k in ("case_id", "messages")} for r in rows] == derived
    assert sum(len(r["messages"]) for r in rows) == 87  # 轮形态清点:87 轮全穷尽
    # R2 交叉验证:C13-T1 直接引语 == 同句
    assert rows[0]["case_id"] == "C13-T1"
    assert rows[0]["messages"][1]["content"] == GENERIC_TURNBACK
    # 两种轮编号约定逐字保留:C15-T1 顺序编号(t1 学生/t2 Tutor/t3/t4 学生)
    c15t1 = next(r for r in rows if r["case_id"] == "C15-T1")
    assert [m["turn"] for m in c15t1["messages"]] == ["t1", "t2", "t3", "t4"]
    assert [m["role"] for m in c15t1["messages"]] == ["user", "assistant", "user", "user"]


def test_expected_three_surfaces():
    """件一 §4 表(冻结面)↔ jsonl.expected ↔ CASES.md proposed_expectation 三面一致。

    口径注记:件一 §4 表头声明 37(24 S2a+13 S2b),机械实数 36(23+13——
    C15-T4 的 S2a 未单列);已呈裁,GA 案级分母 24 不受影响;GB 案数随期望动态。
    """
    rows = {json.loads(line)["case_id"]: json.loads(line)
            for line in _BATTERY.read_text(encoding="utf-8").strip().splitlines()}
    table = re.findall(r"^\| (C\d+-T\d) \| (.*?) \| (.*?) \| (.*?) \|$",
                       _RUBRIC.read_text(encoding="utf-8"), re.M)
    assert len(table) == 24 and set(rows) == {c for c, *_ in table}
    for cid, s2a_cell, s2b_cell, _ in table:
        assert rows[cid]["expected"]["s2a"] == _parse_axis(s2a_cell), cid
        assert rows[cid]["expected"]["s2b"] == _parse_axis(s2b_cell), cid
    text = _CASES.read_text(encoding="utf-8")
    n_s2a = n_s2b = 0
    # 逐案全字段核对(verdict+boundary+turns;note 形态自由不比对)——
    # 实现审补口:此前 proposed 侧只核 verdict,轮号与边界未守住
    for m in re.finditer(r"^(#{2,4} (C\d+-T\d))[^\n]*\n(.*?)(?=^#{2,4} C\d+-T\d|^## \d+\. |\Z)",
                         text, re.M | re.S):
        cid, body = m.group(2), m.group(3)
        prop = re.search(r"^proposed_expectation = (.+)$", body, re.M).group(1)
        for display, axis in (("S2a", "s2a"), ("S2b", "s2b")):
            pm = re.search(rf"{display} (YES|NO|UNSURE)(.*?)(?=S2[ab] |$)", prop)
            expected = rows[cid]["expected"][axis]
            if pm is None:
                assert expected is None, f"{cid} {axis}:proposed 未单列,jsonl 却有"
                continue
            verdict, seg = pm.group(1).lower(), pm.group(2)
            bm = re.search(r"边界([①②④⑤⑥⑦])", seg)
            boundary = bm.group(1) if bm else ("U-0" if verdict == "unsure" and "U-0" in seg else None)
            tm = re.search(r"\(([^)]*)\)", seg)  # 段内首个括号组=轮号锚(其后括号均为注)
            turns = re.findall(r"t\d+", tm.group(1)) if tm else []
            assert expected is not None, f"{cid} {axis}:proposed 单列,jsonl 却无"
            assert expected["verdict"] == verdict, f"{cid} {axis} verdict"
            assert expected["boundary"] == boundary, f"{cid} {axis} boundary"
            assert expected["turns"] == turns, f"{cid} {axis} turns"
        n_s2a += 1 if rows[cid]["expected"]["s2a"] else 0
        n_s2b += 1 if rows[cid]["expected"]["s2b"] else 0
    assert (n_s2a, n_s2b) == (23, 13)  # 机械真值 36=23+13(rubric v0.2 已入文;不为凑数补裁)


# ---------- 期望值泄露防火墙(P1-2:sentinel 机械化) ----------


def test_sentinel_expected_never_reaches_model(tmp_path):
    """expected 只属 scorer:含 sentinel 的 expected 绝不进真实请求载荷
    (system+user+路线 1 schema 附言,全线断言)。"""
    case = {"case_id": "sentinel-case",
            "messages": [{"turn": "t1", "role": "user", "content": "我不会这道题。"},
                         {"turn": "t1", "role": "assistant", "content": GENERIC_TURNBACK}],
            "expected": {"s2a": {"verdict": "no", "boundary": None, "turns": [], "note": SENTINEL},
                         "s2b": None}}
    with s2_env(tmp_path, [completion(s2_output())]) as (fake, gateway):
        s2_judge_transcript(gateway, case)
    wire = json.dumps(fake.requests[0]["messages"], ensure_ascii=False)
    assert SENTINEL not in wire
    assert SENTINEL not in json.dumps(S2_SCHEMA, ensure_ascii=False)


# ---------- 渲染与 schema(方案 §1/§2) ----------


def test_user_prompt_renders_turn_labels_verbatim():
    messages = [{"turn": "t2", "role": "assistant", "content": "路线图内容"},
                {"turn": "t3", "role": "user", "content": "先算 120 加 45。"}]
    text = s2_user_prompt(messages)
    assert "【对话记录】" in text
    assert "小讲师(t2):路线图内容" in text and "学生(t3):先算 120 加 45。" in text
    assert "只输出一个符合 Schema 的 JSON 对象" in text


def _validate(payload: dict) -> list:
    import jsonschema

    validator = jsonschema.validators.validator_for(S2_SCHEMA)(S2_SCHEMA)
    return list(validator.iter_errors(payload))


def test_schema_accepts_both_u0_legal_branches():
    """P0-5 冻结「或」语义:unsure 的两合法分支都过,不得收成单支。"""
    base = {"s2a": None, "s2b": None}
    # 分支一:boundary_markers 非空
    p = {**base, "s2a": axis_payload("unsure", markers=["①"], rationale="两读…"),
         "s2b": axis_payload()}
    assert _validate(p) == []
    # 分支二:markers 空,但 rationale 明确含 U-0
    p = {**base, "s2a": axis_payload("unsure", markers=[],
                                     rationale="B-0 两读,属 U-0 未定"),
         "s2b": axis_payload()}
    assert _validate(p) == []


def test_schema_rejects_violations():
    """V1(unsure 无边界证据)/V2/V3/V4/V5/enum 全部由 gateway 路线 1 原生拦截。"""
    bad = {
        "v1_unsure_no_evidence": {"s2a": axis_payload("unsure", markers=[], rationale="两读"),
                                  "s2b": axis_payload()},
        "v2_yes_no_turns": {"s2a": axis_payload("yes", turns=[]), "s2b": axis_payload()},
        "v3_empty_rationale": {"s2a": axis_payload(rationale=""), "s2b": axis_payload()},
        "v4_bad_turn_format": {"s2a": axis_payload("yes", turns=["turn-1"]),
                               "s2b": axis_payload()},
        "v5_missing_axis": {"s2a": axis_payload()},
        "enum_verdict": {"s2a": axis_payload("maybe"), "s2b": axis_payload()},
    }
    for name, payload in bad.items():
        assert _validate(payload), name


# ---------- 全链路(假上游,路线 1) ----------


def test_s2_judge_full_chain(tmp_path):
    payload_s2a = axis_payload("yes", turns=["t1"], tags=["E1", "A-1a", "A-4.1"],
                               rationale="A-1a E1 在案;A-3 无 R1/R2/R3 → A-4.1 YES(t1)。")
    payload_s2b = axis_payload("no", markers=[], tags=["B-0"],
                               rationale="B-0 仅 A0 基线形态 → NO。")
    with s2_env(tmp_path, [completion(s2_output(payload_s2a, payload_s2b))]) as (fake, gateway):
        result = s2_judge_transcript(gateway, {
            "case_id": "C14-T2",
            "messages": [{"turn": "t1", "role": "user", "content": "我卡住了,能先告诉我单位怎么换吗?"},
                         {"turn": "t1", "role": "assistant", "content": "你是怎么想的?"}],
        })
    assert result["s2a"]["verdict"] == "yes" and result["s2a"]["supporting_turns"] == ["t1"]
    assert result["s2b"]["verdict"] == "no"
    assert result["judge_model"] == "fake-model"  # 披露义务:标注与模型绑定落盘


def test_route1_repairs_invalid_output(tmp_path):
    """路线 1:首次不合规 → gateway 带修复提示重试一次(残余语义层=零)。"""
    with s2_env(tmp_path, [
        completion("我不会标注"),
        completion(s2_output()),
    ]) as (fake, gateway):
        result = s2_judge_transcript(gateway, {
            "case_id": "C13-T3",
            "messages": [{"turn": "t1", "role": "user", "content": "能先给个小提示吗?"},
                         {"turn": "t1", "role": "assistant", "content": GENERIC_TURNBACK}],
        })
    assert result["s2a"]["verdict"] == "no"
    assert len(fake.requests) == 2
    assert "JSON Schema" in fake.requests[1]["messages"][-1]["content"]


def test_subject_maps_env_vs_content_failures(tmp_path):
    case = {"case_id": "C24-T2",
            "messages": [{"turn": "t1", "role": "user", "content": "我不知道先算括号还是先除。"}]}
    with s2_env(tmp_path, [Reply(partial_body="{"), Reply(partial_body="{")]) as (fake, gateway):
        with pytest.raises(Exception) as env_exc:
            S2JudgeSubject(gateway).run_case(case)
    from edu_agent.evals import EnvironmentFailure
    assert isinstance(env_exc.value, EnvironmentFailure)
    with s2_env(tmp_path, [completion("垃圾"), completion("还是垃圾")]) as (fake, gateway):
        with pytest.raises(GatewayError):  # schema_violation:内容失败,重跑改变不了
            S2JudgeSubject(gateway).run_case(case)


# ---------- 脚本门(方案 §4/§5;#490 M3:resume 门与模型身份比较已迁公共层) ----------


class _DummyGateway:
    def __init__(self, *args, **kwargs):
        pass

    def close(self):
        pass


def test_resume_refusal_delegates_to_common_strict_gate(tmp_path, monkeypatch):
    """#490 M3:P0-6 门迁公共层——脚本职责收窄为委托(strict_identity=True、
    identity 字段全链不丢)与 ResumeMismatch → CLI 非零退出;门语义本体由
    tests/evals/test_runner.py 的 strict 用例持有。#521 I6-A 起本路径 = 显式
    `--legacy-runner` 回退通道(默认 Inspect,另测)。"""
    assert not hasattr(s2_judge_battery, "_resume_gate")  # 重复机制已删,不复活
    captured = {}

    class SpyRunner:
        def __init__(self, subject, config, runs_root):
            captured["subject"] = subject

        def run(self, dataset_path, cases, run_dir=None, identity=None,
                strict_identity=False):
            captured.update(run_dir=run_dir, identity=identity,
                            strict_identity=strict_identity)
            raise ResumeMismatch("spy:manifest identity 不一致(字段 git_sha 值变)")

    monkeypatch.setattr(s2_judge_battery, "EvalRunner", SpyRunner)
    monkeypatch.setattr(s2_judge_battery, "Gateway", _DummyGateway)
    battery = tmp_path / "battery.jsonl"
    battery.write_text(json.dumps(_row("C13-T1", "no", None)) + "\n", encoding="utf-8")
    resume_dir = tmp_path / "prior-run"
    monkeypatch.setattr(sys, "argv", [
        "s2-judge-battery", "--battery", str(battery),
        "--artifacts-root", str(tmp_path / "art"), "--run-dir", str(resume_dir),
        "--legacy-runner"])
    with pytest.raises(SystemExit, match="resume 拒绝"):
        s2_judge_battery.main()
    assert captured["strict_identity"] is True and captured["run_dir"] == resume_dir
    # identity 字段全链不丢(#459:git/rubric/prompt/battery/models + primary 双字段)
    # + I6-A owner 明示(execution_owner,manifest 落档)
    assert set(captured["identity"]) == {
        "git_sha", "rubric_freeze_sha", "prompt_asset_sha", "battery_sha",
        "models_yaml_sha", "judge_primary_id", "judge_primary_model",
        "execution_owner"}
    assert captured["identity"]["execution_owner"] == "evalrunner_legacy"
    # 指纹口径与公共 helper 一致(#490 M0 表第③项:构造侧唯一实现)
    assert captured["identity"]["git_sha"] == git_head_sha(_REPO)
    assert captured["identity"]["rubric_freeze_sha"] == head_sha256(_RUBRIC)
    assert captured["identity"]["battery_sha"] == file_sha256(battery)


def test_main_completes_when_common_gate_passes(tmp_path, monkeypatch):
    """迁移后主路径:公共门放行(run 正常返回)→ _score/compare_models/_report
    全链不塌,退出 0。#521 I6-A 起本路径 = 显式 `--legacy-runner` 回退通道。"""
    run_dir = tmp_path / "run"
    (run_dir / "results").mkdir(parents=True)
    transcript = {"s2a": axis_payload(), "s2b": axis_payload(),
                  "judge_model": "any-observed-model"}
    (run_dir / "results" / "C13-T1.json").write_text(json.dumps(
        {"case_id": "C13-T1", "status": "ok", "transcript": transcript}),
        encoding="utf-8")

    class SpyRunner:
        def __init__(self, subject, config, runs_root):
            pass

        def run(self, dataset_path, cases, run_dir=None, identity=None,
                strict_identity=False):
            assert strict_identity is True
            return run_dir

    monkeypatch.setattr(s2_judge_battery, "EvalRunner", SpyRunner)
    monkeypatch.setattr(s2_judge_battery, "Gateway", _DummyGateway)
    battery = tmp_path / "battery.jsonl"
    battery.write_text(json.dumps(_row("C13-T1", "no", None)) + "\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "s2-judge-battery", "--battery", str(battery),
        "--artifacts-root", str(tmp_path / "art"), "--run-dir", str(run_dir),
        "--legacy-runner"])
    assert s2_judge_battery.main() == 0
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "GA 案级一致" in report and "1/1" in report  # 唯一 ok 案 verdict 命中


def _row(cid, s2a_verdict, s2b_verdict, s2a_boundary=None, s2b_boundary=None):
    def exp(verdict, boundary):
        if verdict is None:
            return None
        return {"verdict": verdict, "boundary": boundary, "turns": [], "note": None}
    return {"case_id": cid,
            "messages": [{"turn": "t1", "role": "user", "content": "…"}],
            "expected": {"s2a": exp(s2a_verdict, s2a_boundary),
                         "s2b": exp(s2b_verdict, s2b_boundary)}}


def _result(verdict_a="no", verdict_b="no", markers_a=(), markers_b=(),
            rationale_a="…", rationale_b="…"):
    return {"status": "ok", "transcript": {
        "s2a": axis_payload(verdict_a, markers=markers_a, rationale=rationale_a),
        "s2b": axis_payload(verdict_b, markers=markers_b, rationale=rationale_b),
        "judge_model": "primary-name"}}


def _result_model(result: dict, model: str) -> dict:
    """改写 judge_model(fallback 反例用),避免 _result 第七形参。"""
    return {**result, "transcript": {**result["transcript"], "judge_model": model}}


def test_score_model_identity_gate():
    """P0-2/P0-4:judge_model 同值且 == judge_primary_model;fallback/异值 → 作废。"""
    rows = [_row("C13-T1", "no", None)]
    ok = s2_judge_battery._score(
        rows, {"C13-T1": _result()}, {"judge_primary_model": "primary-name"})
    assert ok["model_valid"] is True
    void = s2_judge_battery._score(
        rows, {"C13-T1": _result_model(_result(), "fallback-name")},
        {"judge_primary_model": "primary-name"})
    assert void["model_valid"] is False


def test_model_mismatch_marks_round_void_in_report(tmp_path):
    """#490 M3 迁移证明:模型比较走公共 compare_models 后,整轮 VOID/不计算 GA/GB
    的领域处置仍由 S2 报告面持有(语义保持;公共层不输出裁决词)。"""
    rows = [_row("C13-T1", "no", None)]
    identity = {"git_sha": "g" * 40, "rubric_freeze_sha": "r" * 64,
                "prompt_asset_sha": "p" * 64, "battery_sha": "b" * 64,
                "models_yaml_sha": "m" * 64, "judge_primary_id": "judge",
                "judge_primary_model": "primary-name"}
    void = s2_judge_battery._score(
        rows, {"C13-T1": _result_model(_result(), "fallback-name")}, identity)
    report = s2_judge_battery._report(tmp_path, void, identity)
    text = report.read_text(encoding="utf-8")
    assert "**作废(VOID)**" in text and "不计算 GA/GB" in text


def test_score_ga_and_gb():
    """GA=案级全显式轴命中;GB:①/④/② marker 词级 + U-0 marker/rationale 二选一。"""
    rows = [_row("C13-T1", "unsure", None, s2a_boundary="①"),
            _row("C24-T2", "unsure", None, s2a_boundary="④"),
            _row("C15-T4", None, "unsure", s2b_boundary="②"),
            _row("C23-T3", None, "unsure", s2b_boundary="U-0")]
    results = {
        "C13-T1": _result(verdict_a="unsure", markers_a=["①"]),
        "C24-T2": _result(verdict_a="unsure", markers_a=["④"]),
        "C15-T4": _result(verdict_b="unsure", markers_b=["②"]),
        # U-0 经 rationale 分支命中(P0-5 二选一);s2a 未单列 → 案级 ✓
        "C23-T3": _result(verdict_b="unsure", markers_b=[], rationale_b="B-0 两读,属 U-0"),
    }
    scored = s2_judge_battery._score(rows, results, {"judge_primary_model": "primary-name"})
    assert scored["ga"] == 4 and scored["gb_pass"] is True
    assert len(scored["misses"]) == 0
    # D2 诊断:4 显式轴全精确匹配(expected turns=[]/actual=[])
    assert (scored["turns_match"], scored["turns_total"]) == (4, 4)
    # GB 分母动态(review 5332914680):命中数/len(gb_cases),非硬编码 4/4
    assert (sum(1 for *_, ok in scored["gb_cases"] if ok),
            len(scored["gb_cases"])) == (4, 4)
    # 反例:verdict 同为 unsure 但边界证据未命中(错误规则猜出的 unsure)——
    # GA 不动(verdict 词级),GB 拦下;且 GB-only miss 必须进归因输入(kind=boundary)
    bad = s2_judge_battery._score(
        rows, {**results, "C13-T1": _result(verdict_a="unsure", markers_a=["②"])},
        {"judge_primary_model": "primary-name"})
    assert bad["gb_pass"] is False and bad["ga"] == 4
    assert [m["kind"] for m in bad["misses"]] == ["boundary"]
    # GB 三案分母形态(v0.3 真实形态:unsure 期望=3):三案两中 → 报告 2/3,fail
    three = [_row("C13-T1", "unsure", None, s2a_boundary="①"),
             _row("C24-T2", "unsure", None, s2a_boundary="④"),
             _row("C23-T3", None, "unsure", s2b_boundary="U-0")]
    res3 = {"C13-T1": _result(verdict_a="unsure", markers_a=["①"]),
            "C24-T2": _result(verdict_a="unsure", markers_a=["④"]),
            "C23-T3": _result(verdict_b="no", markers_b=[])}
    s3 = s2_judge_battery._score(three, res3, {"judge_primary_model": "primary-name"})
    assert len(s3["gb_cases"]) == 3 and s3["gb_pass"] is False
    assert sum(1 for *_, ok in s3["gb_cases"] if ok) == 2
    # turns 诊断反例:命中案 turns 不一致只记诊断不进 miss/GA
    off = s2_judge_battery._score(
        rows, {**results, "C13-T1": _result(verdict_a="unsure", markers_a=["①"],
                                            rationale_a="两读,属 U-0 形态以外的边界①")},
        {"judge_primary_model": "primary-name"})
    assert off["ga"] == 4 and off["turns_match"] == 4  # expected=[] 恒匹配;见下条真失配
    # 真失配:yes 轴给出多余轮号 → 诊断计数下降,miss 清单不动
    yes_row = [_row("C14-T2", "yes", None)]
    yes_row[0]["expected"]["s2a"]["turns"] = ["t1"]
    r = s2_judge_battery._score(
        yes_row, {"C14-T2": _result(verdict_a="yes")}, {"judge_primary_model": "primary-name"})
    assert r["turns_match"] == 0 and r["turns_total"] == 1
    assert r["misses"] == [] and r["ga"] == 1


def test_gb_requires_unsure_verdict_and_evidence():
    """GB 钉死定义(P0):verdict=unsure ∧ 边界证据,缺一不过门——
    yes 带正确 marker 只算 verdict miss,GB 仍 fail。"""
    rows = [_row("C13-T1", "unsure", None, s2a_boundary="①")]
    scored = s2_judge_battery._score(
        rows, {"C13-T1": _result(verdict_a="yes", markers_a=["①"])},
        {"judge_primary_model": "primary-name"})
    assert scored["gb_pass"] is False
    assert [m["kind"] for m in scored["misses"]] == ["verdict"]  # 无 boundary miss(证据未参与)
    # unsure ∧ 证据命中 → 过;unsure ∧ 证据错 → 不过;yes ∧ 证据对 → 不过
    ok = s2_judge_battery._score(
        rows, {"C13-T1": _result(verdict_a="unsure", markers_a=["①"])},
        {"judge_primary_model": "primary-name"})
    assert ok["gb_pass"] is True


def test_turns_exact_match_is_order_sensitive():
    """D2 收紧:精确匹配 = 列表相等;[t3,t2] 对期望 [t2,t3] 不算命中。"""
    row = _row("C14-T2", "yes", None)
    row["expected"]["s2a"]["turns"] = ["t2", "t3"]
    reversed_actual = _result(verdict_a="yes")
    reversed_actual["transcript"]["s2a"]["supporting_turns"] = ["t3", "t2"]
    scored = s2_judge_battery._score(
        [row], {"C14-T2": reversed_actual}, {"judge_primary_model": "primary-name"})
    assert scored["ga"] == 1 and scored["turns_match"] == 0  # GA 不动,诊断失配
    assert scored["misses"] == []


def test_boundary_evidence_u0_dual_path():
    expected_u0 = {"boundary": "U-0"}
    assert s2_judge_battery._boundary_evidence(expected_u0, {
        "boundary_markers": ["U-0"], "rationale": "…"}) is True
    assert s2_judge_battery._boundary_evidence(expected_u0, {
        "boundary_markers": [], "rationale": "属 U-0 两读"}) is True
    assert s2_judge_battery._boundary_evidence(expected_u0, {
        "boundary_markers": [], "rationale": "判不了"}) is False
    assert s2_judge_battery._boundary_evidence({"boundary": "①"}, {
        "boundary_markers": ["②"], "rationale": "① 两读"}) is False  # ①/④/② 只认 marker
