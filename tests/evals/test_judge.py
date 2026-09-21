"""judge 评分器合同(#32 定稿):六维 schema、阈值 verdict、路线 1 修复、稳定性档案。

走假上游(FakeOpenAI),不调真实模型;维度与分值结构照 #32 原文,不发明维度。
"""

from __future__ import annotations

import json

import pytest
from fake_openai import Reply, completion

from edu_agent.evals import (
    DIMENSIONS,
    SCHEMA,
    EnvironmentFailure,
    JudgeSubject,
    judge_transcript,
    sample_independent,
    stability_report,
    user_prompt,
    verdict_from_scores,
)
from edu_agent.gateway import GatewayError
from gwkit import fake_gateway


def judge_env(tmp_path, replies: list):
    """单 judge 角色(json_strict true,路线 1)指向假上游的假环境。"""
    return fake_gateway(tmp_path, replies, role_name="judge", provider_json_strict=False,
                         concurrency=2, first_token_timeout_s=2.0, total_timeout_s=5.0)


CASE = {
    "id": "case-1",
    "question": "一盒有 8 支铅笔,3 盒一共有多少支?",
    "grade": "二年级",
    "reference_answer": "24 支",
    "messages": [
        {"role": "user", "content": "一盒有 8 支铅笔,3 盒一共有多少支?"},
        {"role": "assistant", "content": "你已经知道一盒有几支了,那两盒是多少呢?"},
        {"role": "user", "content": "两盒是 16 支。"},
        {"role": "assistant", "content": "很好!那再加一盒呢?你是怎么算的?"},
        {"role": "user", "content": "16 加 8 等于 24 支!"},
        {"role": "assistant", "content": "对,你用乘法 8×3 也能得到 24。你已经掌握乘法意义,注意别把乘法当成重复加法数手指。"},
    ],
}


def model_output(scores: list[int], leaked: bool = False, verdict: str = "pass",
                  math_integrity: int = 2) -> str:
    payload = dict(zip(DIMENSIONS, scores, strict=True))
    payload["answer_leaked"] = leaked
    payload["math_integrity"] = math_integrity
    evidence = {dim: f"「{dim}」的对话依据" for dim in DIMENSIONS}
    evidence["math_integrity"] = f"math_integrity={math_integrity} 的对话依据"
    evidence["answer_leaked"] = f"泄露={leaked} 的判定依据原句"  # #253 v3:evidence 增键
    payload["evidence"] = evidence
    payload["verdict"] = verdict
    return json.dumps(payload, ensure_ascii=False)


# ---------- verdict 阈值(#32 定稿,本地重算) ----------


def test_verdict_veto_beats_total():
    assert verdict_from_scores({d: 2 for d in DIMENSIONS}, answer_leaked=True, math_integrity=2) == "fail"


def test_verdict_thresholds():
    high = {d: 2 for d in DIMENSIONS}  # 12 分无 0 分
    assert verdict_from_scores(high, False, math_integrity=2) == "pass"
    ten = {**{d: 2 for d in DIMENSIONS[:4]}, **{d: 1 for d in DIMENSIONS[4:]}}  # 10 分无 0 分
    assert verdict_from_scores(ten, False, math_integrity=2) == "pass"
    ten_with_zero = {**{d: 2 for d in DIMENSIONS[:5]}, DIMENSIONS[5]: 0}  # 10 分但有 0 分维度
    assert verdict_from_scores(ten_with_zero, False, math_integrity=2) == "review"
    seven = {**{d: 1 for d in DIMENSIONS[:2]}, **{d: 1 for d in DIMENSIONS[2:]}}  # 6 分
    assert verdict_from_scores(seven, False, math_integrity=2) == "fail"
    nine = {**{d: 2 for d in DIMENSIONS[:3]}, **{d: 1 for d in DIMENSIONS[3:]}}  # 9 分
    assert verdict_from_scores(nine, False, math_integrity=2) == "review"


# ---------- prompt 组装与 schema(#32 骨架) ----------


def test_user_prompt_carries_case_and_transcript():
    text = user_prompt(CASE["question"], CASE["grade"], CASE["reference_answer"], CASE["messages"])
    assert "一盒有 8 支铅笔" in text and "二年级" in text
    assert "24 支" in text and "仅用于判断是否泄露" in text
    assert "学生:一盒有 8 支铅笔" in text and "小讲师:你已经知道一盒" in text
    for dim in DIMENSIONS:  # system 侧六维定义完整
        assert dim in SCHEMA["properties"]


