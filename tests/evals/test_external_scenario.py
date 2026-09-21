"""外部数据 canonical 层 v1 测试(#368):validator 六类红灯 + importer e2e + 指纹稳定。

夹具是**手工构造**的最小样例,但按真原件 837da0b 的真实形态搭建(2026-09-21 适配):
整文件 JSON 数组的 train/val、逐对样本的 test(链式重组)、gb18030 csv 元数据、
题面塞进首轮 assistant 的打包痕迹、8 变体请求语——夹具形状即 importer 对上游原件的
契约,原件若有出入,修显式映射表不修猜测。真数据集不进仓(external/ 已 gitignore)。
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
    validate_external_scenario,
)

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "external" / "socraticmath"
SCHEMA_FILE = REPO / "edu_agent" / "evals" / "datasets" / "external_schemas" / "external_scenario_v1.json"
# 夹具平账数(缩微版:2 train + 1 val + 1 test 母对话)
FIXTURE_COUNTS = {"train": 2, "val": 1, "test": 1}


def _valid_record(**overrides) -> dict:
    """绿路基线:一切字段合法;overrides 浅覆盖指定键构造红灯用例。"""
    record = {
        "schema_version": EXTERNAL_SCHEMA_VERSION,
        "id": "socraticmath_train_1",
        "source": {"dataset": "SocraticMATH", "upstream_id": "train:1",
                   "license": "CC BY-NC 4.0", "version": "837da0b", "modified": False},
        "problem": {"text": "3 加 5 等于几？", "answer": "8",
                    "analysis": "【解析】:解：3+5=8。故答案为：8", "image": None,
                    "grade": None, "knowledge_tags": ["10 以内的加法"]},
        "reference_dialogue": [
            {"role": "student", "text": "3 加 5 等于几？\n这道题怎么解？"},
            {"role": "tutor", "text": "我们先看看 3 和 5 各表示什么，好吗？"},
        ],
        "annotations": {"difficulty": "1", "teacher_moves": [], "outcome": None},
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
    record = _valid_record()  # problem.answer = "8"
    assert any("不一致" in e for e in validate_external_scenario(
        record, expected_answer="8 改写过"))
    assert validate_external_scenario(record, expected_answer="8") == []


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
    tampered["problem"]["answer"] = "八"
    assert external_fingerprint(tampered) != record["fingerprint"]  # 内容变则指纹变
    forged = _valid_record(fingerprint="0" * 64)
    assert any("指纹" in e for e in validate_external_scenario(forged))  # 伪造指纹红灯


# ===== importer e2e(完成判据 ③)=====

def test_importer_fixture_roundtrip(tmp_path):
    out = tmp_path / "external_normalized" / "socraticmath.jsonl"
    stats = import_socraticmath(FIXTURE, out, expected_counts=FIXTURE_COUNTS)
    assert stats == {"records": 4, "train": 2, "val": 1, "test": 1}
    records = load_normalized(out, base_dir=FIXTURE)  # 读回逐条过闸
    # id 带 split 段:真原件 train 与 val 的上游 id 都是 1..N 撞车,split 段是唯一解
    assert [r["id"] for r in records] == ["socraticmath_train_1", "socraticmath_train_2",
                                          "socraticmath_val_1", "socraticmath_test_1"]
    first = records[0]
    assert first["source"] == {"dataset": "SocraticMATH", "upstream_id": "train:1",
                               "license": "CC BY-NC 4.0", "version": "837da0b",
                               "modified": False}  # license/version 逐条带进 source 块
    assert first["problem"]["answer"] == "8"  # 解析列"故答案为"子串,原样保真
    assert first["problem"]["analysis"].startswith("【解析】")
    assert first["problem"]["knowledge_tags"] == ["10 以内的加法"]  # csv 知识点列
    assert first["annotations"]["difficulty"] == "1"  # csv 难度列
    # 首轮(上游 from=assistant 装题面)按位置归 student,之后 assistant=tutor/user=student
    assert [t["role"] for t in first["reference_dialogue"]] == ["student", "tutor"] * 3
    # 题面+请求语逐字保真(含换行,不做空白手术)
    assert first["reference_dialogue"][0]["text"] == "3 加 5 等于几？\n这道题怎么解？"
    # 无"故答案为"的记录 answer 留 None(不造数据),analysis 仍整段保真
    second = records[1]
    assert second["problem"]["answer"] is None
    assert second["problem"]["analysis"].startswith("【解析】")
    # test 母对话重建:请求语在题面前部且对话以 tutor 轮收尾(链式重组的结构结果)
    test_rec = records[3]
    assert [t["role"] for t in test_rec["reference_dialogue"]] == ["student", "tutor",
                                                                   "student", "tutor"]
    assert test_rec["problem"]["answer"] == "1/2"
    # 重跑逐字节稳定(证据层可复现)
    out2 = tmp_path / "again.jsonl"
    import_socraticmath(FIXTURE, out2, expected_counts=FIXTURE_COUNTS)
    assert out.read_bytes() == out2.read_bytes()


def _make_skeleton(root: Path) -> Path:
    """搭一个只够走到 fail 点的最小数据目录骨架(train/val/test + 空 csv 表头)。"""
    src = root / "data"
    (src / "csv").mkdir(parents=True)
    (src / "csv" / "SocratesMATH.csv").write_text(
        "题目,对话,解析,知识点,题型,难度,参考答案,方法提示\n", encoding="gb18030", newline="")
    (src / "SocratesMATH_valdata.jsonl").write_text("[]\n", encoding="utf-8")
    (src / "SocratesMATH_testdata.jsonl").write_text("", encoding="utf-8")
    return src


def test_importer_fail_closed_on_unknown_from(tmp_path):
    """from 值不在显式映射表 → fail closed,不落盘(宁缺毋滥)。"""
    src = _make_skeleton(tmp_path)
    (src / "SocratesMATH_traindata.jsonl").write_text(json.dumps(
        [{"id": "1", "conversations": [
            {"from": "assistant", "value": "q"}, {"from": "system", "value": "x"}]}],
        ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="不在映射表"):
        import_socraticmath(src, tmp_path / "out.jsonl",
                            expected_counts={"train": 1, "val": 0, "test": 0})
    assert not (tmp_path / "out.jsonl").exists()


def test_importer_fail_closed_on_unaligned_dialogue(tmp_path):
    """对话文本对齐不到 csv 行 → 残差如实中止,不硬造(对齐偏离的兜底红灯)。"""
    src = _make_skeleton(tmp_path)
    (src / "SocratesMATH_traindata.jsonl").write_text(
        json.dumps([{"id": "1", "conversations": [
            {"from": "assistant", "value": "对齐不上的题面"}]}], ensure_ascii=False) + "\n",
        encoding="utf-8")
    with pytest.raises(ValueError, match="文本对齐未命中"):
        import_socraticmath(src, tmp_path / "out.jsonl",
                            expected_counts={"train": 1, "val": 0, "test": 0})
    assert not (tmp_path / "out.jsonl").exists()


def test_importer_rejects_file_path_with_direction(tmp_path):
    """传文件当首参 → 指路报错(#369 审 P3-1:目录语义易踩)。"""
    single = tmp_path / "one.jsonl"
    single.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="目录.*不是文件"):
        import_socraticmath(single, tmp_path / "out.jsonl")
    with pytest.raises(ValueError, match="external/socraticmath"):
        import_socraticmath(single, tmp_path / "out.jsonl")  # 文案带正确示例路径


