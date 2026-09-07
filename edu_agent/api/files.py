"""/api/files/** 三步上传(老系统 files API 合同,看板 #34 规格;#48 同源语义)。

本地磁盘读写零外部存储(马尾梯):内存登记表 + {storage}/{file_id}.{ext} 落盘。
PIL 解码校验(jpeg/png/webp 白名单)+ 像素上限 + resize 至 1280×1280(压缩
视觉编码时间)。purpose 仅题图/作答图两个;错误码照老系统原文。
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import uuid
from pathlib import Path

from PIL import Image

from .service import ApiError

PURPOSES = frozenset({
    "micro_lesson_question_image",
    "micro_lesson_student_solution_image",
})
MIME_WHITELIST = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 20_000_000
RESIZE_MAX = (1280, 1280)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class FileRecord:
    __slots__ = ("file_id", "filename", "content_type", "size_bytes", "purpose",
                 "checksum_sha256", "status", "path")

    def __init__(self, **kwargs) -> None:
        for key in self.__slots__:
            setattr(self, key, kwargs.get(key))


class FileService:
    def __init__(self, storage_dir: Path | str | None = None) -> None:
        self.storage = Path(storage_dir or os.environ.get("FILES_STORAGE_DIR", "data/files"))
        self.records: dict[str, FileRecord] = {}

    # ---------- 1) upload-request ----------

    def upload_request(self, body: dict) -> dict:
        filename = str(body.get("filename") or "")
        if not 1 <= len(filename) <= 255:
            raise ApiError(422, None, "filename 长度须 1~255")
        content_type = str(body.get("content_type") or "")
        if not content_type:
            raise ApiError(422, None, "content_type 必填")
        size_bytes = body.get("size_bytes")
        if not isinstance(size_bytes, int) or size_bytes <= 0:
            raise ApiError(422, None, "size_bytes 必须为正整数")
        if size_bytes > MAX_BYTES:
            raise ApiError(413, "FILE_TOO_LARGE", "文件超过 20MB 上限")
        purpose = str(body.get("purpose") or "")
        if purpose not in PURPOSES:
            raise ApiError(422, "UNSUPPORTED_PURPOSE",
                           f"purpose 仅支持 {sorted(PURPOSES)}")
        checksum = body.get("checksum_sha256")
        if checksum is not None and (
                not isinstance(checksum, str) or not _SHA256_RE.fullmatch(checksum)):
            raise ApiError(422, None, "checksum_sha256 须为 64 位 hex")
        file_id = f"file_{uuid.uuid4().hex[:16]}"
        self.records[file_id] = FileRecord(
            file_id=file_id, filename=filename, content_type=content_type,
            size_bytes=size_bytes, purpose=purpose,
            checksum_sha256=checksum if isinstance(checksum, str) else None,
            status="requested")
        return {
            "file_id": file_id,
            "upload_method": "PUT",
            "upload_url": f"/api/files/{file_id}/content",
            "headers": {"Content-Type": content_type},
        }

    # ---------- 2) PUT content ----------

    def store_content(self, file_id: str, payload: bytes) -> dict:
        record = self._record_or_404(file_id)
        if len(payload) > MAX_BYTES:
            raise ApiError(413, "FILE_TOO_LARGE", "文件超过 20MB 上限")
        if len(payload) != record.size_bytes:
            raise ApiError(409, "FILE_SIZE_MISMATCH",
                           f"上传 {len(payload)} 字节 ≠ 申请 {record.size_bytes}")
        if record.checksum_sha256:
            actual = hashlib.sha256(payload).hexdigest()
            if actual != record.checksum_sha256:
                raise ApiError(409, "FILE_CHECKSUM_MISMATCH", "内容哈希与申请不一致")
        ext = self._validate_image(payload, record.content_type)
        record.path = self._persist(file_id, payload, ext)
        record.status = "uploaded"
        return {"file_id": file_id, "status": "uploaded"}

    def _validate_image(self, payload: bytes, declared_type: str) -> str:
        try:
            image = Image.open(io.BytesIO(payload))
            image.load()
        except Exception as error:
            raise ApiError(415, "NATIVE_FILE_CONTENT_INVALID",
                           "内容不是可解码的图片") from error
        actual_mime = Image.MIME.get(image.format)
        ext = MIME_WHITELIST.get(actual_mime or "")
        if ext is None:
            raise ApiError(415, "NATIVE_FILE_CONTENT_INVALID",
                           f"仅支持 {sorted(MIME_WHITELIST)}")
        if actual_mime != declared_type:
            raise ApiError(415, "NATIVE_FILE_CONTENT_TYPE_MISMATCH",
                           f"实际 {actual_mime} ≠ 声明 {declared_type}")
        if image.width * image.height > MAX_PIXELS:
            raise ApiError(413, "NATIVE_QUESTION_IMAGE_PIXELS_EXCEEDED",
                           f"{image.width}×{image.height} 超过 2000 万像素上限")
        return ext

    def _persist(self, file_id: str, payload: bytes, ext: str) -> Path:
        self.storage.mkdir(parents=True, exist_ok=True)
        target = self.storage / f"{file_id}.{ext}"
        # resize 至 1280×1280 内(等比;视觉编码时间压缩,看板 vision 冒烟)
        image = Image.open(io.BytesIO(payload))
        image.thumbnail(RESIZE_MAX)
        buffer = io.BytesIO()
        image.save(buffer, format=image.format)
        target.write_bytes(buffer.getvalue())
        return target

    # ---------- 3) complete ----------

    def complete(self, body: dict) -> dict:
        file_id = str(body.get("file_id") or "")
        record = self._record_or_404(file_id)
        if record.status == "requested":
            raise ApiError(409, "FILE_CONTENT_MISSING", "尚未上传内容,先 PUT /content")
        return {"file_id": file_id, "status": "uploaded"}  # uploaded 幂等重调

    # ---------- 4) GET content ----------

    def read_content(self, file_id: str) -> tuple[bytes, str]:
        record = self._record_or_404(file_id)
        if record.status != "uploaded" or record.path is None:
            raise ApiError(404, "FILE_NOT_READY", "文件不存在或尚未就绪")
        return Path(record.path).read_bytes(), record.content_type

    def _record_or_404(self, file_id: str) -> FileRecord:
        record = self.records.get(file_id)
        if record is None:
            raise ApiError(404, "FILE_NOT_READY", "文件不存在或尚未就绪")
        return record
