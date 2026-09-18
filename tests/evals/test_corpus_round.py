"""corpus_round 纯逻辑测试(#216):零模型——过滤/撞名/跨轮 diff/报告渲染。

批跑面(KernelSubject+EvalRunner+judge)与 tuning_round 同口径,不在单测里重复
(#216 边界:真模型不进 CI);这里只钉数据的分诊与对照语义。
"""

from __future__ import annotations

import csv
import re
import json
from pathlib import Path

import pytest

from edu_agent.evals import (
    DATASETS_DIR,
    DEFAULT_CORPUS,
    check_rows,
    diff_checks,
    load_shortboard_corpus,
    real_model_scenarios,
    render_report,
    scenario_fingerprint,
    soften_counts,
    soften_line,
)


def _scenario(sid: str, *, fake_model: bool = False, checks: bool = True) -> dict:
    scenario = {
        "id": sid,
        "status": "guarded",
        "question": {"text": "鸡和兔一共有8只，共有26只脚。鸡和兔各有多少只？说明思路。",
                     "answer": "鸡3只，兔5只"},
        "student_turns": ["我不会做。"],
        "grade": "六年级",
        "source": {"issue": 197},
    }
    if fake_model:
        scenario["fake_model"] = [{"json": {"reply": "罐头"}}]
    if checks:
        scenario["expect"] = {"checks": [{"name": "finish_status", "status": "completed"}]}
    return scenario


def _write_corpus(tmp_path: Path, name: str, scenarios: list[dict]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({"schema_version": "small_lecturer_shadow_pilot_corpus/v1",
                                "scenarios": scenarios}, ensure_ascii=False), encoding="utf-8")
    return path


def test_real_model_filter_keeps_only_no_fake_model(tmp_path):
    """确定性口径(带 fake_model)不进本面(#216 边界);真模型口径全保留。"""
    path = _write_corpus(tmp_path, "pilot_a.json", [
        _scenario("s1"), _scenario("s2", fake_model=True)])
    scenarios = real_model_scenarios([path])
    assert list(scenarios) == ["pilot_a_s1"]


def test_case_id_prefixes_dataset_and_rejects_collision(tmp_path):
    """case id 加数据集前缀(报告行自带溯源);前缀后仍撞名 = 写错,即刻红。"""
    path_a = _write_corpus(tmp_path, "pilot_a.json", [_scenario("s1")])
    path_b = _write_corpus(tmp_path, "pilot_b.json", [_scenario("s1")])
    scenarios = real_model_scenarios([path_a, path_b])
    assert sorted(scenarios) == ["pilot_a_s1", "pilot_b_s1"]
    # 同一文件传两遍(重复 --corpus 参数)→ 前缀后仍撞名 = 写错,即刻红
    with pytest.raises(ValueError, match="撞名"):
        real_model_scenarios([path_a, path_a])


def test_check_rows_distinguishes_undeclared_from_all_green():
    """未声明 checks(adaptive 形态)记 declared=False,不冒充全绿。"""
    scenarios = {"x_s1": _scenario("s1"), "x_s2": _scenario("s2", checks=False)}
    results = [
        {"case_id": "x_s1", "status": "ok", "transcript": {"final_state": "completed", "turns": []}},
        {"case_id": "x_s2", "status": "ok", "transcript": {"final_state": "needs_review", "turns": []}},
        {"case_id": "x_s3", "status": "environment", "transcript": None},
    ]
    # x_s3 无场景声明 → check_rows 按缺失场景容错?不:scenario 查找必须命中,先补声明
    scenarios["x_s3"] = _scenario("s3")
    rows = check_rows(scenarios, results)
    # advisories = #333 no-progress 非阻断诊断(空转录零报,仅报告不进 failures)
    assert rows["x_s1"] == {"status": "ok", "declared": True, "final_state": "completed",
                            "failures": [], "advisories": []}
    assert rows["x_s2"]["declared"] is False and rows["x_s2"]["failures"] is None
    assert rows["x_s3"]["status"] == "environment"


