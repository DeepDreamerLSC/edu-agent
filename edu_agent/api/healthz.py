"""GET /healthz(04 §2.2):git sha、models.yaml 哈希、上游 /v1/models 可达性、启动时间。

由对话服务内联提供(`api/server.py` 调 `snapshot()`)。M0 那个 stdlib http.server
独立进程已删除:同一台机器同一个环境只留一个端口、一个服务(04 §2.1),
healthz 并入对话服务——合同测试里早有此断言(`test_identity_http.py`:
「healthz 并入对话服务(8300 一个服务全包)」)。

**自述按进程启动时冻结**:sha / 配置哈希 / 上游地址在 import 时各求值一次。
原先三者在请求时读磁盘,于是谁在部署目录里 `git pull` 一下,运行中的旧进程立刻
开始自述新 sha(2026-09-11 实测:未重启的进程自述了新 commit,部署验收可被欺骗)。
自述必须描述"本进程加载了什么",不是"磁盘现在是什么"。

只绑定 127.0.0.1;探测目标仅取 models.yaml 声明的 provider 地址(白名单来自配置,
不接收外部输入)。
"""

from __future__ import annotations

import hashlib
import ipaddress
import os
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

_REPO = Path(__file__).resolve().parents[2]
_STARTED_AT = datetime.now(timezone.utc).isoformat()
_STARTED_MONOTONIC = time.monotonic()


def config_path() -> Path:
    return Path(os.environ.get("EDU_MODELS_YAML") or _REPO / "configs" / "models.yaml")


def _resolve_sha() -> str:
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


def _resolve_config_digest() -> str:
    return hashlib.sha256(config_path().read_bytes()).hexdigest()


def _resolve_provider_urls() -> dict[str, str]:
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


# 进程启动时冻结一次(见模块 docstring:自述不许被后来的 pull 改写)
_GIT_SHA = _resolve_sha()
_CONFIG_DIGEST = _resolve_config_digest()
_PROVIDER_URLS = _resolve_provider_urls()


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
        "git_sha": _GIT_SHA,
        "models_yaml_sha256": _CONFIG_DIGEST,
        "upstreams": {name: reachable(url) for name, url in sorted(_PROVIDER_URLS.items())},
        "started_at": _STARTED_AT,
        "uptime_s": int(time.monotonic() - _STARTED_MONOTONIC),
    }
