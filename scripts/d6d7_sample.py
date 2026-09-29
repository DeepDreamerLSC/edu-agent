#!/usr/bin/env python3
"""D6/D7 独立 gold 集机械抽样脚本(执行 spec v0.1,冻结后单次执行)。

确定性:同 seed + 同输入 = 同输出;零网络零模型;逐行可审计。
用法:python d6d7_sample.py --results-dir <round>/results --out manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

SEED = 2617289367  # int("9c00aa97", 16),与 seed.txt 预注册一致
PROTOCOL_FREEZE_SHA = "9c00aa9715aaf265"
LAYER_QUOTA = {"help_sought_giving": 8, "help_sought_no_giving": 8,
               "no_help_giving": 7, "no_help_no_giving": 7}
LAYER_ORDER = ("help_sought_giving", "help_sought_no_giving",
               "no_help_giving", "no_help_no_giving")

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


def _resolve_session_id(session: dict, fallback_index: int) -> str:
    """统一 resolved session_id(终裁 P0-B):transcript.session_id 优先,case_id 兜底。"""
    tid = session.get("transcript", {}).get("session_id", "")
    if tid and tid.strip():
        return tid.strip()
    cid = session.get("case_id", "")
    if cid and cid.strip():
        return cid.strip()
    return f"unknown-{fallback_index}"


def extract_slice(session: dict) -> tuple[dict | None, list[str]]:
    """tie-break:eligible slice 中 seeded rank 最小者;返回(picked, all_eligible_ids)。

    slice_id = {resolved_session_id}:{turn_index}(终裁 P0-B)。
    """
    turns = session.get("transcript", {}).get("turns", [])
    resolved_sid = _resolve_session_id(session, 0)
    best = None
    eligible_ids: list[str] = []
    for i, turn in enumerate(turns):
        student, tutor = turn.get("student", ""), turn.get("tutor", "")
        if _is_blank(student) or _is_blank(tutor):
            continue
        eligible_ids.append(f"{resolved_sid}:{i}")
        rank = _slice_rank(resolved_sid, i)
        if best is None or rank < best[0]:
            best = (rank, {
                "session_id": resolved_sid,
                "case_id": session.get("case_id", ""),
                "turn_index": i,
                "slice_id": f"{resolved_sid}:{i}",
                "student_text": student,
                "tutor_text": tutor,
                "question": session.get("question", {}),
                "tie_break_rank": rank,
            })
    return (best[1] if best else None), eligible_ids


def classify(slice_data: dict) -> tuple[bool, bool]:
    """stratum_proxy_help × stratum_proxy_giving(表面分类,非 S2 语义)。"""
    return (bool(HELP_SEEKING_RE.search(slice_data["student_text"])),
            bool(GIVING_MOVE_RE.search(slice_data["tutor_text"])))


def layer_key(help_sought: bool, giving: bool) -> str:
    return ("help_sought" if help_sought else "no_help") + \
           ("_giving" if giving else "_no_giving")


def load_candidates(results_dir: Path) -> tuple[list[dict], list[dict], list[str]]:
    """读 session → resolve sid → tie-break → 候选池 + 无效清单 + eligible IDs。

    session_id 唯一性机械检查(终裁 P0-B):重复 resolved_sid 记为无效。
    """
    candidates, invalid, raw_eligible = [], [], []
    seen_sids: dict[str, str] = {}
    for path in sorted(results_dir.glob("*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        reason = None
        if result.get("status") != "ok":
            reason = f"status={result.get('status')}"
        else:
            slice_data, eligible = extract_slice(result)
            raw_eligible.extend(eligible)
            if slice_data is None:
                reason = "no_eligible_slice"
            else:
                sid = slice_data["session_id"]
                if sid in seen_sids:
                    reason = f"duplicate_session_id(also_from={seen_sids[sid]})"
                else:
                    seen_sids[sid] = result.get("case_id", path.stem)
                    if not slice_data.get("question") and result.get("question"):
                        slice_data["question"] = result["question"]
                    candidates.append(slice_data)
        if reason:
            invalid.append({"case_id": result.get("case_id"), "reason": reason})
    return candidates, invalid, raw_eligible


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


def fill_layer(layers: dict, consumed: set, name: str, quota: int) -> list[dict]:
    """按配额从目标层抽;不足从剩余量最大层补(固定层序 tie)。返回 picked 列表。

    consumed 为全局已选 slice_id 集合;层内+补位共用该集合,防双选(终裁 P0-A)。
    """
    picked = []
    for s in layers[name]:
        if len(picked) >= quota:
            break
        if s["slice_id"] not in consumed:
            picked.append(s)
    if len(picked) < quota:
        remaining = sorted(
            [(n, len([x for x in layers[n] if x["slice_id"] not in consumed]))
             for n in LAYER_ORDER if n != name and len(layers[n]) > 0],
            key=lambda x: (-x[1], LAYER_ORDER.index(x[0])))
        for src, _ in remaining:
            if len(picked) >= quota:
                break
            for s in layers[src]:
                if len(picked) >= quota:
                    break
                if s["slice_id"] not in consumed:
                    s["_borrowed_from"] = src
                    picked.append(s)
    for s in picked:
        consumed.add(s["slice_id"])
        s["_layer"] = name
    return picked


def build_manifest(candidates, invalid, raw_eligible, layers, selected,
                   results_dir):
    """生成 sampling manifest(含三层输入完整性 hash,预审 5885823950)。"""
    input_ids = sorted(s["slice_id"] for s in candidates)
    raw_ids = sorted(raw_eligible)
    source_hashes = sorted(
        hashlib.sha256(p.read_bytes()).hexdigest()
        for p in results_dir.glob("*.json"))
    return {
        "spec_version": "v0.1.2",
        "python_version": sys.version,
        "input_candidate_ids_sha256": hashlib.sha256(
            "\n".join(input_ids).encode()).hexdigest(),
        "raw_eligible_slice_ids_sha256": hashlib.sha256(
            "\n".join(raw_ids).encode()).hexdigest(),
        "raw_eligible_slice_count": len(raw_ids),
        "source_results_sha256": hashlib.sha256(
            "\n".join(source_hashes).encode()).hexdigest(),
        "source_file_count": len(source_hashes),
        "script_sha256": hashlib.sha256(
            Path(__file__).read_bytes()).hexdigest(),
        "protocol_freeze_sha_prefix": PROTOCOL_FREEZE_SHA,
        "seed": SEED,
        "candidate_pool_size": len(candidates),
        "invalid_count": len(invalid),
        "invalid_details": invalid,
        "layer_sizes": {n: len(layers[n]) for n in layers},
        "layer_quota": LAYER_QUOTA,
        "total_selected": len(selected),
        "attempts_note": (
            "本轮结构资格过滤在候选池形成前完成;"
            "post-filter selection 不发生无效候选尝试;"
            "50-attempt 上限未成为活跃执行条件"),
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

    candidates, invalid, raw_eligible = load_candidates(args.results_dir)
    layers = build_layers(candidates)

    # fill_layer 返回 picked;主循环直接 extend(终裁 P0-A)
    selected: list[dict] = []
    consumed: set[str] = set()
    for name, quota in LAYER_QUOTA.items():
        selected.extend(fill_layer(layers, consumed, name, quota))

    if len(selected) < 30:
        print(f"FAIL: only {len(selected)}/30 from {len(candidates)} candidates")
        return 1

    manifest = build_manifest(candidates, invalid, raw_eligible, layers,
                              selected, args.results_dir)
    args.out.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"Selected {len(selected)}/30 from {len(candidates)} candidates")
    print(f"Layers: {manifest['layer_sizes']}")
    print(f"Manifest: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
