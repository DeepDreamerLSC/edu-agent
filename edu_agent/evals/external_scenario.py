"""外部数据 canonical 层 v1(#368 用户裁定 2026-09-18):薄 schema + 共享 validator。

定位(章程原话):数据是证据,scenario 才是实验——v1 层保证据保真,slice 层保实验
可控。本模块只做「记录形状校验 + 保真指纹」,不做任何 mapping DSL/插件框架/自动
猜测(禁区);importer 与后续人工筛选共用同一 validator。

流程位置:第三方原件 → **canonical v1 record(本层)** → 人工/规则挑选 → slice
→ 可执行 scenario(才生成 student_turns/steps)。v1 不生成 student_turns。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

EXTERNAL_SCHEMA_VERSION = "edu_agent_external_scenario/v1"
EXTERNAL_ROLES = frozenset({"student", "tutor"})
SOURCE_REQUIRED_KEYS = ("dataset", "upstream_id", "license", "version")


def external_fingerprint(record: dict) -> str:
    """外部证据指纹(sha256):source + upstream_id + 内容面。

    与 scenario_corpus.scenario_fingerprint 的分工(#369 审 P3-3,防 grep 混淆):
    那个是仓内 corpus 场景的切片指纹;本函数只对 external v1 record 负责——

    canonical 载荷 = source/problem/reference_dialogue/annotations(排序键,
    ensure_ascii=False);id/schema_version/fingerprint 是派生面不进指纹——
    指纹要答的问题是「这份证据的实质内容是否一字未动」。
    """
    payload = {key: record[key] for key in
               ("source", "problem", "reference_dialogue", "annotations")}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_source(record: dict, errors: list[str]) -> None:
    source = record.get("source")
    if not isinstance(source, dict):
        errors.append("source 必须为对象(含 dataset/upstream_id/license/version 四件套)")
        return
    for key in SOURCE_REQUIRED_KEYS:
        value = source.get(key)
        if not (isinstance(value, str) and value.strip()):
            errors.append(f"source.{key} 必须为非空字符串(四件套缺一不可)")
    if "modified" in source and not isinstance(source["modified"], bool):
        errors.append("source.modified 若有必须为布尔")


def _validate_problem(record: dict, base_dir: Path, expected_answer: str | None,
                      errors: list[str]) -> None:
    problem = record.get("problem")
    if not isinstance(problem, dict):
        errors.append("problem 必须为对象")
        return
    text = problem.get("text")
    if not (isinstance(text, str) and text.strip()):
        errors.append("problem.text 必须为非空字符串")
    answer = problem.get("answer")
    if answer is not None and not isinstance(answer, str):
        errors.append("problem.answer 有则必须为字符串(原样保真,不翻译不改写)")
    if expected_answer is not None and answer != expected_answer:
        errors.append("problem.answer 与上游原答不一致(保真被破坏:不翻译/不改写/不去空白)")
    if problem.get("analysis") is not None and not isinstance(problem.get("analysis"), str):
        errors.append("problem.analysis 有则必须为字符串")
    grade = problem.get("grade")
    if grade is not None and not isinstance(grade, str):
        errors.append("problem.grade 有则必须为字符串")
    tags = problem.get("knowledge_tags")
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        errors.append("problem.knowledge_tags 必须为字符串列表(无则空列表,不猜)")
    _validate_image(problem.get("image"), base_dir, errors)


def _validate_image(image: object, base_dir: Path, errors: list[str]) -> None:
    """image 引用:文件必须存在且 sha256 一致(引用即校验,不给悬空引用过闸)。"""
    if image is None:
        return
    if not isinstance(image, dict) or not isinstance(image.get("path"), str):
        errors.append("problem.image 有则必须为 {path, sha256} 对象")
        return
    target = base_dir / image["path"]
    if not target.is_file():
        errors.append(f"image 文件不存在:{image['path']}(引用即冻结,路径相对运行根)")
        return
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != image.get("sha256"):
        errors.append(f"image sha256 不符:{image['path']}(期望 {image.get('sha256')},实际 {digest[:16]}…)")


def _validate_dialogue(record: dict, errors: list[str]) -> None:
    dialogue = record.get("reference_dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        errors.append("reference_dialogue 必须为非空列表(v1 是证据层,对话即证据主体)")
        return
    for index, turn in enumerate(dialogue):
        if not isinstance(turn, dict) or turn.get("role") not in EXTERNAL_ROLES:
            errors.append(f"reference_dialogue[{index}].role 必须为 student/tutor"
                          f"(实际 {turn.get('role') if isinstance(turn, dict) else type(turn).__name__!r})")
        elif not (isinstance(turn.get("text"), str) and turn["text"].strip()):
            errors.append(f"reference_dialogue[{index}].text 必须为非空字符串")


def validate_external_scenario(record: dict, *, base_dir: Path | str = ".",
                               expected_answer: str | None = None) -> list[str]:
    """共享 validator(纯函数):返回错误清单,空列表 = 合法。

    importer(逐条)与人工筛选(slice 前)共用同一口径;expected_answer 是保真
    核对的锚——importer 传上游原答,answer 改写即刻红(不翻译/不改写/不去空白)。
    """
    base = Path(base_dir)
    errors: list[str] = []
    if not isinstance(record, dict):
        return ["记录必须为对象"]
    if record.get("schema_version") != EXTERNAL_SCHEMA_VERSION:
        errors.append(f"schema_version 必须为 {EXTERNAL_SCHEMA_VERSION}")
    if not (isinstance(record.get("id"), str) and record["id"].strip()):
        errors.append("id 必须为非空字符串")
    _validate_source(record, errors)
    _validate_problem(record, base, expected_answer, errors)
    _validate_dialogue(record, errors)
    if not isinstance(record.get("annotations"), dict):
        errors.append("annotations 必须为对象(无据字段留 null,不造数据)")
    if "fingerprint" in record and record["fingerprint"] != external_fingerprint(record):
        errors.append("fingerprint 与内容面复算不一致(证据被改动或指纹伪造)")
    return errors


def load_normalized(path: Path | str, *, base_dir: Path | str = ".") -> list[dict]:
    """读回 normalized jsonl 并逐条过闸;首错即抛,带行号。

    消费者 = #368 后半程的人工/slice 侧(本单先行建闸,暂无仓内调用方——
    别做孤儿 API 超过一个里程碑,#369 审 P3-2)。
    """
    records = []
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        errors = validate_external_scenario(record, base_dir=base_dir)
        if errors:
            raise ValueError(f"{path}:{line_no} 未过闸:{';'.join(errors[:3])}")
        records.append(record)
    return records
