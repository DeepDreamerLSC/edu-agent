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

from .files import FileService
from .identity import IdentityError, IdentityService
from .service import ApiError, ConversationService

_OPEN = re.compile(r"^/api/prepared-questions/(?P<question_id>[^/]+)/open$")
# 统一 Open(老系统文档 §5):必须在 _OPEN 之前匹配,否则 "open" 被当作路径 question_id
_OPEN_UNIFIED = re.compile(r"^/api/prepared-questions/open$")
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
_CREATE = re.compile(r"^/api/conversations$")
_GET = re.compile(r"^/api/conversations/(?P<conversation_id>[^/]+)$")
# 00 §5.2 必须保留约定 4:客户端不得提交 answer/analysis/mastery_status
_FORBIDDEN_FIELDS = frozenset({"answer", "analysis", "mastery_status"})
_LOGIN = re.compile(r"^/api/auth/login$")
_NATIVE_CODES = re.compile(r"^/api/openapi/v1/auth/native-codes$")
_NATIVE_TOKEN = re.compile(r"^/api/auth/native/token$")
_HEALTHZ = re.compile(r"^/healthz$")
_FILES_UPLOAD = re.compile(r"^/api/files/upload-request$")
_FILES_COMPLETE = re.compile(r"^/api/files/complete$")
_FILES_CONTENT = re.compile(r"^/api/files/(?P<file_id>[^/]+)/content$")


def sse_frames(response: dict) -> bytes:
    """00 §5.2 多轮流式行(六型):status → start → interaction → delta → done。

    status 帧在流开始前发(会话元信息);未知事件客户端必须忽略。"""
    interaction = response["skill_interaction"]
    frames = [
        ("status", {"state": interaction["state"],
                    "session_version": response["session_version"]}),
        ("start", {"conversation_running": True}),
        ("interaction", interaction),
        ("delta", {"text": response["assistant_message"]["content"]}),
        ("done", {"assistant_message": response["assistant_message"],
                  "session_version": response["session_version"]}),
    ]
    return _encode_sse(frames)


def sse_error_frames(error: ApiError) -> bytes:
    """内核异常的流内错误帧(友好文案+错误码);流已开,客户端按 error 事件收尾。"""
    frames = [
        ("start", {"conversation_running": False}),
        ("error", {"code": error.code or "SERVICE_UNAVAILABLE",
                   "message": "讲解服务暂时不可用,请稍后重试。"}),
    ]
    return _encode_sse(frames)


def _encode_sse(frames: list[tuple[str, dict]]) -> bytes:
    return b"".join(
        f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
        for event, payload in frames
    )


