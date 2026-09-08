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

from edu_agent.agents.small_lecturer import finish, reply, start
from edu_agent.api import build_server, build_service
from edu_agent.api.identity import IdentityService
from edu_agent.store import MemoryConversationStore


class PartnerKernel:
    """Kernel 协议的真内核绑定(00 §5.1 三函数;无状态,绑定即协议实现)。"""

    name = "small-lecturer-kernel"
    start = staticmethod(start)
    reply = staticmethod(reply)
    finish = staticmethod(finish)


def build() -> ThreadingHTTPServer:
    """装配(env→config 转换在此发生:IdentityService 必须无参构造,#72 P1 回归钉)。

    题源默认 bank(合作方真实题库快照,EDU_QUESTION_SOURCE 可切 seed/snapshot);
    FileService 注入题图解析(file_id → data URL,内核 vision 多模态输入);
    FileSessionStore 注入上下文落盘(每回合后全量历史写 data/sessions/,演示复盘用)。"""
    from edu_agent.api import question_source
    from edu_agent.api.files import FileService
    from edu_agent.store import FileSessionStore

    port = int(os.environ.get("EDU_PARTNER_API_PORT", "8300"))
    files = FileService()
    service = build_service(PartnerKernel(), source=question_source(
        os.environ.get("EDU_QUESTION_SOURCE", "bank")),
        image_resolver=files.data_url,
        sessions=FileSessionStore())
    return build_server(service, IdentityService(), files=files,
                        host="127.0.0.1", port=port)


def main() -> int:
    server = build()
    print(f"partner api listening on 127.0.0.1:{server.server_address[1]}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
