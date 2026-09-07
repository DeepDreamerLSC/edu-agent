#!/usr/bin/env python3
"""对话服务启动器(部署接线,launchd plist 的 ProgramArguments 入口)。

装配:真内核(B 线 #59/#60 三函数)+ 内存会话 + 身份服务(#63)+ 合作方 API
(#55/#56 四端点 + SSE)。端口默认 8300(EDU_PARTNER_API_PORT 可覆盖);
凭据走环境变量(IDENTITY_* / EXTERNAL_STUDENT_MAP,issue #3 判例),不进代码。
内核换插说明:api 层经 Kernel 协议注入,本启动器即注入点——A 线内核适配
(LearnerSession 对接)落地后此处零改动。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from edu_agent.agents.small_lecturer import finish, reply, start  # noqa: E402
from edu_agent.api import build_server, build_service  # noqa: E402
from edu_agent.api.identity import IdentityService  # noqa: E402
from edu_agent.store import MemoryConversationStore  # noqa: E402


class PartnerKernel:
    """Kernel 协议的真内核绑定(00 §5.1 三函数;无状态,绑定即协议实现)。"""

    name = "small-lecturer-kernel"
    start = staticmethod(start)
    reply = staticmethod(reply)
    finish = staticmethod(finish)


def main() -> int:
    port = int(os.environ.get("EDU_PARTNER_API_PORT", "8300"))
    server = build_server(build_service(PartnerKernel()), IdentityService(os.environ),
                          host="127.0.0.1", port=port)
    print(f"partner api listening on 127.0.0.1:{port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
