#!/usr/bin/env python3
"""复杂度预算检查器(02 §2、§11)。

统计 docs/plan/02-complexity-budget.md 第 2 节表的全部指标,超限非零退出;
并按 02 §11.4 校验第 2 节、2.1 节表格数字与本文件常量、pyproject.toml 的一致性:
表格解析不到某项按不一致处理,不允许静默跳过。只依赖标准库。
"""

import argparse
import os
import re
import sys
import tomllib
import tokenize
from dataclasses import dataclass
from pathlib import Path

# ---- 02 §2 表的预算常量(文档是唯一事实源;改数字必须同步改文档并走 structural 人批)----
LIMIT_APP_TOTAL_LINES = 30_000
LIMIT_SINGLE_FILE_LINES = 800
LIMIT_TOP_LEVEL_PACKAGES = 6
LIMIT_RUNTIME_DEPS = 15
LIMIT_CONFIG_FILES = 5
LIMIT_TEST_RATIO = 1.0
LIMIT_DEPLOY_SCRIPT_LINES = 100
LIMIT_SUPPRESSIONS = 10

# 02 §6:测试/应用行数比**永久只报告不阻塞**(2026-09-11 人裁:分子可被"搬 helper 进
# tests/fixtures/"刷低,属可刷代理指标;给可刷指标设门会重演 #142。原"M2 起翻 True"计划已撤)。
TEST_RATIO_BLOCKS = False
STRICT_RATIO_ENV = "BUDGET_STRICT_TEST_RATIO"

# ---- 02 §2.1 表的 ruff 阈值常量(与 pyproject.toml [tool.ruff] 由本脚本双向校验)----
RUFF_MAX_STATEMENTS = 50
RUFF_MAX_COMPLEXITY = 12
RUFF_MAX_BRANCHES = 12
RUFF_MAX_RETURNS = 6
RUFF_MAX_ARGS = 6
RUFF_REQUIRED_CODES = (
    "PLR0915", "C901", "PLR0912", "PLR0911", "PLR0913",
    "S102", "S307", "S602", "S605", "S301",
    "E722", "BLE001", "TRY400", "PLW0603", "RUF006", "B",
)

DOC_REL_PATH = Path("docs/plan/02-complexity-budget.md")
SKIP_DIRS = frozenset({
    ".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
    "node_modules", "build", "dist", "var",  # var=部署台账/评测本地产物(04 §2.1),非源码
})

NOQA_RE = re.compile(r"#\s*noqa\b")
TYPE_IGNORE_RE = re.compile(r"#\s*type:\s*ignore")
RULE_CODE_RE = re.compile(r"\b[A-Z]{1,4}\d{3,4}\b")


@dataclass
class Metric:
    """一条预算指标的测量结果。"""

    metric_id: str
    detail: str
    ok: bool
    blocking: bool = True


# ---------- 文件与行数 ----------


def iter_python_files(root: Path):
    """仓库内全部 *.py,跳过 .git/.venv 等非源码目录。

    一级目录(var/ 等本地产物)按相对路径判——绝对路径可能穿过系统的
    /private/var(macOS tmp),parts 全量匹配会误杀。"""
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).parts
        if rel[0] in SKIP_DIRS or SKIP_DIRS.intersection(rel[1:]):
            continue
        yield path


def code_lines(path: Path) -> int:
    """非空且非注释行数(02 §2:行数只统计 *.py,不含空行与注释)。"""
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            count += 1
    return count


def is_under(path: Path, root: Path, *parts: str) -> bool:
    """path 是否位于 root/parts 目录之下。"""
    try:
        path.relative_to(root.joinpath(*parts))
    except ValueError:
        return False
    return True


def load_toml(path: Path):
    """读取 toml,文件不存在返回 None。"""
    if not path.is_file():
        return None
    return tomllib.loads(path.read_text(encoding="utf-8"))


# ---------- 各指标测量 ----------


def app_total_lines(root: Path, py_files: list) -> int:
    return sum(code_lines(p) for p in py_files if is_under(p, root, "edu_agent"))


def max_single_file_lines(py_files: list) -> tuple[int, str]:
    """仓库内最大的单文件非空非注释行数及其路径(00 §10:文件上限 800 行)。"""
    best, name = 0, "-"
    for path in py_files:
        current = code_lines(path)
        if current > best:
            best, name = current, str(path)
    return best, name


def top_level_packages(root: Path) -> list[str]:
    """edu_agent/ 下一级目录(02 §2:顶层包)。"""
    base = root / "edu_agent"
    if not base.is_dir():
        return []
    return sorted(d.name for d in base.iterdir() if d.is_dir() and d.name not in SKIP_DIRS)


def runtime_deps(root: Path) -> int:
    """pyproject.toml [project] dependencies 数量(02 §2)。"""
    data = load_toml(root / "pyproject.toml")
    if data is None:
        return 0
    return len(data.get("project", {}).get("dependencies", []))


