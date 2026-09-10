"""#34 json_first_pass 口径(#34 M2 出口条件,口径文档 docs/evals/json-first-pass-v1.md)。

2026-09-10 评审修订口径:合规分母 = 产出了模型响应的行(outcome ∈
{ok, schema_violation, truncated, content_filtered});基础设施失败(timeout/rate_limited/
upstream/connection)移出分母,单列 availability。分子 = ok。
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


def test_schema_violation_counts_against(tmp_path):
    """attempt==1 schema_violation 计入不合规;重试成功不改判。"""
    facts = _write_facts(tmp_path, [
        _fact("tutor", 1, "ok"),
        _fact("tutor", 1, "schema_violation"),  # 一次违规 → 不计
        _fact("tutor", 2, "ok"),                # 重试行,不进分母
        _fact("judge", 1, "ok"),
    ])
    result = run_py("json_first_pass.py", "--dir", str(facts))
    assert result.returncode == 0
    assert "2/3 = 66.7%" in result.stdout  # 2 ok / 3 产出结果
    assert "❌" in result.stdout  # < 98%


def test_truncated_counts_against(tmp_path):
    """truncated 产出了(不完整)响应 → 在合规分母内,计入未通过。"""
    facts = _write_facts(tmp_path, [
        _fact("tutor", 1, "truncated", session="sess-x"),
        _fact("judge", 1, "ok"),
    ])
    result = run_py("json_first_pass.py", "--dir", str(facts))
    assert result.returncode == 0
    assert "1/2 = 50.0%" in result.stdout
    assert "❌" in result.stdout
    assert "truncated" in result.stdout  # 不合规明细
    assert "sess-x" in result.stdout


def test_infra_failure_out_of_denominator(tmp_path):
    """基础设施失败(connection)移出合规分母,单列 availability。"""
    facts = _write_facts(tmp_path, [
        _fact("tutor", 1, "connection", session="sess-net"),
        _fact("judge", 1, "ok"),
    ])
    result = run_py("json_first_pass.py", "--dir", str(facts))
    assert result.returncode == 0
    assert "1/1 = 100.0%" in result.stdout  # 合规分母只有 ok 一行
    assert "✅" in result.stdout
    assert "availability" in result.stdout  # 单列
    assert "connection" in result.stdout


def test_timeout_and_rate_limited_out_of_denominator(tmp_path):
    """timeout/rate_limited 同样移出分母。"""
    facts = _write_facts(tmp_path, [
        _fact("tutor", 1, "timeout_total"),
        _fact("judge", 1, "rate_limited"),
        _fact("judge", 1, "ok"),
    ])
    result = run_py("json_first_pass.py", "--dir", str(facts))
    assert result.returncode == 0
    assert "1/1 = 100.0%" in result.stdout
    assert "availability" in result.stdout


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
    assert "无产出模型响应" in result.stdout


def test_attempt2_only_rows_excluded(tmp_path):
    """只有 attempt==2 行(如单独的重试文件)→ 不产生分母。"""
    facts = _write_facts(tmp_path, [
        _fact("tutor", 2, "ok"),
    ])
    result = run_py("json_first_pass.py", "--dir", str(facts))
    assert result.returncode == 1
    assert "无产出模型响应" in result.stdout


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
