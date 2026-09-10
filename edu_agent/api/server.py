"""合作方接口 HTTP 面(00 §5.2:对话四端点 + 身份两端点 + healthz;stdlib 不引 web 框架)。

路由与错误信封按 #48 合同快照:错误体 {"error": {code, message, request_id,
details}}(老仓库 ErrorEnvelope 形态)。SSE 六型帧见 sse_frames。
鉴权分面:对话端点查 Authorization 头存在性(401 兜底);身份两端点自带鉴权
(native-codes=partner API Key,token=授权码+PKCE),在全局闸之前路由。
"""

from __future__ import annotations

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .files import MAX_BYTES, FileService
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
_LOGOUT = re.compile(r"^/api/auth/logout$")
_HEALTHZ = re.compile(r"^/healthz$")
_FILES_UPLOAD = re.compile(r"^/api/files/upload-request$")
_FILES_COMPLETE = re.compile(r"^/api/files/complete$")
_FILES_CONTENT = re.compile(r"^/api/files/(?P<file_id>[^/]+)/content$")
# 老合同别名(docs/partner/files.md):同一 service,仅前缀不同——合作方按老文档调
# /api/openapi/v1/files/* → 转调同名 service 方法,不复制逻辑、不改名新路径(内部演示页在用)。
_FILES_UPLOAD_LEGACY = re.compile(r"^/api/openapi/v1/files/upload-url$")
_FILES_COMPLETE_LEGACY = re.compile(r"^/api/openapi/v1/files/complete$")
_FILES_CONTENT_LEGACY = re.compile(r"^/api/openapi/v1/files/(?P<file_id>[^/]+)/content$")
_FILES_DOWNLOAD_LEGACY = re.compile(r"^/api/openapi/v1/files/(?P<file_id>[^/]+)/download-url$")
_FILES_PREVIEW_LEGACY = re.compile(r"^/api/openapi/v1/files/(?P<file_id>[^/]+)/preview-url$")


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
            return self.identity.native_code(self._read_body(), self.headers)
        if _NATIVE_TOKEN.match(self.path):
            return self.identity.native_token(self._read_body())
        if _LOGOUT.match(self.path):
            # 老系统 LogoutResponse = {"ok": true}。token 为无状态 HMAC,不做吊销名单
            # (最小实现,目标指示);按老文档返回成功即可,offline 后 token 过期即失效。
            return 200, {"ok": True}
        return None

    def _authorized(self) -> bool:
        """对话面鉴权闸(P1-1):真验签,HMAC 比签 + exp,失败 401。

        EDU_AUTH_ENFORCE=0 熔断跳过验签(联调应急,决策 7);默认强制。
        """
        token = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not token:
            return False
        if os.environ.get("EDU_AUTH_ENFORCE", "1") == "0":
            return True
        return self.identity.verify_token(token)

    def _dispatch(self) -> None:
        self.path = self.path.partition("?")[0]  # 剥 query string(审查 P2:regex $ 锚定不剥 ? 全 404)
        identity = self._identity_post()
        if identity is not None:
            self._json(identity[1], identity[0])
            return
        if not self._authorized():
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
        """files 面 POST 路由(三步上传的 1/3 步);未命中返回 False。

        老合同别名(/api/openapi/v1/files/upload-url|complete)与现有新路径共用同一
        FileService 方法——仅前缀不同,不复制逻辑。"""
        if _FILES_UPLOAD.match(self.path) or _FILES_UPLOAD_LEGACY.match(self.path):
            self._json(self.files.upload_request(self._read_body()), status=201)
            return True
        if _FILES_COMPLETE.match(self.path) or _FILES_COMPLETE_LEGACY.match(self.path):
            self._json(self.files.complete(self._read_body()))
            return True
        return False

    def do_PUT(self) -> None:
        """PUT 上传二进制(学生 token 鉴权):新路径 + 老合同别名共用 store_content。"""
        self.path = self.path.partition("?")[0]  # 剥 query string(审查 P2)
        match = _FILES_CONTENT.match(self.path) or _FILES_CONTENT_LEGACY.match(self.path)
        if match is None:
            self._error(ApiError(404, None, "路径不在合作方合同内"))
            return
        if not self._authorized():
            self._error(ApiError(401, None, "登录令牌无效或已过期"))
            return
        length = self._content_length()
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

    # ---------- CORS(老系统语义移植:白名单 echo,不放行凭据) ----------
    # 老系统 FastAPI CORSMiddleware:EDU_AGENT_CORS_ALLOWED_ORIGINS 逗号分隔白名单,
    # allow_credentials=False、方法/头全放行。env 名沿用老系统,部署零改动。
    def _cors_origin(self) -> str:
        """请求 Origin 命中白名单 → 原样返回(echo);否则空串(不发 CORS 头)。"""
        origin = self.headers.get("Origin") or ""
        allowed = {o.strip() for o in
                   os.environ.get("EDU_AGENT_CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()}
        return origin if origin in allowed else ""

    def end_headers(self) -> None:
        # 统一注入口:所有响应(json/文件/SSE/错误)在头发送前补 CORS
        origin = self._cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        """浏览器预检:白名单内 → 204 + 放行头;白名单外 → 400(照老系统 CORSMiddleware
        的 Disallowed CORS origin 语义),非浏览器客户端不受影响。"""
        origin = self._cors_origin()
        if not origin:
            self.send_response(400)
            self.end_headers()
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    # 公开文档(老系统 URL 结构兼容):docs/partner 白名单,无 markdown 依赖——
    # index 单页 HTML + 原文 raw.md(浏览器直接可读,合作方是开发者)。
    _DOCS_DIR = Path(__file__).resolve().parents[2] / "docs" / "partner"
    _DOCS_GUIDES = {  # URL 名 → 文件名(白名单即路径穿越防护)
        "small-lecturer-v1": "小讲师对话教学(统一 Open/多轮/流式/总结)",
        "files": "题图三步上传",
        "partner-sso": "合作方 SSO(native-codes/PKCE)",
        "response-conventions": "响应与错误码约定",
    }
    _DOCS_INDEX = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<title>edu-agent 合作方 API 文档</title><style>
body{{font-family:-apple-system,"PingFang SC",sans-serif;max-width:720px;margin:40px auto;padding:0 16px;color:#333}}
h1{{font-size:22px}} p{{color:#666;line-height:1.6}} li{{margin:10px 0}}
a{{color:#4a90d9;text-decoration:none}} code{{background:#f5f5f5;padding:2px 6px;border-radius:4px}}
.meta{{color:#999;font-size:13px}}</style></head><body>
<h1>edu-agent 合作方 API 文档</h1>
<p>小讲师教学对话服务。第一阶段对接建议:登录 → 题图上传(files)→ 统一 Open 开题 →
refresh 取首问 → messages 多轮 → confirm 总结。凭据经对接群单独提供。</p>
<ul>
{items}
</ul>
<p class="meta">本页公开无需鉴权;接口调用需 Bearer token。文档原文均为 Markdown。</p>
</body></html>"""

    def _serve_docs(self) -> bool:
        """GET /api/docs*;未命中返回 False。公开路由(鉴权闸之前调用)。"""
        if self.path in ("/api/docs", "/api/docs/"):
            items = "".join(
                f'<li><a href="/api/docs/guides/{name}/raw.md">{title}</a>'
                f' <span class="meta">/api/docs/guides/{name}/raw.md</span></li>'
                for name, title in self._DOCS_GUIDES.items())
            payload = self._DOCS_INDEX.format(items=items).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        else:
            guide = re.fullmatch(r"/api/docs/guides/([^/]+)/raw\.md", self.path)
            if not guide or guide[1] not in self._DOCS_GUIDES:
                return False
            payload = (self._DOCS_DIR / f"{guide[1]}.md").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Cache-Control", "max-age=300")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        return True

    def _serve_static(self) -> bool:
        """GET /chat 与 /static/*(演示页与题库资产);未命中返回 False。"""
        if not (self.path in ("/chat", "/chat/", "/static/chat.html")
                or self.path.startswith("/static/")):
            return False
        static_root = Path(__file__).resolve().parent / "static"
        name = "chat.html" if not self.path.startswith("/static/") \
            else self.path.removeprefix("/static/")
        asset = (static_root / name).resolve()
        if static_root not in asset.parents or not asset.is_file():
            self.send_error(404)
            return True
        content_type = ("text/html; charset=utf-8" if asset.suffix == ".html"
                        else "application/json" if asset.suffix == ".json"
                        else "image/jpeg" if asset.suffix == ".jpg"
                        else "image/png" if asset.suffix == ".png"
                        else "image/webp" if asset.suffix == ".webp"
                        else "application/octet-stream")
        payload = asset.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "max-age=3600")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        return True

    def do_GET(self) -> None:
        self.path = self.path.partition("?")[0]  # 剥 query string(审查 P2)
        if _HEALTHZ.match(self.path):
            from .healthz import snapshot  # 局部导入:快照依赖模型配置,按需加载
            self._json(snapshot())
            return
        if self._serve_docs() or self._serve_static():
            return
        if not self._authorized():
            self._error(ApiError(401, None, "登录令牌无效或已过期"))
            return
        match = _GET.match(self.path)
        if match:
            self._json(self.service.status(match["conversation_id"]))
            return
        if self._files_get():
            return
        self._error(ApiError(404, None, "路径不在合作方合同内"))

    def _files_get(self) -> bool:
        """files 面 GET:读二进制(content)+ 老合同 download-url/preview-url;未命中 False。

        抽方法保 do_GET 的 return 预算(ruff PLR0911);content 返回二进制字节,
        download/preview 返回 JSON 地址(本地语义,老文档 §7 字段形状)。"""
        match = _FILES_CONTENT.match(self.path) or _FILES_CONTENT_LEGACY.match(self.path)
        if match:
            payload, content_type = self.files.read_content(match["file_id"])
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return True
        dl = _FILES_DOWNLOAD_LEGACY.match(self.path)
        if dl:
            self._json(self.files.download_url(dl["file_id"]))
            return True
        pv = _FILES_PREVIEW_LEGACY.match(self.path)
        if pv:
            self._json(self.files.preview_url(pv["file_id"]))
            return True
        return False

    def _open_unified(self) -> None:
        """POST /api/prepared-questions/open(§5 统一 Open);403 拦截照 00 §5.2 约定 4。"""
        body = self._read_body()
        forbidden = sorted(_FORBIDDEN_FIELDS & set(body))
        if forbidden:
            raise ApiError(403, None, f"客户端不得提交字段:{','.join(forbidden)}")
        self._json(self.service.open_unified(body))

    def _open_prepared_question(self, question_id: str) -> None:
        """POST /api/prepared-questions/{id}/open(#55 既有入口,App 主路径,00 §5.2 约定 1-2)。

        A 线 §8.5(M3 WS1):answer_correct(bool|null)/knowledge_points(≤20,name 必填)
        从请求体接收,经 service.open_request_learner 构造 learner(answer_status 映射
        + provenance)传给 kernel.start()——替换原写死 learner={};约定 4 拦截与统一
        open / conversations 同款。"""
        body = self._read_body()
        forbidden = sorted(_FORBIDDEN_FIELDS & set(body))
        if forbidden:
            raise ApiError(403, None, f"客户端不得提交字段:{','.join(forbidden)}")
        if not body.get("idempotency_key"):
            raise ApiError(422, None, "idempotency_key 必填(00 §5.2:请求只有 idempotency_key)")
        learner, _, _ = ConversationService.open_request_learner(
            body, frozenset({"idempotency_key"}) | ConversationService._OPEN_LEARNER_FIELDS)
        self._json(self.service.open(question_id, str(body["idempotency_key"]), learner))

    def _create_conversation(self) -> None:
        """POST /api/conversations:统一 Open 字段子集(external_question_id/
        question_text/question_image,service 内校验与组合规则);403 拦截照 00 §5.2 约定 4。"""
        body = self._read_body()
        forbidden = sorted(_FORBIDDEN_FIELDS & set(body))
        if forbidden:
            # 00 §5.2 约定 4:掌握结论只能服务端产生,客户端不得提交
            raise ApiError(403, None, f"客户端不得提交字段:{','.join(forbidden)}")
        self._json(self.service.create(body), status=201)

    def _content_length(self) -> int:
        """读 Content-Length 并 clamp 到 20MB 上限;非法(非整数/负) → 400。

        读前有界防 OOM(审查 P2:先整读进内存再校验可被超大 Content-Length 打爆);
        int() 失败原落 503,按「客户端请求格式错误」收口为 400。
        """
        raw = self.headers.get("Content-Length") or "0"
        try:
            length = int(raw)
        except ValueError:
            raise ApiError(400, None, "Content-Length 非法") from None
        if length < 0:
            raise ApiError(400, None, "Content-Length 非法") from None
        return min(length, MAX_BYTES)

    def _read_body(self) -> dict:
        length = self._content_length()
        if not length:
            return {}
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            raise ApiError(422, None, "请求体不是合法 JSON") from None
        if not isinstance(payload, dict):
            raise ApiError(422, None, "请求体必须是 JSON 对象")
        return payload

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
