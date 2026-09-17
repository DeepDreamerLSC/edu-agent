"""GEPA 配对实验测试(#256,2026-09-16):paired_loop / evaluate_batch_paired。

单文件 800 行上限拆分自 test_gepa.py(02 §2,同 gepa_editors.py 拆分先例)。
"""

from unittest.mock import MagicMock, patch



def _wire_writer_counters(gateway: MagicMock, *, start: int = 0) -> None:
    """MagicMock gateway 的 writer 配进程内计数真值(#324 C2 口径,与
    test_gepa.py 同名 helper 一致:生产 FactWriter 自带进程内累计,
    mock 下需显式配 int,否则 Mock 参与算术直接 TypeError)。"""
    gateway.writer.count = start
    gateway.writer.tokens_in = 0
    gateway.writer.tokens_out = 0


# === 配对实验(2026-09-16, #256 配对实验)===

def test_evaluate_batch_paired_returns_per_case_scores(tmp_path):
    """配对模式:逐案返回 scores + 转录快照(首问 + 全 tutor 轮 + 模板注入标记)+ stats。
    
    契约:transcript 真实形状无 first_question 键;首问来自 turns[0].tutor;
    快照含全转录 tutor 轮(review-303-rerun P1-5:空转扫描用)。
    """
    from edu_agent.evals import evaluate_batch_paired
    
    gateway = MagicMock()
    gateway.writer.root = tmp_path  # 空 facts 目录
    _wire_writer_counters(gateway)  # #324 C2:writer 进程内计数
    subject_mock = MagicMock()
    # 真实形状:无 first_question 键;首问在 turns[0].tutor
    subject_mock.run_case.return_value = {
        "turns": [{"student": "", "tutor": "我们从头把思路串一遍——先说说你第一步", "state": "first_question_ready", "elapsed_ms": 0}],
        "summary": "",
        "session_id": "t",
    }
    cases = [
        {"id": "c1", "question": "1+1?", "grade": "三年级", "reference_answer": "2"},
        {"id": "c2", "question": "2+2?", "grade": "三年级", "reference_answer": "4"},
    ]
    
    call_count = {"n": 0}
    def fake_judge(gw, judge_case, role="judge_independent"):
        call_count["n"] += 1
        return {
            "total": 10 + call_count["n"],
            "verdict": "pass",
            "math_integrity": 2,
            "answer_leaked": False,
            "scores": {"first_question": 2, "socratic_followup": 2, "grade_fit": 2,
                       "pacing": 2, "summary_mastery": 2, "termination": 2},
            "evidence": {},
        }
    
    with patch("edu_agent.evals.gepa_paired.ElicitSubject", return_value=subject_mock), \
         patch("edu_agent.evals.gepa.judge_transcript", side_effect=fake_judge):
        per_case, snaps, stats = evaluate_batch_paired(cases, "template", gateway)
    
    assert len(per_case) == 2
    assert per_case[0]["case_id"] == "c1"
    assert per_case[0]["total"] == 11
    assert per_case[1]["total"] == 12
    assert per_case[0]["hard_fail"] is False
    # 快照含首问 + 全 tutor 轮 + 模板注入标记
    assert len(snaps) == 2
    assert snaps[0]["first_question"] == "我们从头把思路串一遍——先说说你第一步"
    assert snaps[0]["tutor_turns"] == ["我们从头把思路串一遍——先说说你第一步"]
    assert snaps[0]["template_in_transcript"] is False  # "template" 不在 tutor 文本里
    # stats.calls 来自 facts 计数(tmp_path 无文件 → 0)
    assert stats["calls"] == 0  # facts 目录空,实测 0 行


