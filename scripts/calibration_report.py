#!/usr/bin/env python3
"""标定卡口③:judge 分 × 人分 → 一致率 markdown 报告(双盲口径,只读任意路径,不进私有面)。

输入:
  --judge <judge-scores.jsonl>   rescore_judge.py 产物:每行 {case_id, scores:{六维}, verdict,
                                 answer_leaked, math_integrity, total}(首行 _comment 头跳过)
  --human <人分 CSV>             任意路径(私有面,不进仓);列:案例号,首问,引导追问,年级适配,
                                 节奏,总结掌握,收尾时机,总评(带 BOM 自动剥)
  --id-col 案例号                人分 CSV 的案号列名(默认「案例号」;缺省时也可直接用 case_id)
  --out <FILE>                   落 markdown 文件(不给则只打印 stdout)

输出:逐维一致率 + 加权 kappa(手写公式,二次权重,0-2 三档)+ verdict 翻转数与案号。
禁 scipy/sklearn(02 §2 依赖预算):kappa 手写 ~20 行,公式钉在测试里。

用法(PM 补充裁定:人分原始 CSV 属私有面,PR 内只放 judge×judge' 机器面演示):
  uv run python scripts/calibration_report.py --judge <a.jsonl> --human <b.csv> --out report.md
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from statistics import fmean

# 人分 CSV 列名 → judge 维度(checks.py/judge.py 六维口径)
DIM_COLUMNS = {
    "first_question": "首问",
    "socratic_followup": "引导追问",
    "grade_fit": "年级适配",
    "pacing": "节奏",
    "summary_mastery": "总结掌握",
    "termination": "收尾时机",
}
VERDICT_MAP = {"过": "pass", "待议": "review", "不及格": "fail"}
# 人分总评列名匹配:DictReader 的键带后缀(如「总评(过/待议/不及格)」),前缀匹配三候选
VERDICT_COLUMN_PREFIXES = ("总评", "judge总评")


def weighted_kappa(a: list[int], b: list[int]) -> float | None:
    """Cohen's weighted kappa(二次权重,类别 0-2)。两列不一致全零时返回 None。

    κ = 1 − Σw·p_obs / Σw·p_exp;w_ij = (i−j)²/(k−1)²。手写公式,禁 scipy(#~20 行)。"""
    n = len(a)
    if n == 0:
        return None
    k = 3
    counts = [[0] * k for _ in range(k)]
    for x, y in zip(a, b, strict=True):
        counts[x][y] += 1
    rows = [sum(counts[i]) for i in range(k)]
    cols = [sum(counts[r][j] for r in range(k)) for j in range(k)]
    p_obs = p_exp = 0.0
    for i in range(k):
        for j in range(k):
            w = (i - j) ** 2 / (k - 1) ** 2
            p_obs += w * counts[i][j] / n
            p_exp += w * rows[i] * cols[j] / (n * n)
    if p_exp == 0:
        return None  # 边缘分布退化(一侧恒同档):kappa 无定义,报告一致率即可
    return 1.0 - p_obs / p_exp


def load_judge(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("_comment"):
            continue  # 金标/评分文件的头注释行
        rows[row["case_id"]] = row
    return rows


def load_human(path: Path, id_col: str) -> dict[str, dict]:
    rows = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:  # BOM 剥除
        for row in csv.DictReader(handle):
            rows[row[id_col].strip()] = row
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge", required=True, metavar="JSONL")
    parser.add_argument("--human", required=True, metavar="CSV")
    parser.add_argument("--id-col", default="案例号", help="人分 CSV 案号列名")
    parser.add_argument("--out", metavar="FILE", help="markdown 落文件(不给则只打印)")
    args = parser.parse_args()

    judge, human = load_judge(Path(args.judge)), load_human(Path(args.human), args.id_col)
    if not human:  # 列名不对早失败:空表只会产出全零报告
        print(f"人分 CSV 读到 0 行(id-col={args.id_col}?列名错或文件空)", file=sys.stderr)
        return 1
    paired = sorted(set(judge) & set(human))
    if not paired:
        print("judge × 人分交集为空(case_id/案号对不上)", file=sys.stderr)
        return 1

    lines = ["# 标定一致率报告(judge × 人分)", "",
             f"- 配对:{len(paired)} 案(judge {len(judge)} × 人分 {len(human)},交集配对)", "",
             "| 维度 | 一致率 | 加权κ(二次) |", "|---|---|---|"]
    for dim, col in DIM_COLUMNS.items():
        same = [c for c in paired if int(human[c][col]) == judge[c]["scores"][dim]]
        a = [int(human[c][col]) for c in paired]
        b = [judge[c]["scores"][dim] for c in paired]
        kappa = weighted_kappa(a, b)
        kappa_text = f"{kappa:.2f}" if kappa is not None else "n/a"
        lines.append(f"| {col}({dim}) | {len(same)}/{len(paired)}"
                     f" = {len(same) / len(paired):.0%} | {kappa_text} |")
    mean_kappas = [k for k in (weighted_kappa([int(human[c][col]) for c in paired],
                                              [judge[c]["scores"][dim] for c in paired])
                               for dim, col in DIM_COLUMNS.items()) if k is not None]
    verdict_col = None
    if paired:
        verdict_col = next((name for name in human[paired[0]]
                            if name.startswith(VERDICT_COLUMN_PREFIXES)), None)
    flips = [c for c in paired
             if verdict_col is None
             or VERDICT_MAP.get(human[c][verdict_col].strip(), human[c][verdict_col]) != judge[c]["verdict"]]
    lines += ["", f"- 六维加权κ均值:{fmean(mean_kappas):.2f}" if mean_kappas else "- 六维加权κ:n/a(边缘退化)",
              f"- verdict 翻转:{len(flips)} 例{(':' + ', '.join(flips)) if flips else ''}",
              "", "口径:双盲(教师材料不带 judge 分数);人分 CSV 属私有面,本报告只落聚合面,不带评注原文。"]
    report = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"报告落 {args.out}")
    print(report, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