def config_file_count(root: Path) -> int:
    """configs/ 下文件数量(02 §2)。"""
    base = root / "configs"
    if not base.is_dir():
        return 0
    return sum(
        1
        for path in base.rglob("*")
        if path.is_file() and not SKIP_DIRS.intersection(path.relative_to(root).parts)
    )  # 相对路径匹配:/private/var 系统路径不算仓库目录(同 iter_python_files)


def deploy_script_lines(root: Path) -> tuple[int, list[str]]:
    """scripts/deploy*.sh 总行数(02 §2、04 §2.1);无部署脚本时为 0,通过。"""
    base = root / "scripts"
    names = sorted(base.glob("deploy*.sh")) if base.is_dir() else []
    total = sum(len(p.read_text(encoding="utf-8").splitlines()) for p in names)
    return total, [p.name for p in names]


def scripts_total_lines(root: Path, py_files: list) -> int:
    """scripts/ 下 *.py 总行数(非空非注释,同 §2 计法)。

    02 §2 预算只覆盖 edu_agent 包;scripts/*.py 是工具面(进仓的评测工具等),
    只登记不设限——2026-09-10 PR #154 审查观察 1:工具行数对预算不可见,至少要可见。
    """
    return sum(code_lines(p) for p in py_files if is_under(p, root, "scripts"))


def test_lines(root: Path, py_files: list) -> int:
    """tests/ 行数,分子不含 tests/rules/ 与 tests/fixtures/(02 §6)。"""
    total = 0
    for path in py_files:
        in_tests = is_under(path, root, "tests")
        excluded = is_under(path, root, "tests", "rules") or is_under(path, root, "tests", "fixtures")
        if in_tests and not excluded:
            total += code_lines(path)
    return total


def count_comment_suppressions(path: Path) -> int:
    """单个文件里 # noqa / # type: ignore 注释数(按注释词元计数,字符串不算)。"""
    count = 0
    with path.open(encoding="utf-8") as handle:
        try:
            for token in tokenize.generate_tokens(handle.readline):
                if token.type != tokenize.COMMENT:
                    continue
                if NOQA_RE.search(token.string) or TYPE_IGNORE_RE.search(token.string):
                    count += 1
        except tokenize.TokenError:
            # 语法损坏的文件由 ruff 关卡负责;这里只统计已解析到的部分。
            pass
    return count


def pyproject_suppressions(root: Path) -> int:
    """per-file-ignores 条目数与 [tool.ruff] exclude 条目数(02 §11.3)。"""
    data = load_toml(root / "pyproject.toml")
    if data is None:
        return 0
    ruff = data.get("tool", {}).get("ruff", {})
    lint = ruff.get("lint", {})
    count = len(ruff.get("exclude", [])) + len(lint.get("exclude", []))
    for codes in lint.get("per-file-ignores", {}).values():
        count += 1 if isinstance(codes, str) else len(codes)
    return count


def test_ratio_metric(root: Path, py_files: list, total_app: int) -> Metric:
    blocking = TEST_RATIO_BLOCKS or os.environ.get(STRICT_RATIO_ENV) == "1"
    numerator = test_lines(root, py_files)
    if total_app == 0:
        detail = "分子 0 / 分母 0(尚无应用代码,不计比值;上限 ≤ 1.0)"
        return Metric("test-ratio", detail, True, blocking=blocking)
    ratio = numerator / total_app
    detail = f"分子 {numerator} / 分母 {total_app} = {ratio:.2f}(上限 ≤ {LIMIT_TEST_RATIO})"
    return Metric("test-ratio", detail, ratio <= LIMIT_TEST_RATIO, blocking=blocking)