def test_paired_loop_produces_paired_report(tmp_path):
    """配对循环:产出 round-*.json + paired-report.json(含 Δ 和验证项)。
    
    契约:变体模板经 _ask_restatement 注入后续轮(mock 转录 tutor 文本含变体模板,
    模板命中 → 非空转);Δ 由逐案分驱动。
    """
    from edu_agent.evals import paired_loop, GepaConfig
    import json
    
    gateway = MagicMock()
    gateway.writer.root = tmp_path
    _wire_writer_counters(gateway)  # #324 C2:writer 进程内计数
    subject_mock = MagicMock()
    # 真实形状:首问是问候语,变体模板经后轮注入(模板命中 → 非空转);
    # parent 与 variant 转录后轮文本不同(配对对照真实形态)
    parent_transcript = {
        "turns": [
            {"student": "", "tutor": "你好同学,这道题你的答案是什么呀?", "state": "first_question_ready", "elapsed_ms": 0},
            {"student": "答案是3", "tutor": "我们从头把思路串一遍——先说说你第一步怎么想的", "state": "dialogue", "elapsed_ms": 0},
        ],
        "summary": "", "session_id": "t",
    }
    variant_transcript = {
        "turns": [
            {"student": "", "tutor": "你好同学,这道题你的答案是什么呀?", "state": "first_question_ready", "elapsed_ms": 0},
            {"student": "答案是3", "tutor": "我们从头理一遍思路——你先说第一步怎么想的", "state": "dialogue", "elapsed_ms": 0},
        ],
        "summary": "", "session_id": "t",
    }
    subject_mock.run_case.side_effect = [
        parent_transcript, parent_transcript,  # parent run: c1, c2
        variant_transcript, variant_transcript,  # variant run: c1, c2
    ]
    cases = [
        {"id": "c1", "question": "1+1?", "grade": "三年级", "reference_answer": "2"},
        {"id": "c2", "question": "2+2?", "grade": "三年级", "reference_answer": "4"},
    ]
    
    call_count = {"n": 0}
    def fake_judge(gw, judge_case, role="judge_independent"):
        call_count["n"] += 1
        total = 10 if call_count["n"] <= 2 else 11  # parent=10, variant=11
        return {
            "total": total,
            "verdict": "pass",
            "math_integrity": 2,
            "answer_leaked": False,
            "scores": {"first_question": 2, "socratic_followup": 2, "grade_fit": 2,
                       "pacing": 2, "summary_mastery": 2, "termination": 2},
            "evidence": {},
        }
    
    def fake_edit(current, failures, gw):
        return "我们从头理一遍思路——你先说第一步怎么想的", "edited"  # #324 A-e
    
    config = GepaConfig(rounds=1, batch_size=2, max_calls=100)
    
    with patch("edu_agent.evals.gepa_paired.ElicitSubject", return_value=subject_mock), \
         patch("edu_agent.evals.gepa.judge_transcript", side_effect=fake_judge), \
         patch("edu_agent.evals.gepa_paired.edit_template", side_effect=fake_edit):
        reports = paired_loop(cases, "initial", config, gateway, tmp_path)
    
    assert len(reports) == 1
    report = reports[0]
    assert "paired_cases" in report
    assert len(report["paired_cases"]) == 2
    # 验证 Δ 计算
    assert report["paired_cases"][0]["delta"] == 1  # variant=11 - parent=10
    # 模板命中(全转录口径:变体模板在后轮出现)→ 非空转
    assert report["paired_cases"][0]["variant_template_in_transcript"] is True
    assert report["paired_cases"][0]["idle"] is False
    assert report["paired_cases"][0]["transcripts_identical"] is False
    assert report["template_hit_validation"]["hit_count"] == 2
    assert report["template_hit_validation"]["idle_count"] == 0
    # 验证三项验证字段存在
    assert "hard_fail_validation" in report
    assert "template_hit_validation" in report
    assert "editor_feedback_sample" in report
    # 首问对比字段存在
    assert "parent_first_question" in report["paired_cases"][0]
    assert "variant_first_question" in report["paired_cases"][0]
    
    # 验证 paired-report.json 产出
    paired_report_path = tmp_path / "paired-report.json"
    assert paired_report_path.exists()
    paired_summary = json.loads(paired_report_path.read_text())
    assert "mean_delta" in paired_summary
    assert paired_summary["mean_delta"] == 1.0
    # 冻结协议:非空转 + Δ>0 多数同向 → GO
    assert paired_summary["verdict"] == "GO"
    assert paired_summary["idle_detected"] is False
    # facts 实测字段存在
    assert "real_calls" in paired_summary
    assert "tokens_in" in paired_summary
    assert "tokens_out" in paired_summary


