"""评测 runner 骨架(00 §8.2):被测对象抽象 + case 级 checkpoint + 失败分类台账。

过夜安全六需求:①每 case 一份结果文件即 checkpoint,续跑只补缺(环境失败可补跑,
内容失败不补);②环境/内容失败分开入台账;③并发上限;④环境失败指数退避;
⑤每轮一目录 + manifest(数据集版本/配置哈希/被测对象标识);⑥晨间摘要见 summary.py。
M1 实现(老系统适配器)与 M2 实现(内核三函数)只实现 Subject 协议,本模块不感知
gateway、老系统与真实模型——桩在协议上,不在代码里。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import uuid4

_UNSAFE_ID = re.compile(r"[^A-Za-z0-9._-]")


class EnvironmentFailure(Exception):
    """环境失败(网络/凭据/服务不可用):指数退避重试,可补跑。

    其他异常一律按内容失败入台账,不重试——重跑改变不了内容缺陷。
    """


class ResumeMismatch(Exception):
    """续跑目录与当前数据集/配置/被测对象不一致:换新目录,不带病续跑。"""


@dataclass(frozen=True)
class RunnerConfig:
    concurrency: int = 2
    env_retry_attempts: int = 3
    backoff_base_s: float = 0.5
    backoff_cap_s: float = 60.0


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


def safe_case_id(raw: object, index: int) -> str:
    text = str(raw) if raw not in (None, "") else f"case-{index:04d}"
    return _UNSAFE_ID.sub("_", text)[:80]


def atomic_write_json(path: Path, payload: dict) -> None:
    """先写临时文件再替换:进程被杀不留半行,checkpoint 可信。"""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


class EvalRunner:
    """一批用例一个 run 目录;同目录重入即续跑(只补缺与环境失败)。

    类名避开 runner 模块名:macOS 大小写不敏感文件系统下
    from edu_agent.evals import Runner 会被私有导入检查当作导入私有模块 runner.py。
    """

    def __init__(self, subject: Subject, config: RunnerConfig, runs_root: Path | str) -> None:
        self.subject = subject
        self.config = config
        self.runs_root = Path(runs_root)
        self._ledger_lock = threading.Lock()

    def run(self, dataset_path: Path | str, cases: list[dict],
            run_dir: Path | str | None = None) -> Path:
        dataset = Path(dataset_path)
        dataset_sha = sha256_bytes(dataset.read_bytes())
        config_sha = sha256_bytes(json.dumps(asdict(self.config), sort_keys=True).encode())
        target = self._run_dir(run_dir, dataset, dataset_sha, config_sha, len(cases))
        pending = [
            (case, safe_case_id(case.get("id", case.get("case_id")), index))
            for index, case in enumerate(cases)
        ]
        pending = [item for item in pending if self._needs_run(target, item[1])]
        results = target / "results"
        results.mkdir(exist_ok=True)
        with ThreadPoolExecutor(max_workers=self.config.concurrency) as pool:
            futures = [pool.submit(self._run_one, target, case, case_id) for case, case_id in pending]
            try:
                for future in as_completed(futures):
                    result = future.result()
                    atomic_write_json(results / f"{result['case_id']}.json", result)
            except KeyboardInterrupt:
                # Ctrl-C:取消未开始的用例再退出,已完成的 checkpoint 保留,晨间摘要可见未跑
                for future in futures:
                    future.cancel()
                raise
        return target

    def _run_dir(self, run_dir: Path | str | None, dataset: Path, dataset_sha: str,
                 config_sha: str, total: int) -> Path:
        if run_dir is not None:
            target = Path(run_dir)
            self._verify_resume(target, dataset_sha, config_sha)
            return target
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = self.runs_root / f"{dataset.stem}-{stamp}-{uuid4().hex[:4]}"
        target.mkdir(parents=True)
        atomic_write_json(target / "manifest.json", {
            "started_at": now_iso(),
            "dataset": {"name": dataset.name, "sha256": dataset_sha},
            "config": {**asdict(self.config), "sha256": config_sha},
            "subject": self.subject.name,
            "total_cases": total,
        })
        return target

    def _verify_resume(self, target: Path, dataset_sha: str, config_sha: str) -> None:
        try:
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise ResumeMismatch(f"{target} 不是可续跑的 run 目录(无 manifest)") from exc
        mismatches = []
        if manifest["dataset"]["sha256"] != dataset_sha:
            mismatches.append("数据集版本")
        if manifest["config"]["sha256"] != config_sha:
            mismatches.append("配置哈希")
        if manifest["subject"] != self.subject.name:
            mismatches.append("被测对象标识")
        if mismatches:
            raise ResumeMismatch(f"{target} 的 {'/'.join(mismatches)} 与当前不一致,请新开 run 目录")

    def _needs_run(self, target: Path, case_id: str) -> bool:
        path = target / "results" / f"{case_id}.json"
        if not path.is_file():
            return True
        status = json.loads(path.read_text(encoding="utf-8"))["status"]
        return status == "environment"  # 内容失败不补跑,环境失败可补跑

    def _run_one(self, target: Path, case: dict, case_id: str) -> dict:
        started = time.monotonic()
        attempts = 0
        while True:
            attempts += 1
            try:
                transcript = self.subject.run_case(case)
            except EnvironmentFailure as exc:
                self._ledger(target, case_id, "environment", attempts, str(exc))
                if attempts <= self.config.env_retry_attempts:
                    delay = min(self.config.backoff_base_s * 2 ** (attempts - 1),
                                self.config.backoff_cap_s)
                    time.sleep(delay)
                    continue
                return self._result(case_id, "environment", attempts, started, error=str(exc))
            except Exception as exc:  # noqa: BLE001 未知异常按内容失败入台账,不中断过夜批次(豁免预算 1/10)
                detail = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-300:]}"
                self._ledger(target, case_id, "content", attempts, detail)
                return self._result(case_id, "content", attempts, started, error=detail)
            return self._result(case_id, "ok", attempts, started, transcript=transcript)

    def _result(self, case_id: str, status: str, attempts: int, started: float,
                *, error: str | None = None, transcript: dict | None = None) -> dict:
        return {
            "case_id": case_id,
            "status": status,
            "attempts": attempts,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "finished_at": now_iso(),
            "error": error,
            "transcript": transcript,
        }

    def _ledger(self, target: Path, case_id: str, kind: str, attempt: int, detail: str) -> None:
        line = json.dumps({"ts": now_iso(), "case_id": case_id, "kind": kind,
                           "attempt": attempt, "detail": detail[:500]}, ensure_ascii=False)
        with self._ledger_lock:
            with (target / "failures.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
