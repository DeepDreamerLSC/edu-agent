"""标定卡口③:calibration_report 一致率脚本合同——加权 kappa 手写公式钉小例 + 端到端。

judge×judge'/judge×人分 走同一脚本;人分原始 CSV 属私有面不进仓(PM 裁定),
测试用脱敏小样例(与预打分 CSV 同构:BOM + 案例号 + 六维中文列 + 总评)。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from calibration_report import weighted_kappa

# ---------- 加权 kappa(手写公式,二次权重,0-2 三档) ----------


def test_weighted_kappa_perfect_agreement_is_one():
    assert weighted_kappa([0, 1, 2, 2, 1, 0], [0, 1, 2, 2, 1, 0]) == 1.0


def test_weighted_kappa_known_small_example():
    """手算小例(二次权重,3 档):
    a=[0,0,2,2],b=[0,2,2,2] → p_obs=(0+1+0+0)/4=1/4;
    行边缘 a=[2,0,2]/4、列边缘 b=[1,0,3]/4 →
    p_exp=(1·2·1+1·2·3)/16=8/16=1/2 → κ=1−(1/4)/(1/2)=0.5。"""
    kappa = weighted_kappa([0, 0, 2, 2], [0, 2, 2, 2])
    assert kappa == pytest.approx(0.5)


def test_weighted_kappa_systematic_one_step_gap():
    """系统性差一档的中间例:[0,1,2]×[1,2,1] 手算 p_obs=p_exp=1/4 → κ=0
    (交叉表 [[0,1,0],[0,0,1],[0,1,0]];行=[1,1,1]/3、列=[0,2,1]/3,
    p_exp=(1/4)·(1·0+1·2+0·1+0+…)/9 → 0.25)。"""
    assert weighted_kappa([0, 1, 2], [1, 2, 1]) == pytest.approx(0.0)


def test_weighted_kappa_degenerate_returns_none():
    """边缘退化(两列同恒同档):κ 无定义返回 None,不除零;空列同样 None。"""
    assert weighted_kappa([1, 1, 1], [1, 1, 1]) is None
    assert weighted_kappa([], []) is None
    # 一侧恒同档但另一侧有分布:可计算(此处 p_obs=p_exp → 0)
    assert weighted_kappa([1, 1, 1], [0, 1, 2]) == pytest.approx(0.0)


# ---------- 端到端(judge JSONL × 人分 CSV → markdown) ----------


def _judge_jsonl(path: Path) -> None:
    rows = [
        {"case_id": "C01", "scores": {"first_question": 2, "socratic_followup": 1,
                                      "grade_fit": 2, "pacing": 1, "summary_mastery": 0,
                                      "termination": 1}, "total": 7, "verdict": "review",
         "answer_leaked": False, "math_integrity": 2},
        {"case_id": "C02", "scores": {"first_question": 1, "socratic_followup": 1,
                                      "grade_fit": 2, "pacing": 1, "summary_mastery": 1,
                                      "termination": 0}, "total": 6, "verdict": "fail",
         "answer_leaked": True, "math_integrity": 2},
    ]
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def _human_csv(path: Path) -> None:
    path.write_bytes(
        "\ufeff案例号,首问,引导追问,年级适配,节奏,总结掌握,收尾时机,总评(过/待议/不及格)\n"
        "C01,2,1,2,1,0,1,待议\n"
        "C02,2,1,2,0,1,0,过\n".encode("utf-8")
    )


def test_report_end_to_end(tmp_path):
    """2 案端到端:BOM 人分 CSV × judge JSONL → 一致率表 + 翻转案号;--out 落文件。"""
    judge, human, out = tmp_path / "j.jsonl", tmp_path / "h.csv", tmp_path / "r.md"
    _judge_jsonl(judge)
    _human_csv(human)
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[2] / "scripts" / "calibration_report.py"),
         "--judge", str(judge), "--human", str(human), "--out", str(out)],
        capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    report = out.read_text(encoding="utf-8")
    assert "配对:2 案" in report
    assert "| 首问(first_question) | 1/2 = 50% | 0.00 |" in report  # C01 同、C02 异
    assert "| 总结掌握(summary_mastery) | 2/2 = 100% | 1.00 |" in report
    # verdict:C01 待议=review 同;C02 过=pass vs judge fail → 翻转 1 例
    assert "verdict 翻转:1 例:C02" in report


def test_report_empty_intersection_fails(tmp_path):
    judge, human = tmp_path / "j.jsonl", tmp_path / "h.csv"
    _judge_jsonl(judge)
    _human_csv(human)
    judge.write_text(json.dumps({"case_id": "X99", "scores": {}, "verdict": "pass"}) + "\n",
                     encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[2] / "scripts" / "calibration_report.py"),
         "--judge", str(judge), "--human", str(human)],
        capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert "交集为空" in result.stderr
