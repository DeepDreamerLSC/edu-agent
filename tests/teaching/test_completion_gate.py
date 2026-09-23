"""Trusted Completion Gate A 段(#414 设计件 v3.1 §一/§二/§三,零行为变化自证)。

断言即规格——六窄面确定性 verifier + CompletionEvidence 类型化事实 + 复合题
红线 + precision-first claim matching(v3.1 §三:value_match≠claim,不确定/
否定/多候选/猜测语境不发 evidence),全部经公开面 verify_completion 驱动
(02 §6:测试只导入公开入口):
  · 六窄面各带正/负案:numeric_with_unit(等价类归一/单位维度安全/省略仅
    schema 授权)、choice_letter、true_false、equation_form(×/·→`*` 绝不
    与变量 x 合并)、ratio_or_expression、short_text_exact(whole-answer
    exact/显式 alias,无编辑距离无裸 substring);
  · precision-first:审查 P1-2 实测违规案值逐字钉死(不确定表达六窄面、
    命中前否定、或/还是多候选、猜非声明、标点三变体、两处意外安全);
  · 复合题红线:多空/复合任何局部槽命中不得构造 CompletionEvidence;
  · 不可构造面:source 恒 student/verdict 恒 matched/answer_type 限六窄面
    (构造期即炸);turn-scoped:turn_id 记本轮,证据随轮重生成。
零模型、零接线(A 段不接 Kernel/generation,行为变化为零的测试面即本文件)。
"""

from __future__ import annotations

import pytest

from edu_agent.agents.small_lecturer import (
    ANSWER_TYPES,
    AnswerSpec,
    CompletionEvidence,
    EvidenceProvenance,
    verify_completion,
)

TURN = 4  # 任意轮号:证据必须原样携带(生命周期 turn-scoped)


def _verify(answer_type: str, ground_truth: str, message: str, **spec_kwargs):
    return verify_completion(
        AnswerSpec(answer_type=answer_type, ground_truth=ground_truth, **spec_kwargs),
        message, TURN)


# ---------- numeric_with_unit:等价类归一 + 单位判定 ----------


def test_numeric_exact_hit_carries_full_provenance():
    """原样命中:全部字段照设计 §二(source/turn_id/answer_type/verdict/
    verifier/provenance),归一空=原样。"""
    evidence = _verify("numeric_with_unit", "25.8度", "答案是25.8度")
    assert evidence is not None
    assert evidence.source == "student"
    assert evidence.turn_id == TURN
    assert evidence.answer_type == "numeric_with_unit"
    assert evidence.verdict == "matched"
    assert evidence.verifier == "numeric_with_unit"
    assert evidence.provenance.ground_truth_ref == "25.8度"
    assert evidence.provenance.matched_span == "25.8度"
    assert evidence.provenance.normalization == ()


def test_numeric_thousands_separator_equivalence():
    """千分位等价类:「1,000米」≡「1000米」,归一记录千分位。"""
    evidence = _verify("numeric_with_unit", "1000米", "我算出是1,000米")
    assert evidence is not None
    assert evidence.provenance.matched_span == "1,000米"
    assert evidence.provenance.normalization == ("千分位",)


def test_numeric_negative_thousands_separator_fullwidth():
    """负数+千分位+全半角:学生写「－1,000米」命中题面「-1000米」,
    归一按施加顺序记录(全半角、千分位)。"""
    evidence = _verify("numeric_with_unit", "-1000米", "－1,000米")
    assert evidence is not None
    assert evidence.provenance.matched_span == "－1,000米"
    assert evidence.provenance.normalization == ("全半角", "千分位")


def test_numeric_fraction_decimal_percent_equivalence():
    """分数/小数/百分号等价类(exact Fraction,非近似):「1/2米」≡「0.5米」、
    「0.5」≡「50%」。"""
    assert _verify("numeric_with_unit", "0.5米", "1/2米").provenance.normalization == ("分数形态",)
    assert _verify("numeric_with_unit", "50%", "0.5") is not None
    assert _verify("numeric_with_unit", "0.5", "50%").provenance.normalization == ("百分号",)


