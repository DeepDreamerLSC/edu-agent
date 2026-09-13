"""#221/#113 P2 回归钉:chat.html 数据不得直插 innerHTML(存储型 XSS)。

题库快照(bank.json)的题面/题号、fetch 错误消息、confirm 总结字段都是潜在注入面;
修法 = 渲染层唯一转义出口 escapeHtml(数据链不动)。浏览器渲染在 pytest 侧不可执行,
本钉做静态可达的最强形态:①转义助手存在且字符表覆盖 & < > " '(载荷
<script>/<img onerror> 经转义后落 DOM 只能是文本);②逐 sink 断言插值全走
escapeHtml;③innerHTML 模板里不允许出现任何未转义的数据插值(唯一例外 =
静态标记常量,全大写,模板自有内容)。
"""

import re
from pathlib import Path

CHAT_HTML = (
    Path(__file__).resolve().parents[2] / "edu_agent" / "api" / "static" / "chat.html"
)

# innerHTML 模板中允许的未转义插值:静态标记常量(全大写)与其三元条件。
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


def test_no_raw_data_interpolation_reaches_any_innerhtml():
    """扫全部 innerHTML 模板:每个 ${} 插值要么过 escapeHtml,要么是静态标记常量。"""
    src = _src()
    blocks = re.findall(r"innerHTML\s*=\s*`([^`]*)`", src)
    assert blocks, "未找到 innerHTML 模板(测试口径失效?)"
    for block in blocks:
        for interp in re.findall(r"\$\{([^{}]*)\}", block):
            if "escapeHtml(" in interp or STATIC_BADGE.match(interp.strip()):
                continue
            raise AssertionError(f"innerHTML 模板存在未转义插值:${{{interp}}}(数据必须过 escapeHtml)")
