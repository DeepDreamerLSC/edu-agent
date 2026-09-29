#!/usr/bin/env python3
"""D6/D7 独立 gold 集机械抽样脚本(执行 spec v0.1,待冻结后单次执行)。

确定性保证:同 seed + 同输入 = 同输出;零网络零模型;逐行可审计。
用法:uv run python d6d7_sample.py --results-dir <round>/results --out manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

SEED = 2617289367
SEED_DERIVATION = 'int("9c00aa97", 16)'
PROTOCOL_FREEZE_SHA = "9c00aa9715aaf265"
LAYER_QUOTA = {"help_sought_giving": 8, "help_sought_no_giving": 8,
               "no_help_giving": 7, "no_help_no_giving": 7}
LAYER_ORDER = ("help_sought_giving", "help_sought_no_giving",
               "no_help_giving", "no_help_no_giving")
MAX_ATTEMPTS = 50

HELP_SEEKING_RE = re.compile(
    r"(怎么|如何|什么|为什么|能.*吗|可以.*吗|帮我|告诉|提示|指导|教我|"
    r"不会|不懂|不知道|卡住|想不出|不明白)")

GIVING_MOVE_RE = re.compile(
    r"(先算|先看|再算|然后|接下来|步骤|第一步|方法|公式|规则|定律|"
    r"先用|需要.*乘|需要.*除|需要.*加|需要.*减|等于|所以.*是)")


def _is_blank(text: str | None) -> bool:
    return not text or not text.strip()


def _slice_rank(session_id: str, turn_index: int) -> int:
    """seeded hash rank(冻结 seed 派生,确定性)。"""
    return int(hashlib.sha256(
        f"{SEED}:{session_id}:{turn_index}".encode()).hexdigest()[:16], 16)


def extract_slice(session: dict) -> dict | None:
    """tie-break:eligible slice 中 seeded rank 最小者(预审 5885318757)。"""
    turns = session.get("transcript", {}).get("turns", [])
    best = None
    for i, turn in enumerate(turns):
        student, tutor = turn.get("student", ""), turn.get("tutor", "")
        if _is_blank(student) or _is_blank(tutor):
            continue
        session_id = session["transcript"].get(
            "session_id", session.get("case_id", f"unknown-{i}"))
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
    """stratum_proxy_help × stratum_proxy_giving(表面分类,非 S2 语义)。"""
    return (bool(HELP_SEEKING_RE.search(slice_data["student_text"])),
            bool(GIVING_MOVE_RE.search(slice_data["tutor_text"])))


def layer_key(help_sought: bool, giving: bool) -> str:
    return ("help_sought" if help_sought else "no_help") + \
           ("_giving" if giving else "_no_giving")


def load_candidates(results_dir: Path) -> tuple[list[dict], list[dict]]:
    """读全部 session → tie-break → 候选池+无效清单。"""
    candidates, invalid = [], []
    for path in sorted(results_dir.glob("*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        reason = None
        if result.get("status") != "ok":
            reason = f"status={result.get('status')}"
        elif not result.get("transcript", {}).get("question_id") and not result.get("question"):
            reason = "question_missing"
        else:
            slice_data = extract_slice(result)
            if slice_data is None:
                reason = "no_eligible_slice"
            else:
                if not slice_data.get("question") and result.get("question"):
                    slice_data["question"] = result["question"]
                candidates.append(slice_data)
        if reason:
            invalid.append({"case_id": result.get("case_id"), "reason": reason})
    return candidates, invalid


def build_layers(candidates: list[dict]) -> dict[str, list[dict]]:
    """分层 + 每层内 session_id 排序 + seed 随机序(确定性)。"""
    layers = {name: [] for name in LAYER_QUOTA}
    for s in candidates:
        a, b = classify(s)
        s["stratum_proxy_help"] = a
        s["stratum_proxy_giving"] = b
        layers[layer_key(a, b)].append(s)
    rng = random.Random(SEED)
    for name in layers:
        layers[name].sort(key=lambda s: s["session_id"])
        rng.shuffle(layers[name])
    return layers


def fill_layer(layers: dict, selected: list, name: str, quota: int) -> tuple[int, int]:
    """按配额抽一层;层内不足从最大剩余层补位(固定层序 tie)。返回(新选数,尝试数)。"""
    attempt_count = 0
    picked = []
    for s in layers[name]:
        if len(picked) >= quota:
            break
        attempt_count += 1
        picked.append(s)
    if len(picked) < quota:
        used = {n: len([x for x in selected if x.get("_layer") == n]) for n in layers}
        borrowable = sorted(
            [(n, len(layers[n]) - used.get(n, 0))
             for n in LAYER_ORDER if len(layers[n]) > 0],
            key=lambda x: (-x[1], LAYER_ORDER.index(x[0])))
        for src, _ in borrowable:
            if src == name or len(picked) >= quota:
                break
            for s in layers[src]:
                if len(picked) >= quota:
                    break
                if s not in picked:
                    attempt_count += 1
                    s["_borrowed_from"] = src
                    picked.append(s)
    for s in picked:
        s["_layer"] = name
    return len(picked), attempt_count


def build_manifest(candidates, invalid, layers, selected, attempts, results_dir):
    """生成 sampling manifest(含完整性 hash,预审 5885823950)。"""
    input_ids = sorted(s["slice_id"] for s in candidates)
    input_hash = hashlib.sha256("\n".join(input_ids).encode()).hexdigest()
    source_hashes = sorted(
        hashlib.sha256(p.read_bytes()).hexdigest()
        for p in results_dir.glob("*.json"))
    source_hash = hashlib.sha256("\n".join(source_hashes).encode()).hexdigest()
    return {
        "spec_version": "v0.1",
        "python_version": sys.version,
        "input_candidate_ids_sha256": input_hash,
        "source_results_sha256": source_hash,
        "source_file_count": len(source_hashes),
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
        "total_attempts": attempts,
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    candidates, invalid = load_candidates(args.results_dir)
    layers = build_layers(candidates)

    selected, total_attempts = [], 0
    for name, quota in LAYER_QUOTA.items():
        n, a = fill_layer(layers, selected, name, quota)
        total_attempts += a
        selected.extend([s for s in layers[name] if s.get("_layer") == name])

    if len(selected) < 30:
        print(f"FAIL: {len(selected)}/30 after {total_attempts} attempts "
              f"(max {MAX_ATTEMPTS})")
        return 1

    manifest = build_manifest(candidates, invalid, layers, selected,
                              total_attempts, args.results_dir)
    args.out.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"Selected {len(selected)}/30 from {len(candidates)} candidates")
    print(f"Layers: {manifest['layer_sizes']}")
    print(f"Manifest: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