def test_numeric_unit_synonym_and_scale_conversion():
    """同义单位维度安全换算:m≡米(1:1)、千米↔米(×1000,exact Fraction);
    换算记入归一。"""
    assert _verify("numeric_with_unit", "0.5m", "0.5米").provenance.normalization == ("单位同义换算",)
    assert _verify("numeric_with_unit", "2千米", "2000米") is not None


def test_numeric_no_default_tolerance():
    """无默认容差:25.9≠25.8;7/36≠0.19(分数值不作小数近似匹配)。"""
    assert _verify("numeric_with_unit", "25.8度", "25.9度") is None
    assert _verify("numeric_with_unit", "7/36", "0.19") is None


def test_numeric_unit_omission_requires_schema():
    """单位省略仅 schema 显式 optional(审查修正③):无授权裸「25.8」不判;
    有授权命中并记「单位省略(schema授权)」。"""
    assert _verify("numeric_with_unit", "25.8度", "25.8") is None
    evidence = _verify("numeric_with_unit", "25.8度", "25.8", unit_optional=True)
    assert evidence is not None
    assert evidence.provenance.normalization == ("单位省略(schema授权)",)


def test_numeric_cross_family_and_counter_units_rejected():
    """维度安全:跨族(米 vs 秒)不换算;计数单位只认 token 相等(3只≠3本);
    省略不换算(「2千米」的省略形态是 2 不是 2000)。"""
    assert _verify("numeric_with_unit", "0.5米", "0.5秒") is None
    assert _verify("numeric_with_unit", "3只", "3本") is None
    assert _verify("numeric_with_unit", "2千米", "2000", unit_optional=True) is None


def test_numeric_picks_matching_token_among_many():
    """多 token 消息里只有**声明 token**可命中(改据 v3.1 §三:原案
    「先算出8,再算出26只」的「算出」不在声明式模板白名单,全文扫数已收窄;
    案值取审查 P1-2 猜测语境例)。正负镜像:「我先猜8。后来算出是26只」
    ——truth=8 时「猜8」不算提交(None),truth=26只 时声明 token 命中,
    span 是它(审计凭证)。"""
    assert _verify("numeric_with_unit", "8", "我先猜8。后来算出是26只") is None
    evidence = _verify("numeric_with_unit", "26只", "我先猜8。后来算出是26只")
    assert evidence is not None
    assert evidence.provenance.matched_span == "26只"


# ---------- choice_letter:字母精确匹配 ----------


def test_choice_letter_exact_match():
    """字母精确匹配:断言语境「选B」「答案是B」命中,span 是字母本身。"""
    assert _verify("choice_letter", "B", "选B", letter_choices=("A", "B", "C", "D")) is not None
    evidence = _verify("choice_letter", "B", "答案是B", letter_choices=("A", "B", "C", "D"))
    assert evidence.provenance.matched_span == "B"


def test_choice_letter_case_sensitive_and_word_boundary():
    """小写 b 不是精确匹配;单词内字母(Apple 的 A)不是独立选项 token。"""
    letters = {"letter_choices": ("A", "B", "C", "D")}
    assert _verify("choice_letter", "B", "b", **letters) is None
    assert _verify("choice_letter", "A", "Apple", **letters) is None


def test_choice_letter_wrong_letter_not_matched():
    """合法字母表里的其他字母(C)不构成对答案 B 的命中。"""
    assert _verify("choice_letter", "B", "C", letter_choices=("A", "B", "C", "D")) is None


# ---------- true_false:对/错/√/× 映射 ----------


def test_true_false_true_tokens():
    """真值 token:对/√ 命中「对」。"""
    assert _verify("true_false", "对", "对") is not None
    assert _verify("true_false", "对", "√") is not None


def test_true_false_false_tokens():
    """假值 token:×/不对 命中「错」(× 与乘号同形,本窄面内无算式,安全)。"""
    assert _verify("true_false", "错", "×") is not None
    assert _verify("true_false", "错", "不对") is not None


def test_true_false_negation_and_polarity():
    """否定形先判:「不对」不含真值「对」;「没错」是真值不是假值;极性
    相反(题面对、学生答错)不命中。"""
    assert _verify("true_false", "对", "不对") is None
    assert _verify("true_false", "错", "没错") is None
    assert _verify("true_false", "对", "错") is None


# ---------- equation_form:符号归一后字符串等价 ----------


