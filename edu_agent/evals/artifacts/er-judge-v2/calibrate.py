#!/usr/bin/env python3
"""ER judge v2 校准与演练 runner(裁令④;judge-only,零 tutor calls)。

三个子命令(数据源 = 既有 r3/ablation 结果工件,只读):
  drill     四案逐轮红灯演练(r3 双臂 × ER 4 案):v1 词面命中轮 vs v2 判定对照;
  dev       开发集校准(10 曝光盘案 × r3 双臂,人审定谳 gold vs v2,一致率);
  replay    r3 全 26 案诊断性 replay(v1 vs v2 逐案对照;不翻 r3 结论);
  holdout   holdout 抽样与判分(冻结后执行;抽样确定性,标注在 gold 文件)。

用法:python3 edu_agent/evals/artifacts/er-judge-v2/calibrate.py <cmd> \
        [--runs-root /tmp/wt-step7-ab] [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from er_judge_v2 import FORM1, judge_case  # noqa: E402

# v1 词面判据(判读员正本照录,只读对照;r3 封存不改)
_V1_DOUBT = ("再想", "再算", "是不是", "确定", "真的", "肯定对", "对吗",
             "对不对", "怎么想到", "你确定", "检查一下", "验证一下")
_V1_REASK = re.compile(r"(是多少|等于几|算出来是多少|填什么)")
_V1_ACK = ("算对", "说对", "对了", "正确", "很准", "扎实", "棒", "👍",
           "已经对", "结论对了", "没问题", "清楚了", "说清楚了", "准确",
           "没错", "成立", "说出了", "讲得很明白", "说得很清楚", "关键")

DEV10 = ("repro-close-loop-cross-stitch", "socraticmath_train_2591",
         "socraticmath_train_675", "socraticmath_val_13",
         "socraticmath_train_3565", "socraticmath_train_4402",
         "socraticmath_train_3666", "socraticmath_train_866",
         "repro-close-loop-ball-bounce", "socraticmath_train_4275")
ER4 = ("socraticmath_train_3565", "socraticmath_train_4402",
       "socraticmath_train_3666", "socraticmath_train_866")
ABL_ARMS = ("baseline", "a-only", "b-old", "b-new", "ab-old")
UNEXPOSED = ("incident-700m-replay", "socraticmath_train_1001",
             "socraticmath_train_1204", "socraticmath_train_1559",
             "socraticmath_train_1827", "socraticmath_train_223",
             "socraticmath_train_2899", "socraticmath_train_3998",
             "socraticmath_train_4510", "socraticmath_train_4776",
             "socraticmath_train_5191", "socraticmath_train_5228",
             "socraticmath_train_559", "socraticmath_val_412",
             "socraticmath_val_495", "socraticmath_val_61")


def load_all(runs_root: Path):
    cases = {}
    for line in (runs_root / "runs/candidate/cases.jsonl").read_text(
            encoding="utf-8").splitlines():
        if line.strip():
            c = json.loads(line)
            cases[c["id"]] = c
    forms = {}
    dataset = runs_root / "edu_agent/evals/datasets/external_slices/socraticmath_executable_v1.json"
    for s in json.loads(dataset.read_text(encoding="utf-8"))["scenarios"]:
        forms[s["id"]] = s["compile"]["form"]
    return cases, forms


def load_transcript(runs_root: Path, arm_dir: str, case_id: str):
    path = runs_root / "runs" / arm_dir / "results" / f"{case_id}.json"
    row = json.loads(path.read_text(encoding="utf-8"))
    return row.get("transcript") or {}


def v1_er_hits(transcript: dict, case: dict, form1: bool) -> list[int]:
    """v1 词面族命中轮(判读员正本逻辑照录,只读对照)。"""
    if not form1:
        return []
    answer = str((case.get("question") or {}).get("answer") or "")
    answer_nums = {float(m) for m in re.findall(r"\d+(?:\.\d+)?", answer)}
    if not answer_nums:
        return []
    qtext_nums = {float(m) for m in re.findall(
        r"\d+(?:\.\d+)?", str((case.get("question") or {}).get("text") or ""))}
    said: set[float] = set()
    hits = []
    for i, turn in enumerate(transcript.get("turns") or []):
        student = str(turn.get("student") or "")
        tutor = str(turn.get("tutor") or "")
        if student:
            said |= answer_nums & {float(m) for m in re.findall(r"\d+(?:\.\d+)?", student)}
        if not (student and tutor.strip() and said):
            continue
        acknowledged = any(m in tutor for m in _V1_ACK)
        doubt = any(m in tutor for m in _V1_DOUBT) and bool(re.search(r"[?？]", tutor))
        reask = bool(_V1_REASK.search(tutor) and re.search(r"[?？]", tutor))
        number_echo = bool(answer_nums & {float(m) for m in re.findall(r"\d+(?:\.\d+)?", tutor)})
        stray = ({float(m) for m in re.findall(r"\d+(?:\.\d+)?", student)}
                 - answer_nums - qtext_nums)
        if ((doubt or reask) and not acknowledged
                and (number_echo or doubt) and not stray):
            hits.append(i)
    return hits


def judge(runs_root: Path, arm_dir: str, case_id: str, cases, forms) -> dict:
    return judge_case(cases[case_id], load_transcript(runs_root, arm_dir, case_id),
                      forms.get(case_id))


def cmd_drill(runs_root: Path, out: Path | None) -> None:
    """四案逐轮红灯演练:v1 命中轮在新 judge 下的判定变化(含全部分母轮)。
    含五臂补充(r3 双臂 + ablation 五臂;§5.2 佐证边界)。"""
    cases, forms = load_all(runs_root)
    table = {}
    arm_dirs = [("r3-baseline", "r3-baseline"), ("r3-candidate", "r3-candidate")] + [
        (f"ablation-{a}", f"ablation-{a}") for a in ABL_ARMS]
    for cid in ER4:
        table[cid] = {}
        for label, arm_dir in arm_dirs:
            transcript = load_transcript(runs_root, arm_dir, cid)
            v2 = judge_case(cases[cid], transcript, forms.get(cid))
            v1 = v1_er_hits(transcript, cases[cid], forms.get(cid) == FORM1)
            rows = []
            for t in v2["turns"]:
                if not t["in_denominator"] and t["index"] not in v1:
                    continue
                rows.append({
                    "turn": t["index"],
                    "v1_lex_hit": t["index"] in v1,
                    "v2_er": t["er_hit"], "v2_er_reason": t["er_reason"],
                    "v2_no_progress": t["no_progress_hit"],
                    "student": str(transcript["turns"][t["index"]].get("student"))[:60],
                    "tutor": str(transcript["turns"][t["index"]].get("tutor"))[:90],
                })
            table[cid][label] = {"v1_hits": v1, "v2": {
                "er_family": v2["er_family"], "no_progress_family": v2["no_progress_family"],
                "denominator": v2["denominator"]}, "denominator_turns": rows}
    payload = {"drill_four_cases": table}
    _emit(payload, out, _drill_text(table))


def _drill_text(table: dict) -> str:
    lines = ["=== 四案逐轮红灯演练(v1 词面命中轮 → v2 判定)==="]
    for cid, arms in table.items():
        lines.append(f"\n-- {cid}")
        for arm, data in arms.items():
            lines.append(f"  [{arm}] v1命中轮={data['v1_hits']} "
                         f"v2: ER={data['v2']['er_family']} "
                         f"NP={data['v2']['no_progress_family']} "
                         f"分母={data['v2']['denominator']}")
            for row in data["denominator_turns"]:
                lines.append(
                    f"    t{row['turn']} v1={'HIT ' if row['v1_lex_hit'] else ' -  '}"
                    f" v2_ER={'Y' if row['v2_er'] else '-'}"
                    f" v2_NP={'Y' if row['v2_no_progress'] else '-'}"
                    f" | T: {row['tutor'][:70]}")
    return "\n".join(lines)


def cmd_dev(runs_root: Path, out: Path | None) -> None:
    """开发集校准:10 曝光盘案 × r3 双臂,gold(人审定谳)vs v2 一致率。"""
    cases, forms = load_all(runs_root)
    gold = json.loads((HERE / "gold_labels_dev.json").read_text(encoding="utf-8"))
    per_traj, agree = [], {"er": [0, 0], "np": [0, 0], "turn": [0, 0]}
    for case_id in DEV10:
        for arm, arm_dir in (("baseline", "r3-baseline"), ("candidate", "r3-candidate")):
            key = f"{case_id}|{arm}"
            v2 = judge(runs_root, arm_dir, case_id, cases, forms)
            g = gold["trajectories"].get(key)
            if g is None:
                continue
            er_ok = v2["er_family"] == g["er_family"]
            np_ok = v2["no_progress_family"] == g["no_progress_family"]
            agree["er"][0] += er_ok
            agree["er"][1] += 1
            agree["np"][0] += np_ok
            agree["np"][1] += 1
            turn_labels = {t["index"]: ("er" if t["er_hit"]
                                        else "np" if t["no_progress_hit"] else "legal")
                           for t in v2["turns"] if t["in_denominator"]}
            gold_turns = g.get("turns") or {}
            for idx_str, label in gold_turns.items():
                actual = turn_labels.get(int(idx_str), "legal")
                agree["turn"][0] += actual == label
                agree["turn"][1] += 1
            per_traj.append({
                "key": key, "gold_er": g["er_family"], "v2_er": v2["er_family"],
                "gold_np": g["no_progress_family"], "v2_np": v2["no_progress_family"],
                "denominator": v2["denominator"],
                "v2_turns": turn_labels, "gold_turns": gold_turns,
                "note": g.get("note", ""),
            })
    payload = {"dev_calibration": {
        "trajectories": per_traj,
        "agreement": {k: {"match": v[0], "total": v[1],
                          "rate": round(v[0] / v[1], 4) if v[1] else None}
                      for k, v in agree.items()}}}
    _emit(payload, out, _calib_text("开发集(10 曝光盘案 × r3 双臂)", per_traj, agree))


def _calib_text(title: str, per_traj: list, agree: dict) -> str:
    lines = [f"=== {title}:gold vs ER judge v2 ==="]
    for row in per_traj:
        flag = ("OK " if row["gold_er"] == row["v2_er"]
                and row["gold_np"] == row["v2_np"] else "DIS")
        lines.append(f"  [{flag}] {row['key']}: "
                     f"ER {row['gold_er']}→{row['v2_er']} "
                     f"NP {row['gold_np']}→{row['v2_np']} den={row['denominator']}")
    for k, v in agree.items():
        rate = round(v[0] / v[1], 4) if v[1] else None
        lines.append(f"  一致率[{k}]: {v[0]}/{v[1]} = {rate}")
    return "\n".join(lines)


def cmd_replay(runs_root: Path, out: Path | None) -> None:
    """r3 全 26 案诊断性 replay:v1 vs v2 逐案对照(不重算 r3 结论)。"""
    cases, forms = load_all(runs_root)
    result = {}
    for results_dir in ("r3-baseline", "r3-candidate"):
        arm = results_dir.split("-", 1)[1]
        result[arm] = {}
        for path in sorted((runs_root / "runs" / results_dir / "results").glob("*.json")):
            row = json.loads(path.read_text(encoding="utf-8"))
            if row["status"] != "ok":
                continue
            cid = row["case_id"]
            transcript = row["transcript"]
            form1 = forms.get(cid) == FORM1
            v1 = v1_er_hits(transcript, cases[cid], form1)
            v2 = judge_case(cases[cid], transcript, forms.get(cid))
            result[arm][cid] = {
                "v1_lex_hits": v1, "v1_count": len(v1),
                "v2_er": v2["er_family"], "v2_np": v2["no_progress_family"],
                "v2_denominator": v2["denominator"], "domain": v2["domain_note"],
                "v2_er_turns": [t["index"] for t in v2["turns"] if t["er_hit"]],
                "v2_np_turns": [t["index"] for t in v2["turns"] if t["no_progress_hit"]],
            }
    payload = {"r3_diagnostic_replay": result,
               "note": "诊断性 replay:r3 FAIL 结论不变,不重算不翻案;"
                       "只报告旧尺子(v1 词面)与新尺子(v2)差异。"}
    _emit(payload, out, _replay_text(result))


def _replay_text(result: dict) -> str:
    lines = ["=== r3 诊断性 replay(v1 vs v2;不翻案)==="]
    for arm in ("baseline", "candidate"):
        lines.append(f"\n[{arm}]")
        for cid, r in sorted(result[arm].items()):
            if r["v1_count"] == 0 and r["v2_er"] == 0 and r["v2_np"] == 0:
                continue
            lines.append(f"  {cid}: v1={r['v1_lex_hits']} v2_ER={r['v2_er_turns']}"
                         f" v2_NP={r['v2_np_turns']} den={r['v2_denominator']}"
                         f" [{r['domain']}]")
    return "\n".join(lines)


def cmd_holdout(runs_root: Path, out: Path | None) -> None:
    """holdout:16 未曝光案 r3 双臂,确定性抽样 + 判分(标注在 gold 文件)。"""
    cases, forms = load_all(runs_root)
    gold = json.loads((HERE / "gold_labels_holdout.json").read_text(encoding="utf-8"))
    rows, agree = [], {"turn": [0, 0], "er": [0, 0], "np": [0, 0]}
    for sample in gold["samples"]:
        case_id, arm = sample["case_id"], sample["arm"]
        v2 = judge(runs_root, "r3-" + arm, case_id, cases, forms)
        turn_labels = {t["index"]: ("er" if t["er_hit"]
                                    else "np" if t["no_progress_hit"] else "legal")
                       for t in v2["turns"] if t["in_denominator"]}
        actual = turn_labels.get(sample["turn"], "legal")
        ok = actual == sample["label"]
        agree["turn"][0] += ok
        agree["turn"][1] += 1
        if sample["label"] == "er":
            agree["er"][0] += actual == "er"
            agree["er"][1] += 1
        if sample["label"] == "np":
            agree["np"][0] += actual == "np"
            agree["np"][1] += 1
        rows.append({**sample, "judge": actual, "match": ok,
                     "tutor": str(load_transcript(runs_root, "r3-" + arm, case_id)
                                  ["turns"][sample["turn"]].get("tutor"))[:90]})
    payload = {"holdout": {"samples": rows,
                           "agreement": {k: {"match": v[0], "total": v[1],
                                             "rate": round(v[0] / v[1], 4) if v[1] else None}
                                         for k, v in agree.items()}}}
    lines = ["=== holdout(16 未曝光案抽样 turn:人标 vs v2)==="]
    for row in rows:
        lines.append(f"  [{'OK ' if row['match'] else 'DIS'}] {row['case_id']}"
                     f"/{row['arm']}/t{row['turn']}: gold={row['label']}"
                     f" judge={row['judge']}")
    for k, v in agree.items():
        rate = round(v[0] / v[1], 4) if v[1] else None
        lines.append(f"  一致率[{k}]: {v[0]}/{v[1]} = {rate}")
    _emit(payload, out, "\n".join(lines))


def cmd_sample(runs_root: Path, out: Path | None) -> None:
    """holdout 抽样(冻结后执行):16 未曝光案 r3 双臂的 ER 域分母轮,
    确定性抽样 ~20 turn——信号轮(v1 命中或 v2 命中)+ 安静轮(步进 2)各半。
    抽样只报轮位与学生/导师文本,标注(label)由人随后填入 gold_labels_holdout.json。"""
    cases, forms = load_all(runs_root)
    pool = []
    for case_id in UNEXPOSED:
        for arm in ("baseline", "candidate"):
            v2 = judge(runs_root, "r3-" + arm, case_id, cases, forms)
            transcript = load_transcript(runs_root, "r3-" + arm, case_id)
            v1 = v1_er_hits(transcript, cases[case_id], forms.get(case_id) == FORM1)
            for t in v2["turns"]:
                if not t["in_denominator"]:
                    continue
                signal = (t["index"] in v1 or t["er_hit"] or t["no_progress_hit"])
                pool.append({"case_id": case_id, "arm": arm, "turn": t["index"],
                             "signal": signal,
                             "student": str(transcript["turns"][t["index"]]
                                            .get("student"))[:110],
                             "tutor": str(transcript["turns"][t["index"]]
                                          .get("tutor"))[:150]})
    signals = [p for p in pool if p["signal"]]
    quiet = [p for p in pool if not p["signal"]]
    picked = signals + quiet[::2][:max(0, 20 - len(signals))]
    picked = picked[:20] if len(signals) >= 20 else picked
    payload = {"holdout_sampling": {
        "pool_size": len(pool), "signal_turns": len(signals), "quiet_turns": len(quiet),
        "picked": [{k: v for k, v in p.items()} for p in picked],
        "note": "确定性抽样:全部信号轮 + 安静轮步进2补足;标注后入 gold_labels_holdout.json"}}
    lines = [f"=== holdout 抽样:池 {len(pool)}(信号 {len(signals)}/安静 {len(quiet)}),"
             f"抽 {len(picked)} ==="]
    for p in picked:
        lines.append(f"  {p['case_id']}/{p['arm']}/t{p['turn']} "
                     f"{'SIG' if p['signal'] else 'qt '} | S: {p['student'][:60]}"
                     f" | T: {p['tutor'][:80]}")
    _emit(payload, out, "\n".join(lines))


def _emit(payload: dict, out: Path | None, text: str) -> None:
    print(text)
    if out:
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nwritten: {out}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["drill", "dev", "replay", "holdout", "sample"])
    parser.add_argument("--runs-root", default="/tmp/wt-step7-ab", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    if args.command == "drill":
        cmd_drill(args.runs_root, args.out)
    elif args.command == "dev":
        cmd_dev(args.runs_root, args.out)
    elif args.command == "replay":
        cmd_replay(args.runs_root, args.out)
    elif args.command == "sample":
        cmd_sample(args.runs_root, args.out)
    else:
        cmd_holdout(args.runs_root, args.out)


if __name__ == "__main__":
    main()
