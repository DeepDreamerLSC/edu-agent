"""listen backlog 回归钉(#263):教室 burst 并发不被内核 accept 队列拒连。

#255 件3 实证 / #263 登记:stdlib ThreadingHTTPServer 默认 request_queue_size=5,
40 生近同时 open 实测 17-24/40 ECONNRESET(内核层拒,未达应用);#263 修为 128。
本钉防静默回退:子类阈值 ≥64 + build_server 实际装配该子类。
"""

from __future__ import annotations

from edu_agent.api import PartnerApiServer, build_server  # 公开入口(02 §6)


def test_server_listen_backlog_fits_classroom_burst():
    # ≥64 = 覆盖出口判据 2 的教室场景上限(50 生近同时 + 客户端重试余量)
    assert PartnerApiServer.request_queue_size >= 64

    # build_server 必须装配该子类(防回退到裸 ThreadingHTTPServer)
    server = build_server(None, port=0)  # 装配面:服务仅注入 handler 属性,构造不触
    try:
        assert isinstance(server, PartnerApiServer)
        assert server.request_queue_size >= 64
    finally:
        server.server_close()
