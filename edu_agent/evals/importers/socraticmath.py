"""SocraticMATH importer(#368 适配真原件 837da0b):冻结原件 → canonical v1。

真原件形态(与首个 fixture 版假设不同,逐条实测 2026-09-21):
- train/val:整文件 JSON 数组(扩展名 .jsonl 但非逐行);记录 {id, conversations},
  from 值全集 = user/assistant(无 human/gpt);**首轮 100% assistant 且装的是学生题面**
  (上游打包痕迹),之后 assistant=老师、user=学生——turn0 按位置归 student。
- test:SocratesMATH_testdata.jsonl = 3,440 行 [历史, 老师下一轮] 逐对样本;链式重组
  elem0[k+1] == elem0[k] + "老师:" + elem1[k] + "\\n学生:<回复>\\n" 后归 685 个母对话
  (组内 2,755 个转移全部精确验证;6,846 = 5,476 train + 685 val + 685 test 平账)。
- _sol 文件与非 _sol 同 id 同对话,仅首轮 value 尾部多拼【解析】→ 只读非 _sol,
  解析走 csv,否则条数翻倍。
- csv(gb18030,8 列,6,846 行,无 id 列):题目/对话/解析/知识点/题型/难度/参考答案/
  方法提示。**对齐偏离记录**:上游没有跨文件 id,采用文本对齐——dialogue 首个学生块
  与 csv.对话 首个学生块,去全部空白(re.sub(r"\\s+",""))后相等即同一条;实测 6,846/6,846
  全量命中、零跨 split 碰撞(csv 对话列 6,846 键唯一)。
- jsonl/ 子目录 6,818 行(较 csv 少 28)且与 csv 解析列有 9 处差异 → 不用它,csv 为元数据权威。
- csv 有 14 行含 "??"(上游自身把 ² 等字符写坏)——只在 csv.对话 列,对齐键与解析列不受影响;
  对话正文一律取 jsonl 侧(无损),csv 只供元数据。

字段映射:problem.text=csv.题目;problem.analysis=csv.解析(整段保真);
problem.answer=解析中"故答案为"子串(3,034/6,846,逐字 substring 非改写;无则 None);
knowledge_tags=csv.知识点 按';'切;annotations.difficulty=csv.难度('1'-'5')。
expected_answer 锚 = problem.answer(None 时不设锚,保真由指纹兜底)。

红线:不生成 student_turns、不编译可执行 case;answer/analysis 原样搬运,不改写不翻译。

用法(仓根;原件目录 external/socraticmath/ 已 gitignore,license=CC BY-NC 4.0
人批 2026-09-20):
  .venv/bin/python -m edu_agent.evals.importers.socraticmath \
    external/socraticmath/SocraticMath-837da0b/data \
    edu_agent/evals/datasets/external_normalized/socraticmath.jsonl
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

from ..external_scenario import (
    EXTERNAL_SCHEMA_VERSION,
    external_fingerprint,
    validate_external_scenario,
)

DATASET_NAME = "SocraticMATH"
LICENSE = "CC BY-NC 4.0"
VERSION = "837da0b"
# 显式映射表(章程反自动猜测):未知 from 值 fail closed。真原件实测 from 全集 =
# user/assistant(fixtrue 时代的 human/gpt 保留,防上游回退);首轮按位置归 student(见模块 docstring)。
FROM_ROLE_MAP = {"human": "student", "gpt": "tutor", "user": "student", "assistant": "tutor"}
# test 链式重组的说话人标签(母对话文本 = "学生:…\\n老师:…\\n…")
_STUDENT_LABEL = "学生："
_TUTOR_LABEL = "老师："
# 答案锚:解析列"故答案为"后的逐字子串(可选冒号,到句号类标点止);不命中即 None,不造数据。
_ANSWER_PATTERN = re.compile(r"故答案为[:：]?\s*([^。．]+)")
# 对齐规范化:去全部空白(含全角空格,Python \s 在 unicode 模式覆盖 U+3000)。
_ALIGN_STRIP_WS = re.compile(r"\s+")
# 说话人标签行(行首锚定):学生:/老师:——按标签位置切轮,题面内换行不破坏切分。
_LABEL_LINE = re.compile(r"^(学生：|老师：)", re.M)


def _align_key(text: str) -> str:
    """对齐键:去全部空白。上游两侧文本只在空白与空位符号(____/　)上有排印差异。"""
    return _ALIGN_STRIP_WS.sub("", text)


def _first_student_block(dialogue: str) -> str:
    """csv.对话 列的首个学生块(到首个"老师:"前,剥"学生:"前缀)——对齐键的 csv 侧。"""
    idx = dialogue.find(_TUTOR_LABEL)
    head = dialogue[:idx] if idx != -1 else dialogue
    return head[len(_STUDENT_LABEL):] if head.startswith(_STUDENT_LABEL) else head


def _split_labeled_dialogue(dialogue: str, *, origin: str) -> list[dict]:
    """母对话文本("学生:…\\n老师:…")→ [{role, text}]。

    按标签行位置切分:题面内的换行、题面后独立成行的"请求语"(这道题怎么解?/
    教我一下这道题目 等)都归属当前轮,不丢字。首标签必须是 学生:,未知标签 fail closed。
    仅剥轮与轮之间的单个分隔换行(母对话构造时统一追加),轮内换行保真——
    实测原件轮体不以换行结尾(6,105/6,106 全 1 例见 _conversations_to_dialogue 旁路)。
    """
    turns: list[dict] = []
    marks = list(_LABEL_LINE.finditer(dialogue))
    if not marks or marks[0].group(1) != _STUDENT_LABEL:
        raise ValueError(f"{origin}: 对话不以 学生： 开头(原件损坏?)")
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(dialogue)
        body = dialogue[mark.end():end]
        body = body[:-1] if body.endswith("\n") else body  # 只剥分隔换行,不动轮内内容
        if not body.strip():
            raise ValueError(f"{origin}: 空 {mark.group(1)} 轮(原件损坏?)")
        turns.append({"role": "student" if mark.group(1) == _STUDENT_LABEL else "tutor",
                      "text": body})
    return turns


def _conversations_to_turns(conversations: list[dict], *, origin: str) -> list[dict]:
    """train/val conversations → [{role, text}],value 逐字保真(零文本手术)。

    turn0=学生题面(实测 6,161/6,161 首轮 assistant,题面塞进 assistant 轮的上游打包
    痕迹,按位置归 student);之后 assistant=老师、user=学生;from 未知值 fail closed。
    """
    turns = []
    for index, turn in enumerate(conversations):
        role = FROM_ROLE_MAP.get(turn.get("from"))
        if role is None:
            raise ValueError(
                f"{origin}: conversations[{index}].from={turn.get('from')!r} 不在映射表"
                f"{sorted(FROM_ROLE_MAP)}——扩充显式映射,不做自动猜测")
        turns.append({"role": "student" if index == 0 else role, "text": turn["value"]})
    return turns


def _rebuild_test_mothers(path: Path, *, expected: int) -> list[str]:
    """testdata.jsonl(逐对样本)→ 母对话文本列表;数量须等于 expected(685,防原件漂移)。

    分组:elem0 无"老师:" = 新母对话起点(学生题面);组内链式:
    elem0[k+1] == elem0[k] + "老师:" + elem1[k] + "\\n学生:<回复>\\n"(结构实测成立)。
    母对话 = 末行 elem0 + "老师:" + elem1(末行 elem1 即收尾老师轮)。
    """
    pairs = [json.loads(line) for line in
             path.read_text(encoding="utf-8").splitlines() if line.strip()]
    groups: list[list[int]] = []
    current: list[int] | None = None
    for index, pair in enumerate(pairs):
        if _TUTOR_LABEL not in pair[0]:
            if current is not None:
                groups.append(current)
            current = [index]
        elif current is None:
            raise ValueError(f"{path.name}: 第 {index + 1} 行带老师轮但无母对话起点(文件损坏?)")
        else:
            current.append(index)
    if current is not None:
        groups.append(current)
    if len(groups) != expected:
        raise ValueError(f"{path.name}: 重组得 {len(groups)} 个母对话 ≠ 冻结原件 {expected}"
                         "(原件目录可能不对或文件损坏)")
    return [pairs[g[-1]][0] + _TUTOR_LABEL + pairs[g[-1]][1] + "\n" for g in groups]


def _load_csv_metadata(data_dir: Path) -> dict[str, dict]:
    """csv(gb18030)→ {对齐键: 元数据};对话列首学生块作键,6,846 键须唯一。"""
    with (data_dir / "csv" / "SocratesMATH.csv").open(encoding="gb18030", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows or rows[0][:4] != ["题目", "对话", "解析", "知识点"]:
        raise ValueError("csv 表头与冻结原件不符(题目/对话/解析/知识点…),原件目录可能不对")
    index: dict[str, dict] = {}
    for number, row in enumerate(rows[1:], 1):
        key = _align_key(_first_student_block(row[1]))
        if not key:
            raise ValueError(f"csv 第 {number} 行对话列无有效学生块")
        if key in index:
            raise ValueError(f"csv 对话列对齐键碰撞(第 {number} 行),文本对齐不可用")
        index[key] = {"题目": row[0], "解析": row[2], "知识点": row[3], "难度": row[5]}
    return index


def _to_v1_record(*, split: str, seq: int, turns: list[dict],
                  meta: dict) -> dict:
    """对话轮 + csv 元数据 → v1 record(纯映射;不造数据,无据字段留 null/空)。"""
    analysis = meta["解析"].strip()
    match = _ANSWER_PATTERN.search(analysis)
    answer = match.group(1).strip() if match else None
    if answer is not None and answer not in analysis:
        raise ValueError(f"{split}:{seq}: 答案锚子串校验失败(不应发生)")
    knowledge_tags = [p.strip() for p in meta["知识点"].split(";") if p.strip()]
    record = {
        "schema_version": EXTERNAL_SCHEMA_VERSION,
        "id": f"{DATASET_NAME.lower()}_{split}_{seq}",
        "source": {
            "dataset": DATASET_NAME,
            "upstream_id": f"{split}:{seq}",
            "license": LICENSE,
            "version": VERSION,
            "modified": False,
        },
        "problem": {
            "text": meta["题目"].strip(),
            "answer": answer,
            "analysis": analysis,
            "image": None,
            "grade": None,
            "knowledge_tags": knowledge_tags,
        },
        "reference_dialogue": turns,
        "annotations": {"difficulty": meta["难度"].strip() or None,
                        "teacher_moves": [], "outcome": None},
    }
    record["fingerprint"] = external_fingerprint(record)
    return record


def collect_records(data_dir: Path | str,
                    expected_counts: dict[str, int]) -> tuple[list[dict], dict]:
    """三 split 归一为 (records, 统计)。对齐不到 csv 即中止(残差如实报,不硬造)。

    公开入口(02 §6:测试只导公开面);expected_counts 由调用方传冻结平账数或缩微数,
    数量对不上 fail closed,防原件漂移或传错目录。
    """
    data_path = Path(data_dir)
    csv_index = _load_csv_metadata(data_path)
    records: list[dict] = []
    stats = {"train": 0, "val": 0, "test": 0}

    def _turns_key(turns: list[dict]) -> str:
        return _align_key(turns[0]["text"])  # 首学生轮(题面+请求语)即对齐键

    def _add(split: str, seq: int, turns: list[dict], meta: dict) -> None:
        records.append(_to_v1_record(split=split, seq=seq, turns=turns, meta=meta))
        stats[split] += 1

    def _align_or_die(turns: list[dict], origin: str) -> dict:
        meta = csv_index.get(_turns_key(turns))
        if meta is None:
            raise ValueError(f"{origin}: 文本对齐未命中 csv(残差如实中止,不硬造)")
        return meta

    for split, filename in (("train", "SocratesMATH_traindata.jsonl"),
                            ("val", "SocratesMATH_valdata.jsonl")):
        path = data_path / filename
        items = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(items, list) or len(items) != expected_counts[split]:
            raise ValueError(f"{filename}: 记录数 {len(items) if isinstance(items, list) else '?'}"
                             f" ≠ 冻结原件 {expected_counts[split]}(原件目录可能不对)")
        for item in items:
            origin = f"{filename}:{item['id']}"
            turns = _conversations_to_turns(item["conversations"], origin=origin)
            _add(split, int(item["id"]), turns, _align_or_die(turns, origin))

    mothers = _rebuild_test_mothers(data_path / "SocratesMATH_testdata.jsonl",
                                    expected=expected_counts["test"])
    for seq, dialogue in enumerate(mothers, 1):
        origin = f"SocratesMATH_testdata.jsonl:mother{seq}"
        turns = _split_labeled_dialogue(dialogue, origin=origin)
        _add("test", seq, turns, _align_or_die(turns, origin))
    return records, stats


def import_socraticmath(input_dir: Path | str, output_path: Path | str,
                       expected_counts: dict[str, int] | None = None) -> dict:
    """冻结原件**数据目录**(…/SocraticMath-837da0b/data)→ normalized jsonl。

    逐条过闸(带原答保真锚);任一条不过闸即中止不落盘(证据层宁缺毋滥)。
    expected_counts 缺省为冻结原件平账数 train/val/test = 5,476/685/685(测试夹具可传
    缩微数)。返回统计 {records, train, val, test}。传文件路径会被明确指路(#369 审 P3-1)。
    """
    input_path = Path(input_dir)
    if input_path.is_file():
        raise ValueError(f"首参是冻结原件**数据目录**(含 SocratesMATH_*.jsonl 与 csv/),"
                         f"不是文件:{input_path}(如 external/socraticmath/"
                         "SocraticMath-837da0b/data)")
    required = [input_path / name for name in
                ("SocratesMATH_traindata.jsonl", "SocratesMATH_valdata.jsonl",
                 "SocratesMATH_testdata.jsonl")]
    if not all(p.is_file() for p in required):
        raise ValueError(f"{input_dir} 下缺 SocratesMATH_{{train,val,test}}data.jsonl"
                         "(首参应为 external/socraticmath/SocraticMath-837da0b/data)")
    counts = expected_counts or {"train": 5476, "val": 685, "test": 685}
    csv_index = _load_csv_metadata(input_path)
    records, stats = collect_records(input_path, counts)
    for record in records:
        errors = validate_external_scenario(
            record, base_dir=input_path, expected_answer=record["problem"]["answer"])
        if errors:
            raise ValueError(f"{record['id']} 未过闸:{';'.join(errors[:3])}")
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    return {"records": len(records), "train": stats["train"], "val": stats["val"],
            "test": stats["test"]}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2:
        print("用法:python -m edu_agent.evals.importers.socraticmath <原件数据目录> <输出.jsonl>\n"
              "示例:python -m edu_agent.evals.importers.socraticmath "
              "external/socraticmath/SocraticMath-837da0b/data "
              "edu_agent/evals/datasets/external_normalized/socraticmath.jsonl"
              "  # 首参=数据目录(含 SocratesMATH_*.jsonl 与 csv/),非单个文件",
              file=sys.stderr)
        return 2
    try:
        stats = import_socraticmath(argv[0], argv[1])
    except (ValueError, KeyError, OSError, json.JSONDecodeError,
            UnicodeDecodeError, csv.Error) as exc:
        print(f"import 失败:{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(f"import-ok {argv[1]} records={stats['records']} "
          f"(train={stats['train']} val={stats['val']} test={stats['test']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
