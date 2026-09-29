#!/usr/bin/env python3
"""D6/D7 独立 gold 集机械抽样脚本(执行 spec v0.1,待冻结后单次执行)。

确定性保证:同 seed + 同输入 = 同输出;零网络零模型;逐行可审计。
用法:uv run python d6d7_sample.py --results-dir <round>/results --spec <spec.yaml> --out manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from pathlib import Path

SEED = 2617289367
SEED_DERIVATION = 'int("9c00aa97", 16)'
PROTOCOL_FREEZE_SHA = "9c00aa9715aaf265"  # 前 16 位;完整值在协议冻结行
LAYER_QUOTA = {"help_sought_giving": 8, "help_sought_no_giving": 8,
               "no_help_giving": 7, "no_help_no_giving": 7}
MAX_ATTEMPTS = 50  # 结构性替换尝试上限(§6)

# 条件 A:学生明确求助(表面匹配,非 S2 E1-E5 语义判定)
HELP_SEEKING_RE = re.compile(
    r"(怎么|如何|什么|为什么|能.*吗|可以.*吗|帮我|告诉|提示|指导|教我|"
    r"不会|不懂|不知道|卡住|想不出|不明白)")

# 条件 B:Tutor 给出步骤/方法(表面匹配,非 S2b B-0 语义判定)
GIVING_MOVE_RE = re.compile(
    r"(先算|先看|再算|然后|接下来|步骤|第一步|方法|公式|规则|定律|"
    r"先用|需要.*乘|需要.*除|需要.*加|需要.*减|等于|所以.*是)")


def _is_blank(text: str | None) -> bool:
    return not text or not text.strip()


def _slice_rank(session_id: str, turn_index: int) -> int:
    """seeded hash rank:对 slice_id 计算确定性 rank(冻结 seed 派生)。"""
    key = f"{session_id}:{turn_index}"
    return int(hashlib.sha256(
        f"{SEED}:{key}".encode()).hexdigest()[:16], 16)


def extract_slice(session: dict) -> dict | None:
    """tie-break:同一 session 内所有 eligible slice 中 seeded rank 最小者。

    (2026-09-29 预审 5885318757 修订:非最小 turn index——避免早期 turn 系统性偏置)
    """
    turns = session.get("transcript", {}).get("turns", [])
    best = None
    for i, turn in enumerate(turns):
        student = turn.get("student", "")
        tutor = turn.get("tutor", "")
        if _is_blank(student) or _is_blank(tutor):
            continue
        session_id = session["transcript"].get("session_id",
            session.get("case_id", f"unknown-{i}"))
        rank = _slice_rank(session_id, i)
        if best is None or rank < best[0]:
            best = (rank, {
                "session_id": session_id,
                "case_id": session.get("case_id", ""),
                "turn_index": i,
                "slice_id": f"{session.get('case_id', '?')}:{i}",
                "student_text": student,
                "tutor_text": tutor,
                "question": session.get("question", {}),
                "tie_break_rank": rank,
            })
    return best[1] if best else None


def classify(slice_data: dict) -> tuple[bool, bool]:
    """条件 A(求助)× 条件 B(给出)。"""
    help_sought = bool(HELP_SEEKING_RE.search(slice_data["student_text"]))
    giving = bool(GIVING_MOVE_RE.search(slice_data["tutor_text"]))
    return help_sought, giving


def layer_name(help_sought: bool, giving: bool) -> str:
    return ("help_sought_giving" if help_sought else "no_help") + \
           ("_giving" if giving else "_no_giving")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    # 1. 读全部 session,提取 primary slice(tie-break)
    candidates = []
    invalid = []
    for path in sorted(args.results_dir.glob("*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        if result.get("status") != "ok":
            invalid.append({"case_id": result.get("case_id"), "reason": f"status={result.get('status')}"})
            continue
        transcript = result.get("transcript", {})
        if not transcript.get("question_id") and not result.get("question"):
            invalid.append({"case_id": result.get("case_id"), "reason": "question_missing"})
            continue
        slice_data = extract_slice(result)
        if slice_data is None:
            invalid.append({"case_id": result.get("case_id"), "reason": "no_eligible_slice"})
            continue
        # 注入 question(从 transcript 或顶层)
        if not slice_data.get("question") and result.get("question"):
            slice_data["question"] = result["question"]
        candidates.append(slice_data)

    # 2. 分层
    layers: dict[str, list[dict]] = {name: [] for name in LAYER_QUOTA}
    for s in candidates:
        a, b = classify(s)
        s["stratum_proxy_help"] = a
        s["stratum_proxy_giving"] = b
        layers[layer_name(a, b)].append(s)

    # 3. 每层内按 session_id 排序 + seed 随机序
    rng = random.Random(SEED)
    for name in layers:
        layers[name].sort(key=lambda s: s["session_id"])
        rng.shuffle(layers[name])  # 确定性:同 seed 同序

    # 4. 按配额抽取;层内不足从最大剩余层补
    selected = []
    replacements = []
    attempt_count = 0

    def try_fill(layer_name: str, quota: int) -> list[dict]:
        nonlocal attempt_count
        picked = []
        pool = layers[layer_name]
        for s in pool:
            if len(picked) >= quota:
                break
            attempt_count += 1
            picked.append(s)
        if len(picked) < quota:
            # 层内不足:从最大剩余层按同 seed 序补
            # 补位 tie 规则(预审 5885318757):数量并列时按固定层序
            _LAYER_ORDER = ("help_sought_giving", "help_sought_no_giving",
                            "no_help_giving", "no_help_no_giving")
            _used = {n: len([x for x in selected if x.get("_layer") == n])
                    for n in layers}
            remaining = sorted(
                [(n, len(layers[n]) - _used.get(n, 0))
                 for n in _LAYER_ORDER if len(layers[n]) > 0],
                key=lambda x: (-x[1], _LAYER_ORDER.index(x[0])))
            for src_name, _ in remaining:
                if src_name == layer_name or len(picked) >= quota:
                    break
                for s in layers[src_name]:
                    if len(picked) >= quota:
                        break
                    if s not in picked:
                        attempt_count += 1
                        s["_borrowed_from"] = src_name
                        picked.append(s)
        return picked

    for name, quota in LAYER_QUOTA.items():
        layer_picked = try_fill(name, quota)
        for s in layer_picked:
            s["_layer"] = name
        selected.extend(layer_picked)

    # 5. 上限检查
    if len(selected) < 30:
        print(f"FAIL: only {len(selected)}/30 slices obtained "
              f"after {attempt_count} attempts (max {MAX_ATTEMPTS})")
        return 1

    # 6. 生成 manifest
    _candidate_ids = sorted(s["slice_id"] for s in candidates)
    _input_hash = hashlib.sha256("\n".join(_candidate_ids).encode()).hexdigest()
    # 原始输入完整性(预审 5885823950):不只 hash 最终 slice ID——还记原始
    # 64 个 source JSON 内容的排序聚合 hash,证明「输入没变」不只是「ID 没变」
    _source_hashes = sorted(
        hashlib.sha256(path.read_bytes()).hexdigest()
        for path in args.results_dir.glob("*.json"))
    _source_results_hash = hashlib.sha256(
        "\n".join(_source_hashes).encode()).hexdigest()
    import sys
    manifest = {
        "spec_version": "v0.1",
        "python_version": sys.version,
        "input_candidate_ids_sha256": _input_hash,
        "source_results_sha256": _source_results_hash,
        "source_file_count": len(_source_hashes),
        "script_sha256": hashlib.sha256(
            Path(__file__).read_bytes()).hexdigest(),
        "protocol_freeze_sha_prefix": PROTOCOL_FREEZE_SHA,
        "seed": SEED,
        "seed_derivation": SEED_DERIVATION,
        "candidate_pool_size": len(candidates),
        "invalid_count": len(invalid),
        "invalid_details": invalid,
        "layer_sizes": {n: len(layers[n]) for n in layers},
        "layer_quota": LAYER_QUOTA,
        "total_selected": len(selected),
        "total_attempts": attempt_count,
        "selected": [
            {
                "slice_id": s["slice_id"],
                "session_id": s["session_id"],
                "case_id": s["case_id"],
                "turn_index": s["turn_index"],
                "stratum_proxy_help": s["stratum_proxy_help"],
                "stratum_proxy_giving": s["stratum_proxy_giving"],
                "layer": s["_layer"],
                "borrowed_from": s.get("_borrowed_from"),
            }
            for s in selected
        ],
    }

    args.out.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"Selected {len(selected)}/30 slices from {len(candidates)} candidates")
    print(f"Layer sizes: {manifest['layer_sizes']}")
    print(f"Manifest: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
