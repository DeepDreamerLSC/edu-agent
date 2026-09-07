"""合作方接口 HTTP 面(00 §5.2:对话四端点 + 身份两端点 + healthz;stdlib 不引 web 框架)。

路由与错误信封按 #48 合同快照:错误体 {"error": {code, message, request_id,
details}}(老仓库 ErrorEnvelope 形态)。SSE 六型帧见 sse_frames。
鉴权分面:对话端点查 Authorization 头存在性(401 兜底);身份两端点自带鉴权
(native-codes=partner API Key,token=授权码+PKCE),在全局闸之前路由。
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .identity import IdentityError, IdentityService
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
_MESSAGES_STREAM = re.compile(r"^/api/conversations/(?P<conversation_id>[^/]+)/messages/stream$")
_NATIVE_CODES = re.compile(r"^/api/openapi/v1/auth/native-codes$")
_NATIVE_TOKEN = re.compile(r"^/api/auth/native/token$")
_HEALTHZ = re.compile(r"^/healthz$")


def sse_frames(response: dict) -> bytes:
    """00 §5.2 多轮流式行:服务端先执行校验持久化,再发 interaction → delta → done
    (frontend-conversations-skills.md §4 帧序;未知事件客户端必须忽略)。"""
    interaction = response["skill_interaction"]
    text = response["assistant_message"]["content"]
    frames = [
        ("start", {"conversation_running": True}),
        ("interaction", interaction),
        ("delta", {"text": text}),
        ("done", {"assistant_message": response["assistant_message"],
                  "session_version": response["session_version"]}),
    ]
    return b"".join(
        f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
        for event, payload in frames
    )


class PartnerApiHandler(BaseHTTPRequestHandler):
    service: ConversationService  # 经 server 属性注入
    identity: IdentityService     # 同上(build_server 注入)

    def _identity_post(self) -> tuple[int, dict] | None:
        """身份两端点自带鉴权(API Key / 授权码+PKCE);非身份路径返回 None。"""
        if _NATIVE_CODES.match(self.path):
            return self.identity.native_code(self._read_body(), dict(self.headers))
        if _NATIVE_TOKEN.match(self.path):
            return self.identity.native_token(self._read_body())
        return None

    def _dispatch(self) -> None:
        identity = self._identity_post()
        if identity is not None:
            self._json(identity[1], identity[0])
            return
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
        match = _MESSAGES_STREAM.match(self.path)
        if match and self.command == "POST":
            # 流式:校验失败(409 等)在开流前以 JSON 错误返回;成功后帧序固定
            response = self.service.send(match["conversation_id"], self._read_body())
            payload = sse_frames(response)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self._error(ApiError(404, None, "路径不在合作方合同内"))

    do_POST = _dispatch

    def do_GET(self) -> None:
        if _HEALTHZ.match(self.path):
            from .healthz import snapshot  # 局部导入:快照依赖模型配置,按需加载
            self._json(snapshot())
            return
        self._error(ApiError(404, None, "路径不在合作方合同内"))

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

    def handle_one_request(self) -> None:  # 统一错误出口;未预期异常兜底 503,不静默断连
        try:
            super().handle_one_request()
        except (ApiError, IdentityError) as error:
            self._error(ApiError(getattr(error, "status_code", 500),
                                 getattr(error, "code", None), error.message))
        except Exception as error:  # noqa: BLE001 传输层兜底:基础设施故障(合同表 503)
            self._error(ApiError(503, None, f"服务暂不可用:{type(error).__name__}"))

    def log_message(self, format: str, *args: object) -> None:
        pass  # 访问日志静默(healthz 同款)


def build_server(service: ConversationService, identity: IdentityService | None = None,
                 host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    handler = type("BoundPartnerApiHandler", (PartnerApiHandler,),
                   {"service": service, "identity": identity or IdentityService()})
    return ThreadingHTTPServer((host, port), handler)
