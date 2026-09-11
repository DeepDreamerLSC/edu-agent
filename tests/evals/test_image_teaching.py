"""题图教学评测集 v1(#130)WP2:schema 校验 + 题图 data URL + 内核透图。

确定性校验不碰真模型:validate_scenario 逐字段过门(必填/枚举/sha256/图路径),
question_image_data_url 走假文件对账,run_case 透图走 FakeOpenAI 断言
image_url 内容块进请求体。零真实模型;Gateway 构造与剧本构造器在
tests/fixtures/teachkit.py。
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from fake_openai import completion

from edu_agent.evals import KernelSubject, question_image_data_url, validate_scenario

from teachkit import kernel_env, open_json


def _write_image(tmp_path: Path, payload: bytes = b"\xff\xd8\xfffake-jpeg") -> tuple[str, str]:
    """写一个测试图,返回 (绝对路径, sha256)。"""
    path = tmp_path / "pqfile_test.jpg"
    path.write_bytes(payload)
    return str(path), hashlib.sha256(payload).hexdigest()


def _scenario(tmp_path: Path, **overrides) -> dict:
    path, sha = _write_image(tmp_path)
    scenario = {
        "id": "image_v1_circular_pond_race",
        "title": "圆·池塘追及",
        "grade": "六年级",
        "question": {"text": "池塘周长 62.8 米,……", "image": {"path": path, "sha256": sha}},
        "reference_answer": {"value": "62.8", "answer_type": "decimal_1", "unit": "米"},
        "bucket": "circle_geometry",
        "visual_dependency": "required",
        "misconception_seed": "半径当直径用",
        "student_turns": ["半径是 62.8÷3.14÷2 吗?", "哦,我先把半径当直径了。", "现在对上了。"],
        "expected": {"outcome": "ready_to_record"},
        "source": {"question_id": "q001", "provider": "pujia_school_question_bank", "lesson_name": "圆的周长"},
    }
    scenario.update(overrides)
    return scenario


# ---------- schema 校验:必填字段/枚举值 ----------


def test_valid_scenario_passes(tmp_path):
    assert validate_scenario(_scenario(tmp_path)) == []


@pytest.mark.parametrize("field", ["id", "title", "grade", "bucket", "misconception_seed"])
def test_missing_required_field(tmp_path, field):
    scenario = _scenario(tmp_path)
    scenario.pop(field)
    errors = validate_scenario(scenario)
    assert any("缺必填字段" in e and field in e for e in errors)


def test_missing_question_text(tmp_path):
    scenario = _scenario(tmp_path)
    scenario["question"]["text"] = ""
    assert any("question.text 缺失" in e for e in validate_scenario(scenario))


def test_missing_image_spec(tmp_path):
    scenario = _scenario(tmp_path)
    scenario["question"]["image"] = {"path": "pqfile_x.jpg"}  # 缺 sha256
    assert any("question.image" in e for e in validate_scenario(scenario))


_ENUM_BUILDERS = {
    "answer_type": lambda tmp_path, v: _scenario(
        tmp_path, reference_answer={"value": "1", "answer_type": v}),
    "visual_dependency": lambda tmp_path, v: _scenario(tmp_path, visual_dependency=v),
    "expected_outcome": lambda tmp_path, v: _scenario(tmp_path, expected={"outcome": v}),
}
_ENUM_INVALID_HINTS = {
    "answer_type": "answer_type 非法",
    "visual_dependency": "visual_dependency 非法",
    "expected_outcome": "expected.outcome",
}
_ENUM_CASES = (
    [("answer_type", v, True) for v in ["integer", "fraction", "decimal_1", "decimal_2", "text"]]
    + [("answer_type", "percent", False)]
    + [("visual_dependency", v, True) for v in ["required", "helpful", "none"]]
    + [("visual_dependency", "partial", False)]
    + [("expected_outcome", v, True) for v in ["ready_to_record", "needed_reveal", "not_ready"]]
    + [("expected_outcome", "yes", False)]
)


_ENUM_IDS = [f"{field}-{value}" for field, value, _ in _ENUM_CASES]


@pytest.mark.parametrize("field,value,is_valid", _ENUM_CASES, ids=_ENUM_IDS)
def test_enum_gates(tmp_path, field, value, is_valid):
    """三处枚举门(参考答案形态/题图依赖/预期收束):合法值全过,非法值逐个拦。"""
    errors = validate_scenario(_ENUM_BUILDERS[field](tmp_path, value))
    if is_valid:
        assert errors == []
    else:
        assert any(_ENUM_INVALID_HINTS[field] in e for e in errors)


# ---------- sha256 与实际文件一致 / 图路径存在 ----------


def test_sha256_mismatch_reported(tmp_path):
    scenario = _scenario(tmp_path)
    scenario["question"]["image"]["sha256"] = "0" * 64
    assert any("sha256 与实际文件不一致" in e for e in validate_scenario(scenario))


def test_image_path_missing_reported(tmp_path):
    scenario = _scenario(tmp_path)
    scenario["question"]["image"]["path"] = str(tmp_path / "no_such.jpg")
    assert any("图路径不存在" in e for e in validate_scenario(scenario))


def test_question_image_data_url_roundtrip(tmp_path):
    path, sha = _write_image(tmp_path, b"\x89PNG\r\n\x1a\nfake")
    data_url = question_image_data_url({"path": path, "sha256": sha})
    prefix, encoded = data_url.split(",", 1)
    assert prefix == "data:image/jpeg;base64"  # .jpg 后缀 → image/jpeg
    assert base64.b64decode(encoded) == b"\x89PNG\r\n\x1a\nfake"


def test_question_image_data_url_sha_mismatch_raises(tmp_path):
    path, _ = _write_image(tmp_path)
    with pytest.raises(ValueError, match="sha256 不符"):
        question_image_data_url({"path": path, "sha256": "0" * 64})


# ---------- 内核透图:假 gateway 断言 image_url 进请求体 ----------


def test_run_case_passes_image_through(tmp_path):
    # 只验 start 首问透图:清空剧本,start+finish 两次调用
    case = _scenario(tmp_path, student_turns=[])
    with kernel_env(tmp_path, [
        completion(open_json("先找题目里的已知条件。")),
        completion(json.dumps({"summary": "你算出了池塘半径 10 米。"}, ensure_ascii=False)),
    ]) as (fake, gateway):
        KernelSubject(gateway).run_case(case)
        # 首问调用(request[0])的第一条 user 消息应被渲染为 [text, image_url] 内容块
        first_messages = fake.requests[0]["messages"]
        user_content = next(m["content"] for m in first_messages if m["role"] == "user")
        image_blocks = [p for p in user_content if p.get("type") == "image_url"]
        assert len(image_blocks) == 1
        url = image_blocks[0]["image_url"]["url"]
        assert url.startswith("data:image/jpeg;base64,")
        assert base64.b64decode(url.split(",", 1)[1]) == b"\xff\xd8\xfffake-jpeg"


# ---------- 真实图池:根存在性 + 裸文件名解析(审查 #132 建议①) ----------

_BANK = Path(__file__).resolve().parents[2] / "edu_agent" / "api" / "static" / "bank"


def test_real_image_bank_root_exists_and_resolves():
    """图池根是 evals 的路径耦合点:目录迁移会让评测期静默 FileNotFoundError,CI 先拦。

    顺带验证裸文件名(pqfile_*.jpg)按图池根解析 + 真字节 sha256 对账通过。
    """
    images = sorted(_BANK.glob("*.jpg"))
    assert images, f"图池根缺失或为空:{_BANK}"
    path = images[0]
    data_url = question_image_data_url({
        "path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    assert data_url.startswith("data:image/jpeg;base64,")
    assert base64.b64decode(data_url.split(",", 1)[1]) == path.read_bytes()
