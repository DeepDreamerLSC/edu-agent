"""评测线入口(00 §4/§8.2):runner 骨架、晨间摘要、judge 评分器与老系统适配器雏形。"""

from .checks import REGISTRY, UnknownCheck, run_check
from .image_teaching import (
    load_scenarios,
    question_image_data_url,
    to_cases,
    validate_scenario,
)
from .kernel_subject import KernelSubject
from .judge import (
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
    to_kernel_case,
)
from .summary import load_results, morning_summary, write_summary

# corpus_round(#216)惰性导出(PEP 562):`python -m edu_agent.evals.corpus_round`
# 与包级急切导入会双导入告警,run 入口保持 -m 形态,符号在首次访问时再加载。
_CORPUS_ROUND_LAZY = ("build_cases", "check_rows", "diff_checks",
                      "real_model_scenarios", "render_report")


def __getattr__(name: str):
    if name in _CORPUS_ROUND_LAZY:
        from . import corpus_round
        return getattr(corpus_round, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DIMENSIONS",
    "EnvironmentFailure",
    "EvalRunner",
    "JudgeSubject",
    "KernelSubject",
    "LegacyAdapter",
    "REGISTRY",
    "ResumeMismatch",
    "build_cases",
    "check_rows",
    "diff_checks",
    "RunnerConfig",
    "SCHEMA",
    "Subject",
    "UnknownCheck",
    "any_judge_model",
    "DATASETS_DIR",
    "deterministic_scenarios",
    "format_failures",
    "judge_transcript",
    "load_results",
    "load_scenarios",
    "load_shortboard_corpus",
    "morning_summary",
    "question_image_data_url",
    "real_model_scenarios",
    "render_report",
    "render_html",
    "run_check",
    "run_scenario_checks",
    "sample_independent",
    "stability_markdown",
    "stability_report",
    "to_cases",
    "to_kernel_case",
    "user_prompt",
    "validate_scenario",
    "verdict_from_scores",
    "write_summary",
]
