"""/api/files/** 三步上传合同(老系统 files API;#34 规格):全流程、逐错误码、
图片安全三例(伪造 MIME/超大像素/非图片字节)、幂等、未传就 complete。

图片全部 PIL 现场生成;HTTP 面含 PUT 二进制与 GET 图片字节(Content-Type 核对);
SSRF 边界:测试只打 127.0.0.1 环回上的本地测试服务器(显式断言)。
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
from test_api_service import ScriptedKernel


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


AUTH = {"Authorization": "Bearer student-token"}


def _post(base, path, payload, status=200):
    _assert_loopback(base)
    response = httpx.post(f"{base}{path}", json=payload, headers=AUTH, timeout=5.0,
                          trust_env=False)
    assert response.status_code == status, response.text
    return response


def _put(base, file_id, payload, content_type="image/png", status=200):
    _assert_loopback(base)
    response = httpx.put(f"{base}/api/files/{file_id}/content", content=payload,
                         headers={**AUTH, "Content-Type": content_type},
                         timeout=10.0, trust_env=False)
    assert response.status_code == status, response.text
    return response


def _get(base, file_id):
    _assert_loopback(base)
    return httpx.get(f"{base}/api/files/{file_id}/content", headers=AUTH,
                     timeout=5.0, trust_env=False)


def _request_upload(base, size=None, purpose="micro_lesson_question_image",
                    content_type="image/png", checksum=None):
    payload, _ = png_bytes()
    body = {"filename": "question.png", "content_type": content_type,
            "size_bytes": size if size is not None else len(payload),
            "purpose": purpose}
    if checksum:
        body["checksum_sha256"] = checksum
    return _post(base, "/api/files/upload-request", body, status=201), payload


# ---------- 全流程 ----------

def test_full_flow_upload_put_complete_get(api):
    base, tmp_path = api
    created, payload = _request_upload(base)
    file_id = created.json()["file_id"]
    assert created.json()["upload_method"] == "PUT"
    assert created.json()["upload_url"] == f"/api/files/{file_id}/content"
    assert created.json()["headers"] == {"Content-Type": "image/png"}

    put = _put(base, file_id, payload)
    assert put.json() == {"file_id": file_id, "status": "uploaded"}

    complete = _post(base, "/api/files/complete", {"file_id": file_id})
    assert complete.json() == {"file_id": file_id, "status": "uploaded"}

    got = _get(base, file_id)
    assert got.status_code == 200
    assert got.headers["content-type"] == "image/png"
    stored = Image.open(io.BytesIO(got.content))  # 返回的是合法图片字节
    assert stored.size == (64, 64)
    # 本地磁盘落盘:file_id 命名,ext 按实际 MIME(不用用户 filename)
    saved = list((tmp_path / "files").glob(f"{file_id}.*"))
    assert len(saved) == 1 and saved[0].suffix == ".png"


def test_resize_large_image_to_1280(api):
    """超大尺寸(未超像素上限)→ 服务端 resize 至 1280×1280 内(视觉编码时间压缩)。"""
    base, _ = api
    payload, _ = png_bytes(2000, 1000)
    created = _post(base, "/api/files/upload-request",
                    {"filename": "big.png", "content_type": "image/png",
                     "size_bytes": len(payload),
                     "purpose": "micro_lesson_question_image"}, status=201)
    file_id = created.json()["file_id"]
    _put(base, file_id, payload)
    got = _get(base, file_id)
    stored = Image.open(io.BytesIO(got.content))
    assert stored.size == (1280, 640)  # 等比缩到宽 1280


# ---------- 错误码逐条 ----------

def test_unsupported_purpose_422(api):
    base, _ = api
    payload, _ = png_bytes()
    response = _post(base, "/api/files/upload-request",
                     {"filename": "x.png", "content_type": "image/png",
                      "size_bytes": len(payload), "purpose": "avatar"},
                     status=422)
    assert response.json()["error"]["code"] == "UNSUPPORTED_PURPOSE"


def test_too_large_413(api):
    base, _ = api
    response = _post(base, "/api/files/upload-request",
                     {"filename": "big.png", "content_type": "image/png",
                      "size_bytes": 21 * 1024 * 1024,
                      "purpose": "micro_lesson_question_image"}, status=413)
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_size_mismatch_409(api):
    base, _ = api
    created, payload = _request_upload(base, size=1024)  # 申请与实际不一致
    response = _put(base, created.json()["file_id"], payload, status=409)
    assert response.json()["error"]["code"] == "FILE_SIZE_MISMATCH"


def test_checksum_mismatch_409(api):
    base, _ = api
    created, payload = _request_upload(base, checksum="0" * 64)  # 合法 hex 但不符
    response = _put(base, created.json()["file_id"], payload, status=409)
    assert response.json()["error"]["code"] == "FILE_CHECKSUM_MISMATCH"


def test_complete_before_upload_409(api):
    base, _ = api
    created, _ = _request_upload(base)  # 只申请不上传
    response = _post(base, "/api/files/complete",
                     {"file_id": created.json()["file_id"]}, status=409)
    assert response.json()["error"]["code"] == "FILE_CONTENT_MISSING"


def test_get_not_ready_404(api):
    base, _ = api
    created, _ = _request_upload(base)  # 已申请未上传
    response = _get(base, created.json()["file_id"])
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FILE_NOT_READY"
    missing = _get(base, "file_nope")
    assert missing.json()["error"]["code"] == "FILE_NOT_READY"


# ---------- 图片安全三例 ----------

def test_fake_mime_415(api):
    """PNG 字节声明 image/jpeg → NATIVE_FILE_CONTENT_TYPE_MISMATCH。"""
    base, _ = api
    payload, _ = png_bytes()
    created = _post(base, "/api/files/upload-request",
                    {"filename": "x.png", "content_type": "image/jpeg",
                     "size_bytes": len(payload),
                     "purpose": "micro_lesson_student_solution_image"}, status=201)
    response = _put(base, created.json()["file_id"], payload,
                    content_type="image/jpeg", status=415)
    assert response.json()["error"]["code"] == "NATIVE_FILE_CONTENT_TYPE_MISMATCH"


def test_not_an_image_415(api):
    """非图片字节 → NATIVE_FILE_CONTENT_INVALID(PIL 解码失败)。"""
    base, _ = api
    payload = b"this is definitely not an image " * 4
    created = _post(base, "/api/files/upload-request",
                    {"filename": "x.png", "content_type": "image/png",
                     "size_bytes": len(payload),
                     "purpose": "micro_lesson_question_image"}, status=201)
    response = _put(base, created.json()["file_id"], payload, status=415)
    assert response.json()["error"]["code"] == "NATIVE_FILE_CONTENT_INVALID"


def test_pixels_exceeded_413(api):
    """解码后像素 > 2000 万 → NATIVE_QUESTION_IMAGE_PIXELS_EXCEEDED。"""
    base, _ = api
    payload, _ = png_bytes(6000, 4000)  # 2400 万像素(纯色压缩后字节仍小)
    created = _post(base, "/api/files/upload-request",
                    {"filename": "huge.png", "content_type": "image/png",
                     "size_bytes": len(payload),
                     "purpose": "micro_lesson_question_image"}, status=201)
    response = _put(base, created.json()["file_id"], payload, status=413)
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
    _put(base, file_id, payload)
    first = _post(base, "/api/files/complete", {"file_id": file_id})
    second = _post(base, "/api/files/complete", {"file_id": file_id})  # 重调不报错
    assert first.json() == second.json() == {"file_id": file_id, "status": "uploaded"}


def test_checksum_happy_path_and_webp(api):
    """带 checksum 的正常路径 + webp 白名单成员 + 落盘扩展名按实际 MIME。"""
    base, tmp_path = api
    payload, _ = png_bytes(fmt="WEBP", mime="image/webp")
    created = _post(base, "/api/files/upload-request",
                    {"filename": "x.webp", "content_type": "image/webp",
                     "size_bytes": len(payload),
                     "purpose": "micro_lesson_question_image",
                     "checksum_sha256": hashlib.sha256(payload).hexdigest()}, status=201)
    file_id = created.json()["file_id"]
    put = _put(base, file_id, payload, content_type="image/webp")
    assert put.json()["status"] == "uploaded"
    saved = list((tmp_path / "files").glob(f"{file_id}.*"))
    assert saved[0].suffix == ".webp"
