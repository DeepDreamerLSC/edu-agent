"""Baseline Anchored Dimension Isolation v0.1 primitive 合同测试(#535)。

确定性、零真实模型调用:活评面走 FakeOpenAI 假上游(gwkit.fake_gateway),
其余面(冻结/装载/组装/flag)纯本地。覆盖六件:
1) registry 与 #535 裁定一致(八字段归属 + 头注释约束来源);
2) 工具锁定集由 registry 驱动,不硬编码(翻转 pacing → 锁定集随动,组装随动);
3) 逐案 anchored locked == baseline;组装键集 = 生产六维;verdict 由生产
   verdict_from_scores 重算(测试独立重算比对);
4) flag iff challenge:活评 locked-view 与 baseline 有张力才有 flag,零静默;
5) baseline 篡改 fail-closed(sidecar sha 不符/缺 sidecar/registry 漂移 → 非零退出);
6) 预算闸 fail-closed;CLI 显式 --cycle-id 才运行(anchored 非默认路径)。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from fake_openai import completion

from edu_agent.evals import DIMENSIONS, verdict_from_scores
from gwkit import fake_gateway

import anchored_calibration as ac  # scripts/(conftest 挂载)

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "anchored_calibration.py"
REGISTRY = REPO / "edu_agent" / "evals" / "rubrics" / "dimension-ownership.yaml"
LOCKED_BASELINE = ("first_question", "socratic_followup", "grade_fit")
ALLOWED = ("pacing", "summary_mastery", "termination")


# ---------- 构造工具(全部离线) ----------


def judge_row(case_id: str, scores: list[int], leaked: bool = False,
              math_integrity: int = 2, verdict: str = "fail") -> dict:
    """冻结 judge 行(baseline 锁定值的来源,零调用)。"""
    return {"case_id": case_id, "scores": dict(zip(DIMENSIONS, scores, strict=True)),
            "answer_leaked": leaked, "math_integrity": math_integrity,
            "total": sum(scores), "verdict": verdict, "judge_model": "fake-judge",
            "judge_input_sha256": "ab" * 32}


def judge_reply(scores: list[int], leaked: bool = False, math_integrity: int = 2):
    """活评 judge 输出(生产 SCHEMA 形态;verdict 字段故意错,本地重算不作数)。"""
    payload = dict(zip(DIMENSIONS, scores, strict=True))
    payload["answer_leaked"] = leaked
    payload["math_integrity"] = math_integrity
    payload["evidence"] = {**{d: f"{d} 对话依据" for d in DIMENSIONS},
                           "math_integrity": "mi 依据", "answer_leaked": "泄露判定原句"}
    payload["verdict"] = "pass"
    return completion(json.dumps(payload, ensure_ascii=False))


def live_case(case_id: str) -> dict:
    return {"case_id": case_id, "question": "3/4 加 1/4 等于多少?",
            "grade": "四年级", "reference_answer": "1",
            "messages": [{"role": "user", "content": "3/4 加 1/4 是多少?"},
                         {"role": "assistant", "content": "分母相同,分子相加,你试试?"}]}


def write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                    encoding="utf-8")
    return path


def registry_variant(path: Path, **flips: str) -> Path:
    """生成 registry 变体:flips 里每个字段改 owner(mutable 随 owner 连动)。"""
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    for field, owner in flips.items():
        data["ownership"][field] = {"owner": owner,
                                    "mutable": owner == "calibration_candidate"}
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
    return path


def judge_env(tmp_path: Path, replies: list):
    """judge 角色 + 路线 1(provider 无服务端保证)指向假上游,同 test_judge 口径。"""
    return fake_gateway(tmp_path, replies, role_name="judge", provider_json_strict=False,
                        concurrency=2, first_token_timeout_s=2.0, total_timeout_s=5.0)


def scenario() -> tuple[list[dict], list[dict], list]:
    """两案:flag 案(活评 mi=0 与 baseline mi=2 张力)与 clean 案(locked 全等)。"""
    rows = [judge_row("flag-case", [2, 1, 2, 0, 1, 0], math_integrity=2, verdict="fail"),
            judge_row("clean-case", [2, 2, 1, 0, 0, 0], math_integrity=1, verdict="fail")]
    cases = [live_case("flag-case"), live_case("clean-case")]
    replies = [judge_reply([2, 1, 2, 1, 2, 1], math_integrity=0),  # locked 张力:mi 2→0
               judge_reply([2, 2, 1, 2, 2, 2], math_integrity=1)]
    return rows, cases, replies


# ---------- 1) registry 与 #535 裁定一致 ----------


def test_registry_header_declares_ruling_source():
    text = REGISTRY.read_text(encoding="utf-8")
    assert "5981592681" in text and "#535" in text  # 约束来源 = #535 裁定
    assert "改 locked 维须另开 calibration cycle" in text  # 治理红线原文


def test_registry_ownership_matches_ruling():
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    own = data["ownership"]
    assert set(own) == set(DIMENSIONS) | {"answer_leaked", "math_integrity"}
    for field in (*LOCKED_BASELINE, "answer_leaked", "math_integrity"):
        assert own[field] == {"owner": "baseline", "mutable": False}, field
    for field in ALLOWED:
        assert own[field] == {"owner": "calibration_candidate", "mutable": True}, field


def test_load_ownership_locks_five_allows_three():
    ownership = ac.load_ownership()
    assert ownership["locked_fields"] == [*LOCKED_BASELINE, "answer_leaked", "math_integrity"]
    assert ownership["allowed_dims"] == list(ALLOWED)


# ---------- 2) registry 驱动锁定集(不硬编码) ----------


def test_registry_flip_changes_locked_set_and_assembly(tmp_path):
    """pacing 翻转为 baseline → 进锁定集;活评 pacing 不再进组装,baseline 值获胜。"""
    variant = registry_variant(tmp_path / "ownership-variant.yaml", pacing="baseline")
    ownership = ac.load_ownership(variant)
    assert "pacing" in ownership["locked_fields"]
    assert ownership["allowed_dims"] == ["summary_mastery", "termination"]
    rows, cases, replies = scenario()
    rows[0]["scores"]["pacing"] = 0  # baseline 冻结 pacing=0;活评给 2
    rows_path = write_jsonl(tmp_path / "rows.jsonl", rows)
    baseline = ac.freeze_baseline("cycle-flip", rows_path, tmp_path / "out", variant)
    replies[0] = judge_reply([2, 1, 2, 2, 2, 1], math_integrity=0)  # 活评 pacing=2
    with judge_env(tmp_path, replies) as (_, gateway):
        summary = ac.run_anchored(gateway, baseline, cases, tmp_path / "out")
    rows_out = ac.read_jsonl(tmp_path / "out" / "anchored-arm.jsonl")
    assert summary["cases"] == 2
    assert rows_out[0]["anchored"]["scores"]["pacing"] == 0  # baseline 机械取值获胜
    assert rows_out[0]["allowed"] == {"summary_mastery": 2, "termination": 1}


def test_hard_fields_must_stay_locked(tmp_path):
    variant = registry_variant(tmp_path / "ownership-mi.yaml", math_integrity="calibration_candidate")
    with pytest.raises(ac.CalibrationGateError, match="硬门字段"):
        ac.load_ownership(variant)


# ---------- 3) 冻结面:逐案 locked 五值 + sha 链 + immutable + sidecar ----------


def test_freeze_writes_baseline_sidecar_and_sha_chain(tmp_path):
    rows, _, _ = scenario()
    rows_path = write_jsonl(tmp_path / "judge-rows.jsonl", rows)
    out = tmp_path / "frozen"
    baseline = ac.freeze_baseline("cycle-42", rows_path, out)
    written = json.loads((out / "baseline.json").read_text(encoding="utf-8"))
    assert written == baseline
    assert baseline["schema"] == "anchored-baseline/1"
    assert baseline["immutable_this_cycle"] is True
    assert baseline["cycle_id"] == "cycle-42"
    sha = hashlib.sha256((out / "baseline.json").read_bytes()).hexdigest()
    assert (out / "baseline.json.sha256").read_text(encoding="utf-8") == f"{sha}  baseline.json\n"
    assert baseline["provenance"]["judge_rows_sha256"] == hashlib.sha256(
        rows_path.read_bytes()).hexdigest()
    locked = baseline["cases"]["flag-case"]["locked"]
    assert locked == {"first_question": 2, "socratic_followup": 1, "grade_fit": 2,
                      "answer_leaked": False, "math_integrity": 2}
    assert baseline["cases"]["flag-case"]["old_arm_reference"]["judge_model"] == "fake-judge"
    assert baseline["counts"] == {"cases": 2}


def test_load_baseline_accepts_untampered_freeze(tmp_path):
    rows, _, _ = scenario()
    rows_path = write_jsonl(tmp_path / "judge-rows.jsonl", rows)
    out = tmp_path / "frozen"
    frozen = ac.freeze_baseline("cycle-ok", rows_path, out)
    assert ac.load_baseline(out / "baseline.json")["cases"] == frozen["cases"]


# ---------- 4) 组装面:locked==baseline / 键集=生产六维 / verdict 生产重算 ----------


def test_run_anchored_assembly_invariants(tmp_path):
    rows, cases, replies = scenario()
    rows_path = write_jsonl(tmp_path / "judge-rows.jsonl", rows)
    out = tmp_path / "anchored"
    baseline = ac.freeze_baseline("cycle-main", rows_path, out)
    with judge_env(tmp_path, replies) as (_, gateway):
        summary = ac.run_anchored(gateway, baseline, cases, out)
    arm = {r["case_id"]: r for r in ac.read_jsonl(out / "anchored-arm.jsonl")}
    assert summary["cases"] == 2 and summary["judge_score_calls"] == 2
    assert (out / "anchored-summary.json").is_file()
    for cid, row in arm.items():
        locked = baseline["cases"][cid]["locked"]
        for field in (*LOCKED_BASELINE, "answer_leaked", "math_integrity"):
            actual = row["anchored"]["scores"].get(field, row["anchored"].get(field))
            assert actual == locked[field], (cid, field)  # 逐案 locked == baseline
        assert set(row["anchored"]["scores"]) == set(DIMENSIONS)  # 键集 = 生产六维
        assert set(row["allowed"]) == set(ALLOWED)  # 活评只供 allowed 三维
        assert row["anchored"]["verdict"] == verdict_from_scores(  # 生产函数独立重算
            row["anchored"]["scores"], locked["answer_leaked"], locked["math_integrity"])
        assert row["judge_model"] == "fake-model"  # 活评 judge 模型披露(FakeOpenAI 上游)
        assert row["old_arm_reference"]["judge_model"] == "fake-judge"  # 老臂披露随 baseline
    # clean 案:baseline mi=1 封顶 review(活评 mi 同值,不改变锚定语义)
    assert arm["clean-case"]["anchored"]["verdict"] == "review"
    # flag 案:baseline mi=2(非 0),六维 9 分无 0 → review;老臂 fail 如实披露
    assert arm["flag-case"]["anchored"]["verdict"] == "review"
    assert arm["flag-case"]["verdict_delta_vs_old_arm"] == {"old": "fail", "anchored": "review"}


# ---------- 5) flag 通道:flag iff challenge,零静默 ----------


def test_flag_raised_iff_locked_tension(tmp_path):
    rows, cases, replies = scenario()
    rows_path = write_jsonl(tmp_path / "judge-rows.jsonl", rows)
    out = tmp_path / "anchored"
    baseline = ac.freeze_baseline("cycle-flag", rows_path, out)
    with judge_env(tmp_path, replies) as (_, gateway):
        summary = ac.run_anchored(gateway, baseline, cases, out)
    flags = ac.read_jsonl(out / "flags.jsonl")
    arm = {r["case_id"]: r for r in ac.read_jsonl(out / "anchored-arm.jsonl")}
    assert summary["flags"] == 1 and summary["flag_cases"] == ["flag-case"]
    assert len(flags) == 1 and flags[0]["case_id"] == "flag-case"
    assert flags[0]["flag"] == ac.FLAG_TEXT == "locked 张力→路由新 calibration cycle"
    assert flags[0]["divergent_fields"] == ["math_integrity"]
    assert flags[0]["divergence"]["math_integrity"] == {"baseline": 2, "probe": 0}
    detector = arm["flag-case"]["challenge_detector"]
    assert detector["flag"] is True and detector["divergent_fields"] == ["math_integrity"]
    assert arm["clean-case"]["challenge_detector"]["flag"] is False
    assert arm["clean-case"]["challenge_detector"]["divergent_fields"] == []
    # 张力不改用 probe 值:flag 案 anchored 仍用 baseline mi=2
    assert arm["flag-case"]["anchored"]["math_integrity"] == 2


# ---------- 6) fail-closed:篡改 / registry 漂移 / 预算闸 / 显式 cycle-id ----------


def test_tampered_baseline_fails_closed_in_process(tmp_path):
    rows, _, _ = scenario()
    rows_path = write_jsonl(tmp_path / "judge-rows.jsonl", rows)
    out = tmp_path / "frozen"
    ac.freeze_baseline("cycle-tamper", rows_path, out)
    target = out / "baseline.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data["cases"]["flag-case"]["locked"]["math_integrity"] = 0  # 改 baseline 锁定值
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ac.CalibrationGateError, match="sidecar"):
        ac.load_baseline(target)


def test_missing_sidecar_fails_closed(tmp_path):
    rows, _, _ = scenario()
    rows_path = write_jsonl(tmp_path / "judge-rows.jsonl", rows)
    out = tmp_path / "frozen"
    ac.freeze_baseline("cycle-nosidecar", rows_path, out)
    (out / "baseline.json.sha256").unlink()
    with pytest.raises(ac.CalibrationGateError, match="sidecar"):
        ac.load_baseline(out / "baseline.json")


def test_registry_drift_fails_closed(tmp_path):
    """改 locked 维没另开 cycle:registry 与 baseline 冻结时不一致即拒。"""
    variant = registry_variant(tmp_path / "ownership.yaml")
    rows, _, _ = scenario()
    rows_path = write_jsonl(tmp_path / "judge-rows.jsonl", rows)
    out = tmp_path / "frozen"
    ac.freeze_baseline("cycle-drift", rows_path, out, variant)
    registry_variant(variant, pacing="baseline")  # 冻结后改 registry(改 locked 维)
    with pytest.raises(ac.CalibrationGateError, match="另开 calibration cycle"):
        ac.load_baseline(out / "baseline.json", variant)


def test_budget_gate_fails_closed(tmp_path):
    rows, cases, replies = scenario()
    rows_path = write_jsonl(tmp_path / "judge-rows.jsonl", rows)
    out = tmp_path / "anchored"
    baseline = ac.freeze_baseline("cycle-budget", rows_path, out)
    with judge_env(tmp_path, replies[:1]) as (_, gateway):
        with pytest.raises(ac.CalibrationGateError, match="预算"):
            ac.run_anchored(gateway, baseline, cases, out, budget=1)
    assert not (out / "anchored-arm.jsonl").exists()  # 半轮不落盘


def test_cli_requires_explicit_cycle_id(tmp_path):
    rows, _, _ = scenario()
    rows_path = write_jsonl(tmp_path / "judge-rows.jsonl", rows)
    proc = subprocess.run([sys.executable, str(SCRIPT), "--freeze-baseline",
                           "--judge-rows", str(rows_path), "--out-dir", str(tmp_path / "o")],
                          capture_output=True, text=True, check=False)
    assert proc.returncode != 0  # argparse 缺 --cycle-id:anchored 无默认运行路径
    assert not (tmp_path / "o" / "baseline.json").exists()


def test_cli_freeze_then_tampered_run_exits_nonzero(tmp_path):
    rows, cases, _ = scenario()
    rows_path = write_jsonl(tmp_path / "judge-rows.jsonl", rows)
    cases_path = write_jsonl(tmp_path / "cases.jsonl", cases)
    out = tmp_path / "cli"
    ok = subprocess.run([sys.executable, str(SCRIPT), "--freeze-baseline",
                         "--cycle-id", "cycle-cli", "--judge-rows", str(rows_path),
                         "--out-dir", str(out)], capture_output=True, text=True, check=False)
    assert ok.returncode == 0 and (out / "baseline.json").is_file()
    target = out / "baseline.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    data["cases"]["clean-case"]["locked"]["grade_fit"] = 0  # 篡改
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    bad = subprocess.run([sys.executable, str(SCRIPT), "--run-anchored",
                          "--cycle-id", "cycle-cli", "--cases", str(cases_path),
                          "--out-dir", str(out)], capture_output=True, text=True, check=False)
    assert bad.returncode != 0 and "FAIL-CLOSED" in bad.stderr


def test_cycle_identity_mismatch_rejected_before_gateway(tmp_path, monkeypatch):
    """#538 阻断修复钉:--cycle-id 与 baseline.cycle_id 不一致 → Gateway 构造前
    fail-closed(exit 1+明示两个 cycle 身份),0 Gateway/0 Judge 调用、零工件写出;
    不允许猜测或覆盖 baseline cycle identity。"""
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "scripts" / "anchored_calibration.py"
    rows, _, _ = scenario()
    rows_path = write_jsonl(tmp_path / "judge-rows.jsonl", rows)
    out_a = tmp_path / "cyA"
    r = subprocess.run([sys.executable, str(script), "--cycle-id", "cycle-A",
                        "--freeze-baseline", "--judge-rows", str(rows_path),
                        "--out-dir", str(out_a)],
                       capture_output=True, text=True, cwd=script.parents[1])
    assert r.returncode == 0, r.stderr
    out_b = tmp_path / "cyB"
    out_b.mkdir()
    rr = subprocess.run([sys.executable, str(script), "--cycle-id", "cycle-B",
                         "--run-anchored", "--cases", str(rows_path),
                         "--baseline", str(out_a / "baseline.json"),
                         "--out-dir", str(out_b)],
                        capture_output=True, text=True, cwd=script.parents[1])
    assert rr.returncode != 0
    combined = rr.stderr + rr.stdout
    assert "cycle 身份不匹配" in combined
    assert "cycle-A" in combined and "cycle-B" in combined
    # 0 Gateway/0 Judge:facts 目录未创建、零评分工件
    assert not (out_b / "facts").exists()
    assert not (out_b / "anchored-arm.jsonl").exists()
    assert not (out_b / "anchored-summary.json").exists()
