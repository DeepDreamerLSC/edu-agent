"""评测线入口(00 §4/§8.2):runner 骨架、晨间摘要、judge 评分器与老系统适配器雏形。"""

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
from .runner import (
    EnvironmentFailure,
    EvalRunner,
    ResumeMismatch,
    RunnerConfig,
    Subject,
)
from .summary import load_results, morning_summary, write_summary

__all__ = [
    "DIMENSIONS",
    "EnvironmentFailure",
    "EvalRunner",
    "JudgeSubject",
    "LegacyAdapter",
    "ResumeMismatch",
    "RunnerConfig",
    "SCHEMA",
    "Subject",
    "any_judge_model",
    "judge_transcript",
    "load_results",
    "morning_summary",
    "sample_independent",
    "stability_markdown",
    "stability_report",
    "user_prompt",
    "verdict_from_scores",
    "write_summary",
]