def test_diff_checks_classifies_new_red_and_flip():
    """绿→红 = 新增红(回归信号);红→绿 = 翻绿;首轮红无前科也是新增红。"""
    current = {
        "a": {"status": "ok", "declared": True, "failures": [{"check": "c", "detail": "d"}], "final_state": ""},
        "b": {"status": "ok", "declared": True, "failures": [], "final_state": ""},
        "c": {"status": "ok", "declared": True, "failures": [], "final_state": ""},
    }
    previous = {
        "a": {"status": "ok", "declared": True, "failures": [], "final_state": ""},
        "b": {"status": "ok", "declared": True, "failures": [{"check": "c", "detail": "d"}], "final_state": ""},
    }
    verdicts = diff_checks(current, previous)
    assert verdicts == {"a": "新增红", "b": "翻绿", "c": "绿"}


def test_soften_counts_aggregate_and_report_line():
    """#241 行 4「掩码成功 vs 整步弃用」:报数层按 guard_events 聚合 cut/mask/dropped
    (dropped 此前只写不读);报告行由 soften_line 拼在 render_report 之后
    (#244 审 P1:render_report 不加参,防与 #242 provenance 撞 PLR0913);全零不占行。"""
    results = [
        {"transcript": {"guard_events": [{"branch": "reveal", "soften": "cut"},
                                         {"branch": "reveal", "soften": "mask"},
                                         {"branch": "model"}]}},
        {"transcript": {"guard_events": [{"branch": "reveal", "soften": "cut"},
                                         {"branch": "reveal", "dropped": True}]}},
        {"transcript": {"guard_events": [{"branch": "model"}]}},
    ]
    assert soften_counts(results) == {"cut": 2, "mask": 1, "dropped": 1}
    assert soften_line({"cut": 0, "mask": 0, "dropped": 0}) == ""
    report = render_report(Path("/tmp/out"), {}, {}) + soften_line(soften_counts(results))
    assert ("cut=2(同分句边界收回) / mask=1(兜底改写「几」) / dropped=1(整步弃用)") in report


def test_render_report_marks_undeclared_and_counts_new_red():
    checks = {
        "x_s1": {"status": "ok", "declared": True, "failures": [], "final_state": "completed"},
        "x_s2": {"status": "ok", "declared": False, "failures": None, "final_state": "needs_review"},
    }
    scores = {"x_s1": {"total": 10, "verdict": "pass", "scores": {"socratic_followup": 2}}}
    report = render_report(Path("/tmp/out"), checks, scores,
                           {"from": "prev/run", "verdicts": {"x_s1": "绿", "x_s2": "新增红"}})
    assert "新增红:1" in report and "无声明" in report and "全绿" in report
    assert "追问=2" in report


def test_render_report_shows_previous_judge_total():
    """审查 P3:有上轮 judge 分(按轮留存)时 judge 列给「上轮→本轮」,噪声对比可复算。"""
    checks = {"x_s1": {"status": "ok", "declared": True, "failures": [], "final_state": "completed"}}
    scores = {"x_s1": {"total": 8, "verdict": "review", "scores": {"socratic_followup": 1}}}
    report = render_report(Path("/tmp/out"), checks, scores,
                           {"from": "prev/run", "verdicts": {"x_s1": "绿"},
                            "prev_scores": {"x_s1": {"total": 12}}})
    assert "total=12→8" in report


def test_render_report_provenance_notes():
    """#238 §5 判分器溯源注记:头带指纹;基线无溯源/版本断点各注一句,同指纹静默。"""
    checks = {"x_s1": {"status": "ok", "declared": True, "failures": [], "final_state": "completed"}}
    scores = {"x_s1": {"total": 8, "verdict": "review", "scores": {"socratic_followup": 1}}}
    diff = {"from": "prev/run", "verdicts": {"x_s1": "绿"}, "prev_scores": {}}

    # 无 diff:头带 judger_sha256,不出现任何基线注记
    report = render_report(Path("/tmp/out"), checks, scores,
                           provenance={"current": "abc123", "prev": None})
    assert "judger_sha256:abc123" in report
    assert "基线无溯源" not in report and "判分器已变更" not in report

    # diff + 基线无指纹(首轮 math-gold-v1 形态)→ 注欠账
    report = render_report(Path("/tmp/out"), checks, scores, diff,
                           provenance={"current": "abc123", "prev": None})
    assert "基线无溯源" in report and "判分器已变更" not in report

    # diff + 指纹不同 → 注版本断点
    report = render_report(Path("/tmp/out"), checks, scores, diff,
                           provenance={"current": "abc123", "prev": "fff000"})
    assert "判分器已变更" in report and "基线无溯源" not in report

    # diff + 同指纹 → 可比,两注记都静默
    report = render_report(Path("/tmp/out"), checks, scores, diff,
                           provenance={"current": "abc123", "prev": "abc123"})
    assert "基线无溯源" not in report and "判分器已变更" not in report