def test_equation_symbol_normalization():
    """符号归一:全角－＝、多余空白归一到同一规范形,命中记「符号归一」。"""
    evidence = _verify("equation_form", "x-21=35", "x－21＝35")
    assert evidence is not None
    assert evidence.provenance.matched_span == "x－21＝35"
    assert evidence.provenance.normalization == ("符号归一",)
    assert _verify("equation_form", "x-21=35", "x - 21 = 35") is not None


def test_equation_multiplication_never_merges_with_variable_x():
    """审查修正①(灾难性等价红线):×/·→独立乘法 token `*`,绝不与变量 x
    合并——「3×4=12」与「3x4=12」**不相等**(x 是变量);· 形态照常归一。"""
    assert _verify("equation_form", "3×4=12", "3x4=12") is None
    assert _verify("equation_form", "3×4=12", "3·4=12") is not None
    assert _verify("equation_form", "3×4=12", "3*4=12") is not None


def test_equation_embedded_in_sentence():
    """句子内嵌算式:汉字断开候选段,span 是算式本身(「我算出来是x-21=35」)。"""
    evidence = _verify("equation_form", "x-21=35", "我算出来是x-21=35")
    assert evidence is not None
    assert evidence.provenance.matched_span == "x-21=35"


def test_equation_retraction_not_evidence():
    """自我否定:「x-21=35不对,应该是…」已撤回,不构成证据(fail-closed)。"""
    assert _verify("equation_form", "x-21=35", "x-21=35不对,应该是x+21=35") is None


# ---------- ratio_or_expression:同族符号归一 ----------


def test_ratio_fullwidth_symbols_normalized():
    """比例符号归一:全角：＝归一到 12:4=6:2 同一规范形。"""
    evidence = _verify("ratio_or_expression", "12:4=6:2", "12：4＝6：2")
    assert evidence is not None
    assert evidence.provenance.matched_span == "12：4＝6：2"
    assert _verify("ratio_or_expression", "3/4", "3/4") is not None


def test_ratio_no_semantic_conversion():
    """比与分数形态不做语义互通(fail-closed):「3:4」不判「3/4」——
    无语义归一是显式设计选择,互通留给第二版。"""
    assert _verify("ratio_or_expression", "3/4", "3:4") is None


# ---------- short_text_exact:whole-answer exact / 显式 alias ----------


def test_short_text_whole_answer_exact():
    """整答精确:裸答案与「答案是易变形。」都命中(句尾标点属无语义归一)。"""
    assert _verify("short_text_exact", "易变形", "易变形") is not None
    evidence = _verify("short_text_exact", "易变形", "答案是易变形。")
    assert evidence.provenance.matched_span == "易变形"


def test_short_text_negation_not_hit():
    """审查修正④(红线):「不是易变形」不得因包含「易变形」命中——
    否定窗口(命中前 2 字含 不/没/非/未)整条拒判。"""
    assert _verify("short_text_exact", "易变形", "不是易变形") is None
    assert _verify("short_text_exact", "易变形", "我觉得不是易变形") is None


def test_short_text_no_bare_substring():
    """不做裸 substring:命中必须是消息末段的完整答案断言——居中出现
    (「金属和水都会易变形哦」不收尾)与主语前缀(「金属易变形」非断言
    系词边界)都不判;变体走题库显式 alias。"""
    assert _verify("short_text_exact", "易变形", "金属和水都会易变形哦") is None
    assert _verify("short_text_exact", "易变形", "金属易变形") is None


def test_short_text_explicit_alias():
    """题库显式 alias:「容易变形」经 alias 命中,span 是学生原文变体;
    且不得经 truth 后缀包含走捷径(左边界须句首或断言系词 是/为)。"""
    evidence = _verify("short_text_exact", "易变形", "容易变形", aliases=("容易变形",))
    assert evidence is not None
    assert evidence.provenance.matched_span == "容易变形"
    assert _verify("short_text_exact", "易变形", "容易变形") is None


def test_short_text_inner_punctuation_and_question_form():
    """命中段内空白/标点剥离记入归一;问句形态(「易变形吗」)不构成证据。"""
    evidence = _verify("short_text_exact", "易变形", "易 变形")
    assert evidence is not None
    assert evidence.provenance.normalization == ("剥空白标点",)
    assert _verify("short_text_exact", "易变形", "易变形吗") is None


