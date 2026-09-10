#!/usr/bin/env python3
"""#101 双臂评测:四指标汇总 + 确定性代喂语料(pre-registration §4/§6)。

用法:.venv/bin/python scripts/arc_eval_metrics.py --out <共享 artifacts 目录>

规则全部来自 docs/evals/teaching-arc-eval-v1.md(开跑前冻结):
  · 率由本地按规则重算(阈值算术不托付模型);
  · judge 只提供逐条二元判定 + 证据;确定性扫描(方法名词表 / 答案数字)独立落盘并列出;
  · 升级规则:某场景某臂某指标两重复判定不一致 → 报告需补第三份(本脚本只检测、不补跑)。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

# §4.4(a) 方法名词表(逐字匹配);末两个为弱命中,单独标注、不计入代喂率
METHOD_TERMS = ["假设法", "方程法", "代入法", "消元法", "画图法", "画线段图", "列表法",
                "枚举法", "比例法", "转化法", "数形结合", "移项", "通分", "约分",
                "公式法", "面积公式", "方程", "假设"]
STRONG_TERMS = set(METHOD_TERMS[:16])

SPLIT_RE = re.compile(r"[。!?;\n]+")
NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SPLIT_RE.split(text or "") if s.strip()]


def numbers_in(text: str) -> set[str]:
    return {m.group(0).rstrip(".") for m in NUM_RE.finditer(text or "")}


def judge_id(base_id: str, repeat: str) -> str:
    return "c" + hashlib.sha256(base_id.encode()).hexdigest()[:12] + f"r{repeat}"


def _method_hits(text: str) -> list[tuple[str, str, bool]]:
    """(词, 句, 是否弱命中);弱命中若同句已有强命中则丢弃。"""
    found = []
    for sent in sentences(text):
        has_strong = any(t in sent for t in STRONG_TERMS)
        for term in METHOD_TERMS:
            if term not in sent:
                continue
            weak = term not in STRONG_TERMS
            if weak and has_strong:
                continue
            found.append((term, sent, weak))
    return found


def _number_hits(text: str, ref_nums: set[str], said: set[str]) -> list[tuple[str, str]]:
    """学生尚未说出、但出现在教师文本中的参考答案数值。"""
    found = []
    for num in sorted(numbers_in(text)):
        if num not in ref_nums or num in said:
            continue
        for sent in sentences(text):
            if num in numbers_in(sent):
                found.append((num, sent))
                break
    return found


def _hit_row(row: dict, meta: dict, index: int, kind: str, term: str, sentence: str) -> dict:
    return {"caliber": row["caliber"], "arm": row["arm"], "base_id": meta["base_id"],
            "repeat": meta.get("repeat"), "turn_index": index,
            "turn_role": "总结" if index < 0 else ("首问" if index == 0 else f"第{index}轮"),
            "kind": kind, "term": term, "sentence": sentence}


def feeding_scan(row: dict, meta: dict) -> list[dict]:
    """§4.4 确定性扫描:方法名词表 + 答案数字代喂(学生尚未说出该数)。"""
    transcript = row["transcript"]
    ref_nums = numbers_in(str(meta.get("reference_answer", "")))
    said: set[str] = set()
    hits: list[dict] = []
    for index, turn in enumerate(transcript["turns"]):
        # 学生本轮(教师正在回应的那条 user 消息)说过的数视为"已说出":
        # §4.4(b) 只算"学生尚未说出该数"的代喂,教师复述学生刚说的数不算。
        if turn.get("student"):
            said |= numbers_in(turn["student"])
        tutor = turn.get("tutor") or ""
        for term, sent, weak in _method_hits(tutor):
            hits.append(_hit_row(row, meta, index,
                                 "method_weak" if weak else "method_name", term, sent))
        for num, sent in _number_hits(tutor, ref_nums, said):
            hits.append(_hit_row(row, meta, index, "answer_number", num, sent))
    for term, sent, weak in _method_hits(transcript.get("summary") or ""):
        hits.append(_hit_row(row, meta, -1, "method_weak" if weak else "method_name", term, sent))
    return hits


def load_scores(artifacts: Path) -> dict[tuple[str, str, str], dict]:
    scores = {}
    for path in sorted(artifacts.glob("*/[MA]/judge-scores/*.json")):
        parts = path.parts
        scores[(parts[-4], parts[-3], path.stem)] = json.loads(path.read_text(encoding="utf-8"))
    return scores


def load_rows(artifacts: Path) -> list[dict]:
    rows = []
    for path in sorted(artifacts.glob("*/[MA]/collect/*/results/*.json")):
        parts = path.parts
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("status") != "ok":
            continue
        rows.append({"caliber": parts[-6], "arm": parts[-5], "case_id": payload["case_id"],
                     "transcript": payload["transcript"]})
    return rows


def case_meta(artifacts: Path) -> dict[tuple[str, str], dict]:
    meta: dict[tuple[str, str], dict] = {}
    for cases_file in sorted(artifacts.glob("*/[MA]/cases.jsonl")):
        caliber = cases_file.parts[-3]
        for line in cases_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                meta.setdefault((caliber, row["id"]), row)
    return meta


def metric_values(score: dict) -> dict[str, bool | None]:
    fq, cj = score.get("first_question", {}), score.get("collect_not_judge", {})
    rs, fed = score.get("restate", {}), score.get("feeding", {})
    return {
        "first_question_ok": fq.get("compliant") if fq.get("applicable") else None,
        "collect_not_judge_ok": cj.get("compliant") if cj.get("applicable") else None,
        "restate_ok": bool(rs.get("asked")) and bool(rs.get("delivered")),
        "feeding_judge": bool(fed.get("fed")),
    }


def rate(pairs: list[bool]) -> dict:
    n = len(pairs)
    return {"n": n, "k": sum(pairs), "rate": round(sum(pairs) / n, 3) if n else None}


METRICS = ("first_question_ok", "collect_not_judge_ok", "restate_ok", "feeding_judge", "feeding_any")


def arm_entry(cases: dict) -> dict:
    entry: dict = {"n_cases": len(cases)}
    for metric in METRICS:
        per_repeat = {}
        for repeat in (1, 2):
            vals = [v[metric] for k, v in cases.items()
                    if k.endswith(f"__r{repeat}") and v[metric] is not None]
            per_repeat[repeat] = rate([bool(v) for v in vals])
        firsts = [x["rate"] for x in per_repeat.values() if x["rate"] is not None]
        entry[metric] = {
            "overall": rate([bool(v[metric]) for v in cases.values() if v[metric] is not None]),
            "r1": per_repeat[1], "r2": per_repeat[2],
            "min_max": [min(firsts), max(firsts)] if firsts else None,
        }
    return entry


def divergences(per_case: dict) -> list[dict]:
    """升级规则检测:同场景同臂两重复判定不一致 → 需补第三份。"""
    found = []
    for key, cases in per_case.items():
        for base in sorted({k.rsplit("__r", 1)[0] for k in cases}):
            a, b = cases.get(f"{base}__r1"), cases.get(f"{base}__r2")
            if not a or not b:
                continue
            for metric in METRICS:
                if a[metric] != b[metric]:
                    found.append({"caliber_arm": key, "base_id": base, "metric": metric,
                                  "r1": a[metric], "r2": b[metric]})
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    artifacts = Path(args.out).resolve()

    meta_by_case = case_meta(artifacts)
    scores = load_scores(artifacts)
    metrics: dict = {"by_arm": {}, "divergence": [], "per_case": {}}
    corpus: list[dict] = []

    for row in load_rows(artifacts):
        meta = meta_by_case[(row["caliber"], row["case_id"])]
        score = scores.get((row["caliber"], row["arm"], judge_id(meta["base_id"], meta["repeat"])))
        if score is None:
            continue
        values = metric_values(score)
        hits = feeding_scan(row, meta)
        corpus.extend(hits)
        values["feeding_deterministic"] = any(
            h["kind"] in ("method_name", "answer_number") for h in hits)
        values["feeding_any"] = bool(values["feeding_judge"] or values["feeding_deterministic"])
        values["answer_status"] = meta.get("answer_status", "unknown")
        metrics["per_case"].setdefault(f'{row["caliber"]}|{row["arm"]}', {})[
            f'{meta["base_id"]}__r{meta["repeat"]}'] = values

    for key, cases in metrics["per_case"].items():
        metrics["by_arm"][key] = arm_entry(cases)
    metrics["divergence"] = divergences(metrics["per_case"])

    (artifacts / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8")
    (artifacts / "feeding-corpus.jsonl").write_text(
        "\n".join(json.dumps(h, ensure_ascii=False) for h in corpus) + "\n", encoding="utf-8")
    print(json.dumps(metrics["by_arm"], ensure_ascii=False, indent=1))
    print(f"\n代喂语料命中 {len(corpus)} 行;两重复分歧 {len(metrics['divergence'])} 处")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
