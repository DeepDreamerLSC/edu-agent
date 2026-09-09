"""评测报告对外视图(00 §8.4 C 线):单文件自包含 HTML——内联样式+表格+内联 SVG。

零外部依赖零框架;边界(人已定默认):不渲染 prompt 源文(只给效果与示例),
不做交互(筛选/下钻/曲线)。多版本设计:versions 按调优轮传入,单版本(基线)也成立。
"""

from __future__ import annotations

import html

from .judge import DIMENSIONS

DIM_LABELS = {"first_question": "首问质量", "socratic_followup": "追问引导",
              "grade_fit": "年级适配", "pacing": "节奏", "summary_mastery": "总结与掌握",
              "termination": "终止行为"}

_STYLE = """
body{font-family:system-ui,sans-serif;margin:2rem;color:#1a1a1a}
h1{font-size:1.4rem}h2{font-size:1.1rem;margin-top:2rem}
table{border-collapse:collapse;margin:.8rem 0}
th,td{border:1px solid #ccc;padding:.35rem .7rem;text-align:left;font-size:.9rem}
th{background:#f0f0f0}
.pass{color:#0a7a2f}.review{color:#a86a00}.fail{color:#b3261e}
.over-tolerance{background:#fde8e8;font-weight:bold}
dialogue td{vertical-align:top;padding:.3rem .6rem}
.meta{color:#555;font-size:.85rem}
"""


def _esc(text) -> str:
    return html.escape(str(text))


def _verdict_span(verdict: str) -> str:
    return f'<span class="{_esc(verdict)}">{_esc(verdict)}</span>'


def _dim_svg(dim_averages: dict[str, float], max_score: float) -> str:
    """六维均分的内联 SVG 横条(0-2 分制按维度归一)。"""
    bars, y = [], 0
    for dim in DIMENSIONS:
        value = dim_averages.get(dim, 0.0)
        width = round(180 * min(value / max_score, 1.0)) if max_score else 0
        bars.append(
            f'<text x="0" y="{y + 12}" font-size="11">{_esc(DIM_LABELS[dim])}</text>'
            f'<rect x="110" y="{y + 3}" width="{width}" height="12" fill="#3b6ea5"/>'
            f'<text x="{110 + width + 5}" y="{y + 12}" font-size="11">{value:.2f}</text>'
        )
        y += 18
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="300" height="{y}" '
            'role="img" aria-label="六维均分">' + "".join(bars) + "</svg>")


def _version_section(version: dict) -> str:
    label = _esc(version["label"])
    averages = version.get("dim_averages", {})
    note = _esc(version.get("note", ""))
    rows = "".join(
        f"<tr><td>{_esc(dim)}</td><td>{_esc(DIM_LABELS[dim])}</td>"
        f"<td>{averages.get(dim, 0):.2f}</td></tr>"
        for dim in DIMENSIONS
    )
    return (f'<section id="version-{label}"><h2>prompt 版本:{label}</h2>'
            + (f'<p class="meta">{note}</p>' if note else "")
            + _dim_svg(averages, version.get("dim_max", 2.0))
            + f'<table><tr><th>维度</th><th>含义</th><th>均分</th></tr>{rows}</table></section>')


def _scenario_table(versions: list[dict], baseline_label: str, tolerance: int) -> str:
    """逐场景分数表:列=各版本总分/verdict,对照基线差超容差的单元格标出。"""
    baseline = next(v for v in versions if v["label"] == baseline_label)
    case_ids = sorted({c for v in versions for c in v["cases"]})
    others = [v for v in versions if v["label"] != baseline_label]
    header = "".join(
        f'<th>{_esc(v["label"])} 总分</th><th>verdict</th>' for v in versions
    ) + ("" if not others else "<th>vs 基线</th>")
    rows = []
    for case_id in case_ids:
        cells = ""
        for v in versions:
            case = v["cases"].get(case_id)
            if case is None:
                cells += "<td>—</td><td>—</td>"
                continue
            cells += f"<td>{case['total']}</td><td>{_verdict_span(case['verdict'])}</td>"
        if others:
            diffs = []
            for v in others:
                current, base = v["cases"].get(case_id), baseline["cases"].get(case_id)
                if current and base:
                    diff = current["total"] - base["total"]
                    mark = ' class="over-tolerance"' if abs(diff) > tolerance else ""
                    diffs.append(f'<td{mark}>{diff:+d}</td>')
                else:
                    diffs.append("<td>—</td>")
            cells += "".join(diffs)
        rows.append(f"<tr><td>{_esc(case_id)}</td>{cells}</tr>")
    note = (f'<p class="meta">vs 基线 = 版本总分 − 基线「{_esc(baseline_label)}」;'
            f'容差 {_esc(tolerance)} 分(12 分制),超容差标红。</p>' if others else "")
    return (f'<section id="scenarios"><h2>逐场景分数(vs 基线)</h2>{note}'
            f'<table><tr><th>场景</th>{header}</tr>{"".join(rows)}</table></section>')


def _examples_section(examples: list[dict]) -> str:
    blocks = []
    for example in examples:
        rows = "".join(
            f'<tr><td style="white-space:nowrap">{_esc(role)}</td>'
            f'<td>{_esc(text)}</td></tr>'
            for role, text in example["messages"]
        )
        blocks.append(f'<h3>{_esc(example["title"])}</h3>'
                      f'<table class="dialogue">{rows}</table>')
    return ('<section id="examples"><h2>示例对话</h2>' + "".join(blocks) + "</section>")


def render_html(versions: list[dict], examples: list[dict], baseline_label: str,
                tolerance: int = 1) -> str:
    """渲染单文件自包含 HTML。

    versions: [{"label", "cases": {case_id: {total, verdict}}, "dim_averages",
                "dim_max"(默认 2.0), "note"(可选,如调优轮说明)}]
    examples: [{"title", "messages": [(role, text), ...]}]
    """
    if not versions:
        raise ValueError("versions 不能为空")
    if baseline_label not in {v["label"] for v in versions}:
        raise ValueError(f"baseline_label {baseline_label!r} 不在 versions 中")
    sections = "".join(_version_section(v) for v in versions)
    return (
        "<!doctype html><html lang=\"zh\"><head><meta charset=\"utf-8\">"
        "<title>小讲师评测报告</title><style>" + _STYLE + "</style></head><body>"
        "<h1>小讲师评测报告</h1>"
        '<p class="meta">单文件自包含视图:教学效果与示例;prompt 源文不在披露范围。</p>'
        + sections + _scenario_table(versions, baseline_label, tolerance)
        + _examples_section(examples)
        + "</body></html>"
    )
