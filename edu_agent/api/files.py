"""/api/files/** 三步上传(老系统 files API 合同,看板 #34 规格;#48 同源语义)。

本地磁盘读写零外部存储(马尾梯):内存登记表 + {storage}/{file_id}.{ext} 落盘。
PIL 解码校验(jpeg/png/webp 白名单)+ 像素上限 + resize 至 1280×1280(压缩
视觉编码时间)。purpose 仅题图/作答图两个;错误码照老系统原文。
"""

from __future__ import annotations

import base64
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
Image.MAX_IMAGE_PIXELS = MAX_PIXELS  # 双保险(审查 P2):Pillow 解码器级上限对齐业务上限
RESIZE_MAX = (1280, 1280)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class FileRecord:
    __slots__ = ("file_id", "filename", "content_type", "size_bytes", "purpose",
                 "checksum_sha256", "status", "path")

    def __init__(self, **kwargs) -> None:
        for key in self.__slots__:
            setattr(self, key, kwargs.get(key))


class FileService:
    def __init__(self, storage_dir: Path | str | None = None,
                 records_store=None) -> None:
        """records_store:文件元数据持久化(M3 DB 存储,SqliteStore 的 files 三操作)。

        注入即落库(登记/内容就绪两个变更点写回,启动预载回内存——此前 records
        只在内存,进程重启后全部 file_id 404);未注入时行为与从前完全一致。"""
        self.storage = Path(storage_dir or os.environ.get("FILES_STORAGE_DIR", "data/files"))
        self.records: dict[str, FileRecord] = {}
        self._records_store = records_store
        if records_store is not None:
            for data in records_store.all_files():
                record = FileRecord(**data)
                self.records[str(record.file_id)] = record

    def _persist_record(self, record: FileRecord) -> None:
        """元数据写回(仅变更点调用;records_store 未注入即空操作)。"""
        if self._records_store is not None:
            self._records_store.put_file(
                str(record.file_id),
                {key: getattr(record, key) for key in FileRecord.__slots__})

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
        record = FileRecord(
            file_id=file_id, filename=filename, content_type=content_type,
            size_bytes=size_bytes, purpose=purpose,
            checksum_sha256=checksum if isinstance(checksum, str) else None,
            status="requested")
        self.records[file_id] = record
        self._persist_record(record)
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
        record.path = str(self._persist(file_id, payload, ext))
        record.status = "uploaded"
        self._persist_record(record)
        return {"file_id": file_id, "status": "uploaded"}

    def _validate_image(self, payload: bytes, declared_type: str) -> str:
        try:
            image = Image.open(io.BytesIO(payload))
        except Image.DecompressionBombError as error:
            # 双保险触发(解码器级上限=业务上限):同样归像素超限,不是内容无效
            raise ApiError(413, "NATIVE_QUESTION_IMAGE_PIXELS_EXCEEDED",
                           "像素超过 2000 万上限(解码器防护)") from error
        except Exception as error:
            raise ApiError(415, "NATIVE_FILE_CONTENT_INVALID",
                           "内容不是可解码的图片") from error
        # 解压炸弹防护窗(审查 P2):像素上限在 load() 全量解码**之前**判——
        # header 的 width/height 此时已可读;高压缩比大图先拒绝再解码。
        if image.width * image.height > MAX_PIXELS:
            raise ApiError(413, "NATIVE_QUESTION_IMAGE_PIXELS_EXCEEDED",
                           f"{image.width}×{image.height} 超过 2000 万像素上限")
        try:
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

    def data_url(self, file_id: str) -> str | None:
        """题图 file_id → data URL(内核 vision 的多模态输入);未就绪返回 None
        (空壳语义留给内核 fail-closed,不在此抛错)。"""
        record = self.records.get(file_id)
        if record is None or record.status != "uploaded" or record.path is None:
            return None
        payload = base64.b64encode(Path(record.path).read_bytes()).decode("ascii")
        return f"data:{record.content_type};base64,{payload}"

    # ---------- 5) download-url / preview-url(老系统 files API §7 字段形状) ----------

    def _content_path(self, file_id: str) -> str:
        """本地存储语义:下载/预览地址指向本服务鉴权 content 端点(等效 JSON)。
        record 必须已 uploaded,否则抛 FILE_NOT_READY(与 read_content 同准)。"""
        self._record_or_404(file_id)
        if self.records[file_id].status != "uploaded":
            raise ApiError(404, "FILE_NOT_READY", "文件不存在或尚未就绪")
        return f"/api/files/{file_id}/content"

    def download_url(self, file_id: str) -> dict:
        """GET /api/openapi/v1/files/{id}/download-url(老系统 files §7 字段形状)。

        本地存储:download_url 指向本服务鉴权 content 端点;requires_authorization=true、
        url_expires_at=null、delivery_mode=authenticated_api_content_proxy(老文档原生 App
        列)。文档未发明的字段不加;未就绪抛 404 FILE_NOT_READY。"""
        record = self._record_or_404(file_id)
        return {
            "file_id": record.file_id,
            "download_url": self._content_path(file_id),
            "requires_authorization": True,
            "headers": {},
            "url_expires_at": None,
            "delivery_mode": "authenticated_api_content_proxy",
        }

    def preview_url(self, file_id: str) -> dict:
        """GET /api/openapi/v1/files/{id}/preview-url(老系统 files §7 字段形状)。

        preview_url 与 download_url 同指鉴权 content 端点(图片场景预览=下载,本地语义);
        head_supported=false(老文档原生前端首版不开放 HEAD)。字段取自老系统
        FrontendFilePreviewUrlResponse 且为文档认可的核心子集,不发明。"""
        record = self._record_or_404(file_id)
        path = self._content_path(file_id)
        return {
            "file_id": record.file_id,
            "preview_url": path,
            "download_url": path,
            "preview_mode": "inline_file",
            "method": "GET",
            "headers": {},
            "url_expires_at": None,
            "requires_authorization": True,
            "range_supported": True,
            "head_supported": False,
            "cache_control": "private, no-store",
            "delivery_mode": "authenticated_api_content_proxy",
        }

    def _record_or_404(self, file_id: str) -> FileRecord:
        record = self.records.get(file_id)
        if record is None:
            raise ApiError(404, "FILE_NOT_READY", "文件不存在或尚未就绪")
        return record
