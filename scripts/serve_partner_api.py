#!/usr/bin/env python3
"""对话服务启动器(部署接线,launchd plist 的 ProgramArguments 入口)。

装配:真内核(B 线 #59/#60 三函数)+ 会话表 + 身份服务(#63)+ 合作方 API
(#55/#56 四端点 + SSE,含 /healthz)。**同一环境只此一个服务、一个端口**
(默认 8300;M0 那个 healthz 独立进程已删,见 edu_agent/api/healthz.py)。
凭据走环境变量(IDENTITY_* / EXTERNAL_STUDENT_MAP,issue #3 判例),不进代码:
launchd 不继承 shell 环境,故由 main() 读 `.env.<EDU_ENV>`(见 _load_env_file)。
内核换插说明:api 层经 Kernel 协议注入,本启动器即注入点——A 线内核适配
(LearnerSession 对接)落地后此处零改动。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

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
    FileSessionStore 注入上下文落盘(每回合后全量历史写 data/sessions/,演示复盘用);
    FileConversationStore 注入会话表落盘(M3 WS2:data/conversations/,进程重启后
    open→message→finish 仍可续——会话本体按 kernel_session_id 从 sessions/ 取回)。"""
    from edu_agent.api import question_source
    from edu_agent.api.files import FileService
    from edu_agent.store import FileConversationStore, FileSessionStore

    port = int(os.environ.get("EDU_PARTNER_API_PORT", "8300"))
    files = FileService()
    service = build_service(PartnerKernel(), source=question_source(
        os.environ.get("EDU_QUESTION_SOURCE", "bank")),
        store=FileConversationStore(),
        image_resolver=files.data_url,
        sessions=FileSessionStore())
    return build_server(service, IdentityService(), files=files,
                        host="127.0.0.1", port=port)


def _load_env_file(env_name: str) -> None:
    """部署接线:把 `.env.<EDU_ENV>`(默认 local)补进环境,已存在的不覆盖。

    凭据的真相源就是那一个文件(600、gitignored);deploy.sh 只把它 source 进
    自己的进程,而 launchd 不继承 shell 环境(2026-09-11 实测:plist 里没有
    IDENTITY_* 时登录直接 503),所以由本启动器读回来。"""
    path = Path(f".env.{env_name}")
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        key = key.strip()
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key, value.strip())


def main() -> int:
    _load_env_file(os.environ.get("EDU_ENV", "local"))
    server = build()
    print(f"partner api listening on 127.0.0.1:{server.server_address[1]}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
