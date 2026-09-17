"""#332 账实三单行修的回归:facts 归位 / 失败不计 calls / 重评账落 checkpoint。

A 试跑两回执(c5712289270 及点火前阻塞单)观察的落地;全假上游零模型,
各一个最小断言。计费口径:#332 起 count 只计成功调用(edu.outcome == "ok")。
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from edu_agent.evals import GepaConfig, ScoreVector, gepa_loop
from edu_agent.gateway import FactWriter


def _sv(mean, nr, viol, hard=0.0):
    return ScoreVector(mean, nr, viol, hard)


def _stats(calls=0, tutor=0, judge=0):
    return {"calls": calls, "tokens_in": 0, "tokens_out": 0, "wall_ms": 1,
            "env_failures": 0, "content_failures": 0,
            "tutor_calls": tutor, "judge_calls": judge,
            "leak_net_violations": 0, "hard_vetoed": False,
            "h": 0, "n": 0, "u": 0, "mean": 0.0}


TRAIN_3 = [
    {"id": "c1", "question": "q", "student_turns": ["a"]},
    {"id": "c2", "question": "q", "student_turns": ["b"]},
    {"id": "c3", "question": "q", "student_turns": ["c"]},
]


def test_driver_wires_facts_dir_to_output():
    """账实①:driver 把 facts 归位 output_dir/facts(不再落 cwd/facts)。

    gepa_driver 是私有脚本模块(02 §6 测试只导公开入口),布线按
    tests/rules/test_backup_wiring.py 先例钉源级接线。
    """
    import edu_agent

    src = (Path(edu_agent.__file__).parent / "evals" / "gepa_driver.py"
           ).read_text(encoding="utf-8")
    assert 'facts_dir=args.output_dir / "facts"' in src
    # 裸构造(不传 facts_dir)不得回归
    assert 'Gateway(load_registry(Path("configs/models.yaml")))' not in src


def test_fact_writer_failure_lines_not_counted_as_calls(tmp_path):
    """账实②:失败行照写(留诊断),count(calls 计费)只含成功。"""
    w = FactWriter(tmp_path)
    w.write({"edu.outcome": "ok", "gen_ai.usage.input_tokens": 10,
             "gen_ai.usage.output_tokens": 2})
    w.write({"edu.outcome": "connection"})
    w.write({"edu.outcome": "schema_violation"})
    assert w.count == 1  # 两次失败不进 calls 计费,只计唯一成功调用
    total = sum(len(p.read_text(encoding="utf-8").splitlines())
                for p in tmp_path.glob("model_calls-*.jsonl"))
    assert total == 3  # 失败行照写,审计事实不丢


def test_refresh_reference_checkpoint_survives_mid_round_crash(tmp_path):
    """账实③:换批重评的预算扣减即落 checkpoint——轮内崩溃不虚增(重启可续)。"""
    def fake_eval(cases, template, gateway, judge_role="judge", support_hint=None):
        return _sv(8.0, 0.1, 0.1), [], _stats(calls=5, tutor=3, judge=2)

    with patch("edu_agent.evals.gepa.evaluate_batch", side_effect=fake_eval), \
         patch("edu_agent.evals.gepa.edit_template",
               side_effect=[("变体0:讲讲思路的第一步", "edited")]), \
         patch("edu_agent.evals.gepa._process_round",
               side_effect=RuntimeError("轮内崩溃")):
        with pytest.raises(RuntimeError):
            gepa_loop(train_cases=TRAIN_3, initial_template="初始:说说思路",
                      config=GepaConfig(rounds=2, max_calls=1000),
                      gateway=MagicMock(), output_dir=tmp_path, resume=False)

    saved = json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8"))
    # 崩溃发生在 _process_round(轮内):种子 5 + 换批重评 5 已落盘,不随进程消失
    assert saved["budget"]["calls"] == 10
    assert saved["next_round"] == 0  # 本轮未跑完,恢复时重跑本轮