def test_importer_rejects_wrong_record_count(tmp_path):
    """记录数对不上冻结平账数 → fail closed(防原件漂移/传错目录)。"""
    src = _make_skeleton(tmp_path)
    (src / "SocratesMATH_traindata.jsonl").write_text("[]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="≠ 冻结原件"):
        import_socraticmath(src, tmp_path / "out.jsonl")  # 缺省期望 5476/685/685


def test_importer_cli_zero_traces(tmp_path):
    """真实 CLI 子进程:夹具 → jsonl,exit 0(零模型调用,纯数据面)。

    CLI 不暴露 expected_counts(那是测试面),故夹具走 CLI 时会按冻结原件
    平账数校验而失败——CLI e2e 用缩微期望不可行,改为验证用法错误路径,
    全量导入由真原件目录亲跑验证(见 PR 描述对账数字)。
    """
    out = tmp_path / "socraticmath.jsonl"
    result = subprocess.run(
        [sys.executable, "-m", "edu_agent.evals.importers.socraticmath",
         str(FIXTURE), str(out)],
        cwd=REPO, capture_output=True, text=True, timeout=60, check=False)
    # 夹具数量对不上冻结原件 → 指路退出码 2(不落盘);这不是失败,是 fail-closed 本身
    assert result.returncode == 2
    assert "≠ 冻结原件" in result.stderr
    assert not out.exists()
    # 用法错误(参数数量)也走 exit 2
    result2 = subprocess.run(
        [sys.executable, "-m", "edu_agent.evals.importers.socraticmath"],
        cwd=REPO, capture_output=True, text=True, timeout=60, check=False)
    assert result2.returncode == 2
    assert "用法" in result2.stderr


def test_to_v1_record_no_student_turns():
    """红线钉死:v1 不生成 student_turns/steps(slice 层的事,字段根本不出现)。"""
    from edu_agent.evals import collect_socraticmath_records  # 公开入口(02 §6)
    records, stats = collect_socraticmath_records(FIXTURE, FIXTURE_COUNTS)
    assert stats == {"train": 2, "val": 1, "test": 1}
    assert len(records) == 4
    for record in records:
        assert "student_turns" not in record and "steps" not in record
        assert set(record) == {"schema_version", "id", "source", "problem",
                               "reference_dialogue", "annotations", "fingerprint"}
