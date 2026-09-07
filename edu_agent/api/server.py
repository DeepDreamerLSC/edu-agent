"""合作方接口 HTTP 面(00 §5.2 四端点;stdlib http.server,不引 web 框架)。

路由与错误信封按 #48 合同快照:错误体 {"error": {code, message, request_id,
details}}(老仓库 ErrorEnvelope 形态)。SSE 流式端点随 PR2 落地,本模块路由
表预留路径。401:v1 单合作方试点,Authorization 头存在性校验(合作方 App 侧
零改动的最小门槛;身份端点属 M3 对齐件)。
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .service import ApiError, ConversationService

_OPEN = re.compile(r"^/api/prepared-questions/(?P<question_id>[^/]+)/open$")
# refresh 两形态同一语义(#48 对账出入①):00 §5.2 表(prepared-questions 前缀)
# 与 Postman 集合(conversations 前缀)并存,skill_session_id 中心解析。
_REFRESH_PQ = re.compile(
    r"^/api/prepared-questions/[^/]+/skill-sessions/(?P<skill_session_id>[^/]+)/refresh$"
)
_REFRESH_CONV = re.compile(
    r"^/api/conversations/[^/]+/skill-sessions/(?P<skill_session_id>[^/]+)/refresh$"
)
_MESSAGES = re.compile(r"^/api/conversations/(?P<conversation_id>[^/]+)/messages$")


class PartnerApiHandler(BaseHTTPRequestHandler):
    service: ConversationService  # 经 server 属性注入

    def _dispatch(self) -> None:
        if not self.headers.get("Authorization"):
            self._error(ApiError(401, None, "登录令牌无效或已过期"))
            return
        match = _OPEN.match(self.path)
        if match and self.command == "POST":
            body = self._body_keys("idempotency_key")
            self._json(self.service.open(match["question_id"], body["idempotency_key"], learner={}))
            return
        refresh = _REFRESH_PQ.match(self.path) or _REFRESH_CONV.match(self.path)
        if refresh and self.command == "POST":
            self._json(self.service.refresh(refresh["skill_session_id"]))
            return
        match = _MESSAGES.match(self.path)
        if match and self.command == "POST":
            self._json(self.service.send(match["conversation_id"], self._read_body()))
            return
        self._error(ApiError(404, None, "路径不在合作方合同内"))

    do_POST = _dispatch

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            raise ApiError(422, None, "请求体不是合法 JSON") from None
        if not isinstance(payload, dict):
            raise ApiError(422, None, "请求体必须是 JSON 对象")
        return payload

    def _body_keys(self, *keys: str) -> dict:
        body = self._read_body()
        missing = [key for key in keys if not body.get(key)]
        if missing:
            raise ApiError(422, None, f"缺必填字段:{','.join(missing)}")
        return {key: body[key] for key in keys}

    def _json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _error(self, error: ApiError) -> None:
        self._json(
            {"error": {"code": error.code, "message": error.message, "request_id": "", "details": {}}},
            status=error.status_code,
        )

    def handle_one_request(self) -> None:  # ApiError 统一出口;未预期异常兜底 503,不静默断连
        try:
            super().handle_one_request()
        except ApiError as error:
            self._error(error)
        except Exception as error:  # noqa: BLE001 传输层兜底:基础设施故障(合同表 503)
            self._error(ApiError(503, None, f"服务暂不可用:{type(error).__name__}"))

    def log_message(self, format: str, *args: object) -> None:
        pass  # 访问日志静默(healthz 同款)


def build_server(service: ConversationService, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    handler = type("BoundPartnerApiHandler", (PartnerApiHandler,), {"service": service})
    return ThreadingHTTPServer((host, port), handler)
