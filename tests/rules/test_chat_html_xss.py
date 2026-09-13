"""#221/#113 P2 回归钉:chat.html 数据不得直插 HTML sink(存储型 XSS)。

题库快照(bank.json)的题面/题号、fetch 错误消息、confirm 总结字段都是潜在注入面;
修法 = 渲染层唯一转义出口 escapeHtml(数据链不动)。浏览器渲染在 pytest 侧不可执行,
本钉做静态可达的最强形态:
①转义助手存在且字符表覆盖 & < > " '(载荷 <script>/<img onerror> 经转义后落 DOM
  只能是文本);
②逐 sink 断言插值全走 escapeHtml;
③扫**这一类** sink 而非"当前形状":innerHTML/outerHTML/insertAdjacentHTML/
  document.write 四族模板全进同一张网(#226 审查变异④:insertAdjacentHTML 曾漏);
④扫不到的形态(间接 sink = 变量赋值、嵌套 {} 插值)直接 raise 人工确认——
  与 UnknownCheck 同哲学,静默跳过 = 盲区(①~④ 收口后已实测抓变异④⑤⑥)。
"""

import re
from pathlib import Path

CHAT_HTML = (
    Path(__file__).resolve().parents[2] / "edu_agent" / "api" / "static" / "chat.html"
)

# 四族 HTML sink 的模板实参/赋值(跨行);捕获组 = 模板体。
SINK_TEMPLATE = re.compile(
    r"(?:\.innerHTML\s*=\s*|\.outerHTML\s*=\s*"
    r"|insertAdjacentHTML\(\s*[^,()]*,\s*|document\.write(?:ln)?\(\s*)`([^`]*)`"
)
# 同一族 sink 的出现点(含未被 SINK_TEMPLATE 捕获的形态,用于"扫不到即 raise")。
SINK_TOKEN = re.compile(
    r"\.innerHTML|\.outerHTML|insertAdjacentHTML|document\.write(?:ln)?"
)
# 模板中允许的未转义插值:静态标记常量(全大写)与其三元条件。
# 数据字段一律过 escapeHtml;新增插值不在此列即红。
STATIC_BADGE = re.compile(r"^q\.image \? BADGE_HAS_IMG : ''$")


def _src() -> str:
    return CHAT_HTML.read_text(encoding="utf-8")


def test_escape_helper_defined_with_full_char_class():
    src = _src()
    assert "function escapeHtml(" in src, "渲染层转义出口缺失(#113 P2)"
    # 字符类必须同时覆盖五类:实体表缺任何一类都是转义旁路(<script>/<img onerror> 复活)
    assert re.search(r"replace\(/\[&<>\"'\]/g", src), (
        "escapeHtml 字符类不全:必须 /[&<>\"']/g 且对应 &amp;&lt;&gt;&quot;&#39;"
    )
    for entity in ("&amp;", "&lt;", "&gt;", "&quot;", "&#39;"):
        assert entity in src, f"实体表缺 {entity}"


def test_question_list_sink_escaped():
    """题面/题号来自题库快照(存储型注入面):L111 两处插值必须过 escapeHtml。"""
    src = _src()
    assert "escapeHtml(q.text || q.id)" in src
    assert "escapeHtml(q.id)" in src
    assert re.search(r"innerHTML[^;]*\$\{q\.text", src) is None, "题面裸插值仍在"


def test_error_message_sink_escaped():
    """fetch 错误消息(可能回显服务端内容)必须过 escapeHtml。"""
    assert "escapeHtml(e.message)" in _src()


def test_summary_fields_escaped():
    """confirm 总结字段(mastery_status/learned/key_ideas,模型侧数据)必须全转义。"""
    src = _src()
    assert "escapeHtml(ls.mastery_status || '—')" in src
    assert "escapeHtml(ls.student_summary?.learned || '—')" in src
    assert "escapeHtml((ls.student_summary?.key_ideas || []).join(';') || '—')" in src
    assert re.search(r"innerHTML[^;]*\$\{ls\.", src) is None, "总结字段裸插值仍在"


def test_no_raw_data_interpolation_reaches_any_html_sink():
    """扫全部 sink 模板(四族):每个 ${} 插值要么过 escapeHtml,要么是静态标记常量;
    嵌套 {} 的插值不允许静默跳过——残留 `${` 即 raise(人工确认)。"""
    src = _src()
    blocks = SINK_TEMPLATE.findall(src)
    assert blocks, "未找到 sink 模板(测试口径失效?)"
    for block in blocks:
        for interp in re.findall(r"\$\{([^{}]*)\}", block):
            if "escapeHtml(" in interp or STATIC_BADGE.match(interp.strip()):
                continue
            raise AssertionError(f"HTML sink 模板存在未转义插值:${{{interp}}}(数据必须过 escapeHtml)")
        residual = re.sub(r"\$\{[^{}]*\}", "", block)
        assert "${" not in residual, (
            f"sink 模板存在嵌套插值(正则解析不了,静默跳过=盲区),需人工确认:{residual.strip()[:80]!r}"
        )


def test_no_unscannable_sink_shape():
    """间接 sink(.innerHTML = someVar / 静态常量实参等非模板形态)不允许静默放过:
    要么是被 SINK_TEMPLATE 扫到的模板,要么是 `= ''` 静态清空,否则 raise 人工确认。"""
    src = _src()
    covered = {m.start() for m in SINK_TEMPLATE.finditer(src)}
    for m in SINK_TOKEN.finditer(src):
        if m.start() in covered:
            continue
        tail = src[m.end():].lstrip()
        if tail.startswith("= ''"):  # 静态清空(无数据),安全
            continue
        raise AssertionError(
            f"HTML sink 出现静态网扫不到的形态({m.group(0)}…),不允许静默放过:"
            f"{src[m.start():m.start() + 60]!r}…——改为模板直写并过 escapeHtml,或人工确认后在此登记例外"
        )