def test_train_corpus_count_and_heldout_isolation():
    """腿② 门锚(#238 §4:裁定 c5657228854 + 算术更正 c5657249546)。

    两个口径分开钉死,「哪个算门」归裁定,不在测试里裁决(#248 审 P3):
    - **raw = 120**:裁定口径训练集计数(87 = 27 legacy + b1 金标 60,
      + b2 13 含硬压力轨 1 + 路 A 20);
    - **loadable = 93**:过 corpus 加载面的金标三件——legacy v1/v3 实测
      过不了 load_shortboard_corpus 且全仓无生产消费者,严格口径下
      优化器可见面 = 93。
    留出 4 独立文件不进默认加载(corpus_round 显式路径加载,不传即不可见,
    #238 切分即文件名)。计数随每批转正翻新:改数字须带裁定/回执出处。
    """
    raw = {"small_lecturer_dialogue_scenarios.json": 3,        # legacy v1
           "small_lecturer_shadow_scenarios_24.json": 24,      # legacy v3
           "small_lecturer_math_gold_candidates.json": 60,     # b1 转正(#236)
           "small_lecturer_math_gold_b2.json": 13,             # b2 转正,含硬压力轨 1
           "small_lecturer_teaching_context_shadow_pilot_20.json": 20}  # 路 A 促升
    assert sum(len(json.loads((DATASETS_DIR / name).read_text(encoding="utf-8"))["scenarios"])
               for name in raw) == 120
    gold_train = ("small_lecturer_math_gold_candidates.json",      # b1(#236)
                  "small_lecturer_math_gold_b2.json",             # b2,含硬压力轨 1
                  "small_lecturer_teaching_context_shadow_pilot_20.json")  # 路 A
    loadable = 0
    for name in gold_train:  # 金标三件全过 corpus 加载面且全 teacher_confirmed
        for scenario in load_shortboard_corpus(DATASETS_DIR / name):
            assert scenario["gold"]["status"] == "teacher_confirmed", (name, scenario["id"])
            loadable += 1
    assert loadable == 93
    # 留出 4:独立文件、同样全确认;默认加载面不含 heldout
    heldout = load_shortboard_corpus(DATASETS_DIR / "small_lecturer_math_gold_b2_heldout.json")
    assert len(heldout) == 4
    assert all(s["gold"]["status"] == "teacher_confirmed" for s in heldout)
    assert not any("heldout" in str(path) for path in DEFAULT_CORPUS)


def test_sidecar_fingerprints_recompute_from_pre_promotion_state():
    """review 侧车指纹可复算(#248 审 P3:口径落盘,不再靠变体矩阵反推)。

    指纹 = **审前快照**的 scenario_fingerprint;转正后从现态剥掉转正新增件
    即回审前态:b2 剥法 gold→null(审前键在值空)、路 A 剥法删 gold 键 +
    promotion_evidence_eligible→false。剧本内容任何漂移(台词/触发词改动)
    → 指纹失配红;纯转正件(金标块/促升翻转)不破指纹——这正是侧车要
    钉住的不变量。b1 侧车是 SHA-1 历史口径,不在本断言面。"""
    batches = [
        ("small_lecturer_math_gold_b2.json", "small_lecturer_math_gold_b2.review.csv", "b2"),
        ("small_lecturer_math_gold_b2_heldout.json", "small_lecturer_math_gold_b2_heldout.review.csv", "b2"),
        ("small_lecturer_teaching_context_shadow_pilot_20.json",
         "small_lecturer_teaching_context_shadow_pilot_20.review.csv", "patha"),
    ]
    checked = 0
    for json_name, csv_name, family in batches:
        scenarios = json.loads((DATASETS_DIR / json_name).read_text(encoding="utf-8"))["scenarios"]
        rows = {r["scenario_id"]: r
                for r in csv.DictReader((DATASETS_DIR / csv_name).open(encoding="utf-8"))}
        assert len(rows) == len(scenarios), csv_name
        for scenario in scenarios:
            pre = dict(scenario)
            if family == "b2":
                pre["gold"] = None
            else:
                del pre["gold"]
                meta = dict(pre["metadata"])
                meta["promotion_evidence_eligible"] = False
                pre["metadata"] = meta
            assert rows[scenario["id"]]["scenario_fingerprint"] == scenario_fingerprint(pre), \
                (csv_name, scenario["id"], "审后内容漂移或侧车指纹错")
            checked += 1
    assert checked == 37


