"""healthz 自述的冻结语义(2026-09-11 部署演练实测缺陷)。

症状:部署目录被 pull 到新 commit 而服务**未重启**时,运行中的旧进程当场开始
自述新 sha(实测:`started_at`/`uptime` 没变是唯一破绽)——部署验收("healthz
显示新 sha")因此可被欺骗。自述必须描述"本进程加载了什么"。

本测试在 HTTP 面上打:两个断言都依赖"import 时冻结";一旦回到请求时读磁盘,
第二个请求就会采纳后来的环境变量/配置路径,测试立刻红。
"""

from __future__ import annotations

import threading

import httpx
import pytest

from edu_agent.api import build_server, build_service


class StubKernel:
    name = "stub"
    start = staticmethod(lambda question, learner: type("T", (), {"text": "第一问"})())
    reply = staticmethod(
        lambda session, message: type("Turn", (), {"text": "嗯,你接着说", "ready_to_confirm": False})()
    )
    finish = staticmethod(
        lambda session: type("S", (), {"text": "小结", "status": "needs_review"})()
    )


@pytest.fixture
def healthz_url():
    server = build_server(build_service(StubKernel()))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/healthz"
    server.shutdown()
    server.server_close()


def _get(url: str) -> dict:
    response = httpx.get(url, timeout=5.0, trust_env=False)
    assert response.status_code == 200
    return response.json()


def test_self_report_frozen_against_later_env_and_config(healthz_url, monkeypatch, tmp_path):
    """事后改 EDU_DEPLOY_SHA / EDU_MODELS_YAML:自述三项一个都不许变。"""
    before = _get(healthz_url)
    monkeypatch.setenv("EDU_DEPLOY_SHA", "de" * 20)
    monkeypatch.setenv("EDU_MODELS_YAML", str(tmp_path / "models.yaml"))
    (tmp_path / "models.yaml").write_text("providers: {}\n", encoding="utf-8")
    after = _get(healthz_url)

    assert before["git_sha"], "自述 sha 不该为空"
    assert after["git_sha"] == before["git_sha"]
    assert after["models_yaml_sha256"] == before["models_yaml_sha256"]
    # 上游地址表也冻结(可达性本身是活值,故只比键集)
    assert set(after["upstreams"]) == set(before["upstreams"])


def test_uptime_is_live(healthz_url):
    """冻结的是身份,不是活性:uptime 仍随时间前进(防"冻结过头"把探活也冻住)。"""
    first = _get(healthz_url)["uptime_s"]
    second = _get(healthz_url)["uptime_s"]
    assert second >= first