def collect_metrics(root: Path) -> list[Metric]:
    py_files = list(iter_python_files(root))
    total_app = app_total_lines(root, py_files)
    single_max, single_name = max_single_file_lines(py_files)
    packages = top_level_packages(root)
    deps = runtime_deps(root)
    configs = config_file_count(root)
    deploy_total, deploy_names = deploy_script_lines(root)
    scripts_total = scripts_total_lines(root, py_files)
    suppressions = sum(count_comment_suppressions(p) for p in py_files) + pyproject_suppressions(root)
    return [
        Metric("app-total-lines", f"{total_app} / {LIMIT_APP_TOTAL_LINES}", total_app <= LIMIT_APP_TOTAL_LINES),
        Metric(
            "single-file-lines",
            f"{single_max} / {LIMIT_SINGLE_FILE_LINES}({single_name})",
            single_max <= LIMIT_SINGLE_FILE_LINES,
        ),
        Metric(
            "top-level-packages",
            f"{len(packages)} / {LIMIT_TOP_LEVEL_PACKAGES}({', '.join(packages) or '无'})",
            len(packages) <= LIMIT_TOP_LEVEL_PACKAGES,
        ),
        Metric("runtime-deps", f"{deps} / {LIMIT_RUNTIME_DEPS}", deps <= LIMIT_RUNTIME_DEPS),
        Metric("config-files", f"{configs} / {LIMIT_CONFIG_FILES}", configs <= LIMIT_CONFIG_FILES),
        Metric(
            "deploy-script-lines",
            f"{deploy_total} / {LIMIT_DEPLOY_SCRIPT_LINES}({', '.join(deploy_names) or '无部署脚本'})",
            deploy_total <= LIMIT_DEPLOY_SCRIPT_LINES,
        ),
        Metric("suppressions", f"{suppressions} / {LIMIT_SUPPRESSIONS}", suppressions <= LIMIT_SUPPRESSIONS),
        test_ratio_metric(root, py_files, total_app),
        # 登记(非 02 §2 预算指标,永不阻塞):工具面行数可见性,#154 审查观察 1。
        Metric("scripts-total-lines", f"{scripts_total}(登记用,不设限)", True, blocking=False),
    ]


# ---------- 文档表格解析与一致性(02 §11.4) ----------

DOC2_ROWS = (
    # (指标 id, §2 表首列关键字, 本文件常量)
    ("app-total-lines", "应用代码总行数", LIMIT_APP_TOTAL_LINES),
    ("single-file-lines", "单文件非空非注释行", LIMIT_SINGLE_FILE_LINES),
    ("top-level-packages", "顶层包数量", LIMIT_TOP_LEVEL_PACKAGES),
    ("runtime-deps", "第三方运行时依赖", LIMIT_RUNTIME_DEPS),
    ("config-files", "配置文件数量", LIMIT_CONFIG_FILES),
    ("test-ratio", "行数比", LIMIT_TEST_RATIO),
    ("deploy-script-lines", "部署脚本行数", LIMIT_DEPLOY_SCRIPT_LINES),
    ("suppressions", "noqa", LIMIT_SUPPRESSIONS),
)

DOC21_THRESHOLD_ROWS = (
    # (§2.1 表行关键字, 规则代码, 本文件常量, pyproject 配置键)
    ("函数语句数", "PLR0915", RUFF_MAX_STATEMENTS, ("pylint", "max-statements")),
    ("圈复杂度", "C901", RUFF_MAX_COMPLEXITY, ("mccabe", "max-complexity")),
    ("分支数", "PLR0912", RUFF_MAX_BRANCHES, ("pylint", "max-branches")),
    ("返回数", "PLR0911", RUFF_MAX_RETURNS, ("pylint", "max-returns")),
    ("参数数", "PLR0913", RUFF_MAX_ARGS, ("pylint", "max-args")),
)

DOC21_FORBIDDEN_ROWS = (
    # (§2.1 表行关键字, 预期规则代码集合)
    ("危险调用", ("S102", "S307", "S602", "S605", "S301")),
    ("吞错", ("E722", "BLE001", "TRY400")),
    ("全局可变状态", ("PLW0603",)),
    ("野生协程", ("RUF006",)),
    ("bugbear", ("B",)),
)


def table_rows(doc_text: str) -> list[list[str]]:
    """Markdown 表格行,每行拆成去空白后的单元格。"""
    rows = []
    for line in doc_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) >= 3:
            rows.append(cells)
    return rows


def find_row(rows: list[list[str]], key: str) -> list[str] | None:
    """首列包含 key 的第一条表格行。"""
    for cells in rows:
        if key in cells[0]:
            return cells
    return None


def parse_number(text: str) -> int | float | None:
    """把 '30 000'、'≤ 1.0' 之类的表格值解析为数字,失败返回 None。"""
    cleaned = re.sub(r"[≤\s,,]", "", text)
    try:
        return int(cleaned)
    except ValueError:
        try:
            return float(cleaned)
        except ValueError:
            return None


def read_doc_rows(root: Path) -> tuple[list[list[str]], str | None]:
    """读取 02 文档表格;失败时返回空表与错误信息。"""
    doc_path = root / DOC_REL_PATH
    if not doc_path.is_file():
        return [], f"找不到 {DOC_REL_PATH}"
    return table_rows(doc_path.read_text(encoding="utf-8")), None


def check_doc_section2(root: Path) -> list[str]:
    """§2 表数字 vs 本文件常量;解析不到按不一致处理。"""
    rows, error = read_doc_rows(root)
    if error:
        return [f"doc-consistency: {error}"]
    errors = []
    for metric_id, key, expected in DOC2_ROWS:
        row = find_row(rows, key)
        if row is None:
            errors.append(f"doc-consistency({metric_id}): 表格解析不到指标'{key}'(按不一致处理)")
            continue
        value = parse_number(row[1])
        if value is None:
            errors.append(f"doc-consistency({metric_id}): 表格值'{row[1]}'不是数字")
        elif value != expected:
            errors.append(f"doc-consistency({metric_id}): 表格 {value} ≠ 常量 {expected}")
    return errors


