# S2 battery 报告(#459 件二,annotation-only)

- run 目录:`/tmp/wt-s2-engine/edu_agent/evals/artifacts/s2-judge-battery-v0.1/smoke-122b-20260928T073212Z-ed2d`
- 实现身份:git `92bf9bb` / rubric 冻结 `d415be391f4e…` / prompt 资产 `57c523ac28be…` / battery `a0eb9f72a6c9…` / models `904b4e6cbb4c…`
- judge_primary:id `qwen122b`(仅追溯) / model `/Users/linsuchang/Desktop/work/models/Qwen3.5-122B-A10B-4bit`(比较基准)

## 运行有效性(P0-2/P0-4)
- judge_model 集合:["/Users/linsuchang/Desktop/work/models/Qwen3.5-122B-A10B-4bit"]
- 判定:单一且=预注册 primary ✓

## G0 运行完整性
- ok 3/3

## GA 案级一致(门 ≥20/24;verdict 词级,supporting_turns 仅诊断)
- 0/3

## GB unsure 纪律(判定 = verdict=unsure ∧ 边界证据命中;①/④/② marker 词级;U-0 marker 或 rationale 二选一)
- C23-T3 s2b:期望边界 U-0 → ✗ 未命中(错误规则猜出的 unsure 不算可靠执行)
- 判定:0/1 ✗(私闭合/边界未命中单列零容忍)(unsure 期望案数随 battery 期望动态,v0.3 起 = 3)

## supporting_turns 诊断(D2:不入 GA,精确匹配计数)
- 1/4
- ✗ C24-T1 s2a:期望 ['t1'] / 实得 []
- ✗ C24-T4 s2a:期望 ['t1'] / 实得 []
- ✗ C23-T3 s2a:期望 ['t2'] / 实得 []

## 轴级 miss 清单(3 个轴级 miss,涉及 3 个失败 case;GC 归因用:①A 实现失真/①B 翻译失真/② 判据—终验张力/③ 模型执行噪声)
- [verdict] C24-T1 s2a:期望 yes / 实得 no|rationale:Step 1: Student t1 '我不记得乘法分配律是怎么说的了' constitutes E2 (Specific Knowledge Gap Statement) as it names a specific fact (multiplication distributive law) needed. Ste
- [verdict] C24-T4 s2a:期望 yes / 实得 no|rationale:Step 1: Student t1 '我卡住了，能先告诉我先算括号还是先除吗？' is a specific request (E1) naming the object (order of operations: brackets vs division) and action (tell me). Step 2:
- [verdict] C23-T3 s2b:期望 unsure / 实得 no|rationale:S2b 判定为 no。t1 Tutor 回应'那你是怎么想到要除以2的？'为 t1 型提前暴露（B-4.5），属 provenance 族，本 Judge 不判其族归属，且该轮未直接给出关键内容（仅提问）。t2 Tutor 回应'那你觉得，两个完全相同的三角形能不能拼成...？'为定向提问（R2 型），未直接给出'拼成

## 口径注记
- 轴级分母 = 36 显式轴期望(23 S2a+13 S2b):终裁机械真值——C15-T4 的 S2a 未单列,未单列轴不记分不推断(不为凑 37 补裁)。件一 v0.1 表头的 37 声明系算术口径偏差,已由 rubric v0.2 改字(PR #463);GA 案级 ≥20/24 分母不受影响(GB 案数随期望动态,v0.3 起 = 3)。
- 核实重跑 = 新开 run(resume 只补环境失败案)。
