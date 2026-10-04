"""Evaluator change promotion packet 合同测试(#537 M5-D)。

确定性、零真实模型调用:validator 全链路离线;语料 = tests/evals/fixtures/
promotion-replay/(M5 历史 cycle 重放,#537 Exit 5)。覆盖七件:
1) B2 真实合规 packet 正路径:唯一肯定输出 structurally complete, awaiting
   human key,且任何输出不含 approved(Validator ≠ Approver);
2) 历史 overreach 候选(M5-A/A'/B 重构件)全部 fail-closed,m5-b 另验静默吸收;
3) human_promotion.decision 非空 → 拒(机器验证面拒绝自带人裁位);
4) schema 不完备(缺节/product_rerun≠0)→ 拒;
5) registry 漂移 → 拒(registry change = meta-change = 新 cycle);
6) evidence 篡改(sha 不符)→ 拒;负保护集丢 old=fail 案 / flag 申报不实 → 拒;
7) requested_dims 越界(无 change right)→ 拒。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

import validate_promotion_packet as vpp  # scripts/(conftest 挂载)

REPO = Path(__file__).resolve().parents[2]
VALIDATOR = REPO / "scripts" / "validate_promotion_packet.py"
SCHEMA = REPO / "docs" / "evals" / "promotion-packet.schema.json"
CORPUS = Path(__file__).parent / "fixtures" / "promotion-replay"
REGISTRY = REPO / "edu_agent" / "evals" / "rubrics" / "dimension-ownership.yaml"
COMPLETE = "structurally complete, awaiting human key"

# 重放预期(#537 Exit 5):三件历史 FAIL 候选的机械拒因(与史实一致)
OVERREACH_EXPECT = {
    "m5-a": ["locked ≠ baseline", "socratic_followup", "math_integrity"],
    "m5-ap": ["locked ≠ baseline", "socratic_followup"],
    "m5-b": ["locked ≠ baseline", "静默吸收"],
}


def run_cli(packet: Path, registry: Path | None = None) -> subprocess.CompletedProcess:
    command = [sys.executable, str(VALIDATOR), str(packet)]
    if registry is not None:
        command += ["--registry", str(registry)]
    return subprocess.run(command, capture_output=True, text=True, cwd=REPO)


def mutate_b2(tmp_path: Path, edit) -> Path:
    """复制 m5-b2 语料到 tmp 后按 edit(packet_dict) 改写 packet,返回其路径。"""
    target = tmp_path / "m5-b2"
    shutil.copytree(CORPUS / "m5-b2", target)
    packet_path = target / "packet.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    edit(packet)
    packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    return packet_path


# ---------- ① B2 真实合规 packet 正路径 ----------


def test_b2_real_packet_structurally_complete():
    result = run_cli(CORPUS / "m5-b2" / "packet.json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert COMPLETE in result.stdout
    assert "approved" not in result.stdout + result.stderr  # Validator ≠ Approver
    summary = json.loads(result.stdout[: result.stdout.rindex("}") + 1])
    assert summary["cases"] == 17 and summary["flags"] == 7
    assert summary["locked_invariant"] == "PASS"


def test_b2_fixture_carries_frozen_facts():
    """夹具忠实承载 M5-B2 冻结事实:17 案、7 flag、challenge 案 locked==baseline。"""
    arm = [json.loads(line) for line in
           (CORPUS / "m5-b2" / "anchored-arm.jsonl").read_text().splitlines() if line.strip()]
    flags = [json.loads(line) for line in
             (CORPUS / "m5-b2" / "flags.jsonl").read_text().splitlines() if line.strip()]
    assert len(arm) == 17 and len(flags) == 7
    probability = next(r for r in arm if r["case_id"].endswith("stability_probability"))
    assert probability["locked"]["math_integrity"] == 0  # baseline 锚定(旧臂 mi=0)
    assert probability["anchored"]["math_integrity"] == 0  # anchored 不改用 probe 值 2
    assert probability["challenge_detector"]["flag"] is True  # 张力如实披露


def test_validate_function_positive_path():
    result = vpp.validate(CORPUS / "m5-b2" / "packet.json")
    assert result["failures"] == []
    assert result["summary"]["verdict_movements"] == [
        "core-b2-circle_area_alternative_method:fail->review",
        "core-b2-rope_unit_app_misconception_repair:fail->review",
        "core-goldc-chicken_rabbit_alternative_method:fail->review",
        "core-imgv1-image_v1_visual_statistics_open_30:fail->review",
    ]  # verdict 变好只披露,不作成功证据(四问③)


# ---------- ② 历史 overreach 候选全部 fail-closed ----------


@pytest.mark.parametrize("slug", sorted(OVERREACH_EXPECT))
def test_overreach_candidates_rejected(slug: str):
    result = run_cli(CORPUS / slug / "packet.json")
    assert result.returncode == 1
    assert "FAIL" in result.stdout
    for expected in OVERREACH_EXPECT[slug]:
        assert expected in result.stdout, result.stdout


def test_m5b_drift_is_silent_absorption():
    """M5-B 独有拒因:7 案检测器发散而 flags.jsonl 空(零 flag 通道,EF-001 史实)。"""
    result = run_cli(CORPUS / "m5-b" / "packet.json")
    assert result.returncode == 1
    assert "静默吸收" in result.stdout
    assert "申报不实" in result.stdout


# ---------- ③ human promotion 位 ----------


def test_human_slot_nonempty_rejected(tmp_path):
    def fill(packet):
        packet["human_promotion"]["decision"] = "granted by pipeline"

    result = run_cli(mutate_b2(tmp_path, fill))
    assert result.returncode == 1
    assert "Validator ≠ Approver" in result.stdout
    assert "approved" not in result.stdout + result.stderr


def test_human_slot_empty_string_is_also_rejected(tmp_path):
    def fill(packet):
        packet["human_promotion"]["decision"] = ""

    assert run_cli(mutate_b2(tmp_path, fill)).returncode == 1


# ---------- ④ schema 完备性 ----------


def test_b2_packet_conforms_schema():
    packet = json.loads((CORPUS / "m5-b2" / "packet.json").read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(packet)  # 不合即抛


def test_missing_masking_proof_rejected(tmp_path):
    def drop(packet):
        del packet["masking_proof"]

    result = run_cli(mutate_b2(tmp_path, drop))
    assert result.returncode == 1 and "schema" in result.stdout


def test_product_rerun_nonzero_rejected(tmp_path):
    def rerun(packet):
        packet["identity"]["execution_identity"]["product_rerun"] = 3

    result = run_cli(mutate_b2(tmp_path, rerun))
    assert result.returncode == 1  # Evidence 不随尺改写:packet v1 恒 0


# ---------- ⑤ registry 漂移 = meta-change ----------


def test_registry_drift_rejected(tmp_path):
    drifted = tmp_path / "dimension-ownership.yaml"
    drifted.write_text(
        REGISTRY.read_text(encoding="utf-8").replace(
            "  pacing:\n    owner: calibration_candidate\n    mutable: true",
            "  pacing:\n    owner: baseline\n    mutable: false"),
        encoding="utf-8")
    result = run_cli(CORPUS / "m5-b2" / "packet.json", registry=drifted)
    assert result.returncode == 1
    assert "新开 calibration cycle" in result.stdout or "meta-change" in result.stdout


# ---------- ⑥ evidence 链与 masking 申报 ----------


def test_evidence_tamper_rejected(tmp_path):
    packet_path = mutate_b2(tmp_path, lambda packet: None)
    flags = packet_path.parent / "flags.jsonl"
    flags.write_text(flags.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    result = run_cli(packet_path)
    assert result.returncode == 1 and "sha256 不符" in result.stdout


def test_negative_protection_dropout_rejected(tmp_path):
    def drop(packet):
        protected = packet["masking_proof"]["negative_protection_set"]
        protected.pop(next(i for i, e in enumerate(protected)
                           if e["case_id"].endswith("application_table_14")))

    result = run_cli(mutate_b2(tmp_path, drop))
    assert result.returncode == 1 and "未全部申报" in result.stdout


def test_flag_cases_dishonest_rejected(tmp_path):
    def shrink(packet):
        packet["masking_proof"]["challenge_flags"]["flag_cases"] = \
            packet["masking_proof"]["challenge_flags"]["flag_cases"][:1]

    result = run_cli(mutate_b2(tmp_path, shrink))
    assert result.returncode == 1 and "申报不实" in result.stdout


# ---------- ⑦ change right ----------


def test_requested_dim_without_change_right_rejected(tmp_path):
    def widen(packet):
        packet["change_scope"]["requested_dims"] = [
            "pacing", "summary_mastery", "termination", "socratic_followup"]

    result = run_cli(mutate_b2(tmp_path, widen))
    assert result.returncode == 1 and "无 change right" in result.stdout