def test_paired_loop_verdict_red_light_when_delta_zero(tmp_path):
    """冻结协议:模板命中(非空转)+ Δ≈0 → 红灯。"""
    from edu_agent.evals import paired_loop, GepaConfig
    import json
    
    gateway = MagicMock()
    gateway.writer.root = tmp_path
    _wire_writer_counters(gateway)  # #324 C2:writer 进程内计数
    subject_mock = MagicMock()
    # 变体模板出现在后续 tutor 轮(模板命中 → 非空转),Δ 才有信息量
    subject_mock.run_case.return_value = {
        "turns": [
            {"student": "", "tutor": "你好同学,这道题你的答案是什么呀?", "state": "first_question_ready", "elapsed_ms": 0},
            {"student": "答案是3", "tutor": "我们从头理一遍思路——你先说第一步怎么想的", "state": "dialogue", "elapsed_ms": 0},
        ],
        "summary": "", "session_id": "t",
    }
    cases = [{"id": "c1", "question": "1+1?", "grade": "三年级", "reference_answer": "2"}]
    
    def fake_judge(gw, judge_case, role="judge_independent"):
        return {"total": 10, "verdict": "pass", "math_integrity": 2, "answer_leaked": False,
                "scores": {"first_question": 2, "socratic_followup": 2, "grade_fit": 2,
                           "pacing": 2, "summary_mastery": 2, "termination": 2}, "evidence": {}}
    
    def fake_edit(current, failures, gw):
        return "我们从头理一遍思路——你先说第一步怎么想的", "edited"  # #324 A-e
    
    config = GepaConfig(rounds=1, batch_size=1, max_calls=100)
    
    with patch("edu_agent.evals.gepa_paired.ElicitSubject", return_value=subject_mock), \
         patch("edu_agent.evals.gepa.judge_transcript", side_effect=fake_judge), \
         patch("edu_agent.evals.gepa_paired.edit_template", side_effect=fake_edit):
        paired_loop(cases, "initial", config, gateway, tmp_path)
    
    paired_summary = json.loads((tmp_path / "paired-report.json").read_text())
    # 模板命中 + 全 Δ=0 → 红灯(冻结协议)
    assert paired_summary["idle_detected"] is False
    assert paired_summary["verdict"] == "红灯"


def test_paired_loop_idle_override_invalid_run(tmp_path):
    """冻结前提(review-303-rerun P1-1):空转 → 无效跑(override,非红灯)。
    
    变体模板未注入转录(全转录扫描不命中)→ Δ 对 judge 敏感度零信息量
    (转录全同 + judge temp=0 确定性)→ 无效跑,即使 Δ 非零也不判 GO。
    """
    from edu_agent.evals import paired_loop, GepaConfig
    import json
    
    gateway = MagicMock()
    gateway.writer.root = tmp_path
    _wire_writer_counters(gateway)  # #324 C2:writer 进程内计数
    subject_mock = MagicMock()
    # 变体模板不出现在任何 tutor 轮(空转)——即使 judge 打出非零 Δ
    idle_transcript = {
        "turns": [
            {"student": "", "tutor": "你好同学,这道题你的答案是什么呀?", "state": "first_question_ready", "elapsed_ms": 0},
            {"student": "答案是3", "tutor": "好的,我们继续看下一问。", "state": "dialogue", "elapsed_ms": 0},
        ],
        "summary": "", "session_id": "t",
    }
    subject_mock.run_case.return_value = idle_transcript
    cases = [{"id": "c1", "question": "1+1?", "grade": "三年级", "reference_answer": "2"}]
    
    call_count = {"n": 0}
    def fake_judge(gw, judge_case, role="judge_independent"):
        call_count["n"] += 1
        total = 10 if call_count["n"] == 1 else 12  # 制造非零 Δ=2,但空转使其无效
        return {"total": total, "verdict": "pass", "math_integrity": 2, "answer_leaked": False,
                "scores": {"first_question": 2, "socratic_followup": 2, "grade_fit": 2,
                           "pacing": 2, "summary_mastery": 2, "termination": 2}, "evidence": {}}
    
    def fake_edit(current, failures, gw):
        return "我们从头理一遍思路——你先说第一步怎么想的", "edited"  # #324 A-e
    
    config = GepaConfig(rounds=1, batch_size=1, max_calls=100)
    
    with patch("edu_agent.evals.gepa_paired.ElicitSubject", return_value=subject_mock), \
         patch("edu_agent.evals.gepa.judge_transcript", side_effect=fake_judge), \
         patch("edu_agent.evals.gepa_paired.edit_template", side_effect=fake_edit):
        reports = paired_loop(cases, "initial", config, gateway, tmp_path)
    
    paired_summary = json.loads((tmp_path / "paired-report.json").read_text())
    # 空转 override:非零 Δ 也不判 GO/红灯 → 无效跑
    assert paired_summary["idle_detected"] is True
    assert paired_summary["verdict"] == "无效跑"
    # 全转录口径逐案标记:模板未注入 + 转录逐字相同(空转辅证)
    assert reports[0]["paired_cases"][0]["variant_template_in_transcript"] is False
    assert reports[0]["paired_cases"][0]["transcripts_identical"] is True
    assert reports[0]["paired_cases"][0]["idle"] is True