def test_run_identity_is_machine_readable():
    """#238 件 A:身份三件套——prompt/models 为 64 位十六进制;git 缺失时 None 不伪造。"""
    from edu_agent.evals import run_identity

    identity = run_identity()
    assert re.fullmatch(r"[0-9a-f]{64}", identity["prompts_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", identity["models_sha256"])
    assert identity["git_sha"] is None or re.fullmatch(r"[0-9a-f]{7,40}", identity["git_sha"])


def _fact(role: str, session: str, *, fallback_to=None) -> dict:
    return {"edu.role": role, "edu.session_id": session, "edu.fallback_to": fallback_to}


def test_facts_dump_load_calibers(tmp_path):
    """#238 件 B:facts 落 run 目录(dump/load 对偶)+ 调用级/会话级口径。"""
    from edu_agent.evals import dump_facts, facts_calibers, load_facts

    facts_dir = tmp_path / "gateway-facts"
    facts_dir.mkdir()
    (facts_dir / "model_calls-2026-09-14.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in [
            _fact("tutor", "kernel_a"), _fact("tutor", "kernel_a", fallback_to="mlx_27b"),
            _fact("judge", "judge-c1"), _fact("tutor", "kernel_b"),
        ]) + "\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    rows = dump_facts(facts_dir, run_dir)
    assert len(rows) == 4 and (run_dir / "facts.jsonl").is_file()
    assert load_facts(run_dir) == rows
    assert load_facts(tmp_path / "no-such-run") == []

    calibers = facts_calibers(rows)
    assert calibers["roles"]["tutor"] == {"calls": 3, "fallbacks": 1, "rate": 1 / 3}
    assert calibers["roles"]["judge"] == {"calls": 1, "fallbacks": 0, "rate": 0.0}
    assert calibers["sessions"] == {"kernel_a": True, "judge-c1": False, "kernel_b": False}


def test_caliber_section_splits_primary_only_vs_with_fallback(tmp_path):
    """#238 件 B:primary-only 剔除任一调用走 fallback 的 case;四指标 + 口径注记随段。"""
    from edu_agent.evals import caliber_section

    def result(cid, session, students, *, final="completed", guard=None):
        turns = [{"student": "", "tutor": "首问"}] + [{"student": s, "tutor": "回"} for s in students]
        return {"case_id": cid, "status": "ok",
                "transcript": {"final_state": final, "turns": turns,
                               "guard_events": guard or [], "session_id": session}}

    # c1:tutor 会话走过 fallback → 只进 with-fallback;学生报了终答(1108)非 false-confirm
    c1 = result("d_c1", "kernel_a", ["我先算了一步", "一共 1108 元"])
    # c2:干净会话但学生从未报出期望数字 3 → false-confirm 代理命中
    c2 = result("d_c2", "kernel_b", ["我想想", "应该没错吧"])
    c3 = result("d_c3", "kernel_c", ["卡住了"], final="needs_review",
                guard=[{"branch": "reveal", "hint_level": 1}])
    sessions = {"kernel_a": True, "kernel_b": False, "kernel_c": False,
                "judge-d_c1": False, "judge-d_c2": False, "judge-d_c3": False}
    checks = {"d_c1": {"final_state": "completed"}, "d_c2": {"final_state": "completed"},
              "d_c3": {"final_state": "needs_review"}}
    scores = {"d_c1": {"total": 12}, "d_c2": {"total": 6}, "d_c3": {"total": 3}}
    scenarios = {
        "d_c1": {"question": {"text": "q", "answer": "1108 元"}},
        "d_c2": {"question": {"text": "q", "answer": "鸡 3 只"}},
        "d_c3": {"question": {"text": "q", "answer": "定性答案"}},  # 无 ASCII 数字:不进分母
    }
    section = caliber_section({"roles": {"tutor": {"calls": 3, "fallbacks": 1, "rate": 1 / 3}},
                               "sessions": sessions},
                              [c1, c2, c3], checks, scores, scenarios)
    assert "口径注记" in section
    # primary-only = c2+c3(c1 的 tutor 会话 fallback 出局):n=2,completed=1(c2,2 学生轮),
    # false-confirm = c2 未报期望数字 3 → 1/1;stuck/needs-review = c3 → 各 50%;judge 均值 (6+3)/2
    assert "| primary-only | 2 | 1 | 2.0 | 1/1 (100.0%) | 50.0% | 50.0% | 4.5 |" in section
    # with-fallback = 全量:n=3,completed=2(ttc=(2+2)/2),false-confirm 1/2,stuck/needs 1/3,均值 7.0
    assert "| with-fallback | 3 | 2 | 2.0 | 1/2 (50.0%) | 33.3% | 33.3% | 7.0 |" in section
    assert "| tutor | 3 | 1 | 33.3% |" in section                # 调用级 role 表


