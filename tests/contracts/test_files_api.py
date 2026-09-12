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

import httpx
import pytest
from PIL import Image

from edu_agent.api import ApiError, FileService
from partner_api import ScriptedKernel, _assert_local_base, get, post, put, serving

from auth_testing import TEST_TOKEN


NEW_UPLOAD = "/api/files/upload-request"
NEW_COMPLETE = "/api/files/complete"
NEW_CONTENT = "/api/files/{file_id}/content"
LEGACY_UPLOAD = "/api/openapi/v1/files/upload-url"
LEGACY_COMPLETE = "/api/openapi/v1/files/complete"
LEGACY_CONTENT = "/api/openapi/v1/files/{file_id}/content"

AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}


def png_bytes(width: int = 64, height: int = 64, fmt: str = "PNG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(30, 144, 255)).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture
def api(tmp_path):
    with serving(ScriptedKernel(replies=["好"], ready_at=99),
                 files=FileService(tmp_path / "files")) as base:
        yield base, tmp_path


def _request_upload(base, size=None, purpose="micro_lesson_question_image",
                    content_type="image/png", checksum=None):
    payload = png_bytes()
    body = {"filename": "question.png", "content_type": content_type,
            "size_bytes": size if size is not None else len(payload),
            "purpose": purpose}
    if checksum:
        body["checksum_sha256"] = checksum
    return post(base, NEW_UPLOAD, body, status=201), payload


def _uploaded(base, tmp_path):
    """走老路径完成一个上传,返回 file_id。"""
    payload = png_bytes()
    created = post(base, LEGACY_UPLOAD,
                   {"filename": "q.png", "content_type": "image/png",
                    "size_bytes": len(payload),
                    "purpose": "micro_lesson_question_image"}, status=201)
    file_id = created.json()["file_id"]
    put(base, LEGACY_CONTENT.format(file_id=file_id), payload, "image/png", status=200)
    post(base, LEGACY_COMPLETE, {"file_id": file_id}, status=200)
    return file_id


# ---------- 全流程(新 + 老) ----------

def test_full_flow_upload_put_complete_get(api):
    base, tmp_path = api
    created, payload = _request_upload(base)
    file_id = created.json()["file_id"]
    assert created.json()["upload_method"] == "PUT"
    assert created.json()["upload_url"] == f"/api/files/{file_id}/content"
    assert created.json()["headers"] == {"Content-Type": "image/png"}

    put_response = put(base, NEW_CONTENT.format(file_id=file_id), payload,
                       "image/png", status=200)
    assert put_response.json() == {"file_id": file_id, "status": "uploaded"}

    complete = post(base, NEW_COMPLETE, {"file_id": file_id}, status=200)
    assert complete.json() == {"file_id": file_id, "status": "uploaded"}

    got = get(base, NEW_CONTENT.format(file_id=file_id))
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
    payload = png_bytes()
    created = post(base, LEGACY_UPLOAD,
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
    put_response = put(base, LEGACY_CONTENT.format(file_id=file_id), payload,
                       "image/png", status=200)
    assert put_response.json() == {"file_id": file_id, "status": "uploaded"}

    complete = post(base, LEGACY_COMPLETE, {"file_id": file_id}, status=200)
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
    payload = png_bytes(2000, 1000)
    created = post(base, NEW_UPLOAD,
                   {"filename": "big.png", "content_type": "image/png",
                    "size_bytes": len(payload),
                    "purpose": "micro_lesson_question_image"}, status=201)
    file_id = created.json()["file_id"]
    put(base, NEW_CONTENT.format(file_id=file_id), payload, "image/png", status=200)
    got = get(base, NEW_CONTENT.format(file_id=file_id))
    stored = Image.open(io.BytesIO(got.content))
    assert stored.size == (1280, 640)  # 等比缩到宽 1280


# ---------- 双族共享行为:非法 purpose 与超限(按路径族参数化) ----------

@pytest.mark.parametrize("upload_path", [NEW_UPLOAD, LEGACY_UPLOAD],
                         ids=["new", "legacy"])
def test_unsupported_purpose_422(api, upload_path):
    """非法 purpose → 422 UNSUPPORTED_PURPOSE(新老路径同一 service,行为一致)。"""
    base, _ = api
    payload = png_bytes()
    response = post(base, upload_path,
                    {"filename": "x.png", "content_type": "image/png",
                     "size_bytes": len(payload), "purpose": "avatar"}, status=422)
    assert response.json()["error"]["code"] == "UNSUPPORTED_PURPOSE"


@pytest.mark.parametrize("upload_path", [NEW_UPLOAD, LEGACY_UPLOAD],
                         ids=["new", "legacy"])
def test_too_large_413(api, upload_path):
    """超限 → 413 FILE_TOO_LARGE(新老路径共享同一条 21MB 上限)。"""
    base, _ = api
    response = post(base, upload_path,
                    {"filename": "big.png", "content_type": "image/png",
                     "size_bytes": 21 * 1024 * 1024,
                     "purpose": "micro_lesson_question_image"}, status=413)
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


# ---------- 新路径错误码逐条 ----------

@pytest.mark.parametrize("request_kwargs,error_code", [
    ({"size": 1024}, "FILE_SIZE_MISMATCH"),               # 申请与实际不一致
    ({"checksum": "0" * 64}, "FILE_CHECKSUM_MISMATCH"),   # 合法 hex 但不符
], ids=["test_size_mismatch_409", "test_checksum_mismatch_409"])
def test_upload_integrity_mismatch_409(api, request_kwargs, error_code):
    base, _ = api
    created, payload = _request_upload(base, **request_kwargs)
    response = put(base, NEW_CONTENT.format(file_id=created.json()["file_id"]),
                   payload, "image/png", status=409)
    assert response.json()["error"]["code"] == error_code


def test_complete_before_upload_409(api):
    base, _ = api
    created, _ = _request_upload(base)  # 只申请不上传
    response = post(base, NEW_COMPLETE,
                    {"file_id": created.json()["file_id"]}, status=409)
    assert response.json()["error"]["code"] == "FILE_CONTENT_MISSING"


def test_get_not_ready_404(api):
    base, _ = api
    created, _ = _request_upload(base)  # 已申请未上传
    response = get(base, NEW_CONTENT.format(file_id=created.json()["file_id"]))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FILE_NOT_READY"
    missing = get(base, NEW_CONTENT.format(file_id="file_nope"))
    assert missing.json()["error"]["code"] == "FILE_NOT_READY"


# ---------- 图片安全三例 ----------

@pytest.mark.parametrize("make_payload,upload_body,put_type,status,code", [
    pytest.param(png_bytes,
                 {"filename": "x.png", "content_type": "image/jpeg",
                  "purpose": "micro_lesson_student_solution_image"},
                 "image/jpeg", 415, "NATIVE_FILE_CONTENT_TYPE_MISMATCH",
                 id="test_fake_mime_415"),
    pytest.param(lambda: b"this is definitely not an image " * 4,
                 {"filename": "x.png", "content_type": "image/png",
                  "purpose": "micro_lesson_question_image"},
                 "image/png", 415, "NATIVE_FILE_CONTENT_INVALID",
                 id="test_not_an_image_415"),
    pytest.param(lambda: png_bytes(6000, 4000),  # 2400 万像素(纯色压缩后字节仍小)
                 {"filename": "huge.png", "content_type": "image/png",
                  "purpose": "micro_lesson_question_image"},
                 "image/png", 413, "NATIVE_QUESTION_IMAGE_PIXELS_EXCEEDED",
                 id="test_pixels_exceeded_413"),
])
def test_invalid_image_payloads_rejected(api, make_payload, upload_body, put_type,
                                         status, code):
    """图片安全三例:假 MIME / 非图片字节 / 超像素,各自错误码(新路径逐条)。"""
    base, _ = api
    payload = make_payload()
    created = post(base, NEW_UPLOAD, {**upload_body, "size_bytes": len(payload)},
                   status=201)
    response = put(base, NEW_CONTENT.format(file_id=created.json()["file_id"]),
                   payload, put_type, status=status)
    assert response.json()["error"]["code"] == code


def test_decompression_bomb_rejected_before_decode(tmp_path):
    """解压炸弹防护窗(审查 P2):header 像素超限在 load() 全量解码**之前**拒绝。

    构造数 MB 压缩体、3 亿+像素声明的 PNG——旧顺序会先 load() 放大出 GB 级
    内存分配再拒绝;新顺序从 header 直读拒绝,Pillow 解码器级上限双保险同值。
    """
    service = FileService(tmp_path / "f")
    buffer = io.BytesIO()
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
    put(base, NEW_CONTENT.format(file_id=file_id), payload, "image/png", status=200)
    first = post(base, NEW_COMPLETE, {"file_id": file_id}, status=200)
    second = post(base, NEW_COMPLETE, {"file_id": file_id}, status=200)  # 重调不报错
    assert first.json() == second.json() == {"file_id": file_id, "status": "uploaded"}


def test_checksum_happy_path_and_webp(api):
    """带 checksum 的正常路径 + webp 白名单成员 + 落盘扩展名按实际 MIME。"""
    base, tmp_path = api
    payload = png_bytes(fmt="WEBP")
    created = post(base, NEW_UPLOAD,
                   {"filename": "x.webp", "content_type": "image/webp",
                    "size_bytes": len(payload),
                    "purpose": "micro_lesson_question_image",
                    "checksum_sha256": hashlib.sha256(payload).hexdigest()}, status=201)
    file_id = created.json()["file_id"]
    put_response = put(base, NEW_CONTENT.format(file_id=file_id), payload,
                       "image/webp", status=200)
    assert put_response.json()["status"] == "uploaded"
    saved = list((tmp_path / "files").glob(f"{file_id}.*"))
    assert saved[0].suffix == ".webp"


# ---------- 老路径 download-url / preview-url(files.md §7) ----------

def test_legacy_upload_missing_fields_422(api):
    """老路径 upload-url 缺必填 → 422(与现实现同一 service 校验,不假设字段顺序)。"""
    base, _ = api
    response = post(base, LEGACY_UPLOAD, {"filename": "x.png"}, status=422)
    assert response.json()["error"]["code"] is None
    assert response.json()["error"]["message"]  # 必填缺失有中文说明


def test_legacy_download_url_shape(api):
    """老路径 download-url 返回老文档 §7 字段形状(requires_authorization/url_expires_at/
    delivery_mode = authenticated_api_content_proxy,不发明字段)。"""
    base, tmp_path = api
    file_id = _uploaded(base, tmp_path)
    body = get(base, f"/api/openapi/v1/files/{file_id}/download-url").json()
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
    body = get(base, f"/api/openapi/v1/files/{file_id}/preview-url").json()
    assert body["file_id"] == file_id
    path = f"/api/files/{file_id}/content"
    assert body["preview_url"] == path and body["download_url"] == path
    assert body["preview_mode"] == "inline_file" and body["method"] == "GET"
    assert body["requires_authorization"] is True
    assert body["head_supported"] is False
    assert body["cache_control"] == "private, no-store"


@pytest.mark.parametrize("file_id", ["pending-upload", "file_nope"],
                         ids=["test_legacy_download_url_not_ready_404",
                              "test_legacy_download_url_missing_404"])
def test_legacy_download_url_not_ready_or_missing_404(api, file_id):
    """老路径 download-url:已申请未上传 / 不存在 file_id → 404 FILE_NOT_READY。"""
    base, _ = api
    if file_id == "pending-upload":  # 已申请未上传
        created = post(base, LEGACY_UPLOAD,
                       {"filename": "x.png", "content_type": "image/png",
                        "size_bytes": 10,
                        "purpose": "micro_lesson_question_image"}, status=201)
        file_id = created.json()["file_id"]
    response = get(base, f"/api/openapi/v1/files/{file_id}/download-url", status=404)
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
    response = post(base, "/api/auth/logout", {}, status=200)
    assert response.json() == {"ok": True}


def test_logout_idempotent_without_token(api):
    """logout 无 Bearer 也返回 ok(老系统 logout 幂等,无会话仍成功)。"""
    base, _ = api
    _assert_local_base(base)
    response = httpx.post(f"{base}/api/auth/logout", json={}, timeout=5.0, trust_env=False)
    assert response.status_code == 200
    assert response.json() == {"ok": True}
