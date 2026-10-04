"""评测共享契约面:Subject 协议 + 失败分类 + Canonical 结果行 + identity 比对面。

execution machinery(EvalRunner:ThreadPoolExecutor 并发、per-case checkpoint 调度、
resume/strict-resume-gate 执行侧、manifest/failures 台账写入)已删(#521 I6-C C4,
Net Deletion §9):执行 owner = inspect_adapter(inspect-ai),本模块只剩两路共用的
契约本体——Subject 协议、EnvironmentFailure/ResumeMismatch 分类、
execute_subject_case/isolated_call/result_row(失败 taxonomy 唯一实现)、
safe_case_id(#450)、_identity_resume_diffs(strict identity 全等比较)、
atomic_write_json。Subject 实现不感知 gateway 之外的世界——桩在协议上,不在代码里。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

_UNSAFE_ID = re.compile(r"[^A-Za-z0-9._-]")
# 结果文件名字节预算(#450):stem + ".json.tmp"(atomic_write_json 临时名)≤ 255B
# ——ext4/APFS 单文件名上限;旧 [:80] 字符截断即此预算的最保守近似。
_SAFE_ID_MAX_BYTES = 240


class EnvironmentFailure(Exception):
    """环境失败(网络/凭据/服务不可用):不进程内重跑整案,落 environment 状态由续跑补跑。

    模型调用可靠性只归 Gateway(其内部已穷尽 retry+fallback);执行层再整案重跑 = 可靠性叠加。
    其他异常一律按内容失败入台账,不重试——重跑改变不了内容缺陷。
    """


class ResumeMismatch(Exception):
    """续跑目录与当前数据集/配置/被测对象不一致:换新目录,不带病续跑。"""


class Subject(Protocol):
    """被测对象:M1 是老系统适配器(open→refresh→messages→confirm),M2 是内核三函数。"""

    name: str

    def run_case(self, case: dict) -> dict:
        """执行单条用例,返回对话记录(judge 输入,runner 不解读只落盘)。

        环境问题抛 EnvironmentFailure;内容缺陷抛其他异常或返回带缺陷标记的记录。
        """
        ...


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def isolated_call(action, on_error):
    """受控异常边界(#521 I5:BLE001 豁免的单一落点,Inspect adapter 全程复用)。

    Subject 内容失败分类与 grader 失败隔离都需要「捕获 Exception 后不重抛、转成
    记录」——此类捕获全仓只允许出现在本函数一处(豁免预算 1/10,#521 I5 起
    Inspect 路径复用同一边界,不再新增豁免点)。on_error 收到原始异常,
    自行分类(environment / content / grader_failed)。KeyboardInterrupt、SystemExit
    不是 Exception,照常穿透。"""
    try:
        return action()
    except Exception as exc:  # noqa: BLE001 未知异常按内容失败/评分失败入台账,不中断过夜批次(豁免预算 1/10,全仓单点)
        return on_error(exc)


def result_row(case_id: str, status: str, attempts: int, started: float,
               *, error: str | None = None, transcript: dict | None = None) -> dict:
    """Canonical 七字段结果行(合同 §4;原 EvalRunner._result 收为模块级)。"""
    return {
        "case_id": case_id,
        "status": status,
        "attempts": attempts,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "finished_at": now_iso(),
        "error": error,
        "transcript": transcript,
    }


def execute_subject_case(subject: Subject, case: dict, case_id: str, ledger) -> tuple[dict, bool]:
    """执行单个 case 并按 Canonical 三态分类(#521 I5:失败 taxonomy 的唯一实现,
    inspect_adapter 执行路径复用)。

    返回 (result, retryable):ok/content → sample 执行完成(retryable=False,content
    不进任何 retry,重跑改变不了内容缺陷);EnvironmentFailure → retryable=True
    (environment 可由 execution resume 重跑,进程内不自动重跑)。ledger 回调签名
    (case_id, kind, detail),由调用方接线写各自的 failures.jsonl(同形)。"""
    started = time.monotonic()

    def _failure(exc: BaseException) -> tuple[dict, bool]:
        if isinstance(exc, EnvironmentFailure):
            detail = str(exc)
            ledger(case_id, "environment", detail)
            return result_row(case_id, "environment", 1, started, error=detail), True
        detail = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-300:]}"
        ledger(case_id, "content", detail)
        return result_row(case_id, "content", 1, started, error=detail), False

    outcome = isolated_call(lambda: subject.run_case(case), _failure)
    if isinstance(outcome, tuple):
        return outcome
    return result_row(case_id, "ok", 1, started, transcript=outcome), False


def safe_case_id(raw: object, index: int) -> str:
    """case id → 结果文件名/结果行 case_id(文件系统安全)。

    #450(Phase A 2026-09-25 infra incident):原 [:80] 字符截断把 97 字符案
    (a64_target_v3_northwest_clarification_not_leakage)截断——结果行 case_id 与
    scenarios 键(原始 id)不一致,corpus_round 的 check_rows/judge_rows 查键
    KeyError 崩溃;同前缀不同案还会撞同一结果文件。现按 UTF-8 字节放宽到 240
    (现网 ID 全谱在内,含中文 80 字 = 240B 旧包络),超预算的病理长 ID 以
    前缀+内容哈希后缀保唯一——同 id 幂等(续跑按文件名找 checkpoint)。"""
    text = str(raw) if raw not in (None, "") else f"case-{index:04d}"
    safe = _UNSAFE_ID.sub("_", text)
    if len(safe.encode("utf-8")) <= _SAFE_ID_MAX_BYTES:
        return safe
    prefix = safe.encode("utf-8")[:_SAFE_ID_MAX_BYTES - 13].decode("utf-8", "ignore")
    return f"{prefix}-{hashlib.sha256(safe.encode('utf-8')).hexdigest()[:12]}"


def _identity_resume_diffs(stored: object, current: dict | None) -> list[str]:
    """strict 续跑的 identity 全等门(#490 M1):空列表 = 放行,非空 = 拒绝理由。

    stored 取 manifest.get("identity")(键缺席/null 均算缺失);current 取本次
    执行的 identity 参数。两边都必须存在且全等:current 缺失 fail closed、stored
    缺失覆盖旧 run 目录、stored 非对象按病态 manifest 拒绝而非崩溃(两个专项脚本
    现行此处 AttributeError)。差异按 新增(current-only)/缺失(stored-only)/值变
    三类枚举字段名,键序 sorted(键并集)——与 s2/d6d7 两个 _resume_gate 同键集。
    比较面归 edu-agent 不随 execution 迁移而迁移(#521 I0 表);执行侧消费方 =
    inspect_adapter._verify_resume_identity。
    """
    if current is None:
        return ["当前调用未传 identity(strict 模式要求显式身份)"]
    if stored is None:
        return ["stored identity 缺失(manifest 无 identity 键或为 null)"]
    if not isinstance(stored, dict):
        return [f"stored identity 非对象({type(stored).__name__}),manifest 病态"]
    if stored == current:
        return []
    diffs = []
    for key in sorted(set(stored) | set(current)):
        if key not in stored:
            diffs.append(f"新增字段 {key}")
        elif key not in current:
            diffs.append(f"缺失字段 {key}")
        elif stored[key] != current[key]:
            diffs.append(f"字段 {key} 值变")
    return diffs


def atomic_write_json(path: Path, payload: dict) -> None:
    """先写临时文件再替换:进程被杀不留半行,checkpoint 可信。"""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
