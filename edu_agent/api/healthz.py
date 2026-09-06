"""GET /healthz(04 §2.2):git sha、models.yaml 哈希、上游 /v1/models 可达性、启动时间。

M0 的最小应用进程:stdlib http.server——不引 web 框架,那是 02 §7 第②类第三方
依赖,M3 api 层真需要时再议。launchd 托管(deploy/launchd),deploy.sh 每次部署
重启。只绑定 127.0.0.1;探测目标仅取 models.yaml 声明的 provider 地址(白名单
来自配置,不接收外部输入)。
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import socket
import subprocess
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

_REPO = Path(__file__).resolve().parents[2]
_STARTED_AT = datetime.now(timezone.utc).isoformat()
_STARTED_MONOTONIC = time.monotonic()


def config_path() -> Path:
    return Path(os.environ.get("EDU_MODELS_YAML") or _REPO / "configs" / "models.yaml")


def git_sha() -> str:
    """部署 sha:环境变量优先(deploy 时注入),否则问 git;都拿不到报 unknown。"""
    sha = os.environ.get("EDU_DEPLOY_SHA")
    if sha:
        return sha
    try:
        return subprocess.run(
            ["git", "-C", str(_REPO), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def config_digest() -> str:
    return hashlib.sha256(config_path().read_bytes()).hexdigest()


def provider_urls() -> dict[str, str]:
    """models.yaml 的 providers 段;配置损坏时返回空表,健康检查不因此崩。"""
    try:
        data = yaml.safe_load(config_path().read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return {
        name: str(spec.get("base_url", ""))
        for name, spec in (data.get("providers") or {}).items()
        if spec.get("base_url")
    }


def probe_target_allowed(hostname: str) -> bool:
    """探测边界:只允许环回(本机模型服务,04 §2.2 的探测对象)与公网地址(云 API);
    私网段、链路本地(169.254 云元数据)、保留段一律拒绝。"""
    try:
        infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False
    return all(
        (ip := ipaddress.ip_address(info[4][0])).is_loopback or ip.is_global
        for info in infos
    )


def reachable(base_url: str) -> bool:
    """GET <base>/models:拿到任何 HTTP 应答都算可达(401 也说明服务活着)。"""
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    if not probe_target_allowed(parsed.hostname):
        return False
    url = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}/models"
    # ponytail: 目标只来自仓库配置且已按环回/公网过滤;DNS rebinding 不设防
    try:
        with httpx.Client(follow_redirects=False) as client:
            response = client.get(url, timeout=3.0)
    except httpx.HTTPError:
        return False
    return response.status_code < 500


def snapshot() -> dict:
    return {
        "git_sha": git_sha(),
        "models_yaml_sha256": config_digest(),
        "upstreams": {name: reachable(url) for name, url in sorted(provider_urls().items())},
        "started_at": _STARTED_AT,
        "uptime_s": int(time.monotonic() - _STARTED_MONOTONIC),
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/healthz":
            self.send_error(404)
            return
        payload = json.dumps(snapshot(), ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        pass  # 访问日志静默:launchd 日志只留错误


def main() -> None:
    port = int(os.environ.get("EDU_HEALTHZ_PORT", "8300"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"healthz listening on 127.0.0.1:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
