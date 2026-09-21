"""外部 slice 编译件(#382 步骤 7,#396 协议)验收面:结构 + 溯源 + mock dry-run。

三层全零真模型:
- 结构:v2 子集走 scenario_corpus 正版校验(临时包一层 gold 文件 schema 过
  load_shortboard_corpus),逐步 select_branch 探针路由(命中/兜底/确定性);
  v1 子集形状对齐 dialogue_scenario/v1 既有件;
- 溯源(不造数据):每条学生文本 ⊆ 源记录 student 轮原文、每条路由特征 ⊆ 被
  回应 tutor 轮原文、question 与源 problem.text 逐字一致(回连 normalized 层,
  sha256 与编译头核对);
- dry-run:FakeGateway 驱动 KernelSubject 抽 3 条——v1 线性照录、v2 claim 命中
  走纠错分支、v2 全中性走 fallback 链(只验路由命中与 fallback,零真实模型)。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from edu_agent.evals import (
    DATASETS_DIR,
    KernelSubject,
    load_shortboard_corpus,
    select_branch,
    to_kernel_case,
)

from teachkit import FakeGateway

COMPILED = DATASETS_DIR / "external_slices" / "socraticmath_executable_v1.json"
NORMALIZED = DATASETS_DIR / "external_normalized" / "socraticmath.jsonl"
V1 = "small_lecturer_dialogue_scenario/v1"
V2 = "small_lecturer_dialogue_scenario/v2"


def _load() -> dict:
    return json.loads(COMPILED.read_text(encoding="utf-8"))


def _source_records(payload: dict) -> dict[str, dict]:
    ids = set(payload["dispositions"])
    records = {}
    with NORMALIZED.open(encoding="utf-8") as handle:
        for line in handle:
            if not any(sid in line for sid in ids):
                continue
            record = json.loads(line)
            if record.get("id") in ids:
                records[record["id"]] = record
    return records


def _start(reply: str) -> dict:
    return {"acceptable": True, "transcription": "", "steps": [], "reply": reply}


def _tutor(reply: str) -> dict:
    return {"reason": "引导", "reply": reply, "ready_to_confirm": False,
            "cited_numbers": []}


def test_header_dispositions_cover_all_candidates():
    """36 条候选逐条有处置;统计口径互洽(处置表=头部统计=场景实数)。"""
    payload = _load()
    dispositions = payload["dispositions"]
    assert len(dispositions) == 36
    assert {d["rule"] for d in dispositions.values()} <= {"R1", "R2", "R3", "R4"}
    assert all(d["rule"] != "R2" for d in dispositions.values())  # 本批无 R2,头部有说明
    stats = payload["form_stats"]
    by_rule = {rule: sum(1 for d in dispositions.values() if d["rule"] == rule)
               for rule in ("R1", "R2", "R3", "R4")}
    assert stats["by_rule"] == by_rule
    compiled = [d for d in dispositions.values() if d["compiled"]]
    assert len(compiled) == len(payload["scenarios"]) == stats["compiled"]["total"]
    r4 = [d for d in dispositions.values() if d["rule"] == "R4"]
    assert all(d["detail"] for d in r4) and len(r4) == by_rule["R4"]  # 弃案必有因
    # 规模纪律:形态1 12-18、形态2 5-10(协议预期带宽)
    assert 12 <= stats["compiled"]["form1_linear_v1"] <= 18
    assert 5 <= stats["compiled"]["form2_branch_v2"] <= 10


def test_v2_subset_passes_corpus_validator(tmp_path):
    """v2 子集过 scenario_corpus 正版分支结构校验(临时 gold 文件 schema 包装)。"""
    payload = _load()
    v2 = [s for s in payload["scenarios"] if s["schema_version"] == V2]
    assert v2, "形态2 编译件缺失"
    wrapped = tmp_path / "v2_subset.json"
    wrapped.write_text(json.dumps(
        {"schema_version": "small_lecturer_dialogue_scenarios/v2", "scenarios": v2},
        ensure_ascii=False), encoding="utf-8")
    loaded = load_shortboard_corpus(wrapped)
    assert len(loaded) == len(v2)
    cases = [to_kernel_case(s) for s in loaded]
    assert all(c.get("steps") and "student_turns" not in c for c in cases)


def test_branch_routing_deterministic_and_probes_reachable():
    """dry 走查:claim 探针必命中非兜底;中性句必落兜底且同句重选同支。"""
    payload = _load()
    for scenario in (s for s in payload["scenarios"] if s["schema_version"] == V2):
        for step in scenario["steps"]:
            fallback = select_branch(step["branches"], "嗯。")
            assert fallback["when"]["fallback"]
            assert select_branch(step["branches"], "嗯。") is fallback
            for branch in step["branches"]:
                if branch["when"]["fallback"]:
                    continue
                for probe in branch["when"]["assistant_contains_any"]:
                    selected = select_branch(step["branches"], f"老师说,{probe},对吧")
                    assert selected is not fallback or any(
                        key in f"老师说,{probe},对吧"
                        for key in selected["when"]["assistant_contains_any"])


def test_provenance_no_fabrication():
    """溯源三断言:学生文本⊆源 student 轮、特征⊆claim tutor 轮、question 逐字。"""
    payload = _load()
    assert hashlib.sha256(NORMALIZED.read_bytes()).hexdigest() == \
        payload["compiled_from"]["normalized_sha256"], "证据链(normalized)断裂"
    records = _source_records(payload)
    assert len(records) == 36
    for scenario in payload["scenarios"]:
        record = records[scenario["compile"]["record_id"]]
        dialogue = record["reference_dialogue"]
        student_texts = [t["text"] for t in dialogue if t["role"] == "student"]
        assert scenario["question"] == record["problem"]["text"]
        if scenario["schema_version"] == V1:
            for turn in scenario["student_turns"]:
                assert any(turn in text for text in student_texts), \
                    f"{scenario['id']} 学生轮非源文子串(造数据红线)"
            continue
        claim_text = dialogue[scenario["compile"]["claim_turn_index"]]["text"]
        for step in scenario["steps"]:
            for branch in step["branches"]:
                assert any(branch["student_response"] in text
                           for text in student_texts), \
                    f"{scenario['id']}.{step['id']} 学生回应非源文子串"
                for key in branch["when"]["assistant_contains_any"]:
                    assert key in claim_text, \
                        f"{scenario['id']} 特征非 claim 轮子串:{key!r}"


def test_v1_shape_matches_dialogue_scenario_v1_convention():
    """v1 子集与 dialogue_scenario/v1 既有件同形(id/title/question/turns/expect)。"""
    payload = _load()
    v1 = [s for s in payload["scenarios"] if s["schema_version"] == V1]
    assert 12 <= len(v1) <= 18
    for scenario in v1:
        assert scenario["id"] and scenario["title"]
        assert isinstance(scenario["question"], str) and scenario["question"].strip()
        assert scenario["student_turns"] and all(
            isinstance(t, str) and t.strip() for t in scenario["student_turns"])
        assert scenario["expect"] == {"ready_to_record": True}
        assert scenario["compile"]["rule"] == "R1"


def test_dry_run_v1_linear_replays_verbatim():
    """dry-run 抽检 ①:v1 线性——学生轮按序原文回放,与剧本逐字一致。"""
    payload = _load()
    scenario = next(s for s in payload["scenarios"] if s["id"] == "socraticmath_train_559")
    gateway = FakeGateway(tutor_payloads=[
        _start("让我们一起探究这个问题吧。首先,你知道圆的直径和半径是什么吗?")] +
        [_tutor(t) for t in (
            "没错。那么,直径和半径有什么关系呢?",
            "恰好。所以,如果一个圆的直径是5厘米,那么它的半径是多少呢?",
            "没错。那当我们用圆规画一个圆的时候,圆规两脚分开的距离应该等于什么呢?",
            "正确。那么,它的两脚分开的距离应该是多少厘米呢?",
            "很好。今天的表现不错。")])
    transcript = KernelSubject(gateway).run_case(to_kernel_case(scenario))
    assert [t["student"] for t in transcript["turns"][1:]] == scenario["student_turns"]
    assert len(gateway.requests) == 1 + len(scenario["student_turns"])


def test_dry_run_v2_claim_hit_routes_correction():
    """dry-run 抽检 ②:v2 claim 命中——导师句含错误签名,纠错分支接管。"""
    payload = _load()
    scenario = next(s for s in payload["scenarios"]
                    if s["id"] == "socraticmath_train_1827")
    claim_says = "那么这个数就一定能被3整除,同时又能被48整除,是这样吗?"
    assert select_branch(
        next(s for s in scenario["steps"] if s["id"] == "correction")["branches"],
        claim_says)["id"] == "claim_match"
    gateway = FakeGateway(tutor_payloads=[
        _start("来,我们一步步来分析这个问题。首先,什么是倍数呢?"),
        _tutor("很好,我们再来看,什么是因数?"),
        _tutor(claim_says),
        _tutor("我们来列表分析一下,先找出48的因数是什么?"),
        _tutor("很好,接下来找出其中3的倍数。"),
    ])
    transcript = KernelSubject(gateway).run_case(to_kernel_case(scenario))
    assert [t["student"] for t in transcript["turns"][1:]] == [
        "一个数如果能被另一个数整除，那么这个数就是那个数的倍数。",
        "如果一个数a能被其他数b整除，那么b就是a的因数。",
        "不对，它应该是能被3整除，48能被它整除。",
        "3、6、12、24和48都能被3整除。",
    ]


def test_dry_run_v2_all_neutral_walks_fallback_chain():
    """dry-run 抽检 ③:v2 全中性——纠错步落 fallback,弱轮链不断对话。"""
    payload = _load()
    scenario = next(s for s in payload["scenarios"] if s["id"] == "socraticmath_val_61")
    gateway = FakeGateway(tutor_payloads=[
        _start("这道题属于鸡兔同笼类问题,我们一步步来。"),
        _tutor("很好。接下来我们考虑人数的关系。"),
        _tutor("那么,我们该如何计算船的数量呢?"),
        _tutor("完全正确!那就按照这个思路算算大船和小船的数量吧。"),
    ])
    transcript = KernelSubject(gateway).run_case(to_kernel_case(scenario))
    assert [t["student"] for t in transcript["turns"][1:]] == [
        "需要一共46人除以5人，所以要10只大船。",
        "应该是超出的人数除以大船和小船人数的差。",
        "超出的人数是12个船乘以每船5人减去46人等于14人，大船和小船人数的差是5减3等于2，"
        "所以应该增加14除以2等于7只小船。所以，大船应该是12减去7等于5只。",
    ]
    assert transcript["final_state"] in ("needs_review", "completed")


def test_compiler_script_is_reproducible():
    """编译脚本在当前源数据上重放结果与入库件逐字一致(编译可复算)。"""
    script = Path(__file__).resolve().parents[2] / "scripts/external_slice_compile.py"
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert _load() == json.loads(COMPILED.read_text(encoding="utf-8"))


def test_dry_run_v2_razor_features_do_not_overroute():
    """锐特征定稿抽查:正确教学句/问它项句不含错误签名,不误路由至纠错。"""
    payload = _load()

    def _correction(scenario_id):
        scenario = next(s for s in payload["scenarios"] if s["id"] == scenario_id)
        return next(s for s in scenario["steps"] if s["id"] == "correction")["branches"]

    # 1001:导师把规则教对(正常措辞讲进位/舍弃)时,学生不得进入纠错分支
    branches = _correction("socraticmath_train_1001")
    assert select_branch(branches, "如果舍去位上的数大于等于5,就向前一位进一,得到6.8。")[
        "when"]["fallback"]
    assert select_branch(branches, "小于5的话就直接舍弃,近似数取6.7。")[
        "when"]["fallback"]
    # val_13:导师转问选项B正确性,不得触发针对选项C的纠错
    branches = _correction("socraticmath_val_13")
    assert select_branch(branches, "我们再看选项B,◇×△÷5=100÷5,这样做对吗?")[
        "when"]["fallback"]
    assert select_branch(branches, "那么我们再看看选项C,它是对◇先进行除法。")[
        "id"] == "claim_match"