def test_structural_probe_dumps_artifacts_before_over_budget_exit(tmp_path):
    """Harness P1:超预算退出必须先落工件再退(付费数据不许销毁)。"""
    import sys
    import json
    import pytest
    from pathlib import Path
    from unittest.mock import patch, MagicMock
    
    # 导入 probe 脚本
    probe_path = Path("edu_agent/evals/artifacts/gepa-spike/structural-probe")
    sys.path.insert(0, str(probe_path))
    import run_probe
    
    # 设置输出目录为 tmp_path
    original_parent = run_probe.PARENT_TEMPLATE
    original_variant = run_probe.STRUCTURAL_VARIANT
    original_cap = run_probe.HARD_CAP_CALLS
    
    try:
        # 修改硬顶为低值以便测试
        run_probe.HARD_CAP_CALLS = 10
        
        # Mock Gateway 和 load_scenarios
        mock_gateway = MagicMock()
        mock_cases = [
            {"id": "c1", "question": "1+1?", "grade": "三年级", "reference_answer": "2"},
            {"id": "c2", "question": "2+2?", "grade": "三年级", "reference_answer": "4"},
        ]
        
        # Mock evaluate_batch_paired 返回高调用数(> HARD_CAP_CALLS)
        def fake_evaluate(cases, template, gateway):
            scores = [
                {"case_id": f"c{i+1}", "total": 10, "verdict": "pass", "mi": 2, "hard_fail": False}
                for i in range(len(cases))
            ]
            snaps = [
                {"case_id": f"c{i+1}", "first_question": "你好同学",
                 "tutor_turns": ["你好同学", template],
                 "template_in_transcript": True}
                for i in range(len(cases))
            ]
            stats = {"calls": 50, "tokens_in": 1000, "tokens_out": 500}  # 50 > 10 硬顶
            return scores, snaps, stats
        
        # Mock 其他依赖
        with patch.object(run_probe, 'load_registry'), \
             patch.object(run_probe, 'Gateway', return_value=mock_gateway), \
             patch.object(run_probe, 'load_scenarios', return_value=mock_cases), \
             patch.object(run_probe, 'evaluate_batch_paired', side_effect=fake_evaluate), \
             patch.object(run_probe, '__file__', str(tmp_path / "run_probe.py")):
            
            # 运行 main(),期望 sys.exit(1)
            with pytest.raises(SystemExit) as exc_info:
                run_probe.main()
            
            # 验证 exit code = 1
            assert exc_info.value.code == 1
            
            # 验证工件已落(关键断言)
            round_path = tmp_path / "round-00.json"
            paired_path = tmp_path / "paired-report.json"
            
            assert round_path.exists(), "round-00.json 必须在超预算退出前写入"
            assert paired_path.exists(), "paired-report.json 必须在超预算退出前写入"
            
            # 验证 paired-report.json 内容
            paired_report = json.loads(paired_path.read_text())
            assert paired_report["over_budget"] is True, "over_budget 标记必须为 true"
            assert paired_report["real_calls"] == 100  # 50 + 50
            assert "deltas" in paired_report
            assert "verdict" in paired_report
    
    finally:
        # 恢复原值
        run_probe.PARENT_TEMPLATE = original_parent
        run_probe.STRUCTURAL_VARIANT = original_variant
        run_probe.HARD_CAP_CALLS = original_cap
        sys.path.remove(str(probe_path))