# ---------- precision-first claim matching(v3.1 §三,审查 P1-2)----------


def test_uncertainty_markers_reject_all_six_faces():
    """不确定表达(消息级 fail-closed;审查实测六窄面全穿,案值逐字):
    「可能 是 6」「可能是6。」「还不确定,我觉得是6」「可能是B」
    「可能是x-21=35」「可能是3/4」「可能是易变形」「答案可能是易变形」
    「可能是对」「对,不过我不确定」——正确值出现但学生未落定,整条不判
    (宁 needs_review 不发 evidence)。"""
    assert _verify("numeric_with_unit", "6", "可能 是 6") is None
    assert _verify("numeric_with_unit", "6", "可能是6。") is None
    assert _verify("numeric_with_unit", "6", "还不确定,我觉得是6") is None
    letters = {"letter_choices": ("A", "B", "C", "D")}
    assert _verify("choice_letter", "B", "可能是B", **letters) is None
    assert _verify("equation_form", "x-21=35", "可能是x-21=35") is None
    assert _verify("ratio_or_expression", "3/4", "可能是3/4") is None
    assert _verify("short_text_exact", "易变形", "可能是易变形") is None
    assert _verify("short_text_exact", "易变形", "答案可能是易变形") is None
    assert _verify("true_false", "对", "可能是对") is None
    assert _verify("true_false", "对", "对,不过我不确定") is None


def test_pre_hit_negation_rejects_all_faces():
    """命中前否定窗(short_text 口径推广到全部六窄面;审查实测 4/6 面穿,
    案值逐字):「不是B」「我不选B」「不选B,选A」「不是x-21=35」——span
    恰是被否定的答案本身时不得发 evidence(「不是易变形」「不是6。我觉得
    是5」分别在 short_text 节与标点变体案)。"""
    letters = {"letter_choices": ("A", "B", "C", "D")}
    assert _verify("choice_letter", "B", "不是B", **letters) is None
    assert _verify("choice_letter", "B", "我不选B", **letters) is None
    assert _verify("choice_letter", "B", "不选B,选A", **letters) is None
    assert _verify("equation_form", "x-21=35", "不是x-21=35") is None
    assert _verify("true_false", "对", "不是对") is None


def test_numeric_negation_punctuation_variants_all_rejected():
    """v3.1 §三 canonical 例句「不是6,我觉得是5」三标点变体各一条:
    逗号/句号/顿号都 None——原逗号变体的 None 是千分位分组吃掉「6,」致
    token 弃值的意外(审查:句号/顿号即穿),现由否定窗+claim 白名单真守卫。"""
    assert _verify("numeric_with_unit", "6", "不是6,我觉得是5") is None
    assert _verify("numeric_with_unit", "6", "不是6。我觉得是5") is None
    assert _verify("numeric_with_unit", "6", "不是6、我觉得是5") is None


def test_alternative_candidates_rejected():
    """多候选(候选间 或/还是 形态;审查实测,案值逐字):「B或D」「选B
    还是D」「6 还是 7」「x-21=35 还是 x+21=35」——未在候选间落终答,
    整条不判。"""
    letters = {"letter_choices": ("A", "B", "C", "D")}
    assert _verify("choice_letter", "B", "B或D", **letters) is None
    assert _verify("choice_letter", "B", "选B还是D", **letters) is None
    assert _verify("numeric_with_unit", "7", "6 还是 7") is None
    assert _verify("equation_form", "x-21=35", "x-21=35 还是 x+21=35") is None


def test_numeric_accidental_safety_now_real_guards():
    """两处「意外安全」改真守卫(审查 P1-2 实测):「6 还不确定」原是
    「还不确定」被当 4 字单位吸收,现由不确定 marker 挡;「我算了6,都不对」
    是审查点名的同类逗号意外,一并钉死(句号变体由 claim 白名单挡)。"""
    assert _verify("numeric_with_unit", "6", "6 还不确定") is None
    assert _verify("numeric_with_unit", "6", "我算了6,都不对") is None


def test_equation_hit_span_strips_trailing_space():
    """equation 命中 span 剥尾随空白(审查 P3):matched_span 是审计凭证,
    「x-21=35 谢谢老师」命中 span 是 'x-21=35' 而非 'x-21=35 '。"""
    evidence = _verify("equation_form", "x-21=35", "x-21=35 谢谢老师")
    assert evidence is not None
    assert evidence.provenance.matched_span == "x-21=35"