def test_render_from_rebuilds_report_offline(tmp_path, capsys):
    """#257 审 P3-2:--render-from 零模型重渲染——只用工件文件重建 report(含三口径段)。"""
    from edu_agent.evals import render_from

    out = tmp_path / "trial"
    run = out / "collect" / "cases-20260914T000000Z-ab12"
    (run / "results").mkdir(parents=True)
    (run / "judger.sha256").write_text("a" * 64 + "\n", encoding="utf-8")
    scenario = {"id": "d_x", "question": {"text": "q", "answer": "3 只"},
                "student_turns": ["我不会"], "grade": "三年级"}
    (out / "cases.jsonl").write_text(
        json.dumps({"id": "d_x", "question": scenario["question"], "grade": "三年级",
                    "student_turns": ["我不会"]}, ensure_ascii=False) + "\n", encoding="utf-8")
    (run / "results" / "d_x.json").write_text(json.dumps({
        "case_id": "d_x", "status": "ok", "attempts": 1, "duration_ms": 1,
        "transcript": {"final_state": "completed",
                       "turns": [{"student": "", "tutor": "首问"},
                                 {"student": "是 3 只", "tutor": "对"}],
                       "guard_events": [], "session_id": "kernel_x"}}, ensure_ascii=False),
        encoding="utf-8")
    (run / "checks.jsonl").write_text(json.dumps({"case_id": "d_x", "status": "ok",
                                                  "declared": False, "failures": None,
                                                  "final_state": "completed"}, ensure_ascii=False) + "\n",
                                      encoding="utf-8")
    (run / "judge-scores.jsonl").write_text(json.dumps({"case_id": "d_x", "total": 9,
                                                        "verdict": "pass"}, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
    (run / "facts.jsonl").write_text(json.dumps({
        "edu.role": "tutor", "edu.session_id": "kernel_x", "edu.fallback_to": None},
        ensure_ascii=False) + "\n", encoding="utf-8")

    assert render_from(out) == 0
    report = (out / "report.md").read_text(encoding="utf-8")
    assert "judger_sha256:" + "a" * 64 in report
    assert "| d_x | ok | completed |" in report          # 判定表
    assert "| with-fallback | 1 | 1 | 1.0 |" in report   # 三口径段离线重建
    assert "| tutor | 1 | 0 | 0.0% |" in report          # 调用级表
    assert "跳过无剧本场景" not in report                  # 装载面信息不在 run 目录,仅活跑有


def test_transcript_messages_same_source_for_live_and_rescore():
    """#254 件1:活跑与 offline rescore 的 transcript→messages 取数必须同源。"""
    from edu_agent.evals import transcript_messages

    transcript = {
        "turns": [{"student": "", "tutor": "先想想一盒几支?"},        # 开口轮无学生话
                  {"student": "16 支。", "tutor": "好,再加一盒呢?"},
                  {"student": "24 支!", "tutor": "对。"}],
        "summary": "你掌握了两步乘法,注意进位。",
    }
    assert transcript_messages(transcript) == [
        {"role": "assistant", "content": "先想想一盒几支?"},
        {"role": "user", "content": "16 支。"},
        {"role": "assistant", "content": "好,再加一盒呢?"},
        {"role": "user", "content": "24 支!"},
        {"role": "assistant", "content": "对。"},
        {"role": "assistant", "content": "你掌握了两步乘法,注意进位。"},  # summary 记导师侧
    ]
    assert transcript_messages({"turns": []}) == []  # 无 summary 时空转不炸


def test_judger_sha256_public_fingerprint():
    """judger_sha256 公开(#254 件1 消费面):64 位十六进制,两次调用稳定。"""
    from edu_agent.evals import judger_sha256

    value = judger_sha256()
    assert len(value) == 64 and int(value, 16) >= 0
    assert judger_sha256() == value