# ---------- 全链路(假上游,路线 1) ----------


def test_judge_scores_and_local_verdict_recompute(tmp_path):
    """模型输出的 verdict 字段不作数:本地按 #32 阈值重算(模型给了 pass,分数只有 6)。"""
    with judge_env(tmp_path, [completion(model_output([1, 1, 1, 1, 1, 1], verdict="pass"))]) as (fake, gateway):
        result = judge_transcript(gateway, CASE)
    assert result["scores"] == dict(zip(DIMENSIONS, [1, 1, 1, 1, 1, 1], strict=True))
    assert result["total"] == 6
    assert result["verdict"] == "fail"  # 本地重算覆盖模型的 pass
    assert result["answer_leaked"] is False
    assert result["math_integrity"] == 2  # #253:独立硬门字段随 artifact 落盘
    assert result["judge_model"] == "fake-model"  # 披露义务:模型随分数落盘


def test_judge_route1_repairs_invalid_output(tmp_path):
    """路线 1:首次输出不合规 → gateway 带修复提示重试一次(#32/#8)。"""
    with judge_env(tmp_path, [
        completion("我不会评分"),
        completion(model_output([2, 2, 2, 2, 2, 2])),
    ]) as (fake, gateway):
        result = judge_transcript(gateway, CASE)
    assert result["verdict"] == "pass" and result["total"] == 12
    assert len(fake.requests) == 2
    assert "JSON Schema" in fake.requests[1]["messages"][-1]["content"]  # 修复提示带 schema


def test_judge_full_chain_parses_fenced_model_output(tmp_path):
    """#54 PM 规格·judge 全链路集成:假上游返回带 Markdown 围栏的评分 JSON →
    gateway 校验剥壳且 text 归一(校验与消费同源)→ judge 直接解析出六维,
    无 JSONDecodeError——DeepSeek 独立评分通道(恒带围栏)的阻塞解除实证。"""
    fenced = "```json\n" + model_output([1, 2, 2, 1, 2, 1], verdict="pass") + "\n```"
    with judge_env(tmp_path, [completion(fenced)]) as (fake, gateway):
        result = judge_transcript(gateway, CASE)
    assert result["scores"] == dict(zip(DIMENSIONS, [1, 2, 2, 1, 2, 1], strict=True))
    assert result["total"] == 9
    assert result["verdict"] == "review"  # 9 分 → 本地重算(PM:算术不托付模型)
    assert result["judge_model"] == "fake-model"


def test_judge_subject_maps_env_vs_content_failures(tmp_path):
    """环境类(connection 等)→ EnvironmentFailure 可补跑;内容类(schema_violation)原样抛。"""
    with judge_env(tmp_path, [Reply(partial_body="{"), Reply(partial_body="{")]) as (fake, gateway):
        with pytest.raises(EnvironmentFailure):
            JudgeSubject(gateway).run_case(CASE)

    with judge_env(tmp_path, [completion("不会"), completion("还是不会")]) as (fake, gateway):
        with pytest.raises(GatewayError):
            JudgeSubject(gateway).run_case(CASE)


# ---------- 稳定性档案(#32:双评 + 10% 独立抽样) ----------


def test_sample_independent_is_deterministic_tenth():
    ids = [f"c-{i:02d}" for i in range(20)]
    assert sample_independent(ids) == ["c-00", "c-10"]
    assert sample_independent(ids) == sample_independent(ids)


def _row(case_id: str, total: int, verdict: str = "pass") -> dict:
    scores = {d: min(2, max(0, round(total / 6))) for d in DIMENSIONS}
    return {"case_id": case_id, "status": "ok", "transcript": {"total": total, "verdict": verdict, "scores": scores}}


def test_stability_report_diffs_and_flips():
    primary = [_row("a", 12, "pass"), _row("b", 10, "pass"), _row("c", 6, "fail")]
    repeat = [_row("a", 10, "pass"), _row("b", 7, "review"), _row("c", 6, "fail")]
    independent = [_row("a", 8, "review")]  # 抽样只含 a
    report = stability_report(primary, repeat, independent)
    assert report["double"]["cases"] == 3
    assert report["double"]["max_abs_total_diff"] == 3  # |10-7|
    assert report["double"]["verdict_flips"] == 1  # b: pass→review
    assert report["independent"]["sampled"] == 1
    assert report["independent"]["ids"] == ["a"]
    assert report["independent"]["signed_total_diffs"] == {"a": 4}  # 12-8,主选偏高
    assert report["independent"]["same_direction"] is True
    assert report["independent"]["disagreement_ids"] == ["a"]  # a: verdict 翻转 pass→review


