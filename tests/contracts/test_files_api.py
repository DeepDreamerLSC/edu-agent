"""/api/files/** 与 /api/openapi/v1/files/** 三步上传合同(#34 新实现 + 老系统 files.md 兼容层)。

新路径(/api/files/upload-request|complete|{id}/content)与老路径
(/api/openapi/v1/files/upload-url|complete|{id}/content)共用同一 FileService(不复制逻辑);
老路径额外带 download-url/preview-url 两族与 logout(partner-sso.md §7)。本文件把两族
共享行为(非法 purpose、超限)按路径族参数化合一;其余各自独有的契约断言原样保留
(决策 1/2:精简测试比分子,零删断言)。
图片全部 PIL 现场生成;HTTP 面含 PUT 二进制与 GET 图片字节;SSRF 边界同:
只打 127.0.0.1 环回测试服务器。
"""

from __future__ import annotations

import hashlib
import io
import threading
from urllib.parse import urlparse

import httpx
import pytest
from PIL import Image

from edu_agent.api import FileService, build_server, build_service
from partner_api import ScriptedKernel


NEW_UPLOAD = "/api/files/upload-request"
NEW_COMPLETE = "/api/files/complete"
NEW_CONTENT = "/api/files/{file_id}/content"
LEGACY_UPLOAD = "/api/openapi/v1/files/upload-url"
LEGACY_COMPLETE = "/api/openapi/v1/files/complete"
LEGACY_CONTENT = "/api/openapi/v1/files/{file_id}/content"

AUTH = {"Authorization": "Bearer student-token"}


def png_bytes(width: int = 64, height: int = 64, fmt: str = "PNG",
              mime: str = "image/png") -> tuple[bytes, str]:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(30, 144, 255)).save(buffer, format=fmt)
    return buffer.getvalue(), mime


def _assert_loopback(base: str) -> None:
    """SSRF 边界:测试只允许打 127.0.0.1 环回上的本地测试服务器。"""
    parsed = urlparse(base)
    assert parsed.scheme == "http" and parsed.hostname == "127.0.0.1", base


