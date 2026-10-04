"""identity 指纹构造公共 helper(#490 §三 / M0 审计表第③项):文件/冻结件/git 三面。

两个原始消费者(s2_judge_battery 与已按 I6-C C2 处置矩阵退役的 d6d7 gold
运行器)在 M3 迁移前各持一份同构实现(_sha / rubric head sha / git rev-parse
内联块),本模块收口构造侧;
stored-vs-current 比较侧在 runner 的 strict identity 门(_identity_resume_diffs)。
本模块只做指纹构造,不知道 rubric/battery/cases 等领域资产语义——指纹选哪些
文件、进 identity 的哪个键,由调用方声明。git 面沿原始消费者口径 fail closed
(check=True):git 缺失/非仓库即抛 CalledProcessError,不静默降级 None
(corpus_round 的 None 兜底是其自身跑批政策,见 #490 §二不下沉清单)。
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def file_sha256(path: Path | str) -> str:
    """文件字节面 sha256(资产/配置指纹的基准口径)。"""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def head_sha256(path: Path | str) -> str:
    """冻结件 head -n -1 口径 sha:排除末行后全文 sha256。

    冻结件以末行承载冻结/版本标记,标记行改动不算内容漂移;其余任何字节变化
    都改变指纹 → 旧 run 随之拒绝续跑(identity 纪律的机械落点,不做字符串断言)。"""
    head = "".join(Path(path).read_text(encoding="utf-8").splitlines(keepends=True)[:-1])
    return hashlib.sha256(head.encode()).hexdigest()


def git_head_sha(repo: Path | str) -> str:
    """repo 工作树的 HEAD commit(git rev-parse;check=True fail closed)。"""
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True,
        text=True, check=True,
    ).stdout.strip()
