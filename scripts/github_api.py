"""GitHub REST 极简封装,供 scripts/ 下的门禁与报警脚本共用(只依赖标准库)。

安全边界(SSRF):域名固定 api.github.com 且必须 https;仓库标识白名单校验;
每次请求解析域名并拒绝私网/环回/链路本地地址;不跟随重定向。
404/422 视为"资源不存在/已存在"返回 None,其余错误抛出。
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import urllib.error
import urllib.request
from urllib.parse import urlparse

API_HOST = "api.github.com"
REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """API 客户端不跟随重定向:3xx 一律按 HTTPError 抛出。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(_NoRedirect())


def assert_public_host(hostname: str) -> None:
    """解析 hostname,拒绝解析到私网/环回/链路本地/保留地址的记录。"""
    for info in socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP):
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ValueError(f"API 主机解析到非公网地址: {ip}")


class GithubApi:
    def __init__(self, token: str, repo: str) -> None:
        if not REPO_RE.match(repo):
            raise ValueError(f"非法仓库标识: {repo!r}")
        self._token = token
        self._repo = repo

    def _request(self, path: str, method: str = "GET", body: dict | None = None):
        url = f"https://{API_HOST}/repos/{self._repo}/{path.lstrip('/')}"
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != API_HOST:
            raise ValueError(f"API 地址越界: {url!r}")
        assert_public_host(parsed.hostname)
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", f"Bearer {self._token}")
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("User-Agent", "edu-agent-scripts")
        try:
            with OPENER.open(request) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 422):
                return None
            raise
        return json.loads(payload) if payload else None

    def get(self, path: str):
        return self._request(path)

    def get_paged(self, path: str) -> list:
        items = []
        page = 1
        while True:
            separator = "&" if "?" in path else "?"
            batch = self.get(f"{path}{separator}per_page=100&page={page}")
            if not isinstance(batch, list) or not batch:
                return items
            items.extend(batch)
            if len(batch) < 100:
                return items
            page += 1

    def create_label(self, name: str, color: str, description: str | None = None) -> None:
        body: dict = {"name": name, "color": color}
        if description:
            body["description"] = description
        self._request("labels", method="POST", body=body)

    def add_label(self, number: int, name: str, color: str) -> None:
        self.create_label(name, color)
        self._request(f"issues/{number}/labels", method="POST", body={"labels": [name]})

    def remove_label(self, number: int, name: str) -> None:
        self._request(f"issues/{number}/labels/{name}", method="DELETE")

    def create_issue(self, title: str, body: str, labels: list[str]):
        return self._request(
            "issues", method="POST", body={"title": title, "body": body, "labels": labels}
        )
