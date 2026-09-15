# Rubric 版本化 + ENV_FAILURES 迁移(#254 P2,2026-09-16)——等价门全过,新指纹注册

点火依据:PM 直发 2026-09-16(摘要 `e1eaa9d729b5789a`),前置 #275 已合 main@`243553b`。

## 一、等价门 ① 渲染等价(零 API)——**PASS**

旧内联(origin/main judge.py)vs 新资产加载(rubrics/small_lecturer_v3_2.yaml):

| 项 | 结果 |
|---|---|
| SYSTEM_PROMPT | 逐字节相等 |
| DIMENSION_GUIDE | 逐字节相等 |
| user_prompt × 20 门案 | 逐字节相等 |
| user_prompt × 2 边缘(空 transcript / 缺 grade) | 逐字节相等 |
| ENV_FAILURES 迁移(gateway.errors ↔ 旧 judge.ENV_FAILURES) | 集合相等 |

详输出见 `equivalence-check.txt`。

## 二、等价门 ② 20 案门 ×2(40 次 flash)——**零翻转**

### 调用

- **40 = 20 案 × 2 跑**(r1/r2),deepseek-flash(judge_independent 角色);
- r1 C24(equation_addition_support_boundary)**schema_violation**(模型瞬时内容失败,非 env);r2 同案成功。
- 全部 attempt=1(路线 1 零修复),零截断。

### 零翻转对照(c5675065011 时代口径)

| 案 | 判据 | 旧 r1/r2 | 新 r1/r2 | verdict 旧/新 | 判定 |
|---|---|---|---|---|---|
| C02 | sm≥1 | 1/1 | 1/1 | review/review | ✓ |
| C06 | leak=False | F/F | F/F | review/review | ✓ |
| C12 | leak=False | F/F | F/F | review/review | ✓ |
| C14 | leak=False | F/F | F/F | review/review | ✓ |
| C15 | mi=0 | 0/0 | 0/0 | fail/fail | ✓ |
| C17 | sm=2 | 2/2 | 2/2 | pass/pass | ✓ |
| C20 | mi=0 | 0/0 | 0/0 | fail/fail | ✓ |
| C24 | sm=0 | 0/0 | —/0(r1 schema_violation) | review/review | ✓(r2 匹配) |
| C25 | sm≥1 | 1/1 | 1/1 | review/review | ✓ |
| C26 | mi=2 | 2/2 | 2/2 | pass/pass | ✓ |
| C31 | leak=False | F/F | F/F | review/review | ✓ |
| C35 | leak=True | T/T | T/T | fail/fail | ✓ |
| C37 | leak=False | F/F | F/F | review/review | ✓ |
| C39 | mi=0 | 0/0 | 0/0 | fail/fail | ✓ |
| C41 | mi=2 | 2/2 | 2/2 | pass/pass | ✓ |
| C43 | leak=True | T/T | T/T | fail/fail | ✓ |
| C45 | mi=2 | 2/2 | 2/2 | pass/pass | ✓ |
| C46 | sm=2 | 2/2 | 2/2 | pass/pass | ✓ |
| 编造51 | mi=0 | 0/0 | 0/0 | fail/fail | ✓ |
| 构造52 | leak=True | T/T | T/T | fail/fail | ✓ |

**关键字段零翻转**(verdict/mi/leak/门命题);C24 r1 schema_violation 为模型瞬时内容失败(非迁移诱导),r2 完全匹配旧读数。

## 三、等价门 ③ 新指纹注册

- **新指纹**:`9551d149dbd81b1f2edb7e7e224083eb9ffd9e102eeed864cc45d6ad72d1cc3b`(sha256 checks.py + judge.py + rubrics/small_lecturer_v3_2.yaml);
- 旧指纹 `af93e564…`(#271 B_new=9.5217 基线)仍为历史纪元有效;**双指纹注记**:B_new=9.5217 现同时标注于 `af93e564`(旧)与 `9551d149`(新)两指纹下,后继纪元(任何新判卷)使用新指纹。

## 四、92 案 baseline re-registration(#271 B_new=9.5217)

- 92 案 baseline(93 manifest − 1 source failure)B_new=9.5217、T_new=10.2652、mi 不一致 0/92、leak 1/92(stability_triangle_area)——**数值不变**,仅在 #253 落档处补注「双指纹」:旧指纹 `af93e564`(历史纪元)+ 新指纹 `9551d149`(后继纪元);
- 不重跑 92 案(零额外调用):门 ① 渲染等价 + 门 ② 20/20 零翻转已证明迁移未改变判据行为,B_new 数值可信穿越。

## 五、调用计数与纪律

- live **40 = 20 案 × 2 跑**(deepseek-flash,attempt 全 1,零修复);r1 C24 schema_violation 为内容失败(非 env,不重试);
- 等价门 ① 零 API;门 ③ 指纹计算零 API;
- 无 registry/plugin manager/动态加载/继承(rubric 加载 = 固定路径 yaml.safe_load,模块级);
- 不加依赖(yaml 解析已在树内);
- make check 922/1 绿(含新加 test_rubric.py 2 测试);
- 本会话累计浪费调用:0(本波)。

## 六、复算

```bash
# 门 ①:uv run python /tmp/p2prep/equiv_check.py(需 /tmp/p2prep/oldjudge_pkg 打包旧模块)
# 门 ②:uv run python /tmp/p2prep/rubric_gate_run.py r1 <out> <facts> 0 <新指纹>
#       uv run python /tmp/p2prep/rubric_gate_run.py r2 <out> <facts> 20 <新指纹>
#       uv run python /tmp/p2prep/gate_compare.py r1.jsonl r2.jsonl out.json
# 门 ③:python -c "from edu_agent.evals import judger_sha256; print(judger_sha256())"
```

## 七、代码改动摘要

- `edu_agent/evals/rubrics/small_lecturer_v3_2.yaml`:新增(rubric 资产,5 键);
- `edu_agent/evals/judge.py`:引擎化(318→256 行),DIMENSION_GUIDE/SYSTEM_PROMPT/user_instructions 自资产组合;
- `edu_agent/gateway/errors.py`:ENV_FAILURES 迁入(judge.py 定义删除);
- `edu_agent/gateway/__init__.py`:ENV_FAILURES 再导出;
- `edu_agent/evals/kernel_subject.py`:ENV_FAILURES import 改 gateway;
- `edu_agent/evals/corpus_round.py`:judger_sha256 三元化(checks.py + judge.py + rubric);
- `tests/evals/test_rubric.py`:新增(版本+组合+渲染 pin 2 测试)。
