"""老合同 files 路径兼容层(docs/partner/files.md /api/openapi/v1/files/* 族)。

老系统文档写的是 /api/openapi/v1/files/{upload-url|complete|{id}/content} 三族 + download-url/
preview-url 两族;新实现叫 /api/files/upload-request|complete|{id}/content。本组只测老路径——
验证合作方按老文档调能通、响应字段形状对齐老合同,且老路径与新路径共用同一 FileService
(不复制逻辑)。logout 同组(git 老系统 LogoutResponse={"ok": true})。

图片全部 PIL 现场生成;HTTP 面含老路径 PUT 二进制与 GET 图片字节;SSRF 边界同
test_files_api:只打 127.0.0.1 环回测试服务器。
"""

from __future__ import annotations

import io
import threading

import httpx
import pytest
from PIL import Image

from edu_agent.api import FileService, build_server, build_service
from test_api_service import ScriptedKernel, _assert_local_base


def png_bytes(width: int = 64, height: int = 64) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(30, 144, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def api(tmp_path):
    server = build_server(build_service(ScriptedKernel(replies=["好"], ready_at=99)),
                          files=FileService(tmp_path / "files"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", tmp_path
    server.shutdown()
    server.server_close()


AUTH = {"Authorization": "Bearer student-token"}
LEGACY_UPLOAD = "/api/openapi/v1/files/upload-url"
LEGACY_COMPLETE = "/api/openapi/v1/files/complete"


def _post(base, path, payload, status=200):
    _assert_local_base(base)
    response = httpx.post(f"{base}{path}", json=payload, headers=AUTH, timeout=5.0,
                          trust_env=False)
    assert response.status_code == status, response.text
    return response


def _put(base, path, payload, content_type="image/png", status=200):
    _assert_local_base(base)
    response = httpx.put(f"{base}{path}", content=payload,
                         headers={**AUTH, "Content-Type": content_type},
                         timeout=10.0, trust_env=False)
    assert response.status_code == status, response.text
    return response


def _get(base, path, status=200):
    _assert_local_base(base)
    response = httpx.get(f"{base}{path}", headers=AUTH, timeout=5.0, trust_env=False)
    assert response.status_code == status, response.text
    return response


# ---------- 老路径三步上传全流程(files.md §3/§5/§6) ----------

def test_legacy_full_flow_upload_url_put_complete(api):
    """老路径 upload-url(POST)→ content(PUT)→ complete(POST) 全流程可用。"""
    base, tmp_path = api
    payload = png_bytes()
    created = _post(base, LEGACY_UPLOAD,
                    {"filename": "question.png", "content_type": "image/png",
                     "size_bytes": len(payload),
                     "purpose": "micro_lesson_question_image"}, status=201)
    body = created.json()
    file_id = body["file_id"]
    # 老文档 §5 响应:file_id + upload_method + upload_url + headers
    assert body["upload_method"] == "PUT"
    assert body["upload_url"] == f"/api/files/{file_id}/content"
    assert body["headers"] == {"Content-Type": "image/png"}

    # 老路径(content)PUT 二进制
    put = _put(base, f"/api/openapi/v1/files/{file_id}/content", payload)
    assert put.json() == {"file_id": file_id, "status": "uploaded"}

    complete = _post(base, LEGACY_COMPLETE, {"file_id": file_id})
    assert complete.json() == {"file_id": file_id, "status": "uploaded"}

    # 老路径(content)PUT 后可直接读取图片字节(files.md §7 content 地址)
    got_bytes = httpx.get(f"{base}/api/openapi/v1/files/{file_id}/content",
                          headers=AUTH, timeout=5.0, trust_env=False)
    assert got_bytes.status_code == 200
    assert got_bytes.headers["content-type"] == "image/png"
    stored = Image.open(io.BytesIO(got_bytes.content))
    assert stored.size == (64, 64)


def test_legacy_upload_missing_fields_422(api):
    """老路径 upload-url 缺必填 → 422(与现实现同一 service 校验,不假设字段顺序)。"""
    base, _ = api
    response = _post(base, LEGACY_UPLOAD, {"filename": "x.png"}, status=422)
    assert response.json()["error"]["code"] is None
    assert response.json()["error"]["message"]  # 必填缺失有中文说明


def test_legacy_unsupported_purpose_422(api):
    """老路径 upload-url 非法 purpose → 422 UNSUPPORTED_PURPOSE(同一 service)。"""
    base, _ = api
    payload = png_bytes()
    response = _post(base, LEGACY_UPLOAD,
                     {"filename": "x.png", "content_type": "image/png",
                      "size_bytes": len(payload), "purpose": "avatar"}, status=422)
    assert response.json()["error"]["code"] == "UNSUPPORTED_PURPOSE"


def test_legacy_too_large_413(api):
    """老路径 upload-url 超限 → 413 FILE_TOO_LARGE(同一 service)。"""
    base, _ = api
    response = _post(base, LEGACY_UPLOAD,
                     {"filename": "big.png", "content_type": "image/png",
                      "size_bytes": 21 * 1024 * 1024,
                      "purpose": "micro_lesson_question_image"}, status=413)
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


# ---------- download-url / preview-url(files.md §7) ----------

def _uploaded(base, tmp_path):
    """走老路径完成一个上传,返回 (file_id, payload)。"""
    payload = png_bytes()
    created = _post(base, LEGACY_UPLOAD,
                    {"filename": "q.png", "content_type": "image/png",
                     "size_bytes": len(payload),
                     "purpose": "micro_lesson_question_image"}, status=201)
    file_id = created.json()["file_id"]
    _put(base, f"/api/openapi/v1/files/{file_id}/content", payload)
    _post(base, LEGACY_COMPLETE, {"file_id": file_id})
    return file_id


def test_legacy_download_url_shape(api):
    """老路径 download-url 返回老文档 §7 字段形状(requires_authorization/url_expires_at/
    delivery_mode = authenticated_api_content_proxy,不发明字段)。"""
    base, tmp_path = api
    file_id = _uploaded(base, tmp_path)
    body = _get(base, f"/api/openapi/v1/files/{file_id}/download-url").json()
    assert body["file_id"] == file_id
    # 本地语义:download_url 指向本服务鉴权 content 端点
    assert body["download_url"] == f"/api/files/{file_id}/content"
    assert body["requires_authorization"] is True
    assert body["url_expires_at"] is None
    assert body["delivery_mode"] == "authenticated_api_content_proxy"


def test_legacy_preview_url_shape(api):
    """老路径 preview-url 返回图片预览=下载的本地语义;head_supported=false。"""
    base, tmp_path = api
    file_id = _uploaded(base, tmp_path)
    body = _get(base, f"/api/openapi/v1/files/{file_id}/preview-url").json()
    assert body["file_id"] == file_id
    path = f"/api/files/{file_id}/content"
    assert body["preview_url"] == path and body["download_url"] == path
    assert body["preview_mode"] == "inline_file" and body["method"] == "GET"
    assert body["requires_authorization"] is True
    assert body["head_supported"] is False
    assert body["cache_control"] == "private, no-store"


def test_legacy_download_url_not_ready_404(api):
    """老路径 download-url 未上传 → 404 FILE_NOT_READY(与现实现同准)。"""
    base, _ = api
    created = _post(base, LEGACY_UPLOAD,
                    {"filename": "x.png", "content_type": "image/png",
                     "size_bytes": 10,
                     "purpose": "micro_lesson_question_image"}, status=201)
    response = _get(base, f"/api/openapi/v1/files/{created.json()['file_id']}/download-url",
                    status=404)
    assert response.json()["error"]["code"] == "FILE_NOT_READY"


def test_legacy_download_url_missing_404(api):
    """老路径 download-url 不存在 file_id → 404 FILE_NOT_READY。"""
    base, _ = api
    response = _get(base, "/api/openapi/v1/files/file_nope/download-url", status=404)
    assert response.json()["error"]["code"] == "FILE_NOT_READY"


def test_legacy_download_url_requires_auth_401(api):
    """老路径 download-url 无 Bearer → 401(现有鉴权闸,不放松)。"""
    base, _ = api
    _assert_local_base(base)
    response = httpx.get(f"{base}/api/openapi/v1/files/file_x/download-url",
                         timeout=5.0, trust_env=False)
    assert response.status_code == 401


# ---------- logout(partner-sso.md §7;LogoutResponse={"ok": true}) ----------

def test_logout_returns_ok(api):
    """POST /api/auth/logout → 200 {"ok": true}(老系统 LogoutResponse 形状)。"""
    base, _ = api
    response = _post(base, "/api/auth/logout", {})
    assert response.json() == {"ok": True}


def test_logout_idempotent_without_token(api):
    """logout 无 Bearer 也返回 ok(老系统 logout 幂等,无会话仍成功)。"""
    base, _ = api
    _assert_local_base(base)
    response = httpx.post(f"{base}/api/auth/logout", json={}, timeout=5.0, trust_env=False)
    assert response.status_code == 200
    assert response.json() == {"ok": True}