def doc_threshold(row: list[str], code: str) -> int | float | None:
    """从 §2.1 阈值行提取指定规则代码的阈值。"""
    codes = [c.strip() for c in row[1].split("/")]
    values = [parse_number(v.strip()) for v in row[2].split("/")]
    if code not in codes:
        return None
    return values[codes.index(code)]


def doc_forbidden_codes(row: list[str]) -> set[str]:
    """从 §2.1 禁止/启用行提取规则代码集合。"""
    if row[1].strip() == "B":
        return {"B"}
    return set(RULE_CODE_RE.findall(row[1]))


def check_threshold_rows(rows: list[list[str]], lint: dict) -> list[str]:
    """§2.1 阈值行:表 vs 常量 vs pyproject 对应配置键。"""
    errors = []
    for key, code, expected, (section, option) in DOC21_THRESHOLD_ROWS:
        row = find_row(rows, key)
        if row is None:
            errors.append(f"ruff-consistency: 表格解析不到'{key}'(按不一致处理)")
            continue
        doc_value = doc_threshold(row, code)
        if doc_value is None:
            errors.append(f"ruff-consistency: 表格'{key}'解析不到 {code} 的阈值(按不一致处理)")
        elif doc_value != expected:
            errors.append(f"ruff-consistency: 表格'{key}' {code}={doc_value} ≠ 常量 {expected}")
        actual = lint.get(section, {}).get(option)
        if actual != expected:
            errors.append(
                f"ruff-consistency: pyproject [tool.ruff.lint.{section}] {option}={actual} ≠ {expected}(02 §2.1)"
            )
    return errors


def check_forbidden_rows(rows: list[list[str]], select: list) -> list[str]:
    """§2.1 禁止/启用行:表内规则代码必须在 pyproject select 中。"""
    errors = []
    for key, expected_codes in DOC21_FORBIDDEN_ROWS:
        row = find_row(rows, key)
        if row is None:
            errors.append(f"ruff-consistency: 表格解析不到'{key}'(按不一致处理)")
            continue
        doc_codes = doc_forbidden_codes(row)
        if doc_codes != set(expected_codes):
            errors.append(
                f"ruff-consistency: 表格'{key}'规则 {sorted(doc_codes)} ≠ 预期 {sorted(expected_codes)}"
            )
    missing = [code for code in RUFF_REQUIRED_CODES if code not in select]
    if missing:
        errors.append(f"ruff-consistency: pyproject select 缺少 {', '.join(missing)}")
    return errors


def check_ruff_consistency(root: Path) -> list[str]:
    """§2.1 表 vs 本文件常量 vs pyproject.toml [tool.ruff]。"""
    rows, error = read_doc_rows(root)
    if error:
        return [f"ruff-consistency: {error}"]
    data = load_toml(root / "pyproject.toml")
    if data is None:
        return ["ruff-consistency: 找不到 pyproject.toml"]
    lint = data.get("tool", {}).get("ruff", {}).get("lint", {})
    select = lint.get("select", [])
    errors = check_threshold_rows(rows, lint)
    errors += check_forbidden_rows(rows, select)
    return errors


# ---------- 输出与入口 ----------


def metric_line(metric: Metric) -> tuple[str, bool]:
    """一行输出与是否计入失败。非阻塞指标永远只报告(02 §6:测试比永久 report-only)。"""
    if metric.blocking:
        tag = "BUDGET-OK" if metric.ok else "BUDGET-FAIL"
        return f"{tag} {metric.metric_id}: {metric.detail}", not metric.ok
    status = "" if metric.ok else "(超限;永久只报告不阻塞——分子可搬运刷低,2026-09-11 人裁)"
    return f"BUDGET-REPORT {metric.metric_id}: {metric.detail} {status}".rstrip(), False


def run(root: Path) -> int:
    failures = 0
    print(f"== edu-agent 复杂度预算(docs/plan/02 §2)root={root} ==")
    for metric in collect_metrics(root):
        line, failed = metric_line(metric)
        print(line)
        failures += failed
    for error in check_doc_section2(root):
        print(f"BUDGET-FAIL {error}")
        failures += 1
    for error in check_ruff_consistency(root):
        print(f"BUDGET-FAIL {error}")
        failures += 1
    if failures:
        print(f"复杂度预算未通过:{failures} 项失败(02 §2,无豁免机制)")
        return 1
    print("复杂度预算通过(02 §2)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="仓库根目录(默认当前目录)")
    args = parser.parse_args()
    return run(Path(args.root).resolve())


if __name__ == "__main__":
    sys.exit(main())
