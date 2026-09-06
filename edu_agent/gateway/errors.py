"""gateway 失败类型(01 §4):九种,不加不减;任何模型调用失败都归入其中之一。"""

from __future__ import annotations

from enum import Enum


class FailureType(Enum):
    """枚举值即事实记录 edu.outcome 的取值。"""

    TIMEOUT_FIRST_TOKEN = "timeout_first_token"  # 首 token 超时(仅流式)
    TIMEOUT_TOTAL = "timeout_total"              # 总时长超时
    RATE_LIMITED = "rate_limited"                # 429,读 Retry-After
    UPSTREAM_5XX = "upstream_5xx"                # 上游服务错误
    UPSTREAM_4XX = "upstream_4xx"                # 请求本身错(模型不存在、上下文超长)
    SCHEMA_VIOLATION = "schema_violation"        # json_schema 输出不合规(路线 1 本地校验)
    TRUNCATED = "truncated"                      # finish_reason=length
    CONTENT_FILTERED = "content_filtered"        # 上游内容过滤
    CONNECTION = "connection"                    # 连不上/中途断开


# 01 §4 表"可重试"列。重试几次、退避多少由 models.yaml 按角色声明,类型级资格在这里。
RETRYABLE = frozenset({
    FailureType.TIMEOUT_FIRST_TOKEN,
    FailureType.RATE_LIMITED,
    FailureType.UPSTREAM_5XX,
    FailureType.SCHEMA_VIOLATION,  # 恰一次,带修复提示(路线 1,issue #8)
    FailureType.CONNECTION,
})

# 01 §4 表"触发备选"列:值 = 当前模型失败几次后切备选;不在表中 = 永不触发。
FALLBACK_AFTER_FAILURES = {
    FailureType.TIMEOUT_FIRST_TOKEN: 1,
    FailureType.TIMEOUT_TOTAL: 1,
    FailureType.RATE_LIMITED: 2,  # 第二次起
    FailureType.UPSTREAM_5XX: 2,  # 第二次起
    FailureType.CONNECTION: 1,
}


class GatewayError(Exception):
    """带失败类型的调用失败(01 §2.4)。output 保留违规原文,供 schema 修复重试。"""

    def __init__(
        self,
        failure: FailureType,
        detail: str,
        *,
        status: int | None = None,
        retry_after: float | None = None,
        output: str | None = None,
    ) -> None:
        super().__init__(f"{failure.value}: {detail}")
        self.failure = failure
        self.detail = detail
        self.status = status
        self.retry_after = retry_after
        self.output = output