def test_choice_letter_requires_nonempty_letter_choices():
    """choice_letter 组装方契约(审查 P3,B 段):letter_choices 必须非空
    ——空=题面选项字母表缺失,调度 None fail-closed,不静默跳过合法集校验。"""
    assert _verify("choice_letter", "B", "选B") is None


def test_question_marker_shi_duoshao_covered_by_duoshao():
    """「是多少」marker 删除(审查 P3,ponytail delete)后的等价钉死:
    「25.8度是多少」仍由「多少」子串拦截——删后无测试红,冗余属实。"""
    assert _verify("numeric_with_unit", "25.8度", "25.8度是多少") is None


# ---------- 复合题红线(设计 §三审查修正②)----------


def test_composite_answer_type_never_constructs():
    """answer_type 不在六窄面(复合/开放)→ 调度即 None:学生给出**完整**
    多空答案也不判定(整体 needs_review,不偷「半完成态」)。"""
    assert _verify("composite", "鸡3只兔5只", "鸡3只兔5只") is None
    assert _verify("open_ended", "言之成理即可", "我觉得平行线永不相交") is None


def test_composite_numeric_multi_slot_never_constructs():
    """多槽复合误标 numeric:ground_truth 含 ≥2 数字 token(鸡3只兔5只)
    → 拒判——局部槽命中(「鸡3只」)与整答复述都不构造 evidence。"""
    assert _verify("numeric_with_unit", "鸡3只兔5只", "鸡3只") is None
    assert _verify("numeric_with_unit", "鸡3只兔5只", "鸡3只兔5只") is None


def test_composite_short_text_multi_slot_never_constructs():
    """多槽复合误标 short_text:同样拒判(设计 §三:多槽复合不属本窄面)。"""
    assert _verify("short_text_exact", "鸡3只兔5只", "鸡3只兔5只") is None


# ---------- fail-closed 与不可构造面 ----------


def test_question_guess_is_not_evidence():
    """问句猜答不构成证据(与 numeric._declarative 同口径):「是不是25.8度?」
    「25.8度对吗」都 None——混合消息整条按问句处理(fail-closed)。"""
    assert _verify("numeric_with_unit", "25.8度", "是不是25.8度?") is None
    assert _verify("numeric_with_unit", "25.8度", "25.8度,对吗") is None


def test_empty_and_none_inputs_are_not_evidence():
    """空消息/None/空 ground_truth 一律 None(fail-closed)。"""
    assert _verify("choice_letter", "B", "") is None
    assert _verify("choice_letter", "B", "   ") is None
    assert _verify("choice_letter", "", "B") is None


def test_evidence_construction_guards():
    """不可构造面(设计 §二)构造期即炸:source 恒 student(LLM/summary/guard
    无构造权)、verdict 恒 matched、answer_type 限六窄面。"""
    provenance = EvidenceProvenance("B", "B", ())
    with pytest.raises(ValueError):
        CompletionEvidence("summary", 1, "choice_letter", "matched", "choice_letter", provenance)
    with pytest.raises(ValueError):
        CompletionEvidence("student", 1, "choice_letter", "needs_review", "choice_letter", provenance)
    with pytest.raises(ValueError):
        CompletionEvidence("student", 1, "composite", "matched", "composite", provenance)


def test_answer_types_are_the_six_narrow_faces():
    """六窄面名单钉死(设计 §三):新窄面=设计件变更,不是实现自由度。"""
    assert ANSWER_TYPES == ("numeric_with_unit", "choice_letter", "true_false",
                            "equation_form", "ratio_or_expression", "short_text_exact")


def test_turn_scoped_turn_id_carried_verbatim():
    """turn-scoped/ephemeral(§二):证据携带本轮 turn_id,跨轮不复用——
    同一消息下一轮重新验证产生**新**证据(新 turn_id),旧证据不迁移。"""
    first = _verify("numeric_with_unit", "25.8度", "25.8度")
    second = verify_completion(
        AnswerSpec(answer_type="numeric_with_unit", ground_truth="25.8度"),
        "25.8度", TURN + 1)
    assert first.turn_id == TURN
    assert second is not None and second.turn_id == TURN + 1
