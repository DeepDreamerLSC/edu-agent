"""评测线入口(00 §4/§8.2):runner 骨架、晨间摘要、judge 评分器与老系统适配器雏形。"""

from .checks import (
    REGISTRY,
    UnknownCheck,
    _tutor_turns,  # #382 PR-D:事故回归电池直连(trajectory 轮次口径钉;纯导出)
    possible_no_progress_cycle,
    run_check,
)
from .image_teaching import (
    load_scenarios,
    question_image_data_url,
    to_cases,
    validate_scenario,
)
from .kernel_subject import KernelSubject
from .lane_m import LaneMResult, compare_lane_m, run as run_lane_m
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
from .runner import (
    EnvironmentFailure,
    EvalRunner,
    ResumeMismatch,
    RunnerConfig,
    Subject,
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
                      "run_identity", "soften_counts", "soften_line",
                      "transcript_messages")


_EXTERNAL_LAZY = ("EXTERNAL_ROLES", "EXTERNAL_SCHEMA_VERSION", "external_fingerprint",
                  "load_normalized", "validate_external_scenario")
_IMPORTER_LAZY = ("import_socraticmath", "to_v1_record")


def __getattr__(name: str):
    if name in _CORPUS_ROUND_LAZY:
        from . import corpus_round
        return getattr(corpus_round, name)
    if name in _EXTERNAL_LAZY:
        from . import external_scenario
        return getattr(external_scenario, name)
    if name in _IMPORTER_LAZY:
        from .importers import socraticmath
        return getattr(socraticmath, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DIMENSION_GUIDE",
    "DIMENSIONS",
    "EnvironmentFailure",
    "validate_external_scenario",
    "to_v1_record",
    "external_fingerprint",
    "import_socraticmath",
    "EXTERNAL_SCHEMA_VERSION",
    "EXTERNAL_ROLES",
    "EvalRunner",
    "JudgeSubject",
    "KernelSubject",
    "LaneMResult",
    "compare_lane_m",
    "run_lane_m",
    "LegacyAdapter",
    "REGISTRY",
    "possible_no_progress_cycle",
    "ResumeMismatch",
    "RunnerConfig",
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
    "format_plan",
    "git_dirty_state",
    "format_failures",
    "judge_rows",
    "judge_gate",
    "judge_transcript",
    "judger_sha256",
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
