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
    datasets_dir,
    deterministic_scenarios,
    format_failures,
    load_shortboard_corpus,
    run_scenario_checks,
    to_kernel_case,
)
from .summary import load_results, morning_summary, write_summary

__all__ = [
    "DIMENSIONS",
    "EnvironmentFailure",
    "EvalRunner",
    "JudgeSubject",
    "KernelSubject",
    "LegacyAdapter",
    "REGISTRY",
    "ResumeMismatch",
    "RunnerConfig",
    "SCHEMA",
    "Subject",
    "UnknownCheck",
    "any_judge_model",
    "datasets_dir",
    "deterministic_scenarios",
    "format_failures",
    "judge_transcript",
    "load_results",
    "load_scenarios",
    "load_shortboard_corpus",
    "morning_summary",
    "question_image_data_url",
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
