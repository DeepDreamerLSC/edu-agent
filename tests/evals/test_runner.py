"""runner 共享契约面合同(#521 I6-C C4 起):EvalRunner 执行机械已删,本文件只测
保留的共享件——safe_case_id(#450 文件名/行 id 契约)与晨间摘要读者面(summary.py
纯读 run 目录;目录形态由 Inspect adapter 写出,与 legacy 工件同形)。失败分类
taxonomy、strict identity 全等门、并发/续跑的现行持有面 = tests/evals/
test_inspect_adapter.py(经公开入口 run_inspect_round)。

全部用假被测对象与假目录,不碰 gateway/老系统/真实模型。
"""

from __future__ import annotations

import json
from pathlib import Path

from edu_agent.evals import (
    morning_summary,
    safe_case_id,
    write_summary,
)


def test_safe_case_id_keeps_long_ids_and_uniqueness():
    """#450 regression(Phase A 2026-09-25 infra incident):97 字符案整串保真——
    结果行 case_id 与 scenarios 键(原始 id)一致,check_rows/judge_rows 查键不再
    断;超文件名字节预算(240B)的病理长 ID 以内容哈希后缀保唯一,同前缀不撞档。"""
    long_id = "a64_target_v3_northwest_clarification_not_leakage" + "z" * 48
    assert len(long_id) == 97
    assert safe_case_id(long_id, 0) == long_id           # 不截断:join 键保真
    # 既有契约回归面:短 id 原样、非法字符替换、None/空 → 序号兜底
    assert safe_case_id("c00", 0) == "c00"
    assert safe_case_id("a/b c", 3) == "a_b_c"
    assert safe_case_id(None, 7) == "case-0007"
    assert safe_case_id("", 7) == "case-0007"
    # 超预算:同 240B 前缀的两个不同 id → 不同 safe id;输出恒 ≤240B;同 id 幂等
    huge_a = "甲" * 200 + "A"                              # 601B,前 600B 同
    huge_b = "甲" * 200 + "B"
    assert safe_case_id(huge_a, 0) != safe_case_id(huge_b, 0)
    assert all(len(safe_case_id(h, 0).encode("utf-8")) <= 240 for h in (huge_a, huge_b))
    assert safe_case_id(huge_a, 0) == safe_case_id(huge_a, 1)


# ------------------------------------------------------------ 晨间摘要读者面 ----
def _row(case_id: str, status: str, *, error: str | None = None) -> dict:
    """Canonical 七字段结果行(执行面只产形状,摘要只读其中五面)。"""
    return {"case_id": case_id, "status": status, "attempts": 1, "duration_ms": 10,
            "finished_at": "2026-10-04T00:00:00+00:00", "error": error, "transcript": None}


def _run_dir(root: Path, rows: list[dict], total: int, tag: str) -> Path:
    """合成 run 目录(manifest + results/<case>.json;与 Inspect/legacy 工件同形)。"""
    run_dir = root / "runs" / f"cases-20261004T000000Z-{tag}"
    results = run_dir / "results"
    results.mkdir(parents=True)
    for row in rows:
        (results / f"{row['case_id']}.json").write_text(
            json.dumps(row, ensure_ascii=False), encoding="utf-8")
    (run_dir / "manifest.json").write_text(json.dumps({
        "started_at": "2026-10-04T00:00:00+00:00",
        "dataset": {"name": "fake20.jsonl", "sha256": "0" * 64},
        "config": {"concurrency": 2, "sha256": "0" * 64},
        "subject": "fake-subject", "total_cases": total}, ensure_ascii=False),
        encoding="utf-8")
    return run_dir


def test_morning_summary_counts_and_actions(tmp_path):
    """过夜中断后的目录状态(20 案:ok 12、env 2、content 3、未跑 3)→ 完成度/
    失败按类/建议动作;p50/p95 与 summary.md 落盘;全绿路径给出 judge 转进动作。"""
    ok = [f"c{i:02d}" for i in range(12)]                    # c00-c11 共 12 案 ok
    rows = ([_row(cid, "ok") for cid in ok]
            + [_row("c12", "environment", error="环境抖动:服务暂不可用"),
               _row("c13", "environment", error="凭据过期"),
               _row("c14", "content", error="ValueError: 输出缺字段"),
               _row("c15", "content", error="TypeError: 坏题面"),
               _row("c16", "content", error="KeyError: 缺总结")])
    # 12 ok + 2 env + 3 content = 17 落盘,c17-c19 三条未跑(过夜中断后的目录状态)
    run_dir = _run_dir(tmp_path, rows, total=20, tag="interrupted")
    summary = morning_summary(run_dir)
    assert "ok 12/20(60%)" in summary
    assert "未跑 3 · 环境失败 2 · 内容失败 3" in summary
    assert "environment 2 · content 3" in summary
    assert "续跑:还有 3 条" in summary
    assert "补跑环境失败 2 条" in summary
    assert "内容失败 3 条转 judge" in summary
    assert "p50" in summary and "p95" in summary
    write_summary(run_dir)
    assert (run_dir / "summary.md").read_text(encoding="utf-8") == summary
    # 全绿路径
    ok_dir = _run_dir(tmp_path, [_row(f"c{i:02d}", "ok") for i in range(20)],
                      total=20, tag="all-ok")
    assert "全部 20 条完成:进入 judge 评分与报告" in morning_summary(ok_dir)