class PartnerApiHandler(BaseHTTPRequestHandler):
    service: ConversationService  # 经 server 属性注入
    identity: IdentityService     # 同上(build_server 注入)
    files: FileService            # 同上(/api/files/** 三步上传)

    def _identity_post(self) -> tuple[int, dict] | None:
        """身份与登录端点自带鉴权(API Key / 授权码+PKCE / 演示账密);非身份路径返回 None。"""
        if _LOGIN.match(self.path):
            return self.identity.demo_login_body(self._read_body())
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
        unified_open = _OPEN_UNIFIED.match(self.path)
        per_question_open = _OPEN.match(self.path)
        if self.command == "POST" and (unified_open or per_question_open):
            # 统一 Open(§5)须先判:否则 "open" 被当作路径 question_id
            if unified_open:
                self._open_unified()
            else:
                self._open_prepared_question(per_question_open["question_id"])
            return
        if self._dialogue_post():
            return
        if not self._files_post():
            self._error(ApiError(404, None, "路径不在合作方合同内"))

    def _dialogue_post(self) -> bool:
        """对话面 POST 路由;未命中返回 False(404 由 _dispatch 收口)。"""
        if _CREATE.match(self.path) and self.command == "POST":
            self._create_conversation()
            return True
        refresh = _REFRESH_PQ.match(self.path) or _REFRESH_CONV.match(self.path)
        if refresh and self.command == "POST":
            self._json(self.service.refresh(refresh["skill_session_id"]))
            return True
        match = _MESSAGES.match(self.path)
        if match and self.command == "POST":
            self._json(self.service.send(match["conversation_id"], self._read_body()))
            return True
        match = _MESSAGES_STREAM.match(self.path)
        if match and self.command == "POST":
            self._stream(match["conversation_id"])
            return True
        return False

    def _files_post(self) -> bool:
        """files 面 POST 路由(三步上传的 1/3 步);未命中返回 False。"""
        if _FILES_UPLOAD.match(self.path):
            self._json(self.files.upload_request(self._read_body()), status=201)
            return True
        if _FILES_COMPLETE.match(self.path):
            self._json(self.files.complete(self._read_body()))
            return True
        return False

    def do_PUT(self) -> None:
        """PUT /api/files/{file_id}/content:二进制上传(学生 token 鉴权)。"""
        match = _FILES_CONTENT.match(self.path)
        if match is None:
            self._error(ApiError(404, None, "路径不在合作方合同内"))
            return
        if not self.headers.get("Authorization"):
            self._error(ApiError(401, None, "登录令牌无效或已过期"))
            return
        length = int(self.headers.get("Content-Length") or 0)
        payload = self.rfile.read(length)
        self._json(self.files.store_content(match["file_id"], payload))

    def _stream(self, conversation_id: str) -> None:
        # 流式:请求类错误(409/422 等)在开流前以 JSON 错误返回;内核异常(503)
        # 走流内 error 帧(友好文案+错误码)——流已开,客户端按 error 事件收尾
        try:
            response = self.service.send(conversation_id, self._read_body())
        except ApiError as error:
            if error.status_code >= 500:
                payload = sse_error_frames(error)
            else:
                self._error(error)
                return
        else:
            payload = sse_frames(response)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_POST = _dispatch

    def do_GET(self) -> None:
        if _HEALTHZ.match(self.path):
            from .healthz import snapshot  # 局部导入:快照依赖模型配置,按需加载
            self._json(snapshot())
            return
        if self.path in ("/chat", "/chat/", "/static/chat.html"):
            from pathlib import Path as _Path

            chat_file = _Path(__file__).resolve().parent / "static" / "chat.html"
            if chat_file.is_file():
                payload = chat_file.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            else:
                self.send_error(404)
            return
        if not self.headers.get("Authorization"):
            self._error(ApiError(401, None, "登录令牌无效或已过期"))
            return
        match = _GET.match(self.path)
        if match:
            self._json(self.service.status(match["conversation_id"]))
            return
        match = _FILES_CONTENT.match(self.path)
        if match:
            payload, content_type = self.files.read_content(match["file_id"])
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self._error(ApiError(404, None, "路径不在合作方合同内"))

    def _open_unified(self) -> None:
        """POST /api/prepared-questions/open(§5 统一 Open);403 拦截照 00 §5.2 约定 4。"""
        body = self._read_body()
        forbidden = sorted(_FORBIDDEN_FIELDS & set(body))
        if forbidden:
            raise ApiError(403, None, f"客户端不得提交字段:{','.join(forbidden)}")
        self._json(self.service.open_unified(body))

    def _open_prepared_question(self, question_id: str) -> None:
        """POST /api/prepared-questions/{id}/open(#55 既有入口,抽方法保 _dispatch 预算)。"""
        body = self._body_keys("idempotency_key")
        self._json(self.service.open(question_id, body["idempotency_key"], learner={}))

    def _create_conversation(self) -> None:
        """POST /api/conversations:统一 Open 字段子集(external_question_id/
        question_text/question_image,service 内校验与组合规则);403 拦截照 00 §5.2 约定 4。"""
        body = self._read_body()
        forbidden = sorted(_FORBIDDEN_FIELDS & set(body))
        if forbidden:
            # 00 §5.2 约定 4:掌握结论只能服务端产生,客户端不得提交
            raise ApiError(403, None, f"客户端不得提交字段:{','.join(forbidden)}")
        self._json(self.service.create(body), status=201)

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
            {"error": {"code": error.code, "message": error.message, "request_id": "",
                       "details": error.details}},
            status=error.status_code,
        )

    def handle_one_request(self) -> None:  # 统一错误出口;未预期异常兜底 503,不静默断连
        try:
            super().handle_one_request()
        except ApiError as error:
            self._error(error)  # 原样透传(保留 details 等合同字段)
        except IdentityError as error:
            self._error(ApiError(getattr(error, "status_code", 500),
                                 getattr(error, "code", None), error.message))
        except Exception as error:  # noqa: BLE001 传输层兜底:基础设施故障(合同表 503)
            self._error(ApiError(503, None, f"服务暂不可用:{type(error).__name__}"))

    def log_message(self, format: str, *args: object) -> None:
        pass  # 访问日志静默(healthz 同款)


def build_server(service: ConversationService, identity: IdentityService | None = None,
                 files: FileService | None = None,
                 host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    handler = type("BoundPartnerApiHandler", (PartnerApiHandler,),
                   {"service": service, "identity": identity or IdentityService(),
                    "files": files or FileService()})
    return ThreadingHTTPServer((host, port), handler)
