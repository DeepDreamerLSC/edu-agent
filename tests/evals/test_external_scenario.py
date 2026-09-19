"""外部数据 canonical 层 v1 测试(#368):validator 六类红灯 + importer e2e + 指纹稳定。

夹具是**手工构造**的最小样例(章程纪律:真数据集不进仓——原件冻结目录
external/ 已 gitignore,license 兼容性核对人批后另行拉取);夹具形状即
importer 对上游原件的契约,真原件落地时若有出入,修显式映射表不修猜测。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from edu_agent.evals import (
    EXTERNAL_ROLES,
    EXTERNAL_SCHEMA_VERSION,
    import_socraticmath,
    load_normalized,
    external_fingerprint,
    to_v1_record,
    validate_external_scenario,
)

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "external" / "socraticmath_samples.jsonl"
SCHEMA_FILE = REPO / "edu_agent" / "evals" / "datasets" / "external_schemas" / "external_scenario_v1.json"


def _valid_record(**overrides) -> dict:
    """绿路基线:一切字段合法;overrides 浅覆盖指定键构造红灯用例。"""
    record = {
        "schema_version": EXTERNAL_SCHEMA_VERSION,
        "id": "socraticmath_9001",
        "source": {"dataset": "SocraticMATH", "upstream_id": "9001",
                   "license": "CC-BY-NC-4.0", "version": "v1-fixture", "modified": False},
        "problem": {"text": "计算 3/4 + 1/8,并说明通分过程。", "answer": "7/8",
                    "analysis": None, "image": None, "grade": None, "knowledge_tags": []},
        "reference_dialogue": [
            {"role": "student", "text": "这两个分数分母不一样,直接加分子吗?"},
            {"role": "tutor", "text": "不行,先通分。4 和 8 的最小公倍数是多少?"},
        ],
        "annotations": {"difficulty": None, "teacher_moves": [], "outcome": None},
    }
    record.update(overrides)
    return record


def test_green_path_and_constants_mirror_schema_file():
    """绿路零错误;JSON Schema 契约文件与 Python 常量互为镜像(枚举/必填钉一致)。"""
    assert validate_external_scenario(_valid_record()) == []
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    assert schema["properties"]["schema_version"]["const"] == EXTERNAL_SCHEMA_VERSION
    assert set(schema["properties"]["source"]["required"]) == {"dataset", "upstream_id",
                                                               "license", "version"}
    assert set(schema["properties"]["reference_dialogue"]["items"]
               ["properties"]["role"]["enum"]) == set(EXTERNAL_ROLES)


# ===== 六类红灯(完成判据 ②)=====

def test_red_missing_source():
    record = _valid_record()
    del record["source"]
    assert any("source" in e for e in validate_external_scenario(record))


def test_red_bad_role():
    record = _valid_record(reference_dialogue=[{"role": "assistant", "text": "hi"}])
    assert any("role" in e for e in validate_external_scenario(record))


def test_red_missing_image_file(tmp_path):
    record = _valid_record()
    record["problem"]["image"] = {"path": "imgs/gone.png", "sha256": "0" * 64}
    assert any("image 文件不存在" in e
               for e in validate_external_scenario(record, base_dir=tmp_path))


def test_red_image_hash_mismatch(tmp_path):
    img = tmp_path / "imgs" / "a.png"
    img.parent.mkdir()
    img.write_bytes(b"png-bytes")
    record = _valid_record()
    record["problem"]["image"] = {"path": "imgs/a.png",
                                  "sha256": hashlib.sha256(b"other").hexdigest()}
    assert any("sha256 不符" in e
               for e in validate_external_scenario(record, base_dir=tmp_path))


def test_red_answer_rewritten():
    record = _valid_record()  # problem.answer = "7/8"
    assert any("不一致" in e for e in validate_external_scenario(
        record, expected_answer="7 / 8 改写过"))
    assert validate_external_scenario(record, expected_answer="7/8") == []


def test_red_missing_upstream_id():
    record = _valid_record()
    record["source"] = {k: v for k, v in record["source"].items() if k != "upstream_id"}
    assert any("upstream_id" in e for e in validate_external_scenario(record))


# ===== 指纹(完成判据 ③ 的稳定面)=====

def test_fingerprint_stable_and_content_sensitive():
    record = _valid_record()
    record["fingerprint"] = external_fingerprint(record)
    assert record["fingerprint"] == external_fingerprint(_valid_record())  # 确定性
    assert validate_external_scenario(record) == []  # 自带指纹过闸
    tampered = _valid_record()
    tampered["problem"]["answer"] = "7 / 8"
    assert external_fingerprint(tampered) != record["fingerprint"]  # 内容变则指纹变
    forged = _valid_record(fingerprint="0" * 64)
    assert any("指纹" in e for e in validate_external_scenario(forged))  # 伪造指纹红灯


# ===== importer e2e(完成判据 ③)=====

def test_importer_fixture_roundtrip(tmp_path):
    out = tmp_path / "external_normalized" / "socraticmath.jsonl"
    stats = import_socraticmath(FIXTURE.parent, out)
    assert stats["records"] == 3
    records = load_normalized(out, base_dir=FIXTURE.parent)  # 读回逐条过闸
    assert [r["id"] for r in records] == ["socraticmath_9001", "socraticmath_9002",
                                          "socraticmath_9003"]
    first = records[0]
    assert first["source"]["license"] == "CC-BY-NC-4.0"  # license 逐条带进 source 块
    assert first["problem"]["answer"] == "7/8"  # 原样保真
    assert [t["role"] for t in first["reference_dialogue"]] == ["student", "tutor"] * 2
    # 重跑指纹逐字节稳定(证据层可复现)
    out2 = tmp_path / "again.jsonl"
    import_socraticmath(FIXTURE.parent, out2)
    assert out.read_bytes() == out2.read_bytes()


def test_importer_fail_closed_on_unknown_from(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"id": "1", "question": "q", "answer": "a",
                               "license": "L", "version": "v",
                               "conversations": [{"from": "system", "value": "x"}]},
                              ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="不在映射表"):
        import_socraticmath(tmp_path, tmp_path / "out.jsonl")
    assert not (tmp_path / "out.jsonl").exists()  # 宁缺毋滥:不过闸不落盘


def test_importer_cli_zero_traces(tmp_path):
    """真实 CLI 子进程:夹具 → jsonl,exit 0(零模型调用,纯数据面)。"""
    out = tmp_path / "socraticmath.jsonl"
    result = subprocess.run(
        [sys.executable, "-m", "edu_agent.evals.importers.socraticmath",
         str(FIXTURE.parent), str(out)],
        cwd=REPO, capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stderr
    assert "import-ok" in result.stdout and out.is_file()


def test_to_v1_record_no_student_turns():
    """红线钉死:v1 不生成 student_turns/steps(slice 层的事,字段根本不出现)。"""
    raw = json.loads(FIXTURE.read_text(encoding="utf-8").splitlines()[0])
    record = to_v1_record(raw)
    assert "student_turns" not in record and "steps" not in record
    assert set(record) == {"schema_version", "id", "source", "problem",
                           "reference_dialogue", "annotations", "fingerprint"}
