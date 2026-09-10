"""#34 json_first_pass 口径(#34 M2 出口条件,口径文档 docs/evals/json-first-pass-v1.md)。

主口径:分母 = schema 角色(tutor/judge)attempt==1 行;分子 = 其中未发生 schema_violation。
透明规则:非 schema 失败(truncated 等)按定义计入通过,但必须单列明细。
"""

import json

import scripts.json_first_pass as jfp

from rulekit import run_py


def _fact(role: str, attempt: int, outcome: str, *, model: str = "mlx_27b",
          session: str = "s1") -> str:
    return json.dumps({
        "edu.role": role, "edu.attempt": attempt, "edu.outcome": outcome,
        "edu.session_id": session, "gen_ai.request.model": model,
    }, ensure_ascii=False)


def _write_facts(tmp_path, rows: list[str], name: str = "model_calls-2026-09-10.jsonl"):
    facts_dir = tmp_path / "facts"
    facts_dir.mkdir(exist_ok=True)
    (facts_dir / name).write_text("\n".join(rows) + "\n", encoding="utf-8")
    return facts_dir


def test_main_rate_schema_violation_counts_against(tmp_path):
    """attempt==1 schema_violation 计入分子外;重试成功不改判。"""
    facts = _write_facts(tmp_path, [
        _fact("tutor", 1, "ok"),
        _fact("tutor", 1, "schema_violation"),  # 一次违规 → 不计
        _fact("tutor", 2, "ok"),                # 重试行,不计分母也不计分子
        _fact("judge", 1, "ok"),
    ])
    result = run_py("json_first_pass.py", "--dir", str(facts))
    assert result.returncode == 0
    assert "2/3 = 66.7%" in result.stdout  # 2 ok / 3 调用
    assert "❌" in result.stdout  # < 98%


def test_truncated_is_first_pass_but_flagged(tmp_path):
    """非 schema 失败(truncated)按定义计通过,但必须单列明细。"""
    facts = _write_facts(tmp_path, [
        _fact("tutor", 1, "truncated", session="sess-x"),
        _fact("judge", 1, "ok"),
    ])
    result = run_py("json_first_pass.py", "--dir", str(facts))
    assert result.returncode == 0
    assert "2/2 = 100.0%" in result.stdout
    assert "✅" in result.stdout
    assert "truncated" in result.stdout  # 透明度单列
    assert "sess-x" in result.stdout


def test_non_schema_roles_excluded(tmp_path):
    """非 schema 角色(vision 等)不进分母。"""
    facts = _write_facts(tmp_path, [
        _fact("tutor", 1, "ok"),
        _fact("vision", 1, "schema_violation"),  # 排除
    ])
    result = run_py("json_first_pass.py", "--dir", str(facts))
    assert result.returncode == 0
    assert "1/1 = 100.0%" in result.stdout


def test_empty_facts_returns_1(tmp_path):
    """无 facts 或无可计数行 → 退出码 1(调用方可见,不静默通过)。"""
    facts = tmp_path / "facts"
    facts.mkdir()
    result = run_py("json_first_pass.py", "--dir", str(facts))
    assert result.returncode == 1
    assert "无 schema 角色" in result.stdout


def test_attempt2_only_rows_excluded(tmp_path):
    """只有 attempt==2 行(如单独的重试文件)→ 不产生分母。"""
    facts = _write_facts(tmp_path, [
        _fact("tutor", 2, "ok"),
    ])
    result = run_py("json_first_pass.py", "--dir", str(facts))
    assert result.returncode == 1
    assert "无 schema 角色" in result.stdout


def test_report_table_shape(tmp_path):
    """Markdown 报告含角色分解表与合计行。"""
    facts = _write_facts(tmp_path, [
        _fact("tutor", 1, "ok"),
        _fact("judge", 1, "ok"),
    ])
    report = jfp.json_first_pass_report(facts)
    assert "| tutor |" in report
    assert "| judge |" in report
    assert "| **合计** | **2** | **2** | **100.0%**" in report


def test_since_filters_by_filename(tmp_path):
    """--since 只统计指定日期及之后的文件。"""
    facts = _write_facts(tmp_path, [_fact("tutor", 1, "ok")], name="model_calls-2026-09-09.jsonl")
    _write_facts(tmp_path, [_fact("judge", 1, "ok")], name="model_calls-2026-09-10.jsonl")
    result = run_py("json_first_pass.py", "--dir", str(facts), "--since", "2026-09-10")
    assert result.returncode == 0
    assert "1/1 = 100.0%" in result.stdout