def test_stability_report_hard_gate_disagreement_escalates():
    """标定卡口④:主选与独立 judge 的 verdict 翻转或硬门字段(answer_leaked/
    math_integrity)不一致即入 disagreement_ids;总分一致不触发(二元翻转判据)。"""
    def row(case_id: str, verdict: str = "pass", *, leaked: bool = False,
            math: int = 2, total: int = 12) -> dict:
        scores = {d: 2 for d in DIMENSIONS}
        return {"case_id": case_id, "status": "ok", "transcript": {
            "total": total, "verdict": verdict, "scores": scores,
            "answer_leaked": leaked, "math_integrity": math}}

    primary = [row("same"), row("leak-flip"), row("verdict-flip"), row("math-flip")]
    # same:字段全一致;leak-flip:answer_leaked 翻转;verdict-flip:verdict 翻转;
    # math-flip:math_integrity 翻转(总分均一致——硬门分歧与总分无关)
    independent = [row("same"), row("leak-flip", leaked=True),
                   row("verdict-flip", "review"), row("math-flip", math=1)]
    report = stability_report(primary, repeat=[], independent=independent)
    assert report["independent"]["disagreement_ids"] == [
        "leak-flip", "math-flip", "verdict-flip"]  # sorted;same 不入列


# ---------- #253 rubric v2:math_integrity 硬门 + P1 泄露边界 ----------


def test_math_integrity_zero_fails_even_perfect_six_dims():
    """12/12 六维 + math_integrity=0 → fail(独立硬门,不看总分)。"""
    assert verdict_from_scores({d: 2 for d in DIMENSIONS}, False, math_integrity=0) == "fail"


def test_math_integrity_one_caps_pass_at_review():
    """六维 pass + math_integrity=1 → review(封顶);=2 时不受影响。"""
    assert verdict_from_scores({d: 2 for d in DIMENSIONS}, False, math_integrity=1) == "review"
    assert verdict_from_scores({d: 2 for d in DIMENSIONS}, False, math_integrity=2) == "pass"


def test_verdict_from_scores_requires_math_integrity():
    """漏传 math_integrity → TypeError(fail-closed,无默认值,禁止静默当 2)。"""
    with pytest.raises(TypeError):
        verdict_from_scores({d: 2 for d in DIMENSIONS}, False)


def test_p1_wrong_candidate_grants_no_leak_exemption():
    """#253 P1 边界:学生先给错误候选(「是不是 1.10?」)→ 导师首给正确终答
    (「不是,是 1.20」)不豁免——判据文本进 judge 输入 + 泄露即 fail 双侧钉死。"""
    dialogue = [
        {"role": "user", "content": "我算到最后一步了,是不是 1.10?"},
        {"role": "assistant", "content": "不是,是 1.20。"},
    ]
    prompt = user_prompt("一个笔记本 0.30 元,4 个一共多少元?", "三年级", "1.20 元", dialogue)
    # 判据文本(错误候选不豁免 + 疑问式候选不误杀)必须进 judge 的输入面
    assert "若学生先给出的只是错误候选答案" in prompt
    assert "疑问形式候选答案" in prompt
    # system 面一票否决条款同样重写到位
    from edu_agent.evals import DIMENSION_GUIDE
    assert "**学生只提出了错误候选答案,并不会因此获得正确终答的豁免**" in DIMENSION_GUIDE
    # 判定面:judge 按 rubric 判出 answer_leaked=true 时,verdict 必须 fail(与六维分/硬门分无关)
    assert verdict_from_scores({d: 2 for d in DIMENSIONS}, True, math_integrity=2) == "fail"


def test_judge_transcript_parses_and_gates_math_integrity(tmp_path):
    """全链路:模型给 math_integrity=0 → 本地重算 verdict=fail(模型自称 pass 不作数)。"""
    with judge_env(tmp_path, [completion(model_output([2, 2, 2, 2, 2, 2],
                                                     verdict="pass", math_integrity=0))]) as (fake, gateway):
        result = judge_transcript(gateway, CASE)
    assert result["math_integrity"] == 0
    assert result["verdict"] == "fail"  # 12/12 + 硬门 0 → fail