@pytest.fixture
def api(tmp_path):
    server = build_server(build_service(ScriptedKernel(replies=["好"], ready_at=99)),
                          files=FileService(tmp_path / "files"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", tmp_path
    server.shutdown()
    server.server_close()


def _post(base, path, payload, status=200):
    _assert_loopback(base)
    response = httpx.post(f"{base}{path}", json=payload, headers=AUTH, timeout=5.0,
                          trust_env=False)
    assert response.status_code == status, response.text
    return response


def _put(base, path, payload, content_type="image/png", status=200):
    _assert_loopback(base)
    response = httpx.put(f"{base}{path}", content=payload,
                         headers={**AUTH, "Content-Type": content_type},
                         timeout=10.0, trust_env=False)
    assert response.status_code == status, response.text
    return response


def _get(base, path, status=None):
    _assert_loopback(base)
    response = httpx.get(f"{base}{path}", headers=AUTH, timeout=5.0, trust_env=False)
    if status is not None:
        assert response.status_code == status, response.text
    return response


def _request_upload(base, size=None, purpose="micro_lesson_question_image",
                    content_type="image/png", checksum=None):
    payload, _ = png_bytes()
    body = {"filename": "question.png", "content_type": content_type,
            "size_bytes": size if size is not None else len(payload),
            "purpose": purpose}
    if checksum:
        body["checksum_sha256"] = checksum
    return _post(base, NEW_UPLOAD, body, status=201), payload


def _uploaded(base, tmp_path):
    """走老路径完成一个上传,返回 file_id。"""
    payload, _ = png_bytes()
    created = _post(base, LEGACY_UPLOAD,
                    {"filename": "q.png", "content_type": "image/png",
                     "size_bytes": len(payload),
                     "purpose": "micro_lesson_question_image"}, status=201)
    file_id = created.json()["file_id"]
    _put(base, LEGACY_CONTENT.format(file_id=file_id), payload)
    _post(base, LEGACY_COMPLETE, {"file_id": file_id})
    return file_id


# ---------- 全流程(新 + 老) ----------

def test_full_flow_upload_put_complete_get(api):
    base, tmp_path = api
    created, payload = _request_upload(base)
    file_id = created.json()["file_id"]
    assert created.json()["upload_method"] == "PUT"
    assert created.json()["upload_url"] == f"/api/files/{file_id}/content"
    assert created.json()["headers"] == {"Content-Type": "image/png"}

    put = _put(base, NEW_CONTENT.format(file_id=file_id), payload)
    assert put.json() == {"file_id": file_id, "status": "uploaded"}

    complete = _post(base, NEW_COMPLETE, {"file_id": file_id})
    assert complete.json() == {"file_id": file_id, "status": "uploaded"}

    got = _get(base, NEW_CONTENT.format(file_id=file_id))
    assert got.status_code == 200
    assert got.headers["content-type"] == "image/png"
    stored = Image.open(io.BytesIO(got.content))  # 返回的是合法图片字节
    assert stored.size == (64, 64)
    # 本地磁盘落盘:file_id 命名,ext 按实际 MIME(不用用户 filename)
    saved = list((tmp_path / "files").glob(f"{file_id}.*"))
    assert len(saved) == 1 and saved[0].suffix == ".png"


def test_legacy_full_flow_upload_url_put_complete(api):
    """老路径 upload-url(POST)→ content(PUT)→ complete(POST) 全流程可用。"""
    base, tmp_path = api
    payload, _ = png_bytes()
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
    put = _put(base, LEGACY_CONTENT.format(file_id=file_id), payload)
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


def test_resize_large_image_to_1280(api):
    """超大尺寸(未超像素上限)→ 服务端 resize 至 1280×1280 内(视觉编码时间压缩)。"""
    base, _ = api
    payload, _ = png_bytes(2000, 1000)
    created = _post(base, NEW_UPLOAD,
                    {"filename": "big.png", "content_type": "image/png",
                     "size_bytes": len(payload),
                     "purpose": "micro_lesson_question_image"}, status=201)
    file_id = created.json()["file_id"]
    _put(base, NEW_CONTENT.format(file_id=file_id), payload)
    got = _get(base, NEW_CONTENT.format(file_id=file_id))
    stored = Image.open(io.BytesIO(got.content))
    assert stored.size == (1280, 640)  # 等比缩到宽 1280


# ---------- 双族共享行为:非法 purpose 与超限(按路径族参数化) ----------

@pytest.mark.parametrize("upload_path", [NEW_UPLOAD, LEGACY_UPLOAD],
                         ids=["new", "legacy"])
def test_unsupported_purpose_422(api, upload_path):
    """非法 purpose → 422 UNSUPPORTED_PURPOSE(新老路径同一 service,行为一致)。"""
    base, _ = api
    payload, _ = png_bytes()
    response = _post(base, upload_path,
                     {"filename": "x.png", "content_type": "image/png",
                      "size_bytes": len(payload), "purpose": "avatar"}, status=422)
    assert response.json()["error"]["code"] == "UNSUPPORTED_PURPOSE"


@pytest.mark.parametrize("upload_path", [NEW_UPLOAD, LEGACY_UPLOAD],
                         ids=["new", "legacy"])
def test_too_large_413(api, upload_path):
    """超限 → 413 FILE_TOO_LARGE(新老路径共享同一条 21MB 上限)。"""
    base, _ = api
    response = _post(base, upload_path,
                     {"filename": "big.png", "content_type": "image/png",
                      "size_bytes": 21 * 1024 * 1024,
                      "purpose": "micro_lesson_question_image"}, status=413)
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


# ---------- 新路径错误码逐条 ----------

def test_size_mismatch_409(api):
    base, _ = api
    created, payload = _request_upload(base, size=1024)  # 申请与实际不一致
    response = _put(base, NEW_CONTENT.format(file_id=created.json()["file_id"]),
                    payload, status=409)
    assert response.json()["error"]["code"] == "FILE_SIZE_MISMATCH"


def test_checksum_mismatch_409(api):
    base, _ = api
    created, payload = _request_upload(base, checksum="0" * 64)  # 合法 hex 但不符
    response = _put(base, NEW_CONTENT.format(file_id=created.json()["file_id"]),
                    payload, status=409)
    assert response.json()["error"]["code"] == "FILE_CHECKSUM_MISMATCH"


def test_complete_before_upload_409(api):
    base, _ = api
    created, _ = _request_upload(base)  # 只申请不上传
    response = _post(base, NEW_COMPLETE,
                     {"file_id": created.json()["file_id"]}, status=409)
    assert response.json()["error"]["code"] == "FILE_CONTENT_MISSING"


def test_get_not_ready_404(api):
    base, _ = api
    created, _ = _request_upload(base)  # 已申请未上传
    response = _get(base, NEW_CONTENT.format(file_id=created.json()["file_id"]))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FILE_NOT_READY"
    missing = _get(base, NEW_CONTENT.format(file_id="file_nope"))
    assert missing.json()["error"]["code"] == "FILE_NOT_READY"


# ---------- 图片安全三例 ----------

def test_fake_mime_415(api):
    """PNG 字节声明 image/jpeg → NATIVE_FILE_CONTENT_TYPE_MISMATCH。"""
    base, _ = api
    payload, _ = png_bytes()
    created = _post(base, NEW_UPLOAD,
                    {"filename": "x.png", "content_type": "image/jpeg",
                     "size_bytes": len(payload),
                     "purpose": "micro_lesson_student_solution_image"}, status=201)
    response = _put(base, NEW_CONTENT.format(file_id=created.json()["file_id"]), payload,
                    content_type="image/jpeg", status=415)
    assert response.json()["error"]["code"] == "NATIVE_FILE_CONTENT_TYPE_MISMATCH"


def test_not_an_image_415(api):
    """非图片字节 → NATIVE_FILE_CONTENT_INVALID(PIL 解码失败)。"""
    base, _ = api
    payload = b"this is definitely not an image " * 4
    created = _post(base, NEW_UPLOAD,
                    {"filename": "x.png", "content_type": "image/png",
                     "size_bytes": len(payload),
                     "purpose": "micro_lesson_question_image"}, status=201)
    response = _put(base, NEW_CONTENT.format(file_id=created.json()["file_id"]), payload,
                    status=415)
    assert response.json()["error"]["code"] == "NATIVE_FILE_CONTENT_INVALID"


def test_pixels_exceeded_413(api):
    """解码后像素 > 2000 万 → NATIVE_QUESTION_IMAGE_PIXELS_EXCEEDED。"""
    base, _ = api
    payload, _ = png_bytes(6000, 4000)  # 2400 万像素(纯色压缩后字节仍小)
    created = _post(base, NEW_UPLOAD,
                    {"filename": "huge.png", "content_type": "image/png",
                     "size_bytes": len(payload),
                     "purpose": "micro_lesson_question_image"}, status=201)
    response = _put(base, NEW_CONTENT.format(file_id=created.json()["file_id"]), payload,
                    status=413)
    assert response.json()["error"]["code"] == "NATIVE_QUESTION_IMAGE_PIXELS_EXCEEDED"


def test_decompression_bomb_rejected_before_decode(tmp_path):
    """解压炸弹防护窗(审查 P2):header 像素超限在 load() 全量解码**之前**拒绝。

    构造数 MB 压缩体、3 亿+像素声明的 PNG——旧顺序会先 load() 放大出 GB 级
    内存分配再拒绝;新顺序从 header 直读拒绝,Pillow 解码器级上限双保险同值。
    """
    import io as _io

    from edu_agent.api import ApiError, FileService

    service = FileService(tmp_path / "f")
    buffer = _io.BytesIO()
    Image.new("RGB", (20000, 16000), color=(0, 0, 0)).save(  # 3.2 亿像素,纯色体积小
        buffer, format="PNG", optimize=True)
    bomb = buffer.getvalue()
    assert len(bomb) < 2 * 1024 * 1024  # 压缩体确实很小(高压缩比)
    created = service.upload_request({"filename": "bomb.png", "content_type": "image/png",
                                      "size_bytes": len(bomb),
                                      "purpose": "micro_lesson_question_image"})
    with pytest.raises(ApiError) as excinfo:
        service.store_content(created["file_id"], bomb)
    assert excinfo.value.code == "NATIVE_QUESTION_IMAGE_PIXELS_EXCEEDED"
    assert excinfo.value.status_code == 413


# ---------- 幂等与完整性 ----------

def test_complete_idempotent(api):
    base, _ = api
    created, payload = _request_upload(base)
    file_id = created.json()["file_id"]
    _put(base, NEW_CONTENT.format(file_id=file_id), payload)
    first = _post(base, NEW_COMPLETE, {"file_id": file_id})
    second = _post(base, NEW_COMPLETE, {"file_id": file_id})  # 重调不报错
    assert first.json() == second.json() == {"file_id": file_id, "status": "uploaded"}


def test_checksum_happy_path_and_webp(api):
    """带 checksum 的正常路径 + webp 白名单成员 + 落盘扩展名按实际 MIME。"""
    base, tmp_path = api
    payload, _ = png_bytes(fmt="WEBP", mime="image/webp")
    created = _post(base, NEW_UPLOAD,
                    {"filename": "x.webp", "content_type": "image/webp",
                     "size_bytes": len(payload),
                     "purpose": "micro_lesson_question_image",
                     "checksum_sha256": hashlib.sha256(payload).hexdigest()}, status=201)
    file_id = created.json()["file_id"]
    put = _put(base, NEW_CONTENT.format(file_id=file_id), payload, content_type="image/webp")
    assert put.json()["status"] == "uploaded"
    saved = list((tmp_path / "files").glob(f"{file_id}.*"))
    assert saved[0].suffix == ".webp"


# ---------- 老路径 download-url / preview-url(files.md §7) ----------

def test_legacy_upload_missing_fields_422(api):
    """老路径 upload-url 缺必填 → 422(与现实现同一 service 校验,不假设字段顺序)。"""
    base, _ = api
    response = _post(base, LEGACY_UPLOAD, {"filename": "x.png"}, status=422)
    assert response.json()["error"]["code"] is None
    assert response.json()["error"]["message"]  # 必填缺失有中文说明


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
    _assert_loopback(base)
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
    _assert_loopback(base)
    response = httpx.post(f"{base}/api/auth/logout", json={}, timeout=5.0, trust_env=False)
    assert response.status_code == 200
    assert response.json() == {"ok": True}