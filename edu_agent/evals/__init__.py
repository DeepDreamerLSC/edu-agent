"""评测线入口(00 §4/§8.2):runner 骨架、晨间摘要、judge 评分器与老系统适配器雏形。"""

from .checks import (
    REGISTRY,
    UnknownCheck,
    _tutor_turns,  # #382 PR-D:事故回归电池直连(trajectory 轮次口径钉;纯导出)
    possible_no_progress_cycle,
    run_check,
)
from .identity import (  # #490 M0 表第③项:指纹构造 helper(M3 迁移两消费者)
    file_sha256,
    git_head_sha,
    head_sha256,
)
from .image_teaching import (
    load_scenarios,
    question_image_data_url,
    to_cases,
    validate_scenario,
)
from .kernel_subject import POST_TURN_OBSERVATION_SCHEMA_VERSION, KernelSubject
from .lane_m import LaneMResult, compare_lane_m, run as run_lane_m
from .model_match import ModelComparison, compare_models  # #490 M2:纯比较 helper
from .judge import (
    DIMENSION_GUIDE,
    DIMENSIONS,
    SCHEMA,
    JudgeSubject,
    any_judge_model,
    judge_transcript,
    sample_independent,
    stability_markdown,
    stability_report,
    user_prompt,
    verdict_from_scores,
)
from .legacy_adapter import LegacyAdapter
from .report import render_html
from .runner import (  # 执行机械已删(#521 I6-C C4):只导共享契约面
    EnvironmentFailure,
    ResumeMismatch,
    Subject,
    safe_case_id,
)
from .s2_judge import (  # #459 件二:S2 专项 Judge(宿主 B,annotation-only)
    S2_SCHEMA,
    S2JudgeSubject,
    s2_judge_transcript,
    s2_user_prompt,
)
from .scenario_corpus import (
    DATASETS_DIR,
    deterministic_scenarios,
    format_failures,
    load_shortboard_corpus,
    run_scenario_checks,
    scenario_fingerprint,
    select_branch,
    to_kernel_case,
)
from .summary import load_results, morning_summary, write_summary

# corpus_round(#216)惰性导出(PEP 562):`python -m edu_agent.evals.corpus_round`
# 与包级急切导入会双导入告警,run 入口保持 -m 形态,符号在首次访问时再加载。
_CORPUS_ROUND_LAZY = ("DEFAULT_CORPUS", "build_cases", "build_plan", "caliber_section",
                      "check_rows", "diff_checks", "dump_facts", "dump_spec_artifacts",
                      "facts_calibers", "format_plan", "git_dirty_state", "judge_gate",
                      "judge_rows", "judger_sha256", "load_facts", "load_run_spec", "merge_options",
                      "real_model_scenarios", "render_from", "render_report",
                      "resolve_round", "resolve_spec_cases", "resume_run_dir",
                      "run_identity", "salvage_facts", "soften_counts", "soften_line",
                      "transcript_messages")


_EXTERNAL_LAZY = ("EXTERNAL_ROLES", "EXTERNAL_SCHEMA_VERSION", "external_fingerprint",
                  "load_normalized", "validate_external_scenario")
# to_v1_record 随真原件适配退役(旧签名不再成立),导出面换成 collect_records 公开别名。
_IMPORTER_LAZY = ("collect_socraticmath_records", "import_socraticmath")
# inspect_adapter(#521 I5)惰性导出:adapter 模块级 import corpus_round,保持包级惰性
# 口径(-m 入口与包级急切导入不双载,同 _CORPUS_ROUND_LAZY 理由)。
_INSPECT_LAZY = ("InspectRoundRequest", "DET_SCORER_NAME", "harness_identity",
                 "run_inspect_round", "validate_canonical")


def __getattr__(name: str):
    if name in _CORPUS_ROUND_LAZY:
        from . import corpus_round
        return getattr(corpus_round, name)
    if name in _INSPECT_LAZY:
        from . import inspect_adapter
        return getattr(inspect_adapter, name)
    if name in _EXTERNAL_LAZY:
        from . import external_scenario
        return getattr(external_scenario, name)
    if name in _IMPORTER_LAZY:
        from .importers import socraticmath
        if name == "collect_socraticmath_records":
            return socraticmath.collect_records
        return getattr(socraticmath, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DIMENSION_GUIDE",
    "DIMENSIONS",
    "EnvironmentFailure",
    "validate_external_scenario",
    "external_fingerprint",
    "import_socraticmath",
    "collect_socraticmath_records",
    "EXTERNAL_SCHEMA_VERSION",
    "EXTERNAL_ROLES",
    "JudgeSubject",
    "KernelSubject",
    "POST_TURN_OBSERVATION_SCHEMA_VERSION",
    "LaneMResult",
    "ModelComparison",
    "compare_lane_m",
    "compare_models",
    "run_lane_m",
    "LegacyAdapter",
    "REGISTRY",
    "possible_no_progress_cycle",
    "ResumeMismatch",
    "S2_SCHEMA",
    "S2JudgeSubject",
    "SCHEMA",
    "Subject",
    "UnknownCheck",
    "_tutor_turns",
    "any_judge_model",
    "build_cases",
    "build_plan",
    "caliber_section",
    "check_rows",
    "DEFAULT_CORPUS",
    "DATASETS_DIR",
    "deterministic_scenarios",
    "diff_checks",
    "dump_facts",
    "dump_spec_artifacts",
    "facts_calibers",
    "file_sha256",
    "format_plan",
    "git_dirty_state",
    "git_head_sha",
    "head_sha256",
    "format_failures",
    "judge_rows",
    "judge_gate",
    "judge_transcript",
    "judger_sha256",
    "InspectRoundRequest",
    "DET_SCORER_NAME",
    "harness_identity",
    "run_inspect_round",
    "validate_canonical",
    "load_facts",
    "load_run_spec",
    "merge_options",
    "load_normalized",
    "load_results",
    "load_scenarios",
    "load_shortboard_corpus",
    "morning_summary",
    "question_image_data_url",
    "real_model_scenarios",
    "render_from",
    "render_html",
    "render_report",
    "resolve_round",
    "resolve_spec_cases",
    "resume_run_dir",
    "run_check",
    "run_identity",
    "run_scenario_checks",
    "s2_judge_transcript",
    "s2_user_prompt",
    "safe_case_id",
    "salvage_facts",
    "sample_independent",
    "scenario_fingerprint",
    "select_branch",
    "soften_counts",
    "soften_line",
    "stability_markdown",
    "stability_report",
    "to_cases",
    "to_kernel_case",
    "transcript_messages",
    "user_prompt",
    "validate_scenario",
    "verdict_from_scores",
    "write_summary",
]
