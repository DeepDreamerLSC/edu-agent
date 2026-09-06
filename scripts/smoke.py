#!/usr/bin/env python3
"""M0 链路 smoke(04 §2.2):3 条固定调用打部署后的 gateway,断言成功与结构合法。

M0 覆盖 stream/invoke × 本地(tutor→8301 mlx-lm)/云(judge→DeepSeek);gateway
调用失败会抛异常,等价于"非 200"。教学合同关键断言 M2 随合同测试移植再补。
这 3 条是链路探针,不是 M1 评测数据集。凭据走环境变量(DEEPSEEK_API_KEY),
缺失时 judge 调用快速失败,由 deploy 记为 failed。
"""

from __future__ import annotations

import sys
import time

from edu_agent.gateway import GatewayError, ModelRequest, RegistryError, invoke, stream

PROMPT = "用一句话回答:3+4 等于几?"


def check_stream(role: str, session: str) -> None:
    start = time.monotonic()
    tokens: list[str] = []
    for event in stream(
        ModelRequest(role=role, messages=[{"role": "user", "content": PROMPT}], session_id=session)
    ):
        if event.kind == "token":
            tokens.append(event.text)
        elif event.kind == "done":
            assert event.response is not None and event.response.finish_reason == "stop"
    assert tokens and "".join(tokens).strip(), "流式没有产出任何 token"
    print(f"smoke stream {role}: {len(tokens)} chunks, {time.monotonic() - start:.1f}s")


def check_invoke(role: str, session: str) -> None:
    start = time.monotonic()
    response = invoke(
        ModelRequest(role=role, messages=[{"role": "user", "content": PROMPT}], session_id=session)
    )
    assert response.finish_reason == "stop" and response.text.strip(), "响应为空或未正常结束"
    print(f"smoke invoke {role}: finish={response.finish_reason}, {time.monotonic() - start:.1f}s")


def main() -> int:
    try:
        check_stream("tutor", "smoke-1")  # 本地 8301
        check_invoke("tutor", "smoke-2")  # 本地
        check_invoke("judge", "smoke-3")  # 云 DeepSeek
    except (GatewayError, RegistryError) as error:
        print(f"smoke 失败:{error}", file=sys.stderr)
        return 1
    print("smoke 通过:stream/invoke × 本地/云 全通(04 §2.2)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
