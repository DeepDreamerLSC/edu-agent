"""题图教学评测集 v1(#130):题图读取(path+sha256→data URL)与 schema 校验。

与 runner 同层:只做确定性文件/字段校验,不调模型、不感知 gateway。
图字节落在 edu_agent/api/static/bank(git 追踪),本模块只按 sha256 对账,
不搬字节、不嵌字节(#130 p7)。
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path

# 图池目录:issue #130「257 张字节已在 static/bank」,路径相对此目录解析。
_BANK_DIR = Path(__file__).resolve().parents[1] / "api" / "static" / "bank"

ANSWER_TYPES = frozenset({"integer", "fraction", "decimal_1", "decimal_2", "text"})
VISUAL_DEPENDENCIES = frozenset({"required", "helpful", "none"})
OUTCOMES = frozenset({"ready_to_record", "needed_reveal", "not_ready"})

_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
         ".webp": "image/webp"}


def _resolve(path: str) -> Path:
    """绝对路径直用;裸文件名/相对路径解析到图池目录。"""
    candidate = Path(path)
    return candidate if candidate.is_absolute() else _BANK_DIR / candidate


def question_image_data_url(image: dict) -> str:
    """题图 {path, sha256} → data URL:读文件、sha256 对账、base64(#130 v1)。

    sha256 不符抛 ValueError;文件缺失抛 FileNotFoundError——都是内容缺陷,
    由 runner 按内容失败入台账(重跑不改变),不按环境失败重试。
    """
    path = _resolve(image["path"])
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != image["sha256"]:
        raise ValueError(f"题图 sha256 不符:{image['path']}")
    mime = _MIME.get(path.suffix.lower(), "application/octet-stream")
    return f"data:{mime};base64,{base64.b64encode(payload).decode('ascii')}"


def _check_image(question: dict, qid: str, errors: list[str]) -> None:
    image = question.get("image")
    if not isinstance(image, dict) or not image.get("path") or not image.get("sha256"):
        errors.append(f"{qid}: question.image 缺 path/sha256")
        return
    path = _resolve(image["path"])
    if not path.is_file():
        errors.append(f"{qid}: 图路径不存在 {image['path']}")
        return
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != image["sha256"]:
        errors.append(f"{qid}: sha256 与实际文件不一致")


def validate_scenario(scenario: dict) -> list[str]:
    """校验单条 v1 场景(#130),返回错误列表(空=通过)。

    覆盖:必填字段、枚举值(answer_type/visual_dependency/outcome)、
    sha256 与实际文件一致、图路径存在。纯确定性校验,不调模型。
    """
    errors: list[str] = []
    qid = scenario.get("id") or "<no-id>"

    for field in ("id", "title", "grade", "bucket", "misconception_seed"):
        if not scenario.get(field):
            errors.append(f"{qid}: 缺必填字段 {field}")

    question = scenario.get("question")
    if not isinstance(question, dict) or not question.get("text"):
        errors.append(f"{qid}: question.text 缺失")
    else:
        _check_image(question, qid, errors)

    answer = scenario.get("reference_answer")
    if not isinstance(answer, dict) or not answer.get("value"):
        errors.append(f"{qid}: reference_answer.value 缺失")
    elif answer.get("answer_type") not in ANSWER_TYPES:
        errors.append(f"{qid}: answer_type 非法 {answer.get('answer_type')!r}")

    if scenario.get("visual_dependency") not in VISUAL_DEPENDENCIES:
        errors.append(f"{qid}: visual_dependency 非法 {scenario.get('visual_dependency')!r}")

    expected = scenario.get("expected")
    if not isinstance(expected, dict) or expected.get("outcome") not in OUTCOMES:
        errors.append(f"{qid}: expected.outcome 缺失/非法 {expected and expected.get('outcome')!r}")

    student_turns = scenario.get("student_turns")
    if not isinstance(student_turns, list) or not student_turns or \
            not all(isinstance(t, str) and t for t in student_turns):
        errors.append(f"{qid}: student_turns 非空字符串列表")

    source = scenario.get("source")
    if not isinstance(source, dict) or not all(source.get(k) for k in
                                               ("question_id", "provider", "lesson_name")):
        errors.append(f"{qid}: source 缺 question_id/provider/lesson_name")

    return errors
